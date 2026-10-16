"""Mechanical state merging and invalidation, never natural-language interpretation."""
from datetime import timedelta,datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select
from . import models as m,schemas as s
from .tools import BusinessError

def merge_requirements(current,patches,date_operations=()):
    data=current.model_dump();defaults=s.BookingRequirements().model_dump()
    seen=set()
    for patch in patches:
        if patch.field not in data:raise BusinessError(f"Unknown requirement: {patch.field}")
        if patch.operation=="UNSET":continue
        if patch.field in seen:raise BusinessError("A requirement was changed twice. Please clarify the intended value.")
        seen.add(patch.field)
        data[patch.field]=defaults[patch.field] if patch.operation=="CLEAR" else patch.value
    try:
        merged=s.BookingRequirements.model_validate(data)
        for op in date_operations:
            if op.field in seen:raise BusinessError("A date has conflicting updates. Please clarify the intended dates.")
            seen.add(op.field)
            base={"from_today":datetime.now(ZoneInfo("Asia/Kolkata")).date(),"from_check_in":merged.check_in,"shift_days":getattr(merged,op.field)}[op.operation]
            if base is None:raise BusinessError("Please provide the date you want to adjust.")
            setattr(merged,op.field,base+timedelta(days=op.days))
        return s.BookingRequirements.model_validate(merged.model_dump())
    except ValueError as exc:
        if isinstance(exc,BusinessError):raise
        raise BusinessError("Some requirements were invalid. Please check dates and guest counts.") from exc

def invalidate_quotes(db,state):
    for quote in db.scalars(select(m.Quote).where(m.Quote.session_id==state.session_id,m.Quote.invalidated.is_(False))):
        quote.invalidated=True
        for offer in db.scalars(select(m.NegotiationOffer).where(m.NegotiationOffer.quote_id==quote.id,m.NegotiationOffer.status.in_(["accepted","countered","pending_approval"]))):offer.status="expired"
    state.latest_recommendations=[]
    state.latest_quote_id=None
    state.quote=None
    state.negotiation_state={}
    state.pending_confirmation=False
    state.selected_room_type_id=None
    state.selected_property_id=None
