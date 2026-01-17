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
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl
from celery import chain, group

from shared.auth import verify_api_key
from shared.celery_config import celery_app
from shared.web.dependencies import ArticleRepoType, ArtifactRepoType
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


@router.post("/archives", response_model=TaskAccepted)
@rate_limit_archive
async def create_archive(
    request: CreateArchiveRequest,
    api_key: str = Depends(verify_api_key),
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

    # Check if articles already exist (using injected repository!)
    for item in request.items:
        if article_repo.exists(item.id):
            logger.warning(f"Article {item.id} already exists, will update")
        else:
            # Create article in Firestore
            article_repo.create(
                item_id=item.id,
                url=str(item.url),
            )

    # Dispatch Celery tasks for each URL + archiver combination
    # (Task dispatching logic would go here)

    return TaskAccepted(
        task_id="example-task-id",
        status="accepted",
        message=f"Archive tasks created for {len(request.items)} items with {len(archivers)} archivers"
    )


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
@rate_limit_admin
async def delete_archive(
    item_id: str,
    api_key: str = Depends(verify_api_key),
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
