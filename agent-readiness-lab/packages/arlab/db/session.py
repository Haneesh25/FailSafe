"""Database session and connection management."""

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .models import Base


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://arlab:arlab@localhost:5432/arlab"
    )


def get_engine(database_url: str | None = None):
    """Create database engine."""
    url = database_url or get_database_url()
    return create_engine(url, pool_pre_ping=True)


def get_session_factory(engine=None):
    """Create session factory."""
    if engine is None:
        engine = get_engine()
    return sessionmaker(bind=engine, expire_on_commit=False)


class DatabaseSession:
    """Database session manager."""

    def __init__(self, database_url: str | None = None):
        self.engine = get_engine(database_url)
        self.SessionFactory = get_session_factory(self.engine)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Get a database session context."""
        session = self.SessionFactory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_session(self) -> Session:
        """Get a new session (caller responsible for closing)."""
        return self.SessionFactory()


_db_session: DatabaseSession | None = None


def get_db() -> DatabaseSession:
    """Get global database session manager."""
    global _db_session
    if _db_session is None:
        _db_session = DatabaseSession()
    return _db_session


def get_session() -> Session:
    """Get a new database session."""
    return get_db().get_session()


def init_db(database_url: str | None = None):
    """Initialize database tables."""
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    return engine
