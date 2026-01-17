"""
Task and queue monitoring API routes.

Provides endpoints for checking Celery queue status and worker health.

Note: Task status tracking has been simplified in Firestore migration.
Individual task tracking (by task_id) is no longer supported.
Use /artifacts/pending to monitor pending work.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from shared.auth import verify_api_key
from shared.celery_config import celery_app
from shared.rate_limit import rate_limit_status, rate_limit_admin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/tasks/queue-stats", dependencies=[Depends(rate_limit_status)])
async def get_queue_stats():
    """
    Get Celery queue statistics.

    Replaces: GET /queue/stats

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
