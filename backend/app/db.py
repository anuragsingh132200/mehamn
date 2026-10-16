from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

class Base(DeclarativeBase):
    pass

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

engine = create_engine(settings.database_url, pool_pre_ping=True, **(
    {"pool_size": 10, "max_overflow": 20, "pool_timeout": 10, "connect_args": {"options": "-c lock_timeout=10000 -c statement_timeout=20000"}}
    if settings.database_url.startswith("postgresql") else {"connect_args": {"check_same_thread": False}}))
SessionLocal = sessionmaker(engine, expire_on_commit=False)

def get_db():
    with SessionLocal() as db:
        yield db
