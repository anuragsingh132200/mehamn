"""Typed validation of business-tool facts before cards, state or model consumption."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator

from .itinerary_schemas import ItineraryResult

class Result(BaseModel):
    model_config=ConfigDict(extra='forbid')
class AddOnResult(Result):
    id:str
    name:str
    amount_minor:int=Field(ge=0)
class QuoteResult(Result):
    id:str
    currency:Literal['INR']
    nights:int=Field(ge=1,le=30)
    nightly_minor:int=Field(ge=0)
    base_minor:int=Field(ge=0)
    add_ons:list[AddOnResult]
    tax_minor:int=Field(ge=0)
    total_minor:int=Field(ge=0)
    fictional:Literal[True]
    expires_at:str
    @model_validator(mode='after')
    def coherent(self):
        if self.total_minor!=self.base_minor+sum(a.amount_minor for a in self.add_ons)+self.tax_minor:raise ValueError('Quote breakdown does not add up')
        if self.base_minor!=self.nights*self.nightly_minor:raise ValueError('Nightly breakdown inconsistent')
        return self
class Recommendation(Result):
    room_type_id:str
    property_id:str
    property_name:str
    location:str
    room_name:str
    description:str
    capacity:int=Field(ge=1)
    amenities:list[str]
    quote:QuoteResult
    preference_score:int=Field(ge=0)
class SearchResult(Result):
    recommendations:list[Recommendation]
class AvailabilityResult(Result):
    available:bool
    units_remaining:int=Field(ge=0)
    nights:int=Field(ge=1,le=30)
class RoomResult(Result):
    id:str
    property_id:str
    name:str
    description:str
    capacity:int=Field(ge=1)
    nightly_minor:int=Field(ge=0)
    amenities:list[str]
class PolicyResult(Result):
    known:bool
    topic:str
    value:str|None
    @model_validator(mode='after')
    def known_value(self):
        if self.known!=(self.value is not None):raise ValueError('Policy known/value mismatch')
        return self
class DiscountResult(Result):
    status:Literal['accepted','pending_approval','countered','rejected']
    proposed_amount:int=Field(gt=0)
    approved_amount:int|None
    discount_bps:int
    policy_version:int
    expires_at:str
class OfferResult(Result):
    id:str
    quote_id:str
    status:Literal['proposed','accepted','countered','pending_approval','rejected','expired']
    approved_amount:int|None
    proposed_amount:int=Field(gt=0)
    expires_at:str
    attempts:int=0
class HoldResult(Result):
    id:str
    quote_id:str
    total_minor:int=Field(ge=0)
    expires_at:str
    status:Literal['temporary_hold','expired','cancelled']
    confirmed_reservation:Literal[False]
class ReviewResult(Result):
    id:str
    status:str
    category:str|None=None

RESULT_SCHEMAS={'plan_itinerary':ItineraryResult,'cancel_booking_hold':HoldResult,'search_properties':SearchResult,'check_availability':AvailabilityResult,'get_room_details':RoomResult,'calculate_price':QuoteResult,'get_policy':PolicyResult,'evaluate_discount':DiscountResult,'create_negotiation_offer':OfferResult,'create_booking_hold':HoldResult,'create_escalation_flag':ReviewResult,'request_human_handoff':ReviewResult,'resolve_escalation_flag':ReviewResult}

def validate_result(name,data):
    RESULT_SCHEMAS[name].model_validate(data)
    return data

def public_results(results):
    def clean(obj):
        if isinstance(obj,dict):return {k:clean(v) for k,v in obj.items() if k not in {'discount_bps','policy_version','reason_code','context','idempotency_key'}}
        if isinstance(obj,list):return [clean(x) for x in obj]
        return obj
    return [({'tool_name':r['tool_name'],'data':{'status':'recorded_for_review'}} if r['tool_name'] in {'create_escalation_flag','request_human_handoff'} else clean(r)) for r in results]
