from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings


@lru_cache(maxsize=None)
def _engine_for_url(_: str = "default") -> Engine:
    """Create a singleton Engine for the configured Postgres database.

    The input key is ignored but retained for lru_cache signature stability
    relative to previous sqlite-based code which cached by path.
    """
    settings = get_settings()
    url = settings.database.sqlalchemy_url()
    # Create engine with pool_pre_ping for better resiliency
    return create_engine(url, pool_pre_ping=True, future=True)


def get_engine(db_path: Path | None = None) -> Engine:  # db_path ignored; kept for compatibility
    return _engine_for_url()


def get_sessionmaker(db_path: Path | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(db_path), autoflush=False, autocommit=False, expire_on_commit=False, future=True)


@contextmanager
def get_session(db_path: Path | None = None) -> Iterator[Session]:
    SessionLocal = get_sessionmaker(db_path)
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
