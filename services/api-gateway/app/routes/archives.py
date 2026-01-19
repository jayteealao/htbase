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
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, HttpUrl
from celery import chain, group

from shared.auth import verify_api_key
from shared.infrastructure.celery import celery_app
from shared.web.dependencies import ArticleRepoType, ArtifactRepoType
from shared.rate_limit import rate_limit_archive, rate_limit_batch, rate_limit_admin, rate_limit_download
from shared.models import TaskAccepted, DeleteResponse
from shared.utils import sanitize_filename, rewrite_paywalled_url
from shared.config import get_settings
from shared.observability import (
    enrich_api_event,
    ArticleContext,
    ArchiveRequestContext,
    get_request_id,
    get_correlation_id,
)
from shared.logging_utils import sanitize_url_for_logging

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


@router.post("/archives", response_model=TaskAccepted)
async def create_archive(
    req: Request,
    response: Response,
    request: CreateArchiveRequest,
    api_key: str = Depends(rate_limit_archive),
    article_repo: ArticleRepoType = None,  # Injected dependency!
):
    """Create archive for one or more URLs.

    This endpoint initiates archiving tasks for the provided URLs.
    Tasks are dispatched to Celery workers for async processing.

    Example:
        ```json
        {
            "items": [
                {"id": "123", "url": "https://example.com/article"}
            ],
            "archivers": ["singlefile", "readability"],
            "options": {
                "summarize": true,
                "webhook_url": "https://yourapp.com/webhook"
            }
        }
        ```
    """
    # Get correlation IDs for passing to workers
    request_id = get_request_id()
    correlation_id = get_correlation_id()

    # Resolve archivers
    if "all" in request.archivers:
        archivers = AVAILABLE_ARCHIVERS
    else:
        archivers = [a for a in request.archivers if a in AVAILABLE_ARCHIVERS]

    if not archivers:
        raise HTTPException(
            status_code=400,
            detail=f"No valid archivers selected. Available: {AVAILABLE_ARCHIVERS}"
        )

    # Track task IDs for wide event
    task_ids = {}
    all_tasks = []

    # Check if articles already exist and dispatch tasks
    for item in request.items:
        article_exists = article_repo.exists(item.id)

        # Enrich wide event with first article context (for single item requests)
        if len(request.items) == 1:
            enrich_api_event(
                req,
                article=ArticleContext(
                    id=item.id,
                    url=sanitize_url_for_logging(str(item.url)),
                    exists=article_exists,
                ),
            )

        if not article_exists:
            # Create article in Firestore
            article_repo.create(
                item_id=item.id,
                url=str(item.url),
            )

        # Dispatch tasks for each archiver
        for archiver in archivers:
            fetch_url = rewrite_paywalled_url(str(item.url))
            task_name = f"services.archive_worker.tasks.archive_{archiver}"

            task = celery_app.signature(
                task_name,
                kwargs={
                    "item_id": item.id,
                    "url": fetch_url,
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                },
            )
            all_tasks.append(task)

            # Track first task ID for each archiver (for single item)
            if len(request.items) == 1 and archiver not in task_ids:
                # Task ID will be generated when applied
                task_ids[archiver] = f"pending_{archiver}"

    # Dispatch all tasks
    if all_tasks:
        try:
            logger.info(f"Dispatching {len(all_tasks)} tasks to Celery workers")
            result = group(all_tasks).apply_async()
            logger.info(f"Tasks dispatched successfully, group_id: {result.id}")
        except Exception as e:
            logger.error(
                f"Failed to dispatch Celery tasks: {e}",
                exc_info=True,
                extra={
                    "task_count": len(all_tasks),
                    "archivers": archivers,
                    "error_type": type(e).__name__,
                }
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to dispatch archive tasks: {str(e)}"
            )

    # Enrich wide event with archive request context
    try:
        if len(request.items) == 1:
            enrich_api_event(
                req,
                archive_request=ArchiveRequestContext(
                    archivers_requested=archivers,
                    celery_task_ids=task_ids,
                ),
            )
    except Exception as e:
        logger.error(f"Failed to enrich API event: {e}", exc_info=True)
        # Don't fail the request for logging issues

    try:
        total_tasks = len(request.items) * len(archivers)
        response = TaskAccepted(
            task_id=request_id or "unknown",
            count=total_tasks,
            message=f"Archive tasks created: {len(request.items)} items × {len(archivers)} archivers = {total_tasks} tasks"
        )
        logger.info(f"Returning success response: {response}")
        return response
    except Exception as e:
        logger.error(f"Failed to create response: {e}", exc_info=True)
        raise


@router.get("/archives/{item_id}")
async def get_archive(
    item_id: str,
    api_key: str = Depends(verify_api_key),
    article_repo: ArticleRepoType = None,  # Injected dependency!
):
    """Get archive details by ID."""
    article = article_repo.get(item_id)

    if not article:
        raise HTTPException(status_code=404, detail="Archive not found")

    return article


@router.delete("/archives/{item_id}", response_model=DeleteResponse)
async def delete_archive(
    response: Response,
    item_id: str,
    api_key: str = Depends(rate_limit_admin),
    article_repo: ArticleRepoType = None,  # Injected dependency!
):
    """Delete an archive and all its artifacts."""
    deleted = article_repo.delete(item_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Archive not found")

    return DeleteResponse(
        success=True,
        message=f"Archive {item_id} deleted successfully"
    )
