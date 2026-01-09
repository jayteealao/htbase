"""
Migration Worker entry point.

Starts the Celery worker for data migration tasks.
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

# Configure worker for migration tasks
configure_for_worker("migration")

# Configure logging
settings = get_settings()
configure_logging(settings)


if __name__ == "__main__":
    # Start worker on migration queue
    celery_app.worker_main(
        argv=[
            "worker",
            "--queues=migration",
            f"--concurrency={os.getenv('CELERY_CONCURRENCY', '1')}",
            f"--loglevel={settings.log_level}",
            "--hostname=migration-worker@%h",
            # Conservative settings for long-running migration tasks
            "--max-tasks-per-child=10",
            "--time-limit=3600",  # 1 hour per task
            "--soft-time-limit=3300",  # 55 minutes soft limit
        ]
    )
