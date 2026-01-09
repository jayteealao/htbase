from __future__ import annotations

from celery import Celery

from core.config import get_settings
from core.logging import setup_logging


_settings = get_settings()
setup_logging(_settings.log_level)

celery_app = Celery("htbase")
celery_app.conf.update(
    broker_url=_settings.celery.broker_url,
    result_backend=_settings.celery.result_backend,
    task_always_eager=_settings.celery.task_always_eager,
    task_default_queue=_settings.celery.default_queue,
    task_acks_late=True,
)
celery_app.autodiscover_tasks(["celery_tasks"])

__all__ = ["celery_app"]
