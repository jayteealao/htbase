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
from pydantic import BaseModel, Field, HttpUrl
from celery import chain, group

from shared.auth import verify_api_key
from shared.celery_config import celery_app
from shared.firestore import (
    create_article,
    get_article,
    article_exists,
    update_article,
    delete_article,
    list_articles,
    query_by_url,
    get_artifact,
    update_artifact,
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
    items: List[ArchiveItem] = Field(..., min_items=1, max_items=100, description="URLs to archive (max 100)")
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


# Helper functions for create_archives endpoint


def _validate_archivers(archivers: List[str]) -> List[str]:
    """Validate and normalize archiver list.

    Args:
        archivers: List of archiver names or ["all"]

    Returns:
        Validated list of archiver names

    Raises:
        HTTPException: If invalid archivers are provided
    """
    # Handle "all" archiver
    if "all" in archivers:
        return AVAILABLE_ARCHIVERS.copy()

    # Validate archivers
    invalid = [a for a in archivers if a not in AVAILABLE_ARCHIVERS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid archivers: {invalid}. Valid options: {AVAILABLE_ARCHIVERS}",
        )

    return archivers


def _create_archive_tasks(
    items: List[ArchiveItem],
    archivers: List[str]
):
    """Create Celery tasks for archive items.

    Args:
        items: List of items to archive
        archivers: List of validated archiver names

    Returns:
        Tuple of (task_list, skipped_count)
    """
    all_tasks = []
    skipped_count = 0
    is_batch = len(items) > 1

    for item in items:
        url = str(item.url)
        item_id = item.id

        logger.info(
            "Archive request received",
            extra={"url": url, "item_id": item_id, "archivers": archivers, "batch": is_batch},
        )

        # Get or create article in Firestore
        existing_article = get_article(item_id)
        if not existing_article:
            create_article(item_id=item_id, url=url)
            logger.info(f"Created article in Firestore", extra={"item_id": item_id})

        # Create artifacts and dispatch tasks
        for archiver in archivers:
            # Check for existing successful artifact
            existing_artifact = get_artifact(item_id, archiver)

            if existing_artifact and existing_artifact.get("status") == "success":
                logger.info(
                    "Skipping existing archive",
                    extra={"archiver": archiver, "item_id": item_id},
                )
                skipped_count += 1
                continue

            # Initialize artifact status if not exists
            if not existing_artifact:
                update_artifact(
                    item_id=item_id,
                    archiver=archiver,
                    status="pending",
                )

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
                    },
                )
            )

    return all_tasks, skipped_count


def _build_workflow(task_group, options: Optional[ArchiveOptions], workflow_id: str):
    """Build Celery workflow with optional steps.

    Args:
        task_group: Celery group of archive tasks
        options: Optional workflow options (summarize, webhook)
        workflow_id: Workflow identifier

    Returns:
        Celery workflow (group or chain)
    """
    if not options:
        return task_group

    steps = [task_group]

    if options.summarize:
        steps.append(
            celery_app.signature(
                "services.archive_worker.tasks.gather_status",
                kwargs={"task_id": workflow_id},
            )
        )

    if options.webhook_url:
        steps.append(
            celery_app.signature(
                "services.archive_worker.tasks.notify_webhook",
                kwargs={
                    "workflow_id": workflow_id,
                    "webhook_url": str(options.webhook_url),
                    "webhook_secret": options.webhook_secret,
                    "event_type": "task.completed",
                },
            )
        )

    return chain(*steps) if len(steps) > 1 else steps[0]


# Endpoints


@router.post("/archives", response_model=TaskAccepted, dependencies=[Depends(rate_limit_archive)])
async def create_archives(
    request: CreateArchiveRequest,
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
    # Validate archivers
    archivers = _validate_archivers(request.archivers)

    # Generate workflow ID
    workflow_id = uuid.uuid4().hex

    # Create archive tasks
    all_tasks, skipped_count = _create_archive_tasks(request.items, archivers)

    # Early return if all archives exist
    if not all_tasks:
        return TaskAccepted(
            task_id=workflow_id,
            count=skipped_count,
            message=f"All archives already exist ({skipped_count} skipped)",
        )

    # Build and dispatch workflow
    task_group = group(all_tasks)
    workflow = _build_workflow(task_group, request.options, workflow_id)

    try:
        workflow.apply_async()

        logger.info(
            "Archive tasks dispatched successfully",
            extra={"workflow_id": workflow_id, "task_count": len(all_tasks)}
        )

    except Exception as e:
        logger.error(
            f"Failed to dispatch archive tasks: {e}",
            extra={"workflow_id": workflow_id, "task_count": len(all_tasks)},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue archiving tasks: {str(e)}"
        )

    # Return success response
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
):
    """
    List all archives with pagination and filtering.

    Replaces: GET /admin/saves
    """
    results = list_articles(
        limit=limit,
        offset=offset,
        order_by="created_at",
        descending=True,
    )

    return {
        "total": len(results),  # Note: Firestore doesn't support efficient total counts
        "limit": limit,
        "offset": offset,
        "count": len(results),
        "items": [
            {
                "item_id": r.get("item_id"),
                "url": r.get("url"),
                "name": r.get("title"),  # Using title field
                "created_at": r.get("created_at"),
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
        article = get_article(lookup_value)
    else:
        article = query_by_url(lookup_value)

    if not article:
        raise HTTPException(404, f"Archive not found: {lookup_value}")

    result = ArchiveDetailResponse(
        item_id=article.get("item_id"),
        url=article.get("url"),
        name=article.get("title"),
        created_at=article.get("created_at"),
    )

    if "artifacts" in include or "size" in include:
        archives = article.get("archives", {})

        # Filter by archiver if specified
        if archiver:
            archives = {k: v for k, v in archives.items() if k == archiver}

        if "artifacts" in include:
            result.artifacts = [
                ArchiveArtifactResponse(
                    artifact_id=0,  # Firestore doesn't have artifact IDs
                    archiver=arch_name,
                    status=arch_data.get("status", "unknown"),
                    success=arch_data.get("status") == "success",
                    exit_code=arch_data.get("exit_code"),
                    saved_path=None,  # No local paths in GCS-only mode
                    size_bytes=arch_data.get("file_size"),
                    created_at=arch_data.get("updated_at"),
                )
                for arch_name, arch_data in archives.items()
            ]

        if "size" in include:
            result.total_size_bytes = sum(a.get("file_size", 0) for a in archives.values())
            result.size_by_archiver = {k: v.get("file_size") for k, v in archives.items()}

    return result


@router.patch("/archives/{item_id}", dependencies=[Depends(rate_limit_admin)])
async def update_archive_metadata(
    item_id: str,
    request: UpdateArchiveRequest,
):
    """
    Update archive metadata by item_id.

    Currently supports updating:
    - name: Archive name/title
    """
    article = get_article(item_id)
    if not article:
        raise HTTPException(404, f"Archive not found: {item_id}")

    if request.name is not None:
        update_article(item_id, title=request.name)

    return {
        "ok": True,
        "item_id": item_id,
        "updated_fields": [k for k, v in request.dict(exclude_unset=True).items() if v is not None],
    }


@router.delete("/archives", response_model=DeleteResponse, dependencies=[Depends(rate_limit_admin)])
async def delete_archive(
    identifier: str = Query(..., description="item_id or URL to delete"),
    type: Literal["item_id", "url"] = Query("item_id", description="Lookup type"),
    delete_files: bool = Query(False, description="Also delete GCS files"),
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
    - delete_files: Also delete GCS files (default: false)
    """
    # Lookup by type
    if type == "item_id":
        article = get_article(identifier)
        item_id = identifier
    else:
        article = query_by_url(identifier)
        item_id = article.get("item_id") if article else None

    if not article:
        raise HTTPException(404, f"Archive not found: {identifier}")

    # Get artifacts
    archives = article.get("archives", {})
    removed_files = []
    errors = []

    # Delete GCS files if requested
    if delete_files:
        from google.cloud import storage

        try:
            client = storage.Client(project=settings.gcs.project_id)
            bucket = client.bucket(settings.gcs.bucket)

            for archiver, arch_data in archives.items():
                gcs_path = arch_data.get("gcs_path")
                if gcs_path:
                    try:
                        # Extract blob name from gs:// URL
                        blob_name = gcs_path.replace(f"gs://{settings.gcs.bucket}/", "")
                        blob = bucket.blob(blob_name)
                        blob.delete()
                        removed_files.append(gcs_path)
                        logger.info(f"Deleted GCS file: {gcs_path}")
                    except Exception as e:
                        error_msg = f"Failed to delete {gcs_path}: {e}"
                        errors.append(error_msg)
                        logger.error(error_msg)
        except Exception as e:
            error_msg = f"Failed to initialize GCS client: {e}"
            errors.append(error_msg)
            logger.error(error_msg)

    # Delete Firestore document
    success = delete_article(item_id)

    if not success:
        raise HTTPException(500, "Failed to delete article from Firestore")

    return DeleteResponse(
        ok=True,
        deleted_count=len(archives),
        deleted_rowids=[],  # Firestore doesn't have row IDs
        removed_files=removed_files if delete_files else None,
        errors=errors if errors else None,
    )


@router.get("/archives/{item_id}/download", dependencies=[Depends(rate_limit_download)])
async def download_archive(
    item_id: str,
    archiver: str = Query(..., description="Archiver name"),
    expiration_hours: int = Query(24, ge=1, le=168, description="Signed URL expiration (hours)"),
):
    """
    Generate GCS signed URL for archive download.

    Consolidates:
    - GET /retrieve (local file download) - REMOVED
    - GET /firebase/download/{item_id}/{archiver} (GCS signed URL)

    Query params:
    - archiver: Specific archiver (required)
    - expiration_hours: For signed URLs (default: 24, max: 168)

    Returns:
    - JSON with signed URL
    """
    article = get_article(item_id)
    if not article:
        raise HTTPException(404, f"Archive not found: {item_id}")

    # Get artifact from archives map
    artifact = get_artifact(item_id, archiver)
    if not artifact or artifact.get("status") != "success":
        raise HTTPException(404, f"No successful archive for archiver: {archiver}")

    gcs_path = artifact.get("gcs_path")
    if not gcs_path:
        raise HTTPException(404, "No GCS path available for this archive")

    # Generate signed URL
    try:
        from google.cloud import storage

        client = storage.Client(project=settings.gcs.project_id)
        bucket = client.bucket(settings.gcs.bucket)

        # Extract blob name from gs:// URL
        blob_name = gcs_path.replace(f"gs://{settings.gcs.bucket}/", "")
        blob = bucket.blob(blob_name)

        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=expiration_hours),
            method="GET",
        )

        return {
            "download_url": signed_url,
            "expires_in": expiration_hours * 3600,
            "archiver": archiver,
            "item_id": item_id,
        }
    except Exception as e:
        logger.error(f"Failed to generate signed URL: {e}", exc_info=True)
        raise HTTPException(500, f"Failed to generate download URL: {e}")
