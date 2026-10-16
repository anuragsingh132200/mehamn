from sqlalchemy import select
import pytest
from app import models as m,schemas as s
from app.db import SessionLocal,now
from app.tools import Tools,BusinessError
from app.agent_schemas import AgentDecision
from app.main import guest_state
from test_booking import select_first
from test_llm_agent import mock_plan,execute

def held(guest):
    select_first(guest,'private pool')
    return guest[2]('Confirm hold').json()['state']

def cancel_plan():
    return execute({'tool':'cancel_booking_hold'},primary_intent='cancel',explicit_cancellation=True)

def test_cancellation_releases_inventory_and_preserves_requirements(guest,monkeypatch):
    before=held(guest)
    mock_plan(monkeypatch,cancel_plan())
    first=guest[2]('Please cancel my current temporary hold.',key='cancel-request-001')
    assert first.status_code==200,first.text
    state=first.json()['state']
    assert state['hold']['status']=='cancelled' and state['active_booking_hold_id'] is None
    assert state['booking_requirements']==before['booking_requirements']
    assert state['latest_quote_id'] is None and not state['pending_confirmation']
    assert guest[2]('Please cancel my current temporary hold.',key='cancel-request-001').json()==first.json()
    again=guest[2]('Cancel that same hold again.').json()['state']
    assert again['hold']['status']=='cancelled'
    with SessionLocal() as db:
        h=db.get(m.BookingHold,before['hold']['id'])
        assert h.cancelled_at and h.expires_at<=now()
        refreshed=guest_state(db,db.get(m.Conversation,guest[0]['session_id']))
        assert refreshed.hold['status']=='cancelled'
        tools=Tools(db,guest[0]['session_id'],'cancel-inventory-check')
        available=tools.check_availability(s.AvailabilityInput(room_type_id=before['selected_room_type_id'],requirements=s.BookingRequirements.model_validate(before['booking_requirements'])))
        assert available['available'] and available['units_remaining']==1
        assert db.get(m.Quote,before['latest_quote_id']).invalidated

def test_policy_question_cannot_cancel_hold(guest,monkeypatch):
    before=held(guest)
    mock_plan(monkeypatch,execute({'tool':'get_policy','arguments':{'topic':'cancellation'}},primary_intent='policy'))
    state=guest[2]('What is the cancellation policy?').json()['state']
    assert state['active_booking_hold_id']==before['active_booking_hold_id']

def test_cancellation_requires_explicit_authorization(guest,monkeypatch):
    before=held(guest)
    mock_plan(monkeypatch,execute({'tool':'cancel_booking_hold'},primary_intent='cancel'))
    state=guest[2]('Maybe I should cancel?').json()['state']
    assert state['active_booking_hold_id']==before['active_booking_hold_id']
    with SessionLocal() as db:assert db.get(m.BookingHold,before['hold']['id']).cancelled_at is None

def test_cancellation_cannot_target_another_session(guest):
    state=held(guest)
    with SessionLocal() as db:
        with pytest.raises(BusinessError):Tools(db,'different-session','cross-session').cancel_booking_hold(s.CancelHoldInput(hold_id=state['hold']['id'],confirmed=True))
        assert db.get(m.BookingHold,state['hold']['id']).cancelled_at is None

def test_expired_hold_cannot_be_cancelled(guest):
    state=held(guest)
    with SessionLocal.begin() as db:
        h=db.get(m.BookingHold,state['hold']['id']);h.expires_at=now()
        with pytest.raises(BusinessError):Tools(db,guest[0]['session_id'],'expired-cancel').cancel_booking_hold(s.CancelHoldInput(hold_id=h.id,confirmed=True))
        assert h.cancelled_at is None
