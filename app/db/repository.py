from pathlib import Path
from typing import Optional, List, Dict, Any

from sqlalchemy import select, or_, desc, delete

from .models import Base, Save
from .session import get_engine, get_session


def init_db(db_path: Path) -> None:
    """Ensure the database exists and the schema is created.

    Alembic should manage migrations, but creating tables here makes
    first-run/local dev smoother if migrations haven't been applied yet.
    """
    engine = get_engine(db_path)
    # Use WAL for better concurrent write performance
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
    # Schema management is exclusively done via Alembic. Do not create or
    # mutate tables here. Ensure `alembic upgrade head` has been run.
    return


def insert_save_result(
    db_path: Path,
    item_id: str,
    url: str,
    success: bool,
    exit_code: Optional[int],
    saved_path: Optional[str],
) -> int:
    init_db(db_path)
    with get_session(db_path) as session:
        row = Save(
            item_id=item_id,
            user_id=item_id,  # keep legacy column populated too
            url=url,
            success=bool(success),
            exit_code=exit_code,
            saved_path=saved_path,
            status=("success" if success else "failed"),
        )
        session.add(row)
        session.flush()  # populate PK
        return int(row.rowid)


def insert_pending_save(
    db_path: Path,
    item_id: str,
    url: str,
    task_id: str,
    name: Optional[str] = None,
) -> int:
    """Insert a pending save row for async processing and return rowid."""
    init_db(db_path)
    with get_session(db_path) as session:
        row = Save(
            item_id=item_id,
            user_id=item_id,  # keep legacy column populated too
            url=url,
            success=False,
            status="pending",
            task_id=task_id,
            name=name,
        )
        session.add(row)
        session.flush()
        return int(row.rowid)


def finalize_save_result(
    db_path: Path,
    rowid: int,
    success: bool,
    exit_code: Optional[int],
    saved_path: Optional[str],
) -> None:
    """Update an existing row with final result and status."""
    init_db(db_path)
    with get_session(db_path) as session:
        row: Save | None = session.get(Save, rowid)
        if row is None:
            return
        row.success = bool(success)
        row.exit_code = exit_code
        row.saved_path = saved_path
        row.status = "success" if success else "failed"


def get_task_rows(db_path: Path, task_id: str) -> List[Dict[str, Any]]:
    init_db(db_path)
    with get_session(db_path) as session:
        stmt = select(Save).where(Save.task_id == task_id).order_by(Save.rowid.asc())
        rows = session.execute(stmt).scalars().all()
        out: List[Dict[str, Any]] = []
        for r in rows:
            created_val = getattr(r, "created_at", None)
            created_at = created_val.isoformat() if hasattr(created_val, "isoformat") else created_val
            out.append(
                {
                    "rowid": r.rowid,
                    "item_id": r.item_id,
                    "user_id": r.user_id,
                    "url": r.url,
                    "success": 1 if r.success else 0,
                    "exit_code": r.exit_code,
                    "saved_path": r.saved_path,
                    "created_at": created_at,
                    "status": r.status,
                    "task_id": r.task_id,
                    "name": r.name,
                }
            )
        return out


def find_existing_success_save(
    db_path: Path, *, item_id: str, url: str
) -> Optional[Save]:
    """Return the most recent successful save row matching item_id or url.

    Looks for any row where success == 1 and (item_id == item_id OR url == url),
    ordering by created_at/rowid descending to get the latest.
    """
    init_db(db_path)
    with get_session(db_path) as session:
        stmt = (
            select(Save)
            .where(or_(Save.item_id == item_id, Save.url == url), Save.success == True)  # noqa: E712
            .order_by(desc(Save.created_at), desc(Save.rowid))
            .limit(1)
        )
        row = session.execute(stmt).scalars().first()
        return row


def is_already_saved_success(db_path: Path, *, item_id: str, url: str) -> bool:
    """Convenience predicate to check for existing successful save."""
    return find_existing_success_save(db_path, item_id=item_id, url=url) is not None


def get_save_by_rowid(db_path: Path, rowid: int) -> Optional[Save]:
    init_db(db_path)
    with get_session(db_path) as session:
        return session.get(Save, rowid)


def get_saves_by_item_id(db_path: Path, item_id: str) -> List[Save]:
    init_db(db_path)
    with get_session(db_path) as session:
        stmt = select(Save).where(Save.item_id == item_id)
        return list(session.execute(stmt).scalars().all())


def get_saves_by_url(db_path: Path, url: str) -> List[Save]:
    init_db(db_path)
    with get_session(db_path) as session:
        stmt = select(Save).where(Save.url == url)
        return list(session.execute(stmt).scalars().all())


def delete_saves_by_rowids(db_path: Path, rowids: List[int]) -> int:
    """Delete saves with the given rowids. Returns number of rows deleted."""
    if not rowids:
        return 0
    init_db(db_path)
    with get_session(db_path) as session:
        stmt = delete(Save).where(Save.rowid.in_(rowids))
        result = session.execute(stmt)
        # SQLAlchemy 2.0 returns rows affected via rowcount
        return int(result.rowcount or 0)


def list_saves(db_path: Path, limit: int = 200, offset: int = 0) -> List[Save]:
    """Return latest saves limited and offset for pagination."""
    init_db(db_path)
    with get_session(db_path) as session:
        stmt = (
            select(Save)
            .order_by(desc(Save.created_at), desc(Save.rowid))
            .limit(int(max(1, limit)))
            .offset(int(max(0, offset)))
        )
        rows = session.execute(stmt).scalars().all()
        return list(rows)
