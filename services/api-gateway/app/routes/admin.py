"""
Admin API routes.

Provides administrative endpoints for managing archives and system status.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.orm import Session
from sqlalchemy import func

from shared.db import (
    ArchivedUrl,
    ArchiveArtifact,
    ArticleSummary,
    UrlMetadata,
)
from shared.models import DeleteResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models


class RequeueRequest(BaseModel):
    """Request model for requeueing artifacts."""

    artifact_ids: Optional[List[int]] = Field(
        default=None, description="Specific artifact IDs to requeue."
    )
    status: Optional[Literal["failed", "pending"]] = Field(
        default=None, description="Filter artifacts by status when requeueing."
    )
    include_all: bool = Field(
        default=False, description="Requeue all artifacts matching the provided status."
    )


class RequeueResponse(BaseModel):
    """Response model for requeue operation."""

    requeued_count: int
    task_ids: List[str]


class SummarizeRequest(BaseModel):
    """Request model for summarization."""

    rowid: Optional[int] = Field(None, description="Artifact row ID")
    item_id: Optional[str] = Field(None, description="Article item_id")
    url: Optional[str] = Field(None, description="Article URL")


class SummarizeResponse(BaseModel):
    """Response model for summarization."""

    ok: bool
    archived_url_id: Optional[int] = None
    summary_created: bool = False
    task_id: Optional[str] = None


class SavesListItem(BaseModel):
    """Single item in saves list."""

    rowid: int
    item_id: str
    url: str
    name: Optional[str]
    status: str
    success: bool
    archiver: Optional[str]
    exit_code: Optional[int]
    saved_path: Optional[str]
    size_bytes: Optional[int]
    created_at: Optional[str]


def get_db():
    """Database session dependency."""
    from shared.db import get_session

    with get_session() as session:
        yield session


@router.get("/stats")
async def get_system_stats(db: Session = Depends(get_db)):
    """
    Get system statistics.

    Returns counts of archived URLs, artifacts, and summaries.
    """
    url_count = db.query(func.count(ArchivedUrl.id)).scalar()
    artifact_count = db.query(func.count(ArchiveArtifact.id)).scalar()
    success_count = (
        db.query(func.count(ArchiveArtifact.id))
        .filter(ArchiveArtifact.success == True)
        .scalar()
    )
    summary_count = db.query(func.count(ArticleSummary.id)).scalar()

    # Size stats
    total_size = (
        db.query(func.sum(ArchiveArtifact.size_bytes))
        .filter(ArchiveArtifact.size_bytes.isnot(None))
        .scalar()
    ) or 0

    # Artifact counts by archiver
    archiver_stats = (
        db.query(
            ArchiveArtifact.archiver,
            func.count(ArchiveArtifact.id).label("total"),
            func.sum(func.cast(ArchiveArtifact.success, Integer)).label("success"),
        )
        .group_by(ArchiveArtifact.archiver)
        .all()
    )

    return {
        "archived_urls": url_count,
        "total_artifacts": artifact_count,
        "successful_artifacts": success_count,
        "summaries": summary_count,
        "total_size_bytes": total_size,
        "archivers": {
            stat.archiver: {
                "total": stat.total,
                "success": stat.success or 0,
            }
            for stat in archiver_stats
        },
    }


@router.delete("/archive/{item_id}", response_model=DeleteResponse)
async def delete_archive(
    item_id: str,
    delete_files: bool = Query(False, description="Also delete local files"),
    db: Session = Depends(get_db),
):
    """
    Delete an archived URL and its artifacts.

    Optionally deletes local files as well.
    """
    logger.info("Delete archive request", extra={"item_id": item_id})

    # Find archived URL
    archived_url = (
        db.query(ArchivedUrl).filter(ArchivedUrl.item_id == item_id).first()
    )

    if not archived_url:
        raise HTTPException(status_code=404, detail="Archive not found")

    # Get artifacts
    artifacts = (
        db.query(ArchiveArtifact)
        .filter(ArchiveArtifact.archived_url_id == archived_url.id)
        .all()
    )

    deleted_rowids = [a.id for a in artifacts]
    removed_files = []
    errors = []

    # Delete local files if requested
    if delete_files:
        import os
        from pathlib import Path
        from shared.config import get_settings

        settings = get_settings()

        for artifact in artifacts:
            if artifact.saved_path:
                try:
                    path = Path(artifact.saved_path)
                    if path.exists():
                        # Delete the archiver directory
                        archiver_dir = path.parent
                        if archiver_dir.exists():
                            import shutil

                            shutil.rmtree(archiver_dir)
                            removed_files.append(str(archiver_dir))
                except Exception as e:
                    errors.append(f"Failed to delete {artifact.saved_path}: {e}")

        # Try to delete the item directory if empty
        try:
            from shared.utils import sanitize_filename

            item_dir = settings.data_dir / sanitize_filename(item_id)
            if item_dir.exists() and not any(item_dir.iterdir()):
                item_dir.rmdir()
                removed_files.append(str(item_dir))
        except Exception as e:
            errors.append(f"Failed to delete item directory: {e}")

    # Delete database records
    for artifact in artifacts:
        db.delete(artifact)

    # Delete summaries
    db.query(ArticleSummary).filter(
        ArticleSummary.archived_url_id == archived_url.id
    ).delete()

    # Delete URL record
    db.delete(archived_url)
    db.commit()

    return DeleteResponse(
        ok=True,
        deleted_count=len(artifacts),
        deleted_rowids=deleted_rowids,
        removed_files=removed_files,
        errors=errors,
    )


@router.post("/retry-failed")
async def retry_failed_artifacts(
    archivers: Optional[List[str]] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    Retry failed archive artifacts.

    Re-queues failed artifacts for processing.
    """
    from shared.celery_config import celery_app
    from shared.utils import rewrite_paywalled_url
    import uuid

    # Find failed artifacts
    query = (
        db.query(ArchiveArtifact, ArchivedUrl)
        .join(ArchivedUrl)
        .filter(
            ArchiveArtifact.success == False,
            ArchiveArtifact.status == "failed",
        )
    )

    if archivers:
        query = query.filter(ArchiveArtifact.archiver.in_(archivers))

    query = query.limit(limit)
    failed_artifacts = query.all()

    if not failed_artifacts:
        return {"message": "No failed artifacts to retry", "count": 0}

    # Create new task ID
    task_id = uuid.uuid4().hex

    tasks = []
    for artifact, archived_url in failed_artifacts:
        # Update artifact status
        artifact.status = "pending"
        artifact.task_id = task_id

        fetch_url = rewrite_paywalled_url(archived_url.url)

        task_name = f"services.archive_worker.tasks.archive_{artifact.archiver}"
        tasks.append(
            celery_app.signature(
                task_name,
                kwargs={
                    "item_id": archived_url.item_id,
                    "url": fetch_url,
                    "archived_url_id": archived_url.id,
                    "artifact_id": artifact.id,
                },
            )
        )

    db.commit()

    # Dispatch tasks
    from celery import group

    if tasks:
        group(tasks).apply_async()

    logger.info(
        "Retry failed artifacts",
        extra={"task_id": task_id, "count": len(tasks)},
    )

    return {
        "message": f"Retrying {len(tasks)} failed artifact(s)",
        "task_id": task_id,
        "count": len(tasks),
    }


@router.post("/cleanup-local")
async def cleanup_local_files(
    older_than_hours: int = Query(24, ge=1),
    dry_run: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    Clean up local files for artifacts uploaded to cloud storage.

    Only cleans up files where all storage uploads succeeded.
    """
    from datetime import datetime, timedelta
    from pathlib import Path

    cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)

    # Find artifacts eligible for cleanup
    artifacts = (
        db.query(ArchiveArtifact)
        .filter(
            ArchiveArtifact.success == True,
            ArchiveArtifact.all_uploads_succeeded == True,
            ArchiveArtifact.local_file_deleted == False,
            ArchiveArtifact.created_at < cutoff,
            ArchiveArtifact.saved_path.isnot(None),
        )
        .all()
    )

    files_to_delete = []
    for artifact in artifacts:
        path = Path(artifact.saved_path)
        if path.exists():
            files_to_delete.append({
                "artifact_id": artifact.id,
                "path": str(path),
                "size_bytes": artifact.size_bytes,
            })

    if dry_run:
        return {
            "dry_run": True,
            "files_to_delete": len(files_to_delete),
            "files": files_to_delete[:20],  # Show first 20
        }

    # Actually delete files
    deleted = []
    errors = []

    for file_info in files_to_delete:
        try:
            path = Path(file_info["path"])
            if path.exists():
                path.unlink()
                deleted.append(file_info["path"])

                # Update artifact
                artifact = db.query(ArchiveArtifact).get(file_info["artifact_id"])
                if artifact:
                    artifact.local_file_deleted = True
                    artifact.local_file_deleted_at = datetime.utcnow()
        except Exception as e:
            errors.append({"path": file_info["path"], "error": str(e)})

    db.commit()

    return {
        "deleted": len(deleted),
        "errors": len(errors),
        "error_details": errors[:10],  # Show first 10 errors
    }


@router.get("/pending")
async def list_pending_artifacts(
    archiver: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    List pending artifacts.

    Returns artifacts that are still pending processing.
    """
    query = (
        db.query(ArchiveArtifact, ArchivedUrl)
        .join(ArchivedUrl)
        .filter(ArchiveArtifact.status == "pending")
    )

    if archiver:
        query = query.filter(ArchiveArtifact.archiver == archiver)

    query = query.limit(limit)
    results = query.all()

    return {
        "count": len(results),
        "artifacts": [
            {
                "artifact_id": a.id,
                "archiver": a.archiver,
                "item_id": u.item_id,
                "url": u.url,
                "task_id": a.task_id,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a, u in results
        ],
    }


# Import Integer for SQLAlchemy cast
from sqlalchemy import Integer


# Available archivers
AVAILABLE_ARCHIVERS = ["singlefile", "monolith", "readability", "pdf", "screenshot"]


@router.get("/saves", response_model=List[Dict[str, Any]])
async def list_saves(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Filter by status"),
    archiver: Optional[str] = Query(None, description="Filter by archiver"),
    db: Session = Depends(get_db),
):
    """
    List all saves with pagination.

    Returns a list of archived artifacts with metadata.
    """
    query = (
        db.query(ArchiveArtifact, ArchivedUrl)
        .join(ArchivedUrl)
        .order_by(ArchiveArtifact.created_at.desc())
    )

    if status:
        query = query.filter(ArchiveArtifact.status == status)

    if archiver:
        query = query.filter(ArchiveArtifact.archiver == archiver)

    query = query.offset(offset).limit(limit)
    results = query.all()

    out: List[Dict[str, Any]] = []
    for artifact, archived_url in results:
        created_at = (
            artifact.created_at.isoformat() if artifact.created_at else None
        )
        out.append({
            "rowid": artifact.id,
            "item_id": archived_url.item_id,
            "url": archived_url.url,
            "name": archived_url.name,
            "status": artifact.status,
            "success": artifact.success or False,
            "archiver": artifact.archiver,
            "exit_code": artifact.exit_code,
            "saved_path": artifact.saved_path,
            "size_bytes": artifact.size_bytes,
            "gcs_path": artifact.gcs_path,
            "created_at": created_at,
        })

    return out


@router.get("/archivers", response_model=List[str])
async def list_archivers():
    """
    List available archivers.

    Returns the names of all configured archiver types.
    """
    return sorted(AVAILABLE_ARCHIVERS)


@router.post("/saves/requeue", response_model=RequeueResponse)
async def requeue_saves(
    payload: RequeueRequest,
    db: Session = Depends(get_db),
):
    """
    Requeue artifacts for processing.

    Re-queues failed or pending artifacts based on the provided criteria.
    """
    import uuid

    from shared.celery_config import celery_app
    from shared.utils import rewrite_paywalled_url

    logger.info(f"Requeue requested | payload={payload.model_dump()}")

    artifacts_to_requeue = []
    statuses_filter = set()

    if payload.status:
        statuses_filter.add(payload.status.lower())

    pull_all = payload.include_all or (
        payload.status is not None and not payload.artifact_ids
    )

    # Fetch artifacts by ID
    if payload.artifact_ids:
        fetched = (
            db.query(ArchiveArtifact, ArchivedUrl)
            .join(ArchivedUrl)
            .filter(ArchiveArtifact.id.in_(payload.artifact_ids))
            .all()
        )
        logger.info(
            f"Loaded artifacts by id | requested={len(payload.artifact_ids)} found={len(fetched)}"
        )
        artifacts_to_requeue.extend(fetched)

    # Fetch artifacts by status
    if pull_all and payload.status:
        fetched = (
            db.query(ArchiveArtifact, ArchivedUrl)
            .join(ArchivedUrl)
            .filter(ArchiveArtifact.status == payload.status)
            .all()
        )
        logger.info(
            f"Loaded artifacts by status | status={payload.status} count={len(fetched)}"
        )
        artifacts_to_requeue.extend(fetched)

    if not payload.artifact_ids and not pull_all:
        raise HTTPException(
            status_code=400,
            detail="Provide artifact_ids or set include_all with a status to requeue.",
        )

    # Deduplicate and filter
    seen: set[int] = set()
    filtered = []

    for artifact, archived_url in artifacts_to_requeue:
        if artifact.id in seen:
            continue
        seen.add(artifact.id)

        status = (artifact.status or "").lower()
        if status not in {"failed", "pending"}:
            logger.info(
                f"Skipping artifact due to status | artifact_id={artifact.id} status={status}"
            )
            continue

        if statuses_filter and status not in statuses_filter:
            continue

        filtered.append((artifact, archived_url))
        logger.info(f"Artifact ready for requeue | artifact_id={artifact.id} status={status}")

    if not filtered:
        logger.info("No artifacts matched filters; nothing to requeue")
        return RequeueResponse(requeued_count=0, task_ids=[])

    # Create new task ID
    task_id = uuid.uuid4().hex
    task_ids = [task_id]
    tasks = []

    for artifact, archived_url in filtered:
        # Update artifact status
        artifact.status = "pending"
        artifact.task_id = task_id

        fetch_url = rewrite_paywalled_url(archived_url.url)

        task_name = f"services.archive_worker.tasks.archive_{artifact.archiver}"
        tasks.append(
            celery_app.signature(
                task_name,
                kwargs={
                    "item_id": archived_url.item_id,
                    "url": fetch_url,
                    "archived_url_id": archived_url.id,
                    "artifact_id": artifact.id,
                },
            )
        )

    db.commit()

    # Dispatch tasks
    from celery import group

    if tasks:
        group(tasks).apply_async()

    logger.info(f"Requeue completed | requeued={len(filtered)} task_id={task_id}")

    return RequeueResponse(requeued_count=len(filtered), task_ids=task_ids)


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize_article(
    payload: SummarizeRequest,
    db: Session = Depends(get_db),
):
    """
    Manually trigger summarization for an article.

    Finds the article by rowid, item_id, or URL and queues it for summarization.
    """
    import uuid

    from shared.celery_config import celery_app
    from shared.config import get_settings

    settings = get_settings()

    if not settings.summarization.enabled:
        raise HTTPException(status_code=503, detail="Summarization is disabled")

    archived_url_id: Optional[int] = None
    item_id: Optional[str] = None

    # Find the article
    if payload.rowid is not None:
        artifact = db.query(ArchiveArtifact).filter(ArchiveArtifact.id == payload.rowid).first()
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        archived_url_id = artifact.archived_url_id

        archived_url = db.query(ArchivedUrl).filter(ArchivedUrl.id == archived_url_id).first()
        if archived_url:
            item_id = archived_url.item_id

    elif payload.item_id:
        from shared.utils import sanitize_filename

        safe_id = sanitize_filename(payload.item_id.strip())
        archived_url = db.query(ArchivedUrl).filter(ArchivedUrl.item_id == safe_id).first()
        if not archived_url:
            raise HTTPException(status_code=404, detail="Article not found")
        archived_url_id = archived_url.id
        item_id = archived_url.item_id

    elif payload.url:
        archived_url = db.query(ArchivedUrl).filter(ArchivedUrl.url == payload.url).first()
        if not archived_url:
            raise HTTPException(status_code=404, detail="Article not found")
        archived_url_id = archived_url.id
        item_id = archived_url.item_id

    else:
        raise HTTPException(
            status_code=400, detail="Provide rowid, item_id, or url"
        )

    if not archived_url_id:
        raise HTTPException(status_code=404, detail="Unable to resolve archived URL")

    # Queue summarization task
    task_id = uuid.uuid4().hex

    celery_app.send_task(
        "services.summarization_worker.tasks.summarize_article",
        kwargs={
            "item_id": item_id,
            "archived_url_id": archived_url_id,
            "force": True,
        },
        queue="summarization",
    )

    logger.info(
        "Summarization task queued",
        extra={"archived_url_id": archived_url_id, "item_id": item_id, "task_id": task_id},
    )

    return SummarizeResponse(
        ok=True,
        archived_url_id=archived_url_id,
        summary_created=False,  # It's queued, not yet created
        task_id=task_id,
    )


@router.delete("/saves/by-item/{item_id}", response_model=DeleteResponse)
async def delete_saves_by_item(
    item_id: str,
    remove_files: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    Delete all saves for a specific item_id.
    """
    from pathlib import Path
    from shared.config import get_settings
    from shared.utils import sanitize_filename

    settings = get_settings()
    safe_id = sanitize_filename(item_id.strip())

    archived_url = db.query(ArchivedUrl).filter(ArchivedUrl.item_id == safe_id).first()
    if not archived_url:
        raise HTTPException(status_code=404, detail="Article not found")

    artifacts = (
        db.query(ArchiveArtifact)
        .filter(ArchiveArtifact.archived_url_id == archived_url.id)
        .all()
    )

    rowids = [a.id for a in artifacts]
    saved_paths = [a.saved_path for a in artifacts if a.saved_path]

    # Delete artifacts
    for artifact in artifacts:
        db.delete(artifact)

    # Delete related records
    db.query(ArticleSummary).filter(ArticleSummary.archived_url_id == archived_url.id).delete()

    # Delete archived URL
    db.delete(archived_url)

    removed_files: List[str] = []
    errors: List[str] = []

    if remove_files:
        data_root = settings.data_dir

        for sp in saved_paths:
            try:
                p = Path(sp)
                if not p.exists():
                    continue
                rp = p.resolve()
                if data_root and data_root in rp.parents:
                    p.unlink()
                    removed_files.append(str(p))
                    # Prune empty parents
                    parent = p.parent
                    while parent != data_root and parent.is_dir():
                        try:
                            parent.rmdir()
                        except OSError:
                            break
                        parent = parent.parent
            except Exception as e:
                errors.append(str(e))

    db.commit()

    return DeleteResponse(
        ok=True,
        deleted_count=len(artifacts),
        deleted_rowids=rowids,
        removed_files=removed_files,
        errors=errors,
    )


@router.delete("/saves/by-url", response_model=DeleteResponse)
async def delete_saves_by_url(
    url: str = Query(..., description="URL to delete"),
    remove_files: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    Delete all saves for a specific URL.
    """
    from pathlib import Path
    from shared.config import get_settings

    settings = get_settings()

    archived_url = db.query(ArchivedUrl).filter(ArchivedUrl.url == url).first()
    if not archived_url:
        raise HTTPException(status_code=404, detail="Article not found")

    artifacts = (
        db.query(ArchiveArtifact)
        .filter(ArchiveArtifact.archived_url_id == archived_url.id)
        .all()
    )

    rowids = [a.id for a in artifacts]
    saved_paths = [a.saved_path for a in artifacts if a.saved_path]

    # Delete artifacts
    for artifact in artifacts:
        db.delete(artifact)

    # Delete related records
    db.query(ArticleSummary).filter(ArticleSummary.archived_url_id == archived_url.id).delete()

    # Delete archived URL
    db.delete(archived_url)

    removed_files: List[str] = []
    errors: List[str] = []

    if remove_files:
        data_root = settings.data_dir

        for sp in saved_paths:
            try:
                p = Path(sp)
                if not p.exists():
                    continue
                rp = p.resolve()
                if data_root and data_root in rp.parents:
                    p.unlink()
                    removed_files.append(str(p))
                    parent = p.parent
                    while parent != data_root and parent.is_dir():
                        try:
                            parent.rmdir()
                        except OSError:
                            break
                        parent = parent.parent
            except Exception as e:
                errors.append(str(e))

    db.commit()

    return DeleteResponse(
        ok=True,
        deleted_count=len(artifacts),
        deleted_rowids=rowids,
        removed_files=removed_files,
        errors=errors,
    )
