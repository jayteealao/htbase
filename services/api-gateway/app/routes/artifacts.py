"""
Artifacts API routes - Artifact operations and maintenance endpoints.

This module provides operations for managing archive artifacts including
retry logic and status monitoring.

Endpoints:
- POST /artifacts/retry   - Retry failed/pending artifacts
- GET  /artifacts/pending - List pending artifacts

Note: Cleanup endpoint removed (no local files in GCS-only mode)
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

from shared.auth import verify_api_key
from shared.infrastructure.celery import celery_app
from shared.firestore import get_article, get_artifacts_by_status, update_artifact
from shared.rate_limit import rate_limit_admin
from shared.utils import rewrite_paywalled_url

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models


class RetryRequest(BaseModel):
    """Request model for retrying artifacts."""

    status: Literal["failed", "pending"] = Field(
        default="failed", description="Filter artifacts by status"
    )
    archivers: Optional[List[str]] = Field(
        default=None, description="Filter by specific archivers"
    )
    limit: int = Field(
        default=100, ge=1, le=1000, description="Maximum number of artifacts to retry"
    )


class RetryResponse(BaseModel):
    """Response model for retry operation."""

    message: str
    task_id: str
    count: int


class PendingArtifactItem(BaseModel):
    """Single pending artifact."""

    archiver: str
    item_id: str
    url: str
    status: str
    updated_at: Optional[str]


# Endpoints


@router.post("/artifacts/retry", response_model=RetryResponse, dependencies=[Depends(rate_limit_admin)])
async def retry_artifacts(
    request: RetryRequest,
):
    """
    Retry failed or pending artifacts.

    Consolidates:
    - POST /admin/retry-failed (retry failed artifacts)
    - POST /admin/saves/requeue (requeue artifacts with flexible criteria)

    Request body:
    {
        "status": "failed",                # Filter by status (failed or pending)
        "archivers": ["readability"],      # Optional: filter by archiver
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

    # Get artifacts by status from Firestore
    artifacts_to_retry = get_artifacts_by_status(
        status=request.status,
        archiver=request.archivers[0] if request.archivers and len(request.archivers) == 1 else None,
        limit=request.limit,
    )

    if not artifacts_to_retry:
        return RetryResponse(
            message="No artifacts to retry",
            task_id="",
            count=0,
        )

    # Filter by multiple archivers if specified
    if request.archivers and len(request.archivers) > 1:
        artifacts_to_retry = [
            a for a in artifacts_to_retry
            if a["archiver"] in request.archivers
        ]

    # Create new task ID
    task_id = uuid.uuid4().hex

    tasks = []
    for result in artifacts_to_retry:
        item_id = result["item_id"]
        archiver = result["archiver"]
        url = result["url"]

        # Update artifact status to pending
        update_artifact(item_id, archiver, status="pending")

        fetch_url = rewrite_paywalled_url(url)

        task_name = f"services.archive_worker.tasks.archive_{archiver}"
        tasks.append(
            celery_app.signature(
                task_name,
                kwargs={
                    "item_id": item_id,
                    "url": fetch_url,
                },
            )
        )

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


@router.get("/artifacts/pending", dependencies=[Depends(rate_limit_admin)])
async def list_pending_artifacts(
    archiver: Optional[str] = Query(None, description="Filter by archiver"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
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
                "archiver": "readability",
                "item_id": "article-123",
                "url": "https://example.com",
                "status": "pending",
                "updated_at": "2026-01-16T..."
            },
            ...
        ]
    }
    """
    results = get_artifacts_by_status(
        status="pending",
        archiver=archiver,
        limit=limit,
    )

    return {
        "count": len(results),
        "artifacts": [
            {
                "archiver": r["archiver"],
                "item_id": r["item_id"],
                "url": r["url"],
                "status": r["artifact"].get("status"),
                "updated_at": r["artifact"].get("updated_at"),
            }
            for r in results
        ],
    }
