import os
from celery import Celery

# Get Redis URL from environment or default to localhost
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "ht_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "common.tasks.archive_singlefile": {"queue": "browser_queue"},
        "common.tasks.archive_pdf": {"queue": "browser_queue"},
        "common.tasks.archive_screenshot": {"queue": "browser_queue"},
        "common.tasks.archive_monolith": {"queue": "monolith_queue"},
        "common.tasks.generate_summary": {"queue": "summary_queue"},
    },
)

# Task Signatures
TASK_ARCHIVE_SINGLEFILE = "common.tasks.archive_singlefile"
TASK_ARCHIVE_PDF = "common.tasks.archive_pdf"
TASK_ARCHIVE_SCREENSHOT = "common.tasks.archive_screenshot"
TASK_ARCHIVE_MONOLITH = "common.tasks.archive_monolith"
TASK_GENERATE_SUMMARY = "common.tasks.generate_summary"

ARCHIVER_TASK_MAP = {
    "monolith": TASK_ARCHIVE_MONOLITH,
    "singlefile": TASK_ARCHIVE_SINGLEFILE,
    "pdf": TASK_ARCHIVE_PDF,
    "screenshot": TASK_ARCHIVE_SCREENSHOT,
    "singlefile-cli": TASK_ARCHIVE_SINGLEFILE,
}
