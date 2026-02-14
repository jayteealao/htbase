"""Legacy repository functions for backward compatibility.

DEPRECATED: Use the new repository classes in repositories.py instead.

This module now only re-exports 2 remaining legacy functions that haven't been
fully migrated yet. All other functions have been removed.

New code should use:
    from common.db import (
        ArchiveArtifactRepository,
        ArchivedUrlRepository,
        UrlMetadataRepository,
        etc.
    )
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from .models import ArchivedUrl, ArchiveArtifact
from .session import get_session


def _get_or_create_archived_url(
    session, *, url: str, item_id: Optional[str], name: Optional[str]
) -> ArchivedUrl:
    """Internal helper to get or create archived URL."""
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
    """Internal helper to get or create artifact."""
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
    """DEPRECATED: Use ArchiveArtifactRepository instead.

    Insert or update artifact with save result. Returns artifact ID.
    """
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


def record_http_failure(
    db_path: Path | None,
    *,
    rowid: int | None = None,
    item_id: Optional[str] = None,
    url: Optional[str] = None,
    archiver_name: Optional[str] = None,
    exit_code: int = 404,
) -> int | None:
    """DEPRECATED: Use ArchiveArtifactRepository instead.

    Mark an artifact as failed due to an HTTP error (e.g., 404).

    Either `rowid` may be provided to update an existing artifact, or
    `item_id`+`url`+`archiver_name` will be used to insert/update the
    artifact row. Returns the artifact id if available, else None.
    """
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
