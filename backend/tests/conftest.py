import os
# Tests default to a local SQLite smoke database. Set TEST_DATABASE_URL to run real locking tests.
os.environ['DATABASE_URL']=os.environ.get('TEST_DATABASE_URL','sqlite:////tmp/mira-tests.db')
os.environ['LLM_MODE']='openai'
os.environ['ADMIN_TOKEN']='test-admin-only-token'
import pytest
from freezegun import freeze_time
from fastapi.testclient import TestClient
from app.db import Base, engine, SessionLocal
from app.main import app
from app.seed import seed

@pytest.fixture(autouse=True)
def database():
    # WARNING: TEST_DATABASE_URL must point to a disposable database.
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with SessionLocal.begin() as db: seed(db)
    with freeze_time('2026-10-16 06:00:00',real_asyncio=True): yield

@pytest.fixture
def client():
    # Deliberately skip lifespan checkpoint pool in unit tests. The integration test
    # invokes it explicitly after initializing LangGraph's migrations.
    return TestClient(app)

@pytest.fixture
def guest(client):
    session=client.post('/api/sessions').json()
    headers={'Authorization':'Bearer '+session['token']}
    from uuid import uuid4
    def chat(message,key=None,**extra):
        return client.post('/api/chat',headers=headers,json={'session_id':session['session_id'],'message':message,'idempotency_key':key or str(uuid4()),**extra})
    return session,headers,chat

@pytest.fixture(autouse=True)
def structured_model_fixtures(monkeypatch):
    from app.config import settings
    from app.model_gateway import ModelGateway
    from model_fixtures import request_fixture
    monkeypatch.setattr(settings,'openai_api_key','test-only-placeholder')
    monkeypatch.setattr(ModelGateway,'_request',request_fixture)
