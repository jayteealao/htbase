"""
Artifacts API routes - Artifact operations and maintenance endpoints.

This module provides operations for managing archive artifacts including
retry logic, cleanup, and status monitoring.

Endpoints:
- POST /artifacts/retry   - Retry failed/pending artifacts
- POST /artifacts/cleanup - Clean up local files
- GET  /artifacts/pending - List pending artifacts
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Literal

from celery import group
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shared.auth import verify_api_key
from shared.celery_config import celery_app
from shared.db import ArchivedUrl, ArchiveArtifact
from shared.rate_limit import rate_limit_admin
from shared.utils import rewrite_paywalled_url

logger = logging.getLogger(__name__)

router = APIRouter()


def get_db():
    """Database session dependency."""
    from shared.db import get_session

    with get_session() as session:
        yield session


# Request/Response Models


class RetryRequest(BaseModel):
    """Request model for retrying artifacts."""

    artifact_ids: Optional[List[int]] = Field(
        default=None, description="Specific artifact IDs to retry (optional)"
    )
    status: Optional[Literal["failed", "pending"]] = Field(
        default="failed", description="Filter artifacts by status"
    )
    archivers: Optional[List[str]] = Field(
        default=None, description="Filter by specific archivers"
    )
    include_all: bool = Field(
        default=False, description="Retry all matching artifacts"
    )
    limit: int = Field(
        default=100, ge=1, le=1000, description="Maximum number of artifacts to retry"
    )


class RetryResponse(BaseModel):
    """Response model for retry operation."""

    message: str
    task_id: str
    count: int


class CleanupRequest(BaseModel):
    """Request model for cleanup operation."""

    older_than_hours: int = Field(
        default=24, ge=1, description="Only clean files older than this"
    )
    dry_run: bool = Field(
        default=True, description="Preview without deleting"
    )


class CleanupResponse(BaseModel):
    """Response model for cleanup operation."""

    dry_run: bool
    files_deleted: int
    space_freed_bytes: int
    files: Optional[List[dict]] = None


class PendingArtifactItem(BaseModel):
    """Single pending artifact."""

    artifact_id: int
    archiver: str
    item_id: str
    url: str
    task_id: Optional[str]
    created_at: Optional[str]


# Endpoints


@router.post("/artifacts/retry", response_model=RetryResponse, dependencies=[Depends(rate_limit_admin)])
async def retry_artifacts(
    request: RetryRequest,
    db: Session = Depends(get_db),
):
    """
    Retry failed or pending artifacts.

    Consolidates:
    - POST /admin/retry-failed (retry failed artifacts)
    - POST /admin/saves/requeue (requeue artifacts with flexible criteria)

    Request body:
    {
        "artifact_ids": [1, 2, 3],        # Optional: specific artifacts
        "status": "failed",                # Optional: filter by status
        "archivers": ["readability"],      # Optional: filter by archiver
        "include_all": true,               # Optional: retry all matching
        "limit": 100                       # Maximum artifacts to retry
    }

    Returns:
    {
        "message": "Retrying N artifact(s)",
        "task_id": "abc123",
        "count": N
    }
    """
    logger.info(
        "Retry artifacts requested",
        extra=request.dict(exclude_unset=True)
    )

    artifacts_to_retry = []
    statuses_filter = set()

    if request.status:
        statuses_filter.add(request.status.lower())

    pull_all = request.include_all or (request.status is not None and not request.artifact_ids)

    # Fetch artifacts by ID
    if request.artifact_ids:
        fetched = (
            db.query(ArchiveArtifact, ArchivedUrl)
            .join(ArchivedUrl)
            .filter(ArchiveArtifact.id.in_(request.artifact_ids))
            .all()
        )
        logger.info(
            f"Loaded artifacts by ID",
            extra={"requested": len(request.artifact_ids), "found": len(fetched)}
        )
        artifacts_to_retry.extend(fetched)

    # Fetch artifacts by status
    if pull_all and request.status:
        query = (
            db.query(ArchiveArtifact, ArchivedUrl)
            .join(ArchivedUrl)
            .filter(ArchiveArtifact.status == request.status)
        )

        if request.archivers:
            query = query.filter(ArchiveArtifact.archiver.in_(request.archivers))

        query = query.limit(request.limit)
        fetched = query.all()

        logger.info(
            f"Loaded artifacts by status",
            extra={"status": request.status, "found": len(fetched)}
        )
        artifacts_to_retry.extend(fetched)

    # Deduplicate
    seen = set()
    unique_artifacts = []
    for artifact, archived_url in artifacts_to_retry:
        if artifact.id not in seen:
            seen.add(artifact.id)
            unique_artifacts.append((artifact, archived_url))

    if not unique_artifacts:
        return RetryResponse(
            message="No artifacts to retry",
            task_id="",
            count=0,
        )

    # Create new task ID
    task_id = uuid.uuid4().hex

    tasks = []
    for artifact, archived_url in unique_artifacts:
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
    if tasks:
        group(tasks).apply_async()

    logger.info(
        "Retry artifacts dispatched",
        extra={"task_id": task_id, "count": len(tasks)}
    )

    return RetryResponse(
        message=f"Retrying {len(tasks)} artifact(s)",
        task_id=task_id,
        count=len(tasks),
    )


@router.post("/artifacts/cleanup", response_model=CleanupResponse, dependencies=[Depends(rate_limit_admin)])
async def cleanup_artifacts(
    request: CleanupRequest,
    db: Session = Depends(get_db),
):
    """
    Clean up local files for artifacts uploaded to cloud storage.

    Replaces: POST /admin/cleanup-local

    Only cleans up files where all storage uploads succeeded.
    By default runs in dry-run mode to preview deletions.

    Request body:
    {
        "older_than_hours": 24,    # Only clean files older than this
        "dry_run": true             # Preview without deleting (default: true)
    }

    Returns:
    {
        "dry_run": true,
        "files_deleted": 0,
        "space_freed_bytes": 0,
        "files": [...]              # List of files (if dry_run=true)
    }
    """
    cutoff = datetime.utcnow() - timedelta(hours=request.older_than_hours)

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
                "size_bytes": artifact.size_bytes or 0,
                "archiver": artifact.archiver,
            })

    if request.dry_run:
        total_size = sum(f["size_bytes"] for f in files_to_delete)
        return CleanupResponse(
            dry_run=True,
            files_deleted=0,
            space_freed_bytes=total_size,
            files=files_to_delete,
        )

    # Actually delete files
    deleted_count = 0
    space_freed = 0

    for artifact in artifacts:
        if not artifact.saved_path:
            continue

        path = Path(artifact.saved_path)
        if not path.exists():
            continue

        try:
            size = artifact.size_bytes or 0
            path.unlink()
            artifact.local_file_deleted = True
            deleted_count += 1
            space_freed += size
            logger.info(f"Deleted local file: {path} ({size} bytes)")
        except Exception as e:
            logger.error(f"Failed to delete {path}: {e}")

    db.commit()

    logger.info(
        "Cleanup completed",
        extra={"deleted": deleted_count, "space_freed": space_freed}
    )

    return CleanupResponse(
        dry_run=False,
        files_deleted=deleted_count,
        space_freed_bytes=space_freed,
        files=None,
    )


@router.get("/artifacts/pending", dependencies=[Depends(rate_limit_admin)])
async def list_pending_artifacts(
    archiver: Optional[str] = Query(None, description="Filter by archiver"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    db: Session = Depends(get_db),
):
    """
    List pending artifacts.

    Replaces: GET /admin/pending

    Returns artifacts that are still pending processing.

    Query params:
    - archiver: Filter by specific archiver (optional)
    - limit: Maximum results (default: 100)

    Returns:
    {
        "count": N,
        "artifacts": [
            {
                "artifact_id": 123,
                "archiver": "readability",
                "item_id": "article-123",
                "url": "https://example.com",
                "task_id": "abc123",
                "created_at": "2026-01-16T..."
            },
            ...
        ]
    }
    """
    query = (
        db.query(ArchiveArtifact, ArchivedUrl)
        .join(ArchivedUrl)
        .filter(ArchiveArtifact.status == "pending")
        .order_by(ArchiveArtifact.created_at.desc())
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
