"""LLM prose with backend-rendered factual spans and conservative output checks."""
import re
from .agent_schemas import GroundedResponse
from .context import build_context
from .prompts import RESPONSE_PROMPT
from .model_gateway import ModelOutputInvalid
from .db import now

class ResponseGroundingError(ValueError):pass

def rupees(value):return f"₹{value/100:,.2f}"

def fact_catalog(state,results,reviewed=()):
    facts={}
    for i,card in enumerate(state.latest_recommendations,1):
        q=card['quote']
        facts[f'option_{i}']=f"Option {i}: {card['room_name']} at {card['property_name']} in {card['location']}; capacity {card['capacity']}. Verified amenities: {', '.join(card['amenities'])}. Total {rupees(q['total_minor'])} for {q['nights']} nights, including tax."
    if state.quote:
        q=state.quote
        facts['active_quote']=f"The {'expired' if q['expires_at']<=now().isoformat() else 'current'} quote is {rupees(q['total_minor'])} for {q['nights']} nights, including tax and selected add-ons. Quote expiry: {q['expires_at']} UTC."
    for i,result in enumerate(results):
        name,data=result['tool_name'],result['data']
        if name=='get_policy':facts[f'policy_{i}']=data['value'] if data['known'] else "I can’t confirm that detail from this property’s records."
        elif name=='check_availability':facts[f'availability_{i}']="This room is available for the requested stay at the time of checking." if data['available'] else "This room is unavailable for the requested stay."
        elif name=='get_room_details':facts[f'room_{i}']=f"{data['name']}: {data['description']} Recorded amenities: {', '.join(data['amenities'])}. Capacity: {data['capacity']}."
        elif name=='search_properties':facts['search_result']=f"{len(data['recommendations'])} available options match the current hard requirements and all-in budget." if data['recommendations'] else "No available rooms match all current requirements and the all-in budget."
    offer=state.negotiation_state
    if offer:
        status=offer.get('status')
        if offer.get('expires_at','')<=now().isoformat():status='expired'
        if status=='pending_approval':facts['offer']='The proposed price is pending manager review. No discount has been approved.'
        elif status in {'accepted','countered'} and offer.get('approved_amount') is not None:
            facts['offer']=f"The {'approved offer' if status=='accepted' else 'available counteroffer'} is {rupees(offer['approved_amount'])} for the full stay, including tax. Guest confirmation is required before a temporary hold."
        else:facts['offer']=f"The negotiation offer status is {status}. It is not an active discounted booking."
    if reviewed:facts['review']='Your request has been recorded for staff review. No human response is available yet, and no response time is promised.'
    if state.hold:
        h=state.hold
        status='cancelled' if h['status']=='cancelled' else 'expired' if h['expires_at']<=now().isoformat() else h['status']
        if status=='cancelled':
            facts['hold']=f"Temporary hold {h['id'][:8]} has been cancelled and its inventory claim released. No payment was taken; no refund was processed."
        else: facts['hold']=f"Temporary hold {h['id'][:8]}: {status}; total {rupees(h['total_minor'])}; expiry {h['expires_at']} UTC. This is not a confirmed reservation. No payment has been taken."
    if state.pending_confirmation:facts['confirmation_required']='Please review the current quote or offer and explicitly confirm if you want a temporary hold.'
    return facts

def render_response(output,facts):
    output=GroundedResponse.model_validate(output)
    used=[p.fact_key for p in output.parts if p.kind=='fact']
    if set(used)!=set(output.referenced_fact_keys) or any(k not in facts for k in used):raise ResponseGroundingError('Unknown or uncited fact')
    prose=' '.join([p.text for p in output.parts if p.kind=='text']+[output.follow_up_question or ''])
    # These are output integrity checks, not semantic intent routing. Numeric factual
    # content must be inserted from server facts, not generated/recomputed by a model.
    if re.search(r'\d|[₹$€£]|\b(?:INR|USD)\b',prose):raise ResponseGroundingError('Numeric facts must use fact parts')
    if re.search(r'\b(?:booking|reservation)\s+(?:is\s+)?confirmed\b|\bmanager\s+(?:has\s+)?approved\b|\bpayment\s+(?:was\s+)?(?:received|taken)\b',prose,re.I):raise ResponseGroundingError('Business status must use fact parts')
    rendered=' '.join(facts[p.fact_key] if p.kind=='fact' else p.text for p in output.parts).strip()
    if output.follow_up_question:rendered+=' '+output.follow_up_question
    return rendered

def generate_response(gateway,message,state,history,results,reviewed=()):
    facts=fact_catalog(state,results,reviewed)
    context=build_context(message,state,history,results)
    context['fact_catalog']=facts
    output=gateway.parse(GroundedResponse,context,RESPONSE_PROMPT,'response')
    try:return render_response(output,facts),output.follow_up_question
    except ResponseGroundingError:
        # One repair, still subject to the whole-turn model/deadline budget.
        context['validation_feedback']='The response failed fact validation. Use only provided fact keys for factual amounts/status; no numeric or booking-status assertions in free text.'
        output=gateway.parse(GroundedResponse,context,RESPONSE_PROMPT,'response_repair')
        return render_response(output,facts),output.follow_up_question

def safe_receipt(state,results,reviewed=()):
    """Guaranteed outage wording, never an offline conversational fallback."""
    facts=fact_catalog(state,results,reviewed)
    keys=[k for k in ('hold','offer','review','active_quote','search_result','confirmation_required') if k in facts]
    return 'The language service could not complete the explanation. '+(' '.join(facts[k] for k in keys) if keys else 'No new booking has been confirmed. Please retry your message.')
