"""
Admin API routes.

Provides administrative endpoints for managing archives and system status.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from shared.db import (
    ArchivedUrl,
    ArchiveArtifact,
    ArticleSummary,
)
from shared.models import DeleteResponse

logger = logging.getLogger(__name__)

router = APIRouter()


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
