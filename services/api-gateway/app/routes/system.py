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
from sqlalchemy import func, Integer
from sqlalchemy.orm import Session

from shared.auth import verify_api_key
from shared.celery_config import celery_app
from shared.config import get_settings
from shared.db import ArchivedUrl, ArchiveArtifact, ArticleSummary
from shared.rate_limit import rate_limit_admin
from shared.utils import sanitize_filename

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
async def get_system_stats(db: Session = Depends(get_db)):
    """
    Get system statistics.

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

    return SystemStatsResponse(
        archived_urls=url_count,
        total_artifacts=artifact_count,
        successful_artifacts=success_count,
        summaries=summary_count,
        total_size_bytes=total_size,
        archivers={
            stat.archiver: {
                "total": stat.total,
                "success": stat.success or 0,
            }
            for stat in archiver_stats
        },
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
    db: Session = Depends(get_db),
):
    """
    Manually trigger AI summarization for an article.

    Replaces: POST /admin/summarize

    Finds the article by rowid, item_id, or URL and queues it for summarization.
    Requires at least one lookup field (rowid, item_id, or url).

    Request body:
    {
        "rowid": 123,           # Option 1: Artifact row ID
        "item_id": "article-123",  # Option 2: Article item_id
        "url": "https://..."    # Option 3: Article URL
    }

    Returns:
    {
        "ok": true,
        "archived_url_id": 456,
        "summary_created": false,  # false = queued, not yet created
        "task_id": "abc123"
    }
    """
    if not settings.summarization.enabled:
        raise HTTPException(status_code=503, detail="Summarization is disabled")

    archived_url_id: Optional[int] = None
    item_id: Optional[str] = None

    # Find the article by rowid, item_id, or URL
    if request.rowid is not None:
        artifact = db.query(ArchiveArtifact).filter(ArchiveArtifact.id == request.rowid).first()
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        archived_url_id = artifact.archived_url_id

        archived_url = db.query(ArchivedUrl).filter(ArchivedUrl.id == archived_url_id).first()
        if archived_url:
            item_id = archived_url.item_id

    elif request.item_id:
        safe_id = sanitize_filename(request.item_id.strip())
        archived_url = db.query(ArchivedUrl).filter(ArchivedUrl.item_id == safe_id).first()
        if not archived_url:
            raise HTTPException(status_code=404, detail="Article not found")
        archived_url_id = archived_url.id
        item_id = archived_url.item_id

    elif request.url:
        archived_url = db.query(ArchivedUrl).filter(ArchivedUrl.url == request.url).first()
        if not archived_url:
            raise HTTPException(status_code=404, detail="Article not found")
        archived_url_id = archived_url.id
        item_id = archived_url.item_id

    else:
        raise HTTPException(
            status_code=400,
            detail="Provide one of: rowid, item_id, or url"
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
