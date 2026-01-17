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

from sqlalchemy import create_engine, text
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

    Raises:
        ValueError: If environment variables have invalid values
    """
    # Use DATABASE_URL if provided, otherwise build from components
    url = os.getenv("DATABASE_URL", get_database_url())

    # Parse pool settings from environment with validation
    try:
        pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
    except ValueError as e:
        raise ValueError(
            f"Invalid DB_POOL_SIZE environment variable: '{os.getenv('DB_POOL_SIZE')}'. "
            f"Must be an integer. Example: DB_POOL_SIZE=5"
        ) from e

    try:
        max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    except ValueError as e:
        raise ValueError(
            f"Invalid DB_MAX_OVERFLOW environment variable: '{os.getenv('DB_MAX_OVERFLOW')}'. "
            f"Must be an integer. Example: DB_MAX_OVERFLOW=10"
        ) from e

    try:
        pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    except ValueError as e:
        raise ValueError(
            f"Invalid DB_POOL_TIMEOUT environment variable: '{os.getenv('DB_POOL_TIMEOUT')}'. "
            f"Must be an integer. Example: DB_POOL_TIMEOUT=30"
        ) from e

    # Validate ranges
    if pool_size < 1:
        raise ValueError(f"DB_POOL_SIZE must be >= 1, got: {pool_size}")
    if max_overflow < 0:
        raise ValueError(f"DB_MAX_OVERFLOW must be >= 0, got: {max_overflow}")
    if pool_timeout < 1:
        raise ValueError(f"DB_POOL_TIMEOUT must be >= 1, got: {pool_timeout}")

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

    ⚠️ IMPORTANT: This context manager AUTO-COMMITS on successful exit.

    Behavior:
    - On success (no exception): Automatically commits the transaction
    - On exception: Automatically rolls back the transaction
    - Always: Closes the session in finally block

    Best Practice:
    - For single operations: Auto-commit is convenient
    - For multi-step transactions: Consider explicit session.commit() for clarity
    - For complex transactions: Use session.begin_nested() for savepoints

    Note: Many routes explicitly call db.commit() which is redundant but harmless
    (becomes a no-op if transaction already committed by context manager).

    Yields:
        SQLAlchemy Session instance

    Usage:
        # Simple usage (auto-commit on exit)
        with get_session() as session:
            session.add(model)  # Committed automatically

        # Explicit commit (redundant but clear)
        with get_session() as session:
            session.add(model1)
            session.add(model2)
            session.commit()  # Explicit (no-op, already committed by context)

        # Multi-step with explicit control
        with get_session() as session:
            session.add(model1)
            session.flush()  # Write to DB but don't commit
            # Do more work...
            session.commit()  # Explicit commit point
    """
    SessionLocal = get_sessionmaker()
    session: Session = SessionLocal()
    try:
        yield session
        # Auto-commit on successful completion (no exception raised)
        session.commit()
    except Exception:
        # Auto-rollback on any exception
        session.rollback()
        raise
    finally:
        # Always close the session to return connection to pool
        session.close()


def get_session_dependency():
    """FastAPI dependency for database sessions.

    ⚠️ IMPORTANT: Auto-commits on successful completion.

    See get_session() for detailed behavior documentation.

    Usage:
        @app.get("/items")
        def get_items(session: Session = Depends(get_session_dependency)):
            return session.query(Item).all()
            # Auto-committed when function returns successfully
    """
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
        # Auto-commit on successful completion
        session.commit()
    except Exception:
        # Auto-rollback on exception
        session.rollback()
        raise
    finally:
        # Always close session
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
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
