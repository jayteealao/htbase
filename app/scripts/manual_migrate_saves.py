from __future__ import annotations

"""
One-time, idempotent manual migration for the `saves` table.

This script is intended to be run if Alembic migrations didn’t apply
properly to an existing SQLite database. It makes minimal, safe changes:

- Adds missing columns: item_id, status, task_id, name
- Backfills item_id from legacy user_id when empty
- Ensures helpful indexes exist

Usage:
  - Inside container (recommended):
      python -m app.scripts.manual_migrate_saves

  - On host (venv + .env configured):
      python -m app.scripts.manual_migrate_saves --db \
          path/to/app.db

The script is idempotent and safe to re-run.
"""

import argparse
from typing import Set
from pathlib import Path

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine


def _existing_columns(conn) -> Set[str]:
    rows = conn.exec_driver_sql("PRAGMA table_info('saves')").fetchall()
    return {row[1] for row in rows}  # row[1] = column name


def _existing_indexes(conn) -> Set[str]:
    rows = conn.exec_driver_sql("PRAGMA index_list('saves')").fetchall()
    # row[1] = name for index_list pragma
    return {row[1] for row in rows}


def migrate(db_path: Path) -> None:
    print(f"[migrate] DB: {db_path}")
    engine = get_engine(db_path)
    with engine.begin() as conn:
        # Use WAL for better concurrent write performance
        conn.exec_driver_sql("PRAGMA journal_mode=WAL;")

    with engine.begin() as conn:
        # Verify table exists
        tables = {row[0] for row in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
        if "saves" not in tables:
            print("[migrate] Table 'saves' does not exist. Run Alembic initial migration first.")
            return

        cols = _existing_columns(conn)
        idxs = _existing_indexes(conn)

        # Add columns if missing (SQLite supports simple ADD COLUMN)
        if "item_id" not in cols:
            print("[migrate] Adding column: item_id")
            conn.exec_driver_sql("ALTER TABLE saves ADD COLUMN item_id VARCHAR")
        else:
            print("[migrate] Column exists: item_id")

        if "status" not in cols:
            print("[migrate] Adding column: status")
            conn.exec_driver_sql("ALTER TABLE saves ADD COLUMN status VARCHAR")
        else:
            print("[migrate] Column exists: status")

        if "task_id" not in cols:
            print("[migrate] Adding column: task_id")
            conn.exec_driver_sql("ALTER TABLE saves ADD COLUMN task_id VARCHAR")
        else:
            print("[migrate] Column exists: task_id")

        if "name" not in cols:
            print("[migrate] Adding column: name")
            conn.exec_driver_sql("ALTER TABLE saves ADD COLUMN name VARCHAR")
        else:
            print("[migrate] Column exists: name")

        # Backfills / defaults
        # Backfill item_id from user_id when item_id is NULL or empty
        try:
            print("[migrate] Backfilling item_id from user_id where missing...")
            conn.exec_driver_sql(
                "UPDATE saves SET item_id = COALESCE(NULLIF(item_id, ''), user_id) "
                "WHERE item_id IS NULL OR item_id = ''"
            )
        except Exception as e:
            print(f"[migrate] WARN: backfill item_id failed: {e}")

        # Ensure status has a value
        try:
            print("[migrate] Backfilling status to 'pending' where missing...")
            conn.exec_driver_sql(
                "UPDATE saves SET status = COALESCE(NULLIF(status, ''), 'pending') "
                "WHERE status IS NULL OR status = ''"
            )
        except Exception as e:
            print(f"[migrate] WARN: backfill status failed: {e}")

        # Indexes
        if "idx_saves_item_id_created_at" not in idxs:
            print("[migrate] Creating index idx_saves_item_id_created_at")
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS idx_saves_item_id_created_at ON saves(item_id, created_at)"
            )
        else:
            print("[migrate] Index exists: idx_saves_item_id_created_at")

        if "idx_saves_user_id_created_at" not in idxs:
            print("[migrate] Creating index idx_saves_user_id_created_at")
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS idx_saves_user_id_created_at ON saves(user_id, created_at)"
            )
        else:
            print("[migrate] Index exists: idx_saves_user_id_created_at")

    print("[migrate] Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual saves table migration")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to SQLite DB (defaults to settings.resolved_db_path)",
    )
    args = parser.parse_args()

    if args.db is None:
        settings = get_settings()
        db_path = settings.resolved_db_path
    else:
        db_path = args.db

    migrate(db_path)


if __name__ == "__main__":
    main()

