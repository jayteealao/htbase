"""
Task status API routes.

Provides endpoints for checking task status and progress.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from shared.celery_config import celery_app, get_task_info
from shared.db import get_session_dependency, ArchivedUrl, ArchiveArtifact
from shared.models import TaskStatusResponse, TaskItemStatus

logger = logging.getLogger(__name__)

router = APIRouter()


def get_db():
    """Database session dependency."""
    from shared.db import get_session

    with get_session() as session:
        yield session


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    db: Session = Depends(get_db),
):
    """
    Get status of a task or batch of tasks.

    Returns status of all items associated with the task ID.
    """
    logger.debug("Task status request", extra={"task_id": task_id})

    # Find all artifacts with this task ID
    artifacts = (
        db.query(ArchiveArtifact, ArchivedUrl)
        .join(ArchivedUrl)
        .filter(ArchiveArtifact.task_id == task_id)
        .all()
    )

    if not artifacts:
        raise HTTPException(status_code=404, detail="Task not found")

    items = []
    completed = 0
    failed = 0
    pending = 0

    for artifact, archived_url in artifacts:
        status = artifact.status or "pending"

        if artifact.success:
            status = "success"
            completed += 1
        elif status == "failed" or (artifact.exit_code and artifact.exit_code != 0):
            status = "failed"
            failed += 1
        else:
            pending += 1

        items.append(
            TaskItemStatus(
                url=archived_url.url,
                id=archived_url.item_id or "",
                name=archived_url.name,
                status=status,
                exit_code=artifact.exit_code,
                saved_path=artifact.saved_path,
                db_rowid=artifact.id,
            )
        )

    total = len(items)
    if total == 0:
        overall_status = "pending"
        progress = 0.0
    elif pending > 0:
        overall_status = "in_progress"
        progress = (completed + failed) / total * 100
    elif failed == total:
        overall_status = "failed"
        progress = 100.0
    else:
        overall_status = "completed"
        progress = 100.0

    return TaskStatusResponse(
        task_id=task_id,
        status=overall_status,
        progress=progress,
        items=items,
    )


@router.get("/tasks/{task_id}/celery")
async def get_celery_task_info(task_id: str):
    """
    Get Celery task information.

    Returns the raw Celery task status and result.
    """
    try:
        info = get_task_info(task_id)
        return info
    except Exception as e:
        logger.error(f"Error getting Celery task info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    db: Session = Depends(get_db),
):
    """
    Cancel a pending task.

    Revokes any pending Celery tasks and marks artifacts as cancelled.
    """
    logger.info("Cancel task request", extra={"task_id": task_id})

    # Find artifacts
    artifacts = (
        db.query(ArchiveArtifact)
        .filter(
            ArchiveArtifact.task_id == task_id,
            ArchiveArtifact.status == "pending",
        )
        .all()
    )

    if not artifacts:
        raise HTTPException(status_code=404, detail="No pending tasks found")

    # Revoke Celery tasks
    celery_app.control.revoke(task_id, terminate=True)

    # Update artifact status
    for artifact in artifacts:
        artifact.status = "cancelled"

    db.commit()

    return {
        "message": f"Cancelled {len(artifacts)} task(s)",
        "task_id": task_id,
    }


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List recent tasks.

    Returns a paginated list of task IDs with summary status.
    """
    from sqlalchemy import func, distinct

    # Get distinct task IDs with counts
    query = db.query(
        ArchiveArtifact.task_id,
        func.count(ArchiveArtifact.id).label("total"),
        func.sum(func.cast(ArchiveArtifact.success, Integer)).label("completed"),
    ).group_by(ArchiveArtifact.task_id)

    if status:
        query = query.filter(ArchiveArtifact.status == status)

    query = query.order_by(ArchiveArtifact.task_id.desc())
    query = query.offset(offset).limit(limit)

    results = query.all()

    return {
        "tasks": [
            {
                "task_id": r.task_id,
                "total": r.total,
                "completed": r.completed or 0,
            }
            for r in results
            if r.task_id
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/queue/stats")
async def get_queue_stats():
    """
    Get Celery queue statistics.

    Returns information about queue lengths and worker status.
    """
    try:
        # Get active queues
        inspect = celery_app.control.inspect()

        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        scheduled = inspect.scheduled() or {}

        # Count tasks per queue
        active_count = sum(len(tasks) for tasks in active.values())
        reserved_count = sum(len(tasks) for tasks in reserved.values())
        scheduled_count = sum(len(tasks) for tasks in scheduled.values())

        # Get worker info
        stats = inspect.stats() or {}
        workers = list(stats.keys())

        return {
            "workers": workers,
            "active_tasks": active_count,
            "reserved_tasks": reserved_count,
            "scheduled_tasks": scheduled_count,
            "queues": {
                "archive.singlefile": _get_queue_length("archive.singlefile"),
                "archive.monolith": _get_queue_length("archive.monolith"),
                "archive.readability": _get_queue_length("archive.readability"),
                "archive.pdf": _get_queue_length("archive.pdf"),
                "archive.screenshot": _get_queue_length("archive.screenshot"),
                "summarization": _get_queue_length("summarization"),
                "storage": _get_queue_length("storage"),
            },
        }
    except Exception as e:
        logger.error(f"Error getting queue stats: {e}")
        return {
            "error": str(e),
            "workers": [],
            "active_tasks": 0,
        }


def _get_queue_length(queue_name: str) -> int:
    """Get approximate queue length from Redis."""
    try:
        from shared.config import get_settings

        settings = get_settings()
        import redis

        r = redis.from_url(settings.redis.url())
        return r.llen(queue_name)
    except Exception:
        return -1


# Import Integer for SQLAlchemy cast
from sqlalchemy import Integer
