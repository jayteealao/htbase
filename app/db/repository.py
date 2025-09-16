from pathlib import Path
from typing import Optional, List, Dict, Any

from sqlalchemy import select, or_, desc, update, delete

import json
from .models import Base, ArchivedUrl, UrlMetadata, ArchiveArtifact
from .session import get_engine, get_session


def init_db(db_path: Path | None = None) -> None:
    """Schema is managed by Alembic; nothing to do here for Postgres."""
    # Keeping this function for compatibility; Postgres schema creation is handled
    # by Alembic migrations. This becomes a no-op at runtime.
    _ = get_engine(db_path)  # ensure engine is initialized
    return


def _get_or_create_archived_url(
    session, *, url: str, item_id: Optional[str], name: Optional[str]
) -> ArchivedUrl:
    row = (
        session.execute(select(ArchivedUrl).where(ArchivedUrl.url == url))
        .scalars()
        .first()
    )
    if row is None:
        row = ArchivedUrl(url=url, item_id=item_id, name=name)
        session.add(row)
        session.flush()
    else:
        # backfill item_id/name if missing
        changed = False
        if item_id and not row.item_id:
            row.item_id = item_id
            changed = True
        if name and not row.name:
            row.name = name
            changed = True
        if changed:
            session.flush()
    return row


def _get_or_create_artifact(
    session, *, archived_url_id: int, archiver: str, task_id: Optional[str] = None
) -> ArchiveArtifact:
    art = (
        session.execute(
            select(ArchiveArtifact).where(
                ArchiveArtifact.archived_url_id == archived_url_id,
                ArchiveArtifact.archiver == archiver,
            )
        )
        .scalars()
        .first()
    )
    if art is None:
        art = ArchiveArtifact(
            archived_url_id=archived_url_id,
            archiver=archiver,
            task_id=task_id,
            status="pending" if task_id else None,
        )
        session.add(art)
        session.flush()
    else:
        if task_id:
            art.task_id = task_id
            art.status = "pending"
            session.flush()
    return art


def insert_save_result(
    db_path: Path | None,
    item_id: str,
    url: str,
    success: bool,
    exit_code: Optional[int],
    saved_path: Optional[str],
    archiver_name: Optional[str] = None,
) -> int:
    init_db(db_path)
    with get_session(db_path) as session:
        archiver = archiver_name or "unknown"
        au = _get_or_create_archived_url(session, url=url, item_id=item_id, name=None)
        art = _get_or_create_artifact(session, archived_url_id=au.id, archiver=archiver)
        art.success = bool(success)
        art.exit_code = exit_code
        art.saved_path = saved_path
        art.status = "success" if success else "failed"
        session.flush()
        return int(art.id)


def insert_pending_save(
    db_path: Path | None,
    item_id: str,
    url: str,
    task_id: str,
    name: Optional[str] = None,
    archiver_name: Optional[str] = None,
) -> int:
    """Ensure an artifact row exists and mark it pending; return artifact id."""
    init_db(db_path)
    with get_session(db_path) as session:
        au = _get_or_create_archived_url(session, url=url, item_id=item_id, name=name)
        art = _get_or_create_artifact(
            session,
            archived_url_id=au.id,
            archiver=archiver_name or "unknown",
            task_id=task_id,
        )
        return int(art.id)


def finalize_save_result(
    db_path: Path | None,
    rowid: int,
    success: bool,
    exit_code: Optional[int],
    saved_path: Optional[str],
) -> None:
    """Update an existing artifact row with final result and status."""
    init_db(db_path)
    with get_session(db_path) as session:
        art: ArchiveArtifact | None = session.get(ArchiveArtifact, rowid)
        if art is None:
            return
        art.success = bool(success)
        art.exit_code = exit_code
        art.saved_path = saved_path
        art.status = "success" if success else "failed"


def record_http_failure(
    db_path: Path | None,
    *,
    rowid: int | None = None,
    item_id: Optional[str] = None,
    url: Optional[str] = None,
    archiver_name: Optional[str] = None,
    exit_code: int = 404,
) -> int | None:
    """Mark an artifact as failed due to an HTTP error (e.g., 404).

    Either `rowid` may be provided to update an existing artifact, or
    `item_id`+`url`+`archiver_name` will be used to insert/update the
    artifact row. Returns the artifact id if available, else None.
    """
    init_db(db_path)
    with get_session(db_path) as session:
        if rowid is not None:
            art: ArchiveArtifact | None = session.get(ArchiveArtifact, int(rowid))
            if art is None:
                return None
        else:
            if not url:
                return None
            au = _get_or_create_archived_url(
                session, url=url, item_id=item_id, name=None
            )
            art = _get_or_create_artifact(
                session, archived_url_id=au.id, archiver=archiver_name or "unknown"
            )

        art.success = False
        art.exit_code = int(exit_code)
        art.saved_path = None
        art.status = "failed"
        session.flush()
        return int(art.id)


def insert_save_metadata(
    db_path: Path | None,
    *,
    save_rowid: int,
    data: Dict[str, Any],
) -> int:
    """Insert readability-derived metadata associated with an archived URL; returns metadata id.

    The input `save_rowid` refers to the artifact id (for compatibility). We
    resolve the parent archived_url_id and upsert metadata for that URL.
    """
    init_db(db_path)
    with get_session(db_path) as session:
        art: ArchiveArtifact | None = session.get(ArchiveArtifact, save_rowid)
        if art is None:
            raise ValueError("artifact not found")
        au_id = art.archived_url_id

        row = (
            session.execute(
                select(UrlMetadata).where(UrlMetadata.archived_url_id == au_id)
            )
            .scalars()
            .first()
        )
        payload = dict(
            archived_url_id=au_id,
            source_url=data.get("source_url"),
            title=data.get("title"),
            byline=data.get("byline"),
            site_name=data.get("site_name"),
            description=data.get("description"),
            published=data.get("published"),
            language=data.get("language"),
            canonical_url=data.get("canonical_url"),
            top_image=data.get("top_image"),
            favicon=data.get("favicon"),
            keywords=json.dumps(data.get("keywords") or [], ensure_ascii=False),
            text=data.get("text"),
            word_count=int(data.get("word_count"))
            if data.get("word_count") is not None
            else None,
            reading_time_minutes=float(data.get("reading_time_minutes"))
            if data.get("reading_time_minutes") is not None
            else None,
        )
        if row is None:
            row = UrlMetadata(**payload)  # type: ignore[arg-type]
            session.add(row)
            session.flush()
        else:
            for k, v in payload.items():
                setattr(row, k, v)
            session.flush()
        return int(row.id)


def get_task_rows(db_path: Path | None, task_id: str) -> List[Dict[str, Any]]:
    init_db(db_path)
    with get_session(db_path) as session:
        stmt = (
            select(ArchiveArtifact, ArchivedUrl)
            .join(ArchivedUrl, ArchiveArtifact.archived_url_id == ArchivedUrl.id)
            .where(ArchiveArtifact.task_id == task_id)
            .order_by(ArchiveArtifact.id.asc())
        )
        rows = session.execute(stmt).all()
        out: List[Dict[str, Any]] = []
        for art, au in rows:
            created_val = getattr(art, "created_at", None)
            created_at = (
                created_val.isoformat()
                if hasattr(created_val, "isoformat")
                else created_val
            )
            out.append(
                {
                    "rowid": art.id,
                    "item_id": au.item_id,
                    "user_id": None,
                    "url": au.url,
                    "success": 1 if art.success else 0,
                    "exit_code": art.exit_code,
                    "saved_path": art.saved_path,
                    "created_at": created_at,
                    "status": art.status,
                    "task_id": art.task_id,
                    "name": au.name,
                }
            )
        return out


def find_existing_success_save(
    db_path: Path | None, *, item_id: str, url: str, archiver: str
) -> Optional[ArchiveArtifact]:
    """Return the successful artifact row for a specific archiver and URL."""
    init_db(db_path)
    with get_session(db_path) as session:
        au = (
            session.execute(
                select(ArchivedUrl).where(
                    or_(ArchivedUrl.url == url, ArchivedUrl.item_id == item_id)
                )
            )
            .scalars()
            .first()
        )
        if not au:
            return None
        art = (
            session.execute(
                select(ArchiveArtifact)
                .where(
                    ArchiveArtifact.archived_url_id == au.id,
                    ArchiveArtifact.archiver == archiver,
                    ArchiveArtifact.success == True,  # noqa: E712
                )
                .limit(1)
            )
            .scalars()
            .first()
        )
        return art


def is_already_saved_success(
    db_path: Path | None, *, item_id: str, url: str, archiver: str
) -> bool:
    return (
        find_existing_success_save(db_path, item_id=item_id, url=url, archiver=archiver)
        is not None
    )


def get_save_by_rowid(db_path: Path | None, rowid: int) -> Optional[ArchiveArtifact]:
    init_db(db_path)
    with get_session(db_path) as session:
        return session.get(ArchiveArtifact, rowid)


def get_saves_by_item_id(db_path: Path | None, item_id: str) -> List[ArchiveArtifact]:
    init_db(db_path)
    with get_session(db_path) as session:
        stmt = (
            select(ArchiveArtifact)
            .join(ArchivedUrl, ArchiveArtifact.archived_url_id == ArchivedUrl.id)
            .where(ArchivedUrl.item_id == item_id)
        )
        return list(session.execute(stmt).scalars().all())


def get_saves_by_url(db_path: Path | None, url: str) -> List[ArchiveArtifact]:
    init_db(db_path)
    with get_session(db_path) as session:
        stmt = (
            select(ArchiveArtifact)
            .join(ArchivedUrl, ArchiveArtifact.archived_url_id == ArchivedUrl.id)
            .where(ArchivedUrl.url == url)
        )
        return list(session.execute(stmt).scalars().all())


def delete_saves_by_rowids(db_path: Path | None, rowids: List[int]) -> int:
    """Delete saves with the given rowids. Returns number of rows deleted."""
    if not rowids:
        return 0
    init_db(db_path)
    with get_session(db_path) as session:
        stmt = delete(ArchiveArtifact).where(ArchiveArtifact.id.in_(rowids))
        result = session.execute(stmt)
        return int(result.rowcount or 0)


def list_saves(
    db_path: Path | None, limit: int = 200, offset: int = 0
) -> List[tuple[ArchiveArtifact, ArchivedUrl]]:
    """Return latest artifact rows with their URL anchor for pagination."""
    init_db(db_path)
    with get_session(db_path) as session:
        stmt = (
            select(ArchiveArtifact, ArchivedUrl)
            .join(ArchivedUrl, ArchiveArtifact.archived_url_id == ArchivedUrl.id)
            .order_by(desc(ArchiveArtifact.created_at), desc(ArchiveArtifact.id))
            .limit(int(max(1, limit)))
            .offset(int(max(0, offset)))
        )
        return list(session.execute(stmt).all())
