"""
Archive Worker entry point.

Starts the Celery worker for archive tasks.
"""

from __future__ import annotations

import os

from shared.config import get_settings, configure_logging
from shared.infrastructure.celery import celery_app, configure_for_worker

# Import archiver tasks to register them with Celery
from app.celery_tasks import (  # noqa: F401
    archive_singlefile,
    archive_monolith,
    archive_readability,
    archive_pdf,
    archive_screenshot,
)

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
