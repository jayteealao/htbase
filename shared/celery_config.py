"""
Celery configuration for HTBase microservices.

This module provides the centralized Celery application configuration
used by all worker services.
"""

from __future__ import annotations

import os
from typing import Any

from celery import Celery
from kombu import Exchange, Queue


def get_redis_url() -> str:
    """Get Redis URL from environment."""
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = os.getenv("REDIS_PORT", "6379")
    redis_db = os.getenv("REDIS_DB", "0")
    redis_password = os.getenv("REDIS_PASSWORD", "")

    if redis_password:
        return f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
    return f"redis://{redis_host}:{redis_port}/{redis_db}"


# Create Celery application
celery_app = Celery(
    "htbase",
    broker=os.getenv("CELERY_BROKER_URL", get_redis_url()),
    backend=os.getenv("CELERY_RESULT_BACKEND", get_redis_url()),
)

# Define exchanges
default_exchange = Exchange("default", type="direct")
archive_exchange = Exchange("archive", type="direct")
summarization_exchange = Exchange("summarization", type="direct")
storage_exchange = Exchange("storage", type="direct")

# Define queues with routing
celery_app.conf.task_queues = (
    # Default queue
    Queue("default", default_exchange, routing_key="default"),

    # Archive worker queues - one per archiver type
    Queue("archive.singlefile", archive_exchange, routing_key="archive.singlefile"),
    Queue("archive.monolith", archive_exchange, routing_key="archive.monolith"),
    Queue("archive.readability", archive_exchange, routing_key="archive.readability"),
    Queue("archive.pdf", archive_exchange, routing_key="archive.pdf"),
    Queue("archive.screenshot", archive_exchange, routing_key="archive.screenshot"),

    # Summarization worker queue
    Queue("summarization", summarization_exchange, routing_key="summarization"),

    # Storage worker queue
    Queue("storage", storage_exchange, routing_key="storage"),
)

# Task routing configuration
celery_app.conf.task_routes = {
    # Archive tasks - route to archiver-specific queues
    "services.archive_worker.tasks.archive_singlefile": {"queue": "archive.singlefile"},
    "services.archive_worker.tasks.archive_monolith": {"queue": "archive.monolith"},
    "services.archive_worker.tasks.archive_readability": {"queue": "archive.readability"},
    "services.archive_worker.tasks.archive_pdf": {"queue": "archive.pdf"},
    "services.archive_worker.tasks.archive_screenshot": {"queue": "archive.screenshot"},

    # Summarization tasks
    "services.summarization_worker.tasks.summarize_article": {"queue": "summarization"},
    "services.summarization_worker.tasks.extract_entities": {"queue": "summarization"},
    "services.summarization_worker.tasks.generate_tags": {"queue": "summarization"},

    # Storage tasks
    "services.storage_worker.tasks.upload_to_gcs": {"queue": "storage"},
    "services.storage_worker.tasks.download_from_gcs": {"queue": "storage"},
    "services.storage_worker.tasks.cleanup_local_files": {"queue": "storage"},
}

# Celery configuration
celery_app.conf.update(
    # Task execution settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task result settings
    result_expires=86400,  # 24 hours
    result_extended=True,  # Include task name in result

    # Task acknowledgment settings
    task_acks_late=True,  # Acknowledge after task completes
    task_reject_on_worker_lost=True,  # Reject task if worker dies

    # Worker settings
    worker_prefetch_multiplier=1,  # Disable prefetching for fair distribution
    worker_concurrency=int(os.getenv("CELERY_CONCURRENCY", "4")),

    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,

    # Monitoring
    task_track_started=True,
    task_send_sent_event=True,
    worker_send_task_events=True,

    # Beat scheduler (for periodic tasks)
    beat_schedule={
        "cleanup-expired-local-files": {
            "task": "services.storage_worker.tasks.cleanup_expired_files",
            "schedule": 3600.0,  # Every hour
        },
        "retry-failed-uploads": {
            "task": "services.storage_worker.tasks.retry_failed_uploads",
            "schedule": 300.0,  # Every 5 minutes
        },
    },
)


def configure_for_worker(worker_type: str) -> None:
    """
    Configure Celery for a specific worker type.

    Args:
        worker_type: One of 'archive', 'summarization', 'storage'
    """
    if worker_type == "archive":
        # Archive workers need more memory and longer timeouts
        celery_app.conf.update(
            task_time_limit=600,  # 10 minutes
            task_soft_time_limit=540,  # 9 minutes
        )
    elif worker_type == "summarization":
        # Summarization workers need moderate resources
        celery_app.conf.update(
            task_time_limit=300,  # 5 minutes
            task_soft_time_limit=270,  # 4.5 minutes
        )
    elif worker_type == "storage":
        # Storage workers handle I/O-bound tasks
        celery_app.conf.update(
            task_time_limit=180,  # 3 minutes
            task_soft_time_limit=150,  # 2.5 minutes
        )


def get_task_info(task_id: str) -> dict[str, Any]:
    """
    Get information about a Celery task.

    Args:
        task_id: The Celery task ID

    Returns:
        Dictionary with task status and result
    """
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=celery_app)

    info: dict[str, Any] = {
        "task_id": task_id,
        "status": result.status,
        "ready": result.ready(),
        "successful": result.successful() if result.ready() else None,
    }

    if result.ready():
        try:
            info["result"] = result.result
        except Exception as e:
            info["error"] = str(e)

    if result.failed():
        info["error"] = str(result.result)
        info["traceback"] = result.traceback

    return info
