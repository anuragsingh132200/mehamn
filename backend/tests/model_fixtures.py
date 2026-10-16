"""Recorded structured model fixtures for the existing 50 regressions; never imported by app.
These validate business behavior, not model language accuracy. Unknown utterances fail
instead of silently invoking a fake conversational engine.
"""
import json
from pathlib import Path
from app.agent_schemas import AgentDecision,Interpretation,GroundedResponse,ResponsePart

RECORDS=json.loads((Path(__file__).parent/'fixtures/legacy_interpretations.json').read_text())

def fixture_decision(message):
    raw=RECORDS[message]
    intent=raw['intent'];reference={'source':'recommendation','index':raw['selection']} if raw['selection'] else None
    data={'primary_intent':intent,'patches':raw['patches'],'reference':reference,'explicit_confirmation':intent=='confirm'}
    if raw['add_on_action']!='none':
        op,name=raw['add_on_action'].split('_',1)
        data['add_on_changes']=[{'operation':op,'name':'airport_transfer' if name=='transfer' else 'breakfast'}]
    if intent=='negotiate':
        proposal={'kind':'best_price'}
        if raw['concession']=='free_breakfast':proposal={'kind':'complimentary_add_on','add_on':'breakfast'}
        elif raw['proposed_amount']:proposal={'kind':'amount','amount_minor':raw['proposed_amount'],'basis':raw['proposed_basis']}
        data['negotiation']=proposal
    calls={
        'search':[{'tool':'search_properties'}],
        'select':[{'tool':'select_room','arguments':{'reference':reference}}],
        'policy':[{'tool':'get_policy','arguments':{'topic':raw['policy_topic'],'reference':{'source':'selected'}}}],
        'negotiate':[{'tool':'create_negotiation_offer'}],
        'confirm':[{'tool':'create_booking_hold'}],
    }.get(intent,[])
    return AgentDecision.model_validate({'interpretation':data,'proposed_next_action':'execute_tools' if calls else 'respond_to_guest','requested_tool_calls':calls})

def fixture_response(context):
    facts=context['fact_catalog']
    keys=[key for key in facts if key.startswith('policy_')]
    if not keys:keys=[key for key in ('itinerary','hold','offer','review','active_quote','search_result','confirmation_required') if key in facts]
    if keys:return GroundedResponse(parts=[ResponsePart(kind='fact',fact_key=k) for k in keys],referenced_fact_keys=keys)
    return GroundedResponse(parts=[ResponsePart(kind='text',text='Please share your destination, arrival date, departure date and adult count.')])

def request_fixture(self,schema,context,system,purpose):
    result=fixture_decision(context['latest_message']) if schema is AgentDecision else fixture_response(context)
    return result,{'input_tokens':100,'output_tokens':50}
