"""Database-backed business tools. The LLM cannot access ORM sessions or write SQL."""
import hashlib
import json
import time
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select, func
from pydantic import BaseModel
from . import models as m
from . import schemas as s
from .db import now
from .config import settings
from .tool_results import validate_result

class BusinessError(ValueError): pass
class ToolUnavailable(RuntimeError): pass

def money(value): return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
def fingerprint(req):
    return hashlib.sha256(req.model_dump_json().encode()).hexdigest()
def public_row(row, fields): return {k: getattr(row, k) for k in fields}
def nights(req):
    if not req.check_in or not req.check_out or not req.adults:
        raise BusinessError("Arrival, departure, and adult count are required.")
    count = (req.check_out - req.check_in).days
    if req.check_in < now().date() or not 1 <= count <= 30:
        raise BusinessError("Choose future dates and a stay of 1–30 nights.")
    if req.child_ages and (len(req.child_ages) != req.children or any(a < 0 or a > 17 for a in req.child_ages)):
        raise BusinessError("Provide one age from 0–17 for each child, or omit child ages.")
    return [req.check_in + timedelta(days=i) for i in range(count)]

class Tools:
    def __init__(self, db, session_id, correlation_id):
        self.db, self.session_id, self.correlation_id = db, session_id, correlation_id
        self.results = []
        self.calls = 0

    def run(self, name: str, args: BaseModel):
        self.calls += 1
        if self.calls > 40: raise BusinessError("Tool execution limit reached. Please try a narrower search.")
        started, tick = now(), time.monotonic()
        # Arguments deliberately omit free-text special requests and personal data.
        safe = args.model_dump(mode="json", exclude={"requirements"})
        for k in ("idempotency_key", "context", "reason_code"): safe.pop(k, None)
        if hasattr(args, "requirements"):
            req = args.requirements
            safe["requirements"] = req.model_dump(mode="json", include={"check_in", "check_out", "adults", "children", "budget_amount", "budget_basis", "add_on_ids"})
            known={"wifi","private_pool","shared_pool","beach_access","parking","kitchenette","family_suite","balcony","villa","restaurant"}
            safe["requirements"]["required_amenities"]=[a for a in req.required_amenities if a in known]
        if "topic" in safe and safe["topic"] not in {"cancellation","check_in","pets","children","breakfast","pool_heating"}: safe["topic"]="unknown"
        ok = False
        summary = {}
        try:
            for attempt in range(2):
                try:
                    result = getattr(self, name)(args)
                    break
                except TimeoutError as exc:
                    if attempt or name not in {"search_properties", "check_availability", "get_room_details", "get_policy"}:
                        raise ToolUnavailable("A hotel tool timed out. Your request is marked for operational review; please retry.") from exc
            # Validate JSON serializability before exposing any result.
            result = json.loads(json.dumps(result, default=str))
            validate_result(name, result)
            summary = {"count": len(result.get("recommendations", []))} if "recommendations" in result else {k: result[k] for k in ("status", "available", "known", "total_minor", "id") if k in result}
            ok = True
            self.results.append({"tool_name": name, "data": result})
            return result
        except BusinessError:
            summary = {"error": "business_rule_rejected"}
            raise
        except Exception:
            summary = {"error": "tool_unavailable"}
            raise
        finally:
            self.db.add(m.ToolLog(session_id=self.session_id, correlation_id=self.correlation_id, tool_name=name, arguments=safe, started_at=started, duration_ms=int((time.monotonic()-tick)*1000), success=ok, summary=summary))

    def room(self, rid):
        room = self.db.get(m.RoomType, rid)
        if not room: raise BusinessError("Room was not found.")
        return room

    def search_properties(self, arg: s.SearchInput):
        req = arg.requirements
        nights(req)
        if req.destination and "goa" not in req.destination.lower() and not any(x in req.destination.lower() for x in ("candolim", "anjuna", "palolem")):
            return {"recommendations": []}
        options = []
        for room in self.db.scalars(select(m.RoomType).order_by(m.RoomType.nightly_minor, m.RoomType.id)):
            prop = self.db.get(m.Property, room.property_id)
            if req.destination and any(x in req.destination.lower() for x in ("candolim", "anjuna", "palolem")) and req.destination.lower().split(",")[0] not in prop.location.lower(): continue
            if room.capacity < req.adults + req.children: continue
            if any((addon := self.db.get(m.AddOn, aid)) is None or addon.property_id != room.property_id for aid in req.add_on_ids): continue
            if not set(req.required_amenities).issubset(room.amenities): continue
            if req.room_preferences and not all(p.lower() in (room.name+" "+" ".join(room.amenities)).lower() for p in req.room_preferences): continue
            if not self.run("check_availability", s.AvailabilityInput(room_type_id=room.id, requirements=req))["available"]: continue
            q = self.run("calculate_price", s.PriceInput(room_type_id=room.id, requirements=req, session_id=self.session_id))
            compare = q["total_minor"] if req.budget_basis == "stay" else (q["total_minor"] + q["nights"]-1)//q["nights"]
            if req.budget_amount and compare > req.budget_amount: continue
            options.append({"room_type_id": room.id, "property_id": prop.id, "property_name": prop.name, "location": prop.location, "room_name": room.name, "description": room.description, "capacity": room.capacity, "amenities": room.amenities, "quote": q, "preference_score": len(set(req.preferred_amenities) & set(room.amenities))})
        options.sort(key=lambda o: (-o["preference_score"], o["quote"]["total_minor"]))
        return {"recommendations": options[:3]}

    def check_availability(self, arg: s.AvailabilityInput):
        req, room = arg.requirements, self.room(arg.room_type_id)
        days = nights(req)
        inv = self.db.scalar(select(m.RoomInventory).where(m.RoomInventory.room_type_id == room.id))
        if not inv: raise BusinessError("Inventory is not configured.")
        remaining = []
        for day in days:
            restriction = self.db.scalar(select(m.RoomAvailability).where(m.RoomAvailability.room_type_id==room.id, m.RoomAvailability.night==day))
            reserved = self.db.scalar(select(func.coalesce(func.sum(m.Reservation.units),0)).where(m.Reservation.room_type_id==room.id, m.Reservation.check_in<=day, m.Reservation.check_out>day))
            held = self.db.scalar(select(func.count()).select_from(m.BookingHold).where(m.BookingHold.room_type_id==room.id, m.BookingHold.check_in<=day, m.BookingHold.check_out>day, m.BookingHold.expires_at>now()))
            remaining.append(0 if restriction and restriction.closed else max(0, inv.units-reserved-held-(restriction.blocked_units if restriction else 0)))
        return {"available": min(remaining)>0 and req.adults+req.children<=room.capacity, "units_remaining": min(remaining), "nights": len(days)}

    def get_room_details(self, arg: s.RoomInput):
        room = self.room(arg.room_type_id)
        return public_row(room, ["id", "property_id", "name", "description", "capacity", "nightly_minor", "amenities"])

    def calculate_price(self, arg: s.PriceInput):
        req, room = arg.requirements, self.room(arg.room_type_id)
        days = nights(req)
        if req.adults+req.children>room.capacity: raise BusinessError("Guest count exceeds capacity.")
        policy = self.db.scalar(select(m.PricingPolicy).where(m.PricingPolicy.property_id==room.property_id))
        base = room.nightly_minor*len(days)
        addons = []
        for aid in sorted(set(req.add_on_ids)):
            addon = self.db.get(m.AddOn, aid)
            if not addon or addon.property_id!=room.property_id: raise BusinessError("An add-on is not available at this property.")
            amount = addon.price_minor * (len(days)*(req.adults+req.children) if addon.basis=="guest-night" else 1)
            addons.append({"id": addon.id, "name": addon.name, "amount_minor": amount})
        subtotal = base + sum(a["amount_minor"] for a in addons)
        tax = money(Decimal(subtotal)*policy.tax_bps/10000)
        breakdown = {"currency": "INR", "nights": len(days), "nightly_minor": room.nightly_minor, "base_minor": base, "add_ons": addons, "tax_minor": tax, "total_minor": subtotal+tax, "fictional": True}
        quote = m.Quote(session_id=arg.session_id, room_type_id=room.id, fingerprint=fingerprint(req), breakdown=breakdown, total_minor=subtotal+tax, policy_version=policy.version, expires_at=now()+timedelta(minutes=settings.quote_minutes))
        self.db.add(quote); self.db.flush()
        return {**breakdown, "id": quote.id, "expires_at": quote.expires_at.isoformat()}

    def get_policy(self, arg: s.PolicyInput):
        prop = self.db.get(m.Property, arg.property_id)
        if not prop: raise BusinessError("Select a property first.")
        key = arg.topic.lower().replace(" ", "_")
        value = prop.policies.get(key)
        return {"known": value is not None, "topic": key, "value": value}

    def fresh_quote(self, qid):
        q = self.db.get(m.Quote, qid)
        if not q or q.session_id != self.session_id: raise BusinessError("Select a room to get a quote first.")
        if q.invalidated or q.expires_at<=now(): raise BusinessError("This quote has expired or changed. Please refresh your options.")
        room = self.room(q.room_type_id)
        policy = self.db.scalar(select(m.PricingPolicy).where(m.PricingPolicy.property_id==room.property_id))
        if q.policy_version!=policy.version: raise BusinessError("Pricing rules changed. Please refresh your quote.")
        return q, policy

    def evaluate_discount(self, arg: s.DiscountInput):
        q, p = self.fresh_quote(arg.quote_id)
        proposed = arg.proposed_amount
        if proposed is None: proposed = (q.total_minor*(10000-p.auto_bps)+9999)//10000
        elif arg.basis=="night": proposed *= q.breakdown["nights"]
        if proposed>q.total_minor: raise BusinessError("The proposed price is higher than the current total.")
        bps = money(Decimal(q.total_minor-proposed)*10000/q.total_minor)
        if (q.total_minor-proposed)*10000<=q.total_minor*p.auto_bps: status, approved = "accepted", proposed
        elif (q.total_minor-proposed)*10000<=q.total_minor*p.manager_bps: status, approved = "pending_approval", None
        else: status, approved = "countered", (q.total_minor*(10000-p.auto_bps)+9999)//10000
        return {"status": status, "proposed_amount": proposed, "approved_amount": approved, "discount_bps": bps, "policy_version": p.version, "expires_at": q.expires_at.isoformat()}

    def create_negotiation_offer(self, arg: s.OfferInput):
        old = self.db.scalar(select(m.NegotiationOffer).where(m.NegotiationOffer.session_id==arg.session_id, m.NegotiationOffer.idempotency_key==arg.idempotency_key))
        if old: return self.offer_result(old)
        result = self.run("evaluate_discount", s.DiscountInput(**arg.model_dump(include={"quote_id","proposed_amount","basis"})))
        q, _ = self.fresh_quote(arg.quote_id)
        # Supersede prior offers so a previous acceptance cannot silently price a new hold.
        for previous in self.db.scalars(select(m.NegotiationOffer).where(m.NegotiationOffer.quote_id==q.id, m.NegotiationOffer.status.in_(["accepted","countered","pending_approval"]))): previous.status="expired"
        offer = m.NegotiationOffer(session_id=arg.session_id, quote_id=q.id, proposed_amount=result["proposed_amount"], approved_amount=result["approved_amount"], discount_bps=result["discount_bps"], status=result["status"], policy_version=result["policy_version"], expires_at=q.expires_at, idempotency_key=arg.idempotency_key)
        self.db.add(offer)
        ns = self.db.scalar(select(m.NegotiationSession).where(m.NegotiationSession.quote_id==q.id))
        if not ns:
            ns=m.NegotiationSession(session_id=arg.session_id, quote_id=q.id, attempts=0); self.db.add(ns)
        ns.attempts += 1
        self.db.flush()
        return self.offer_result(offer) | {"attempts": ns.attempts}

    @staticmethod
    def offer_result(o):
        return {"id": o.id, "quote_id": o.quote_id, "status": "expired" if o.expires_at<=now() else o.status, "approved_amount": o.approved_amount, "proposed_amount": o.proposed_amount, "expires_at": o.expires_at.isoformat()}

    def create_booking_hold(self, arg: s.HoldInput):
        if not arg.confirmed: raise BusinessError("Explicit confirmation is required.")
        old = self.db.scalar(select(m.BookingHold).where(m.BookingHold.session_id==arg.session_id, m.BookingHold.idempotency_key==arg.idempotency_key))
        if old: return self.hold_result(old)
        q, _ = self.fresh_quote(arg.quote_id)
        if q.fingerprint!=fingerprint(arg.requirements): raise BusinessError("Requirements changed; get a fresh quote.")
        # Serialize ALL stays for a room type. PostgreSQL READ COMMITTED ensures the next
        # availability query sees holds committed by the previous owner of this lock.
        self.db.scalar(select(m.RoomInventory).where(m.RoomInventory.room_type_id==q.room_type_id).with_for_update())
        existing = self.db.scalar(select(m.BookingHold).where(m.BookingHold.session_id==arg.session_id, m.BookingHold.quote_id==q.id, m.BookingHold.expires_at>now()))
        if existing: return self.hold_result(existing)
        if not self.run("check_availability", s.AvailabilityInput(room_type_id=q.room_type_id, requirements=arg.requirements))["available"]:
            raise BusinessError("This room is no longer available. Please search for another option.")
        offer = self.db.scalar(select(m.NegotiationOffer).where(m.NegotiationOffer.quote_id==q.id).order_by(m.NegotiationOffer.created_at.desc(), m.NegotiationOffer.id.desc()))
        total = q.total_minor
        if offer and offer.expires_at>now():
            if offer.status=="pending_approval": raise BusinessError("Manager review is still pending. No discount has been approved.")
            if offer.status in ("accepted", "countered"):
                total = offer.approved_amount
                offer.status="accepted"
        hold = m.BookingHold(session_id=arg.session_id, room_type_id=q.room_type_id, quote_id=q.id, check_in=arg.requirements.check_in, check_out=arg.requirements.check_out, total_minor=total, expires_at=now()+timedelta(minutes=settings.hold_minutes), idempotency_key=arg.idempotency_key)
        self.db.add(hold); self.db.flush()
        return self.hold_result(hold)

    def cancel_booking_hold(self, arg: s.CancelHoldInput):
        if not arg.confirmed: raise BusinessError("Please explicitly request cancellation of your temporary hold.")
        hold=self.db.scalar(select(m.BookingHold).where(m.BookingHold.id==arg.hold_id,m.BookingHold.session_id==self.session_id).with_for_update())
        if not hold: raise BusinessError("No matching temporary hold exists in this session.")
        self.db.scalar(select(m.RoomInventory).where(m.RoomInventory.room_type_id==hold.room_type_id).with_for_update())
        if hold.cancelled_at is None:
            if hold.expires_at<=now(): raise BusinessError("This temporary hold has already expired; no cancellation is needed.")
            hold.cancelled_at=now()
            # Availability already excludes expired claims. Retain the cancellation
            # timestamp to distinguish a voluntary release from natural expiry.
            hold.expires_at=hold.cancelled_at
            quote=self.db.get(m.Quote,hold.quote_id)
            quote.invalidated=True
            for offer in self.db.scalars(select(m.NegotiationOffer).where(m.NegotiationOffer.quote_id==hold.quote_id)):
                offer.status="expired"
            self.db.flush()
        return self.hold_result(hold)

    @staticmethod
    def hold_result(h): return {"id": h.id, "quote_id": h.quote_id, "total_minor": h.total_minor, "expires_at": h.expires_at.isoformat(), "status": "cancelled" if h.cancelled_at else "temporary_hold" if h.expires_at>now() else "expired", "confirmed_reservation": False}

    def create_escalation_flag(self, arg: s.FlagInput):
        old = self.db.scalar(select(m.EscalationFlag).where(m.EscalationFlag.session_id==arg.session_id, m.EscalationFlag.idempotency_key==arg.idempotency_key))
        if old: return {"id": old.id, "status": old.status}
        flag = m.EscalationFlag(**arg.model_dump())
        self.db.add(flag); self.db.flush()
        return {"id": flag.id, "status": flag.status, "category": flag.category}

    def request_human_handoff(self, arg: s.HandoffInput):
        old = self.db.scalar(select(m.HandoffRequest).where(m.HandoffRequest.flag_id==arg.flag_id))
        if old: return {"id": old.id, "status": old.status}
        flag = self.db.get(m.EscalationFlag, arg.flag_id)
        if not flag or flag.session_id!=arg.session_id: raise BusinessError("Invalid review request.")
        handoff = m.HandoffRequest(flag_id=arg.flag_id, session_id=arg.session_id)
        self.db.add(handoff); self.db.flush()
        return {"id": handoff.id, "status": "pending"}

    def resolve_escalation_flag(self, arg: s.ResolveInput):
        flag = self.db.get(m.EscalationFlag, arg.flag_id)
        if not flag: raise BusinessError("Flag not found.")
        flag.status, flag.resolved_at = "resolved", now()
        for h in self.db.scalars(select(m.HandoffRequest).where(m.HandoffRequest.flag_id==flag.id)): h.status="resolved"
        return {"id": flag.id, "status": flag.status}
