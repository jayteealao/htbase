from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool


# Ensure project root is on sys.path so we can import app.*
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:  # Work in both local (repo root) and container (/app) layouts
    from core.config import get_settings  # type: ignore  # noqa: E402
    from db.models import Base  # type: ignore  # noqa: E402
except Exception:  # pragma: no cover
    from app.core.config import get_settings  # type: ignore  # noqa: E402
    from app.db.models import Base  # type: ignore  # noqa: E402


config = context.config
target_metadata = Base.metadata

def get_url() -> str:
    settings = get_settings()
    return settings.database_url

def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = context.config.get_section(context.config.config_ini_section) or {}
    url = get_url()

    connectable = create_engine(url, poolclass=pool.NullPool, future=True)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
