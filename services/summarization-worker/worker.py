"""
Summarization Worker entry point.

Starts the Celery worker for summarization tasks.
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

# Configure worker
configure_for_worker("summarization")

# Configure logging
settings = get_settings()
configure_logging(settings)


if __name__ == "__main__":
    # Start worker
    celery_app.worker_main(
        argv=[
            "worker",
            "--queues=summarization",
            f"--concurrency={os.getenv('CELERY_CONCURRENCY', '4')}",
            f"--loglevel={settings.log_level}",
            "--hostname=summarization-worker@%h",
        ]
    )
