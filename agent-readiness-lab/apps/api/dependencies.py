"""FastAPI dependencies."""

import os
from typing import Generator

from redis import Redis
from rq import Queue
from sqlalchemy.orm import Session

import sys
sys.path.insert(0, "/app/packages")

from arlab.db import get_engine, get_session_factory, init_db, Base


# Database
_engine = None
_session_factory = None


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://arlab:arlab@db:5432/arlab"
    )


def init_database():
    """Initialize the database."""
    global _engine, _session_factory
    url = get_database_url()
    _engine = get_engine(url)
    Base.metadata.create_all(_engine)
    _session_factory = get_session_factory(_engine)


def get_db() -> Generator[Session, None, None]:
    """Get database session."""
    global _session_factory
    if _session_factory is None:
        init_database()
    session = _session_factory()
    try:
        yield session
    finally:
        session.close()


# Redis and Queue
def get_redis_url() -> str:
    """Get Redis URL from environment."""
    return os.environ.get("REDIS_URL", "redis://redis:6379/0")


def get_redis() -> Redis:
    """Get Redis connection."""
    return Redis.from_url(get_redis_url())


def get_queue() -> Queue:
    """Get RQ queue."""
    return Queue("default", connection=get_redis())
