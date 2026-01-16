"""
Archives API routes - Consolidated archive management endpoints.

This module consolidates archive operations that were previously spread across
saves.py, admin.py, and firebase.py into a unified RESTful API.

Endpoints:
- POST   /archives         - Create archive (single or batch)
- GET    /archives         - List archives
- GET    /archives/{id}    - Get archive details
- PATCH  /archives/{id}    - Update archive metadata
- DELETE /archives         - Delete archive
- GET    /archives/{id}/download - Download archive
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from pathlib import Path
from typing import List, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.orm import Session
from celery import chain, group

from shared.auth import verify_api_key
from shared.celery_config import celery_app
from shared.db import (
    ArchivedUrl,
    ArchiveArtifact,
    ArticleSummary,
    UrlMetadata,
)
from shared.rate_limit import rate_limit_archive, rate_limit_batch, rate_limit_admin, rate_limit_download
from shared.models import TaskAccepted, DeleteResponse
from shared.utils import sanitize_filename, rewrite_paywalled_url
from shared.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()

# Available archivers
AVAILABLE_ARCHIVERS = ["singlefile", "monolith", "readability", "pdf", "screenshot"]


def get_db():
    """Database session dependency."""
    from shared.db import get_session

    with get_session() as session:
        yield session


# Request/Response Models

class ArchiveItem(BaseModel):
    """Single item to archive."""
    id: str = Field(..., description="Unique identifier for the archive")
    url: HttpUrl = Field(..., description="URL to archive")


class ArchiveOptions(BaseModel):
    """Optional archive workflow features."""
    summarize: bool = Field(False, description="Generate AI summary after archiving")
    upload_to_storage: bool = Field(False, description="Upload to cloud storage")
    webhook_url: Optional[HttpUrl] = Field(None, description="Webhook URL for completion notification")
    webhook_secret: Optional[str] = Field(None, description="Webhook secret for HMAC signing")


class CreateArchiveRequest(BaseModel):
    """Request model for creating archives."""
    items: List[ArchiveItem] = Field(..., min_items=1, description="URLs to archive")
    archivers: List[str] = Field(["all"], description="Archivers to use (default: all)")
    options: Optional[ArchiveOptions] = Field(None, description="Optional workflow features")


class ArchiveArtifactResponse(BaseModel):
    """Artifact info in archive response."""
    artifact_id: int
    archiver: str
    status: str
    success: bool
    exit_code: Optional[int]
    saved_path: Optional[str]
    size_bytes: Optional[int]
    created_at: Optional[str]


class ArchiveDetailResponse(BaseModel):
    """Detailed archive response."""
    item_id: str
    url: str
    name: Optional[str]
    created_at: str
    artifacts: Optional[List[ArchiveArtifactResponse]] = None
    total_size_bytes: Optional[int] = None
    size_by_archiver: Optional[dict] = None


class ArchiveListItem(BaseModel):
    """Single item in archives list."""
    rowid: int
    item_id: str
    url: str
    name: Optional[str]
    created_at: Optional[str]


class UpdateArchiveRequest(BaseModel):
    """Request model for updating archive metadata."""
    name: Optional[str] = Field(None, description="Update the archive name")


# Endpoints


@router.post("/archives", response_model=TaskAccepted, dependencies=[Depends(rate_limit_archive)])
async def create_archives(
    request: CreateArchiveRequest,
    db: Session = Depends(get_db),
):
    """
    Create archives (single or batch).

    Consolidates:
    - POST /save (single URL, all archivers)
    - POST /save/batch (multiple URLs, all archivers)
    - POST /archive/{archiver} (single URL, specific archiver)
    - POST /archive/{archiver}/batch (multiple URLs, specific archiver)
    - POST /workflow (archive + summarize workflow)
    - POST /firebase/archive (Firebase-specific archiving)

    Request body:
    {
        "items": [{"id": "...", "url": "..."}],  # Single item or batch
        "archivers": ["readability", "pdf"],      # Optional, defaults to ["all"]
        "options": {                              # Optional workflow features
            "summarize": true,
            "upload_to_storage": true,
            "webhook_url": "..."
        }
    }

    Logic:
    - Single item (items.length == 1): Single save behavior
    - Multiple items (items.length > 1): Batch behavior
    - archivers=["all"]: Use all available archivers
    - options.summarize: Chain summarization task
    """
    is_batch = len(request.items) > 1
    archivers = request.archivers

    # Handle "all" archiver
    if "all" in archivers:
        archivers = AVAILABLE_ARCHIVERS

    # Validate archivers
    invalid = [a for a in archivers if a not in AVAILABLE_ARCHIVERS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid archivers: {invalid}. Valid options: {AVAILABLE_ARCHIVERS}",
        )

    # Generate workflow ID for this batch
    workflow_id = uuid.uuid4().hex
    all_tasks = []
    skipped_count = 0

    for item in request.items:
        url = str(item.url)
        item_id = item.id

        logger.info(
            "Archive request received",
            extra={"url": url, "item_id": item_id, "archivers": archivers, "batch": is_batch},
        )

        # Get or create archived URL
        existing = db.query(ArchivedUrl).filter(ArchivedUrl.url == url).first()
        if existing:
            archived_url_id = existing.id
        else:
            archived_url = ArchivedUrl(url=url, item_id=item_id)
            db.add(archived_url)
            db.flush()
            archived_url_id = archived_url.id

        # Create artifacts and dispatch tasks
        for archiver in archivers:
            # Lock row to prevent race conditions
            locked_url = (
                db.query(ArchivedUrl)
                .filter(ArchivedUrl.id == archived_url_id)
                .with_for_update()
                .first()
            )

            # Check for existing successful artifact
            existing_artifact = (
                db.query(ArchiveArtifact)
                .filter(
                    ArchiveArtifact.archived_url_id == archived_url_id,
                    ArchiveArtifact.archiver == archiver,
                    ArchiveArtifact.success == True,
                )
                .first()
            )

            if existing_artifact:
                logger.info(
                    "Skipping existing archive",
                    extra={"archiver": archiver, "item_id": item_id},
                )
                skipped_count += 1
                continue

            # Create or get artifact
            artifact = (
                db.query(ArchiveArtifact)
                .filter(
                    ArchiveArtifact.archived_url_id == archived_url_id,
                    ArchiveArtifact.archiver == archiver,
                )
                .first()
            )

            if not artifact:
                artifact = ArchiveArtifact(
                    archived_url_id=archived_url_id,
                    archiver=archiver,
                    status="pending",
                    task_id=workflow_id,
                )
                db.add(artifact)
                db.flush()

            # Rewrite URL for paywall bypass
            fetch_url = rewrite_paywalled_url(url)

            # Create Celery task
            task_name = f"services.archive_worker.tasks.archive_{archiver}"
            all_tasks.append(
                celery_app.signature(
                    task_name,
                    kwargs={
                        "item_id": item_id,
                        "url": fetch_url,
                        "archived_url_id": archived_url_id,
                        "artifact_id": artifact.id,
                    },
                )
            )

    db.commit()

    if not all_tasks:
        return TaskAccepted(
            task_id=workflow_id,
            count=skipped_count,
            message=f"All archives already exist ({skipped_count} skipped)",
        )

    # Build workflow
    task_group = group(all_tasks)

    # Add optional workflow steps
    if request.options:
        steps = [task_group]

        if request.options.summarize:
            steps.append(
                celery_app.signature(
                    "services.archive_worker.tasks.gather_status",
                    kwargs={"task_id": workflow_id},
                )
            )

        if request.options.webhook_url:
            steps.append(
                celery_app.signature(
                    "services.archive_worker.tasks.notify_webhook",
                    kwargs={
                        "workflow_id": workflow_id,
                        "webhook_url": str(request.options.webhook_url),
                        "webhook_secret": request.options.webhook_secret,
                        "event_type": "task.completed",
                    },
                )
            )

        workflow = chain(*steps) if len(steps) > 1 else steps[0]
        workflow.apply_async()
    else:
        task_group.apply_async()

    return TaskAccepted(
        task_id=workflow_id,
        count=len(all_tasks),
        message=f"Queued {len(all_tasks)} archiving task(s)" + (f" ({skipped_count} skipped)" if skipped_count else ""),
    )


@router.get("/archives", dependencies=[Depends(rate_limit_admin)])
async def list_archives(
    limit: int = Query(200, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    status: Optional[str] = Query(None, description="Filter by status"),
    archiver: Optional[str] = Query(None, description="Filter by archiver"),
    db: Session = Depends(get_db),
):
    """
    List all archives with pagination and filtering.

    Replaces: GET /admin/saves
    """
    query = db.query(ArchivedUrl).order_by(ArchivedUrl.created_at.desc())

    total = query.count()
    results = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "count": len(results),
        "items": [
            {
                "item_id": r.item_id,
                "url": r.url,
                "name": r.name,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in results
        ],
    }


@router.get("/archives/{item_id}", response_model=ArchiveDetailResponse, dependencies=[Depends(rate_limit_admin)])
async def get_archive(
    item_id: str,
    include: List[Literal["metadata", "artifacts", "size"]] = Query(["metadata"]),
    archiver: Optional[str] = Query(None, description="Filter artifacts by archiver"),
    type: Literal["item_id", "url"] = Query("item_id", description="Lookup type"),
    identifier: Optional[str] = Query(None, description="Override identifier for URL lookup"),
    db: Session = Depends(get_db),
):
    """
    Get archive details by item_id or URL.

    Consolidates:
    - GET /admin/archive/{item_id} (metadata + artifacts)
    - GET /admin/archive/by-url (lookup by URL)
    - GET /archive/{item_id}/size (size info)

    Query params:
    - include: ["metadata", "artifacts", "size"] (default: ["metadata"])
    - archiver: Filter artifacts by specific archiver
    - type: "item_id" or "url" (default: "item_id")
    - identifier: Override for URL lookup (use this instead of item_id path param)
    """
    # Lookup by type
    lookup_value = identifier if identifier else item_id

    if type == "item_id":
        archived_url = db.query(ArchivedUrl).filter(ArchivedUrl.item_id == lookup_value).first()
    else:
        archived_url = db.query(ArchivedUrl).filter(ArchivedUrl.url == lookup_value).first()

    if not archived_url:
        raise HTTPException(404, f"Archive not found: {lookup_value}")

    result = ArchiveDetailResponse(
        item_id=archived_url.item_id,
        url=archived_url.url,
        name=archived_url.name,
        created_at=archived_url.created_at.isoformat(),
    )

    if "artifacts" in include or "size" in include:
        query = db.query(ArchiveArtifact).filter(ArchiveArtifact.archived_url_id == archived_url.id)
        if archiver:
            query = query.filter(ArchiveArtifact.archiver == archiver)
        artifacts = query.all()

        if "artifacts" in include:
            result.artifacts = [
                ArchiveArtifactResponse(
                    artifact_id=a.id,
                    archiver=a.archiver,
                    status=a.status,
                    success=a.success,
                    exit_code=a.exit_code,
                    saved_path=a.saved_path,
                    size_bytes=a.size_bytes,
                    created_at=a.created_at.isoformat() if a.created_at else None,
                )
                for a in artifacts
            ]

        if "size" in include:
            result.total_size_bytes = sum(a.size_bytes or 0 for a in artifacts)
            result.size_by_archiver = {a.archiver: a.size_bytes for a in artifacts}

    return result


@router.patch("/archives/{item_id}", dependencies=[Depends(rate_limit_admin)])
async def update_archive_metadata(
    item_id: str,
    request: UpdateArchiveRequest,
    db: Session = Depends(get_db),
):
    """
    Update archive metadata by item_id.

    Currently supports updating:
    - name: Archive name/title
    """
    archived_url = db.query(ArchivedUrl).filter(ArchivedUrl.item_id == item_id).first()
    if not archived_url:
        raise HTTPException(404, f"Archive not found: {item_id}")

    if request.name is not None:
        archived_url.name = request.name

    db.commit()

    return {
        "ok": True,
        "item_id": item_id,
        "updated_fields": [k for k, v in request.dict(exclude_unset=True).items() if v is not None],
    }


@router.delete("/archives", response_model=DeleteResponse, dependencies=[Depends(rate_limit_admin)])
async def delete_archive(
    identifier: str = Query(..., description="item_id or URL to delete"),
    type: Literal["item_id", "url"] = Query("item_id", description="Lookup type"),
    delete_files: bool = Query(False, description="Also delete local files"),
    db: Session = Depends(get_db),
):
    """
    Delete archive by item_id or URL.

    Consolidates:
    - DELETE /admin/archive/{item_id}
    - DELETE /admin/saves/by-item/{item_id}
    - DELETE /admin/saves/by-url

    Query params:
    - identifier: item_id or URL value
    - type: "item_id" or "url" (default: "item_id")
    - delete_files: Also delete local files (default: false)
    """
    # Lookup by type
    if type == "item_id":
        archived_url = db.query(ArchivedUrl).filter(ArchivedUrl.item_id == identifier).first()
    else:
        archived_url = db.query(ArchivedUrl).filter(ArchivedUrl.url == identifier).first()

    if not archived_url:
        raise HTTPException(404, f"Archive not found: {identifier}")

    # Get artifacts
    artifacts = db.query(ArchiveArtifact).filter(ArchiveArtifact.archived_url_id == archived_url.id).all()

    deleted_rowids = [a.id for a in artifacts]
    removed_files = []
    errors = []

    # Delete files if requested
    if delete_files:
        for artifact in artifacts:
            if artifact.saved_path:
                try:
                    path = Path(artifact.saved_path)
                    if path.exists():
                        path.unlink()
                        removed_files.append(str(path))
                        logger.info(f"Deleted file: {path}")
                except Exception as e:
                    error_msg = f"Failed to delete {artifact.saved_path}: {e}"
                    errors.append(error_msg)
                    logger.error(error_msg)

    # Delete database records
    for artifact in artifacts:
        db.delete(artifact)

    # Delete related summaries
    db.query(ArticleSummary).filter(ArticleSummary.archived_url_id == archived_url.id).delete()

    # Delete URL record
    db.delete(archived_url)
    db.commit()

    return DeleteResponse(
        ok=True,
        deleted_count=len(artifacts),
        deleted_rowids=deleted_rowids,
        removed_files=removed_files if delete_files else None,
        errors=errors if errors else None,
    )


@router.get("/archives/{item_id}/download", dependencies=[Depends(rate_limit_download)])
async def download_archive(
    item_id: str,
    archiver: str = Query(..., description="Archiver name"),
    expiration_hours: int = Query(24, ge=1, le=168, description="Signed URL expiration (hours)"),
    db: Session = Depends(get_db),
):
    """
    Download archived file or generate signed URL.

    Consolidates:
    - GET /retrieve (local file download)
    - GET /firebase/download/{item_id}/{archiver} (GCS signed URL)

    Query params:
    - archiver: Specific archiver (required)
    - expiration_hours: For signed URLs (default: 24, max: 168)

    Returns:
    - For local storage: File download
    - For cloud storage: JSON with signed URL
    """
    archived_url = db.query(ArchivedUrl).filter(ArchivedUrl.item_id == item_id).first()
    if not archived_url:
        raise HTTPException(404, f"Archive not found: {item_id}")

    artifact = (
        db.query(ArchiveArtifact)
        .filter(
            ArchiveArtifact.archived_url_id == archived_url.id,
            ArchiveArtifact.archiver == archiver,
            ArchiveArtifact.success == True,
        )
        .first()
    )

    if not artifact:
        raise HTTPException(404, f"No successful archive for archiver: {archiver}")

    # If cloud storage, generate signed URL
    if artifact.gcs_path:
        try:
            from shared.storage.gcs_file_storage import GCSFileStorage

            gcs = GCSFileStorage(
                bucket_name=settings.gcs.bucket,
                project_id=settings.gcs.project_id,
            )
            signed_url = gcs.generate_access_url(
                artifact.gcs_path,
                timedelta(hours=expiration_hours),
            )
            return {
                "download_url": signed_url,
                "expires_in": expiration_hours * 3600,
                "archiver": archiver,
                "item_id": item_id,
            }
        except Exception as e:
            logger.error(f"Failed to generate signed URL: {e}")
            raise HTTPException(500, f"Failed to generate download URL: {e}")

    # If local storage, return file
    if artifact.saved_path:
        path = Path(artifact.saved_path)
        if path.exists():
            return FileResponse(
                path,
                media_type="application/octet-stream",
                filename=path.name,
            )

    raise HTTPException(404, "No download available for this archive")
