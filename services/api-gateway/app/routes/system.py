"""
System API routes - System-level operations and configuration endpoints.

This module provides system-wide operations including statistics, configuration,
summarization, and command execution.

Endpoints:
- GET  /system/stats      - Get system statistics
- GET  /system/archivers  - List available archivers
- POST /system/summarize  - Trigger AI summarization
- POST /system/commands   - Send command to HyperTerm runner
"""

from __future__ import annotations

import logging
import uuid
from contextlib import ExitStack
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.auth import verify_api_key
from shared.infrastructure.celery import celery_app
from shared.config import get_settings
from shared.infrastructure.firestore import get_articles_collection
from shared.rate_limit import rate_limit_admin
from shared.utils import sanitize_filename

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()

# Available archivers
AVAILABLE_ARCHIVERS = ["singlefile", "monolith", "readability", "pdf", "screenshot"]


# Request/Response Models


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


class SystemStatsResponse(BaseModel):
    """System statistics response."""

    archived_urls: int
    total_artifacts: int
    successful_artifacts: int
    summaries: int
    total_size_bytes: int
    archivers: Dict[str, Dict[str, int]]


class CommandRequest(BaseModel):
    """Request model for command execution."""

    payload: str = Field(..., description="Command to execute")
    wait_marker: Optional[str] = Field(None, description="Wait for this marker in output")
    timeout: float = Field(15.0, ge=1.0, le=300.0, description="Timeout in seconds")


class CommandResponse(BaseModel):
    """Response model for command execution."""

    ok: bool
    exit_code: Optional[int] = None


# Endpoints


@router.get("/system/stats", response_model=SystemStatsResponse, dependencies=[Depends(rate_limit_admin)])
async def get_system_stats():
    """
    Get system statistics from Firestore.

    Replaces: GET /admin/stats

    Returns counts of archived URLs, artifacts, summaries, and storage usage.

    Returns:
    {
        "archived_urls": 1234,
        "total_artifacts": 5678,
        "successful_artifacts": 4321,
        "summaries": 890,
        "total_size_bytes": 123456789,
        "archivers": {
            "readability": {"total": 1234, "success": 1100},
            "pdf": {"total": 567, "success": 500},
            ...
        }
    }
    """
    collection = get_articles_collection()

    # Initialize counters
    url_count = 0
    artifact_count = 0
    success_count = 0
    summary_count = 0
    total_size = 0
    archiver_stats: Dict[str, Dict[str, int]] = {}

    # Stream all articles and aggregate stats
    for doc in collection.stream():
        article = doc.to_dict()
        url_count += 1

        # Count archives (artifacts)
        archives = article.get("archives", {})
        for archiver_name, artifact_data in archives.items():
            artifact_count += 1

            # Initialize archiver stats if needed
            if archiver_name not in archiver_stats:
                archiver_stats[archiver_name] = {"total": 0, "success": 0}

            archiver_stats[archiver_name]["total"] += 1

            # Count successful artifacts
            if artifact_data.get("success") or artifact_data.get("status") == "success":
                success_count += 1
                archiver_stats[archiver_name]["success"] += 1

            # Sum file sizes
            size = artifact_data.get("file_size") or artifact_data.get("size_bytes") or 0
            if size:
                total_size += size

        # Count summaries
        summary = article.get("summary", {})
        if summary and (summary.get("text") or summary.get("summary_text") or summary.get("bullet_points")):
            summary_count += 1

    return SystemStatsResponse(
        archived_urls=url_count,
        total_artifacts=artifact_count,
        successful_artifacts=success_count,
        summaries=summary_count,
        total_size_bytes=total_size,
        archivers=archiver_stats,
    )


@router.get("/system/archivers", response_model=List[str], dependencies=[Depends(rate_limit_admin)])
async def list_archivers():
    """
    List available archivers.

    Replaces: GET /admin/archivers

    Returns the names of all configured archiver types.

    Returns:
    [
        "monolith",
        "pdf",
        "readability",
        "screenshot",
        "singlefile"
    ]
    """
    return sorted(AVAILABLE_ARCHIVERS)


@router.post("/system/summarize", response_model=SummarizeResponse, dependencies=[Depends(rate_limit_admin)])
async def trigger_summarization(
    request: SummarizeRequest,
):
    """
    Manually trigger AI summarization for an article.

    Replaces: POST /admin/summarize

    Finds the article by item_id or URL and queues it for summarization.
    Requires either item_id or url.

    Request body:
    {
        "rowid": 123,           # DEPRECATED: No longer used (Firestore has no row IDs)
        "item_id": "article-123",  # Option 1: Article item_id (preferred)
        "url": "https://..."    # Option 2: Article URL
    }

    Returns:
    {
        "ok": true,
        "archived_url_id": null,  # Deprecated (always null in Firestore)
        "summary_created": false,  # false = queued, not yet created
        "task_id": "abc123"
    }
    """
    if not settings.summarization.enabled:
        raise HTTPException(status_code=503, detail="Summarization is disabled")

    from shared.firestore import get_article, query_by_url

    item_id: Optional[str] = None
    article = None

    # Find the article by item_id or URL
    if request.item_id:
        safe_id = sanitize_filename(request.item_id.strip())
        article = get_article(safe_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        item_id = safe_id

    elif request.url:
        articles = query_by_url(str(request.url))
        if not articles:
            raise HTTPException(status_code=404, detail="Article not found for URL")
        # Use first match (should only be one)
        article = articles[0]
        item_id = article.get("item_id")

    elif request.rowid is not None:
        # DEPRECATED: rowid is a PostgreSQL concept, not supported in Firestore
        raise HTTPException(
            status_code=400,
            detail="rowid lookup is deprecated. Use item_id or url instead."
        )

    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either item_id or url"
        )

    if not item_id:
        raise HTTPException(status_code=404, detail="Unable to resolve article")

    # Queue summarization task
    task_id = uuid.uuid4().hex

    celery_app.send_task(
        "services.summarization_worker.tasks.summarize_article",
        kwargs={
            "item_id": item_id,
            "archived_url_id": None,  # Deprecated parameter, kept for worker compatibility
            "force": True,
        },
        queue="summarization",
    )

    logger.info(
        "Summarization task queued",
        extra={"item_id": item_id, "task_id": task_id},
    )

    return SummarizeResponse(
        ok=True,
        archived_url_id=None,  # Deprecated (Firestore doesn't use integer IDs)
        summary_created=False,  # It's queued, not yet created
        task_id=task_id,
    )


@router.post("/system/commands", response_model=CommandResponse, dependencies=[Depends(rate_limit_admin)])
async def send_command(
    request_app: Request,
    command: CommandRequest,
):
    """
    Send command to HyperTerm runner.

    Replaces: POST /ht/send

    Executes a command in the HyperTerm runner and optionally waits for completion.
    Requires ht_runner to be initialized in app state.

    Request body:
    {
        "payload": "ls -la",        # Command to execute
        "wait_marker": "DONE",      # Optional: Wait for this marker in output
        "timeout": 15.0             # Timeout in seconds (default: 15.0)
    }

    Returns:
    {
        "ok": true,
        "exit_code": 0  # null if wait_marker not provided
    }
    """
    ht = getattr(request_app.app.state, "ht_runner", None)
    if ht is None:
        raise HTTPException(status_code=500, detail="HyperTerm runner not initialized")

    # Serialize access to ht via its internal lock
    with ht.lock if hasattr(ht, "lock") else ExitStack():
        ht.send_input(command.payload)
        rc = None
        if command.wait_marker:
            rc = ht.wait_for_done_marker(command.wait_marker, timeout=command.timeout)

    logger.info(
        "Command sent to HyperTerm",
        extra={"payload": command.payload, "exit_code": rc}
    )

    return CommandResponse(ok=True, exit_code=rc)
