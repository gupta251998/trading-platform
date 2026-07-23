"""
Database connection and session management.

Handles PostgreSQL connection pooling, session creation, and cleanup.
"""

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://trading_user:trading_password@localhost:5432/trading_db"
)

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,  # recycle connections every hour
    echo=os.getenv("SQL_DEBUG", "false").lower() == "true",
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Session:
    """Get a new database session."""
    return SessionLocal()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Context manager for database sessions. Automatically commits on success,
    rolls back on exception.
    
    Usage:
        with session_scope() as session:
            session.add(some_object)
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Initialize database (create all tables). Called once on startup."""
    from models.base import Base
    Base.metadata.create_all(bind=engine)


def drop_db():
    """Drop all tables. Use only for testing/cleanup."""
    from models.base import Base
    Base.metadata.drop_all(bind=engine)
