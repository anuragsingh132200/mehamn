import pytest
from pydantic import ValidationError
from app.agent_schemas import AgentDecision,StatePatch,NegotiationProposal,RecommendationReference

def test_multiple_intents_and_typed_tools():
    plan=AgentDecision.model_validate({'interpretation':{'primary_intent':'select','secondary_intents':['negotiate'],'reference':{'source':'recommendation','index':2},'add_on_changes':[{'name':'breakfast','operation':'add'}]},'proposed_next_action':'execute_tools','requested_tool_calls':[{'tool':'select_room','arguments':{'reference':{'source':'recommendation','index':2}}},{'tool':'create_negotiation_offer'}]})
    assert len(plan.requested_tool_calls)==2 and plan.interpretation.secondary_intents==['negotiate']

def test_unknown_tool_is_rejected_before_execution():
    with pytest.raises(ValidationError):AgentDecision.model_validate({'proposed_next_action':'execute_tools','requested_tool_calls':[{'tool':'execute_sql','arguments':{'sql':'SELECT 1'}}]})

def test_state_patch_requires_explicit_clear():
    with pytest.raises(ValidationError):StatePatch(field='adults',operation='SET',value=None)
    assert StatePatch(field='budget_amount',operation='CLEAR').value is None

def test_negotiation_schema_rejects_incoherent_amount():
    with pytest.raises(ValidationError):NegotiationProposal(kind='amount')
    with pytest.raises(ValidationError):NegotiationProposal(kind='best_price',amount_minor=1000)
    assert NegotiationProposal(kind='percentage',percentage_bps=750).percentage_bps==750

def test_reference_requires_real_ordinal():
    with pytest.raises(ValidationError):RecommendationReference(source='recommendation')
    with pytest.raises(ValidationError):RecommendationReference(source='recommendation',index=0)
