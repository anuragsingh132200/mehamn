"""Strict model contracts. No arbitrary tool names, SQL, identities, or pricing policy fields."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

Intent = Literal["search", "select", "policy", "negotiate", "confirm", "cancel", "human", "complaint", "exception", "injection", "modify", "decline", "greeting", "small_talk", "general_question", "unknown"]
FieldName = Literal["destination", "check_in", "check_out", "adults", "children", "child_ages", "budget_amount", "budget_basis", "required_amenities", "preferred_amenities", "room_preferences", "special_requests"]

class StatePatch(StrictModel):
    field: FieldName
    operation: Literal["SET", "CLEAR", "UNSET"]
    value: str | int | list[str] | list[int] | None = None

    @model_validator(mode="after")
    def value_matches_operation(self):
        if self.operation=="SET" and self.value is None:
            raise ValueError("SET requires a value; use CLEAR for removal")
        if self.operation!="SET" and self.value is not None:
            raise ValueError("CLEAR/UNSET cannot carry a value")
        return self

class DateOperation(StrictModel):
    field: Literal["check_in", "check_out"]
    operation: Literal["shift_days", "from_today", "from_check_in"]
    days: int = Field(ge=-365, le=730)

class RecommendationReference(StrictModel):
    source: Literal["selected", "recommendation"] = "selected"
    index: int | None = Field(None, ge=1, le=9)
    @model_validator(mode="after")
    def reference_shape(self):
        if self.source=="recommendation" and self.index is None: raise ValueError("A recommendation needs an index")
        if self.source=="selected" and self.index is not None: raise ValueError("A selected reference cannot carry an index")
        return self

class NegotiationProposal(StrictModel):
    kind: Literal["best_price", "amount", "percentage", "complimentary_add_on"] = "best_price"
    amount_minor: int | None = Field(None, gt=0)
    basis: Literal["night", "stay"] | None = None
    percentage_bps: int | None = Field(None, ge=1, le=10000)
    add_on: Literal["breakfast", "airport_transfer"] | None = None
    @model_validator(mode="after")
    def coherent(self):
        if self.kind=="amount" and self.amount_minor is None: raise ValueError("An amount proposal needs an amount")
        if self.kind=="percentage" and self.percentage_bps is None: raise ValueError("A percentage proposal needs basis points")
        if self.kind=="complimentary_add_on" and self.add_on is None: raise ValueError("Specify the requested concession")
        if self.kind!="amount" and (self.amount_minor is not None or self.basis is not None): raise ValueError("Only an amount proposal accepts amount and basis")
        if self.kind!="percentage" and self.percentage_bps is not None: raise ValueError("Unexpected percentage")
        if self.kind!="complimentary_add_on" and self.add_on is not None: raise ValueError("Unexpected concession")
        return self

class AddOnChange(StrictModel):
    name: Literal["breakfast", "airport_transfer"]
    operation: Literal["add", "remove"]

class EscalationClassification(StrictModel):
    category: Literal["guest_complaint", "abusive_language", "requested_human", "policy_exception", "unsupported_request", "possible_prompt_injection", "repeated_unresolved_issue"]
    severity: Literal["info", "warning", "critical"] = "warning"

class Interpretation(StrictModel):
    primary_intent: Intent = "unknown"
    secondary_intents: list[Intent] = Field(default_factory=list, max_length=8)
    patches: list[StatePatch] = Field(default_factory=list, max_length=16)
    date_operations: list[DateOperation] = Field(default_factory=list, max_length=2)
    add_on_changes: list[AddOnChange] = Field(default_factory=list, max_length=2)
    reference: RecommendationReference | None = None
    explicit_confirmation: bool = False
    declines_pending_action: bool = False
    explicit_cancellation: bool = False
    negotiation: NegotiationProposal | None = None
    escalations: list[EscalationClassification] = Field(default_factory=list, max_length=4)
    ambiguities: list[str] = Field(default_factory=list, max_length=4)
    clarification_question: str | None = Field(None, max_length=300)

    @model_validator(mode="after")
    def consistent_confirmation(self):
        changed=[p.field for p in self.patches if p.operation!='UNSET']
        dates=[d.field for d in self.date_operations]
        if len(changed)!=len(set(changed)) or len(dates)!=len(set(dates)) or set(changed)&set(dates):
            raise ValueError("Use exactly one update per field: either a SET/CLEAR patch OR a date operation, never both")
        if self.explicit_confirmation and self.declines_pending_action:
            raise ValueError("A turn cannot both confirm and decline an action")
        return self

class EmptyArguments(StrictModel):
    pass
class ReferenceArguments(StrictModel):
    reference: RecommendationReference = Field(default_factory=RecommendationReference)
class PolicyArguments(ReferenceArguments):
    topic: str = Field(min_length=1, max_length=80)
class SearchCall(StrictModel):
    tool: Literal["search_properties"] = "search_properties"
    arguments: EmptyArguments = Field(default_factory=EmptyArguments)
class SelectCall(StrictModel):
    tool: Literal["select_room"] = "select_room"
    arguments: ReferenceArguments
class AvailabilityCall(StrictModel):
    tool: Literal["check_availability"] = "check_availability"
    arguments: ReferenceArguments = Field(default_factory=ReferenceArguments)
class DetailsCall(StrictModel):
    tool: Literal["get_room_details"] = "get_room_details"
    arguments: ReferenceArguments = Field(default_factory=ReferenceArguments)
class PriceCall(StrictModel):
    tool: Literal["calculate_price"] = "calculate_price"
    arguments: ReferenceArguments = Field(default_factory=ReferenceArguments)
class PolicyCall(StrictModel):
    tool: Literal["get_policy"] = "get_policy"
    arguments: PolicyArguments
class DiscountCall(StrictModel):
    tool: Literal["evaluate_discount"] = "evaluate_discount"
    arguments: EmptyArguments = Field(default_factory=EmptyArguments)
class OfferCall(StrictModel):
    tool: Literal["create_negotiation_offer"] = "create_negotiation_offer"
    arguments: EmptyArguments = Field(default_factory=EmptyArguments)
class FlagArguments(StrictModel):
    classification_index: int = Field(ge=1, le=4)
class FlagCall(StrictModel):
    tool: Literal["create_escalation_flag"] = "create_escalation_flag"
    arguments: FlagArguments
class HandoffCall(StrictModel):
    tool: Literal["request_human_handoff"] = "request_human_handoff"
    arguments: FlagArguments
class HoldCall(StrictModel):
    tool: Literal["create_booking_hold"] = "create_booking_hold"
    arguments: EmptyArguments = Field(default_factory=EmptyArguments)

class CancelHoldCall(StrictModel):
    tool: Literal["cancel_booking_hold"] = "cancel_booking_hold"
    arguments: EmptyArguments = Field(default_factory=EmptyArguments)

ToolCall = CancelHoldCall | SearchCall | SelectCall | AvailabilityCall | DetailsCall | PriceCall | PolicyCall | DiscountCall | OfferCall | FlagCall | HandoffCall | HoldCall

class AgentDecision(StrictModel):
    interpretation: Interpretation = Field(default_factory=Interpretation)
    proposed_next_action: Literal["execute_tools", "ask_clarification", "respond_to_guest"] = "respond_to_guest"
    requested_tool_calls: list[ToolCall] = Field(default_factory=list, max_length=8)
    needs_human_approval: bool = False  # Advisory only; engine determines actual approval.
    request_followup: bool = False
    referenced_quote_id: str | None = None  # Must match this session's active quote.
    @model_validator(mode="after")
    def action_consistency(self):
        if self.proposed_next_action!="execute_tools" and self.requested_tool_calls:
            raise ValueError("Only execute_tools may request calls")
        if self.proposed_next_action=="ask_clarification" and not self.interpretation.clarification_question:
            raise ValueError("Clarification needs one question")
        if self.proposed_next_action=="execute_tools" and not self.requested_tool_calls:
            raise ValueError("Tool action requires calls")
        return self

class ResponsePart(StrictModel):
    kind: Literal["text", "fact"]
    text: str | None = Field(None, max_length=1200)
    fact_key: str | None = Field(None, max_length=100)
    @model_validator(mode="after")
    def shape(self):
        if self.kind=="fact" and (not self.fact_key or self.text is not None): raise ValueError("Facts reference an existing key only")
        if self.kind=="text" and (self.text is None or self.fact_key is not None): raise ValueError("Text requires text only")
        return self

class GroundedResponse(StrictModel):
    parts: list[ResponsePart] = Field(min_length=1, max_length=16)
    referenced_fact_keys: list[str] = Field(default_factory=list, max_length=32)
    follow_up_question: str | None = Field(None, max_length=300)
