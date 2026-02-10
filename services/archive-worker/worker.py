"""
Archive Worker entry point.

Starts the Celery worker for archive tasks.
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
configure_for_worker("archive")

# Configure logging
settings = get_settings()
configure_logging(settings)


if __name__ == "__main__":
    # Get queue from environment or use all archive queues
    queue = os.getenv("ARCHIVE_QUEUE", None)

    if queue:
        queues = [f"archive.{queue}"]
    else:
        queues = [
            "archive.singlefile",
            "archive.monolith",
            "archive.readability",
            "archive.pdf",
            "archive.screenshot",
        ]

    # Start worker
    celery_app.worker_main(
        argv=[
            "worker",
            f"--queues={','.join(queues)}",
            f"--concurrency={os.getenv('CELERY_CONCURRENCY', '2')}",
            f"--loglevel={settings.log_level}",
            "--hostname=archive-worker@%h",
        ]
    )
