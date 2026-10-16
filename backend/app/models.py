from datetime import date, datetime
from uuid import uuid4
from sqlalchemy import String, ForeignKey, JSON, DateTime, Date, Integer, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, now

def uid(): return str(uuid4())
class Identified:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)

class Property(Identified, Base):
    __tablename__ = "properties"
    name: Mapped[str]
    location: Mapped[str]
    description: Mapped[str]
    amenities: Mapped[list] = mapped_column(JSON)
    policies: Mapped[dict] = mapped_column(JSON)

class RoomType(Identified, Base):
    __tablename__ = "room_types"
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"), index=True)
    name: Mapped[str]
    description: Mapped[str]
    capacity: Mapped[int]
    nightly_minor: Mapped[int]
    amenities: Mapped[list] = mapped_column(JSON)

class RoomInventory(Identified, Base):
    __tablename__ = "room_inventory"
    room_type_id: Mapped[str] = mapped_column(ForeignKey("room_types.id"), unique=True)
    units: Mapped[int]

class RoomAvailability(Identified, Base):
    __tablename__ = "room_availability"
    room_type_id: Mapped[str] = mapped_column(ForeignKey("room_types.id"))
    night: Mapped[date] = mapped_column(Date)
    blocked_units: Mapped[int] = mapped_column(default=0)
    closed: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (UniqueConstraint("room_type_id", "night"),)

class Reservation(Identified, Base):
    __tablename__ = "reservations"
    room_type_id: Mapped[str] = mapped_column(ForeignKey("room_types.id"), index=True)
    check_in: Mapped[date] = mapped_column(Date)
    check_out: Mapped[date] = mapped_column(Date)
    units: Mapped[int] = mapped_column(default=1)

class AddOn(Identified, Base):
    __tablename__ = "add_ons"
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"), index=True)
    name: Mapped[str]
    price_minor: Mapped[int]
    basis: Mapped[str]  # guest-night or stay

class PricingPolicy(Identified, Base):
    __tablename__ = "pricing_policies"
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"), unique=True)
    auto_bps: Mapped[int] = mapped_column(default=500)
    manager_bps: Mapped[int] = mapped_column(default=1000)
    tax_bps: Mapped[int] = mapped_column(default=1200)
    version: Mapped[int] = mapped_column(default=1)

class Conversation(Identified, Base):
    __tablename__ = "conversations"
    token_hash: Mapped[str]
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Message(Identified, Base):
    __tablename__ = "messages"
    session_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str]
    content: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class ChatRequest(Identified, Base):
    __tablename__ = "chat_requests"
    session_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    key: Mapped[str]
    payload_hash: Mapped[str]
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (UniqueConstraint("session_id", "key"),)

class Quote(Identified, Base):
    __tablename__ = "quotes"
    session_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    room_type_id: Mapped[str] = mapped_column(ForeignKey("room_types.id"))
    fingerprint: Mapped[str]
    breakdown: Mapped[dict] = mapped_column(JSON)
    total_minor: Mapped[int]
    policy_version: Mapped[int]
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    invalidated: Mapped[bool] = mapped_column(default=False)

class BookingHold(Identified, Base):
    __tablename__ = "booking_holds"
    session_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    room_type_id: Mapped[str] = mapped_column(ForeignKey("room_types.id"), index=True)
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"))
    check_in: Mapped[date] = mapped_column(Date)
    check_out: Mapped[date] = mapped_column(Date)
    total_minor: Mapped[int]
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    idempotency_key: Mapped[str]
    __table_args__ = (UniqueConstraint("session_id", "idempotency_key"),)

class NegotiationSession(Identified, Base):
    __tablename__ = "negotiation_sessions"
    session_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"), unique=True)
    attempts: Mapped[int] = mapped_column(default=0)

class NegotiationOffer(Identified, Base):
    __tablename__ = "negotiation_offers"
    session_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"), index=True)
    proposed_amount: Mapped[int]
    approved_amount: Mapped[int | None]
    discount_bps: Mapped[int]
    status: Mapped[str]
    policy_version: Mapped[int]
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    idempotency_key: Mapped[str]
    __table_args__ = (UniqueConstraint("session_id", "idempotency_key"),)

class EscalationFlag(Identified, Base):
    __tablename__ = "escalation_flags"
    session_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    category: Mapped[str]
    severity: Mapped[str]
    status: Mapped[str] = mapped_column(default="open", index=True)
    reason_code: Mapped[str]
    context: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    idempotency_key: Mapped[str]
    __table_args__ = (UniqueConstraint("session_id", "idempotency_key"),)

class HandoffRequest(Identified, Base):
    __tablename__ = "human_handoff_requests"
    flag_id: Mapped[str] = mapped_column(ForeignKey("escalation_flags.id"), unique=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    status: Mapped[str] = mapped_column(default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class ToolLog(Identified, Base):
    __tablename__ = "tool_execution_logs"
    session_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    correlation_id: Mapped[str] = mapped_column(index=True)
    tool_name: Mapped[str]
    arguments: Mapped[dict] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    duration_ms: Mapped[int]
    success: Mapped[bool]
    summary: Mapped[dict] = mapped_column(JSON)

Index("ix_hold_overlap", BookingHold.room_type_id, BookingHold.check_in, BookingHold.check_out, BookingHold.expires_at)
