from pathlib import Path
from typing import Optional, List, Dict, Any, Sequence

from sqlalchemy import select, or_, desc, update, delete

import json
from .models import (
    Base,
    ArchivedUrl,
    UrlMetadata,
    ArchiveArtifact,
    ArticleSummary,
    ArticleEntity,
    ArticleTag,
)
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


def get_archived_url_by_id(
    db_path: Path | None, archived_url_id: int
) -> Optional[ArchivedUrl]:
    init_db(db_path)
    with get_session(db_path) as session:
        return session.get(ArchivedUrl, archived_url_id)


def get_metadata_for_archived_url(
    db_path: Path | None, archived_url_id: int
) -> Optional[UrlMetadata]:
    init_db(db_path)
    with get_session(db_path) as session:
        stmt = select(UrlMetadata).where(UrlMetadata.archived_url_id == archived_url_id)
        return session.execute(stmt).scalars().first()


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


def upsert_article_summary(
    db_path: Path | None,
    *,
    archived_url_id: int,
    summary_type: str,
    summary_text: str,
    bullet_points: Optional[List[Any]] = None,
    model_name: Optional[str] = None,
) -> int:
    """Create or update a summary row for an archived URL.

    Returns the summary row id."""
    normalized_type = (summary_type or "default").strip() or "default"
    init_db(db_path)
    with get_session(db_path) as session:
        summary = (
            session.execute(
                select(ArticleSummary).where(
                    ArticleSummary.archived_url_id == archived_url_id,
                    ArticleSummary.summary_type == normalized_type,
                )
            )
            .scalars()
            .first()
        )
        if summary is None:
            summary = ArticleSummary(
                archived_url_id=archived_url_id,
                summary_type=normalized_type,
                summary_text=summary_text,
                bullet_points=bullet_points,
                model_name=model_name,
            )
            session.add(summary)
        else:
            summary.summary_text = summary_text
            summary.bullet_points = bullet_points
            summary.model_name = model_name
        session.flush()
        return int(summary.id)


def get_article_summary(
    db_path: Path | None,
    *,
    archived_url_id: int,
    summary_type: str = "default",
) -> Optional[ArticleSummary]:
    init_db(db_path)
    normalized_type = (summary_type or "default").strip() or "default"
    with get_session(db_path) as session:
        return (
            session.execute(
                select(ArticleSummary).where(
                    ArticleSummary.archived_url_id == archived_url_id,
                    ArticleSummary.summary_type == normalized_type,
                )
            )
            .scalars()
            .first()
        )


def list_article_summaries(
    db_path: Path | None,
    *,
    archived_url_id: int,
) -> List[ArticleSummary]:
    init_db(db_path)
    with get_session(db_path) as session:
        stmt = (
            select(ArticleSummary)
            .where(ArticleSummary.archived_url_id == archived_url_id)
            .order_by(ArticleSummary.summary_type.asc())
        )
        return list(session.execute(stmt).scalars().all())



def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None



def replace_article_tags(
    db_path: Path | None,
    *,
    archived_url_id: int,
    tags: Sequence[Dict[str, Any]],
) -> int:
    """Replace all tag rows for an archived URL; returns number of rows inserted."""
    init_db(db_path)
    normalized: list[ArticleTag] = []
    seen: set[tuple[str, str]] = set()
    for payload in tags:
        if not payload:
            continue
        raw_tag = str(payload.get("tag", "")).strip()
        if not raw_tag:
            continue
        raw_source = str(payload.get("source", "llm")).strip() or "llm"
        key = (raw_tag.lower(), raw_source.lower())
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            ArticleTag(
                archived_url_id=archived_url_id,
                tag=raw_tag,
                source=raw_source,
                confidence=_coerce_float(payload.get("confidence")),
                reason=payload.get("reason"),
            )
        )
    with get_session(db_path) as session:
        session.execute(
            delete(ArticleTag).where(ArticleTag.archived_url_id == archived_url_id)
        )
        for obj in normalized:
            session.add(obj)
        session.flush()
        return len(normalized)



def list_article_tags(
    db_path: Path | None,
    *,
    archived_url_id: int,
) -> List[ArticleTag]:
    init_db(db_path)
    with get_session(db_path) as session:
        stmt = (
            select(ArticleTag)
            .where(ArticleTag.archived_url_id == archived_url_id)
            .order_by(ArticleTag.source.asc(), ArticleTag.tag.asc())
        )
        return list(session.execute(stmt).scalars().all())



def replace_article_entities(
    db_path: Path | None,
    *,
    archived_url_id: int,
    entities: Sequence[Dict[str, Any]],
) -> int:
    """Replace entity rows for an archived URL; returns number of rows inserted."""
    init_db(db_path)
    normalized: list[ArticleEntity] = []
    seen: set[tuple[str, Optional[str]]] = set()
    for payload in entities:
        if not payload:
            continue
        raw_entity = str(payload.get("entity", "")).strip()
        if not raw_entity:
            continue
        raw_type_value = payload.get("entity_type")
        raw_type = str(raw_type_value).strip() if raw_type_value else None
        key = (raw_entity.lower(), raw_type.lower() if raw_type else None)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            ArticleEntity(
                archived_url_id=archived_url_id,
                entity=raw_entity,
                entity_type=raw_type,
                alias=(
                    str(payload.get("alias", "")).strip() or None
                ),
                reason=payload.get("reason"),
                confidence=_coerce_float(payload.get("confidence")),
                validated=bool(payload.get("validated", True)),
            )
        )
    with get_session(db_path) as session:
        session.execute(
            delete(ArticleEntity).where(ArticleEntity.archived_url_id == archived_url_id)
        )
        for obj in normalized:
            session.add(obj)
        session.flush()
        return len(normalized)



def list_article_entities(
    db_path: Path | None,
    *,
    archived_url_id: int,
) -> List[ArticleEntity]:
    init_db(db_path)
    with get_session(db_path) as session:
        stmt = (
            select(ArticleEntity)
            .where(ArticleEntity.archived_url_id == archived_url_id)
            .order_by(ArticleEntity.entity_type.asc().nullsfirst(), ArticleEntity.entity.asc())
        )
        return list(session.execute(stmt).scalars().all())
