from __future__ import annotations

from typing import Any, Dict

from celery.utils.log import get_task_logger

from celery_app import celery_app
from celery_worker_runtime import get_worker_runtime
from task_manager.archiver import BatchItem

logger = get_task_logger(__name__)


@celery_app.task(name="htbase.archive.process_item")
def process_archiver_item(payload: Dict[str, Any]) -> None:
    """Run a single archiver item inside a Celery worker."""
    task_id = payload.get("task_id") or "unknown"
    item_data = payload.get("item") or {}
    runtime = get_worker_runtime()

    try:
        batch_item = BatchItem(**item_data)
    except TypeError as exc:
        logger.error("Invalid batch payload", extra={"payload": item_data, "error": str(exc)})
        return

    logger.info(
        "Celery worker processing archiver item",
        extra={
            "task_id": task_id,
            "archiver": batch_item.archiver_name,
            "item_id": batch_item.item_id,
        },
    )

    runtime.archiver_task_manager._process_item(task_id=task_id, item=batch_item)

    logger.info(
        "Completed Celery archiver item",
        extra={
            "task_id": task_id,
            "archiver": batch_item.archiver_name,
            "item_id": batch_item.item_id,
        },
    )


__all__ = ["process_archiver_item"]
