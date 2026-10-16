"""Actual PostgreSQL tests. SQLite cannot establish row-locking correctness."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import date
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from app.db import engine,SessionLocal
from app import models as m,schemas as s
from app.seed import sid
from app.tools import Tools,BusinessError

pytestmark=pytest.mark.skipif(engine.dialect.name!='postgresql',reason='PostgreSQL required for real row locking')

def test_two_sessions_cannot_hold_last_unit():
    req=s.BookingRequirements(destination='Goa',check_in=date(2026,11,10),check_out=date(2026,11,12),adults=2)
    pairs=[]
    with SessionLocal.begin() as db:
        for _ in range(2):
            c=m.Conversation(token_hash=str(uuid4()),state={});db.add(c);db.flush()
            q=Tools(db,c.id,'setup').run('calculate_price',s.PriceInput(room_type_id=sid('casa2'),requirements=req,session_id=c.id))
            pairs.append((c.id,q['id']))
    barrier=Barrier(2)
    def compete(pair):
        with SessionLocal.begin() as db:
            t=Tools(db,pair[0],str(uuid4()))
            barrier.wait(timeout=10)
            try:
                return t.run('create_booking_hold',s.HoldInput(session_id=pair[0],quote_id=pair[1],requirements=req,confirmed=True,idempotency_key=str(uuid4())))['status']
            except BusinessError: return 'unavailable'
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(compete,pairs))
    assert sorted(results)==['temporary_hold','unavailable'],f'Unsafe contention outcome: {results}'
    with SessionLocal() as db: assert db.scalar(select(func.count()).select_from(m.BookingHold))==1

def test_same_session_messages_are_serialized(client,guest):
    session,headers,chat=guest
    barrier=Barrier(2)
    def send(i):
        barrier.wait(timeout=10)
        return chat(f'Goa {i+1} adults').json()
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(send,[0,1]))
    assert sorted(r['state']['state_version'] for r in results)==[1,2]
    with SessionLocal() as db:
        c=db.get(m.Conversation,session['session_id'])
        assert c.version==2
        assert db.scalar(select(func.count()).select_from(m.Message))==4
