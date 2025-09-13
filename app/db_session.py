from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


@lru_cache(maxsize=None)
def _engine_for_path(path_str: str) -> Engine:
    # Ensure parent directory exists
    Path(path_str).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{path_str}",
        connect_args={"check_same_thread": False},
        future=True,
    )


def get_engine(db_path: Path) -> Engine:
    return _engine_for_path(str(db_path))


def get_sessionmaker(db_path: Path) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(db_path), autoflush=False, autocommit=False, expire_on_commit=False, future=True)


@contextmanager
def get_session(db_path: Path) -> Iterator[Session]:
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

