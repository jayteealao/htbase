"""
Database session management for HTBase microservices.

Provides SQLAlchemy engine and session factory configuration
with support for connection pooling and environment-based configuration.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from shared.db.models import Base


def get_database_url() -> str:
    """Build database URL from environment variables."""
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "htbase")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "")

    # Handle Cloud SQL socket connections
    db_socket = os.getenv("DB_SOCKET")
    if db_socket:
        # Cloud SQL uses Unix socket connection
        user = quote_plus(db_user)
        pwd = quote_plus(db_password)
        return f"postgresql+psycopg://{user}:{pwd}@/{db_name}?host={db_socket}"

    user = quote_plus(db_user)
    pwd = quote_plus(db_password)
    return f"postgresql+psycopg://{user}:{pwd}@{db_host}:{db_port}/{db_name}"


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create a singleton SQLAlchemy Engine.

    Returns:
        SQLAlchemy Engine instance
    """
    url = os.getenv("DATABASE_URL", get_database_url())

    # Parse pool settings from environment
    pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        future=True,
    )


def get_sessionmaker() -> sessionmaker[Session]:
    """Get a session factory bound to the engine.

    Returns:
        SQLAlchemy sessionmaker instance
    """
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )


@contextmanager
def get_session() -> Iterator[Session]:
    """Get a database session with automatic commit/rollback.

    Yields:
        SQLAlchemy Session instance

    Usage:
        with get_session() as session:
            # Do database operations
            session.add(model)
    """
    SessionLocal = get_sessionmaker()
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session_dependency():
    """FastAPI dependency for database sessions.

    Usage:
        @app.get("/items")
        def get_items(session: Session = Depends(get_session_dependency)):
            return session.query(Item).all()
    """
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Initialize database tables.

    Creates all tables defined in the Base metadata.
    Should only be used for development/testing.
    Production should use Alembic migrations.
    """
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def check_connection() -> bool:
    """Check if database connection is working.

    Returns:
        True if connection is successful
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False
