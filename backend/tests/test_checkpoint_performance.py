"""A turn checkpoints once while preserving replay and session restoration."""
from langgraph.checkpoint.memory import InMemorySaver
from app.main import app
from app.agent_schemas import AgentDecision
from app.model_gateway import ModelGateway
from model_fixtures import fixture_response


class CountingSaver(InMemorySaver):
    def __init__(self):
        super().__init__()
        self.checkpoint_count = 0
        self.write_count = 0

    def put(self, *args, **kwargs):
        self.checkpoint_count += 1
        return super().put(*args, **kwargs)

    def put_writes(self, *args, **kwargs):
        self.write_count += 1
        return super().put_writes(*args, **kwargs)


def test_one_checkpoint_per_turn_with_idempotency_and_restore(client, guest, monkeypatch):
    def request(self, schema, context, system, purpose):
        value = AgentDecision() if schema is AgentDecision else fixture_response(context)
        return value, {}
    monkeypatch.setattr(ModelGateway, '_request', request)
    saver = CountingSaver()
    monkeypatch.setattr(app.state, 'checkpointer', saver, raising=False)
    session, headers, chat = guest
    first = chat('Hello', key='checkpoint-turn-one')
    assert first.status_code == 200, first.text
    assert saver.checkpoint_count == 1
    assert saver.write_count == 0
    checkpoint = saver.get_tuple({'configurable': {'thread_id': session['session_id']}})
    assert checkpoint.checkpoint['channel_values']['state'] == first.json()['state']
    assert chat('Hello', key='checkpoint-turn-one').json() == first.json()
    assert saver.checkpoint_count == 1
    second = chat('Hello again', key='checkpoint-turn-two')
    assert second.status_code == 200, second.text
    assert saver.checkpoint_count == 2
    assert saver.write_count == 0
    restored = client.get('/api/sessions/' + session['session_id'], headers=headers).json()
    assert restored['state'] == second.json()['state']
    assert len(restored['messages']) == 4
