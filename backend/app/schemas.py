from datetime import date
from enum import StrEnum
from typing import Literal, Any
from pydantic import BaseModel, Field, model_validator, ConfigDict

class BookingRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination: str | None = None
    check_in: date | None = None
    check_out: date | None = None
    adults: int | None = Field(None, ge=1, le=12)
    children: int = Field(0, ge=0, le=10)
    child_ages: list[int] = Field(default_factory=list)
    budget_amount: int | None = Field(None, gt=0, description="INR minor units")
    budget_basis: Literal["night", "stay"] = "night"
    required_amenities: list[str] = Field(default_factory=list)
    preferred_amenities: list[str] = Field(default_factory=list)
    room_preferences: list[str] = Field(default_factory=list)
    special_requests: list[str] = Field(default_factory=list)
    add_on_ids: list[str] = Field(default_factory=list)

from .agent_schemas import StatePatch as Patch, Interpretation as Extraction

from .itinerary_schemas import ItineraryPreferences,ItineraryResult

class AgentState(BaseModel):
    session_id: str
    messages: list[dict] = Field(default_factory=list)
    booking_requirements: BookingRequirements = Field(default_factory=BookingRequirements)
    itinerary_preferences: ItineraryPreferences = Field(default_factory=ItineraryPreferences)
    itinerary: ItineraryResult | None = None
    active_intent: str = "search"
    secondary_intents: list[str] = Field(default_factory=list)
    pending_clarification: str | None = None
    model_usage: dict = Field(default_factory=dict)
    response_degraded: bool = False
    selected_property_id: str | None = None
    selected_room_type_id: str | None = None
    latest_recommendations: list[dict] = Field(default_factory=list)
    recommendation_references: list[dict] = Field(default_factory=list, max_length=3)
    latest_quote_id: str | None = None
    negotiation_state: dict = Field(default_factory=dict)
    pending_confirmation: bool = False
    active_booking_hold_id: str | None = None
    escalation_status: str = "none"
    last_tool_results: list[dict] = Field(default_factory=list)
    next_action: str = "collect_requirements"
    state_version: int = 0
    quote: dict | None = None
    hold: dict | None = None

class SearchInput(BaseModel):
    requirements: BookingRequirements
class RoomInput(BaseModel):
    room_type_id: str
class AvailabilityInput(RoomInput):
    requirements: BookingRequirements
class PriceInput(AvailabilityInput):
    session_id: str
class PolicyInput(BaseModel):
    property_id: str
    topic: str
class HoldInput(BaseModel):
    session_id: str
    quote_id: str
    requirements: BookingRequirements
    confirmed: bool
    idempotency_key: str
class CancelHoldInput(BaseModel):
    hold_id: str
    confirmed: bool

class DiscountInput(BaseModel):
    quote_id: str
    proposed_amount: int | None = Field(None, gt=0)
    basis: Literal["night", "stay"] = "stay"
class OfferInput(DiscountInput):
    session_id: str
    idempotency_key: str
class FlagInput(BaseModel):
    session_id: str
    category: Literal["pricing_approval_required", "repeated_negotiation", "guest_complaint", "abusive_language", "requested_human", "policy_exception", "unsupported_request", "possible_prompt_injection", "tool_failure", "suspicious_booking_activity"]
    severity: Literal["info", "warning", "critical"] = "warning"
    reason_code: str
    context: dict = Field(default_factory=dict)
    idempotency_key: str
class HandoffInput(BaseModel):
    session_id: str
    flag_id: str
class ResolveInput(BaseModel):
    flag_id: str
class ChatInput(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=100)
    expected_version: int | None = Field(None, ge=0)
class SessionCreated(BaseModel):
    session_id: str
    token: str
class ChatOutput(BaseModel):
    response: str
    state: AgentState
    request_id: str
class SessionOutput(BaseModel):
    state: AgentState
    messages: list[dict]
    llm_mode: str
class ErrorOutput(BaseModel):
    error: str
    request_id: str
class ToolResult(BaseModel):
    tool_name: str
    data: dict
class ReservationOutput(BaseModel):
    recommendations: list[dict] = Field(default_factory=list)
    quote: dict | None = None
class NegotiationOutput(BaseModel):
    status: str
    offer_id: str | None = None
    approved_amount: int | None = None
class SupportOutput(BaseModel):
    known: bool
    value: Any = None
class RiskOutput(BaseModel):
    status: str
    flag_id: str | None = None

class TraceOutput(BaseModel):
    id: str
    tool_name: str
    arguments: dict
    started_at: str
    duration_ms: int
    success: bool
    summary: dict
    correlation_id: str
class OfferOutput(BaseModel):
    id: str
    quote_id: str
    status: str
    approved_amount: int | None
    proposed_amount: int
    expires_at: str
class FlagOutput(BaseModel):
    id: str
    status: str
    created_at: str
    message: str
class AdminFlag(BaseModel):
    id: str
    session_id: str
    category: str
    severity: str
    status: str
    reason_code: str
    context: dict
class AdminOffer(OfferOutput):
    session_id: str
class AdminQueue(BaseModel):
    flags: list[AdminFlag]
    offers: list[AdminOffer]
class StatusOutput(BaseModel):
    id: str
    status: str
class HealthOutput(BaseModel):
    status: str
    fictional: bool
    llm_mode: str
    model_configured: bool
class PropertyDetails(BaseModel):
    id: str
    name: str
    location: str
    policies: dict
    fictional: bool
    rooms: list[dict]
    add_ons: list[dict]
