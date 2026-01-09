"""
Sync Worker entry point.

Starts the Celery worker for data sync tasks.
"""

from __future__ import annotations

import os
import sys

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from shared.config import get_settings, configure_logging
from shared.celery_config import celery_app, configure_for_worker

# Import tasks to register them
from app import tasks  # noqa: F401

# Configure worker for sync tasks
configure_for_worker("sync")

# Configure logging
settings = get_settings()
configure_logging(settings)


if __name__ == "__main__":
    # Start worker on sync queue
    celery_app.worker_main(
        argv=[
            "worker",
            "--queues=sync",
            f"--concurrency={os.getenv('CELERY_CONCURRENCY', '1')}",
            f"--loglevel={settings.log_level}",
            "--hostname=sync-worker@%h",
            # Conservative settings for long-running sync tasks
            "--max-tasks-per-child=10",
            "--time-limit=3600",  # 1 hour per task
            "--soft-time-limit=3300",  # 55 minutes soft limit
        ]
    )
