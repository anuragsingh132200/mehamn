import pytest
from pydantic import ValidationError
from app.agent_schemas import AgentDecision
from app.itinerary import catalog,create_plan
from app.itinerary_schemas import BuildInput,ItineraryPreferences
from app.tools import BusinessError
from app.response import fact_catalog
from app.db import SessionLocal
from app import models as m
from test_llm_agent import execute,mock_plan
from test_booking import select_first

def test_fictional_catalog_and_family_exclusions():
    assert len(catalog())==30 and len({a.id for a in catalog()})==30
    result=create_plan(BuildInput(preferences=ItineraryPreferences(days=3,region='south_goa',family_friendly=True,avoid=['adventure'],pace='relaxed')))
    stops=[s for d in result['days'] for s in d['stops']]
    assert len(stops)==6 and len({s['activity']['id'] for s in stops})==6
    assert all(s['activity']['fictional'] and s['activity']['family_friendly'] and s['activity']['region']=='south_goa' for s in stops)
    assert all(s['activity']['category']!='adventure' for s in stops)
    assert all(d['date'] is None for d in result['days'])

def test_catalog_exhaustion_does_not_invent_activities():
    result=create_plan(BuildInput(preferences=ItineraryPreferences(days=7,region='north_goa',interests=['culture'],pace='busy')))
    assert len(result['days'])==7
    assert sum(len(d['stops']) for d in result['days'])==3
    assert result['days'][-1]['note'] and not result['days'][-1]['stops']

def test_conflicting_or_empty_preferences_rejected():
    with pytest.raises(BusinessError):create_plan(BuildInput(preferences=ItineraryPreferences(days=2,region='north_goa',interests=['beach'],avoid=['beach'])))
    with pytest.raises(BusinessError):create_plan(BuildInput(preferences=ItineraryPreferences(days=2,region='north_goa',avoid=['beach','culture','food','nature','relaxation','adventure'])))
    with pytest.raises(ValidationError):AgentDecision.model_validate({'proposed_next_action':'execute_tools','requested_tool_calls':[{'tool':'plan_itinerary','arguments':{'days':99}}]})

def test_undated_plan_saved_without_hotel_or_booking(guest,monkeypatch):
    mock_plan(monkeypatch,execute({'tool':'plan_itinerary','arguments':{'days':3,'region':'north_goa','interests':['beach','food'],'pace':'relaxed'}},primary_intent='itinerary'))
    response=guest[2]('Plan three relaxed days in North Goa with beaches and food.')
    assert response.status_code==200,response.text
    assert 'Fictional demo itinerary' in response.json()['response']
    state=response.json()['state']
    assert len(state['itinerary']['days'])==3 and state['itinerary']['fictional']
    assert not state['hold'] and not state['quote'] and not state['latest_recommendations']
    with SessionLocal() as db:
        saved=db.get(m.Conversation,guest[0]['session_id']).state
        assert saved['itinerary']==state['itinerary']
        assert saved['itinerary_preferences']['interests']==['beach','food']

def test_revision_preserves_booking_and_preferences(guest,monkeypatch):
    selected=select_first(guest)
    mock_plan(monkeypatch,execute({'tool':'plan_itinerary','arguments':{'interests':['beach','culture']}},primary_intent='itinerary'))
    first=guest[2]('Plan activities for these dates, with beaches and culture.').json()['state']
    assert len(first['itinerary']['days'])==2
    assert first['itinerary']['days'][0]['date']=='2026-11-10'
    assert first['itinerary']['days'][1]['date']=='2026-11-11'
    mock_plan(monkeypatch,execute({'tool':'plan_itinerary','arguments':{'pace':'relaxed','avoid':['adventure']}},primary_intent='itinerary'))
    revised=guest[2]('Make the plan more relaxed and avoid adventure.').json()['state']
    assert revised['itinerary_preferences']['interests']==['beach','culture']
    assert revised['itinerary_preferences']['pace']=='relaxed'
    for field in ['booking_requirements','latest_quote_id','quote','pending_confirmation']:
        assert revised[field]==selected[field]

def test_date_change_marks_plan_stale_until_regenerated(guest,monkeypatch):
    select_first(guest)
    mock_plan(monkeypatch,execute({'tool':'plan_itinerary'},primary_intent='itinerary'))
    guest[2]('Plan an itinerary for my stay.')
    mock_plan(monkeypatch,AgentDecision.model_validate({'interpretation':{'primary_intent':'modify','date_operations':[{'field':'check_out','operation':'shift_days','days':1}]}}))
    state=guest[2]('Extend checkout by one night.').json()['state']
    assert state['itinerary']['stale'] and state['latest_quote_id'] is None
    from app.schemas import AgentState
    assert 'needs updating' in fact_catalog(AgentState.model_validate(state),[])['itinerary']
    mock_plan(monkeypatch,execute({'tool':'plan_itinerary','arguments':{'days':3}},primary_intent='itinerary'))
    fresh=guest[2]('Refresh the itinerary for all three days.').json()['state']
    assert not fresh['itinerary']['stale'] and len(fresh['itinerary']['days'])==3

def test_plan_cannot_exceed_stay_or_change_previous_plan_on_failure(guest,monkeypatch):
    select_first(guest)
    mock_plan(monkeypatch,execute({'tool':'plan_itinerary'},primary_intent='itinerary'))
    before=guest[2]('Plan my stay.').json()['state']
    mock_plan(monkeypatch,execute({'tool':'plan_itinerary','arguments':{'days':4}},primary_intent='itinerary'))
    after=guest[2]('Make the itinerary four days.').json()['state']
    assert after['itinerary']==before['itinerary'] and after['booking_requirements']==before['booking_requirements']

def test_itinerary_only_includes_server_grounded_facts(guest,monkeypatch):
    mock_plan(monkeypatch,execute({'tool':'plan_itinerary','arguments':{'days':2,'region':'south_goa'}},primary_intent='itinerary'))
    state=guest[2]('Give me a South Goa plan.').json()['state']
    from app.schemas import AgentState
    facts=fact_catalog(AgentState.model_validate(state),[])
    assert 'Day 1' in facts['itinerary'] and 'Fictional' in facts['itinerary'] and 'No activities or transport have been booked' in facts['itinerary']
