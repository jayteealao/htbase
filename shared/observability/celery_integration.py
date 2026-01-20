"""Celery integration for wide-event logging in workers.

Provides signal handlers and task decorators for Archive and Summarization workers.
"""

import time
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from functools import wraps

from .correlation import set_request_id, set_correlation_id, generate_request_id
from .events import (
    ArchiveProcessingEvent,
    SummarizationEvent,
    ArticleContext,
    Outcome,
    ErrorDetails,
    ProcessingContext,
    SummarizationMetrics,
    ContentContext,
    emit_wide_event,
)
from shared.metrics import (
    archive_tasks_total,
    archive_task_duration_seconds,
    archive_file_size_bytes,
    summarization_tasks_total,
    summarization_task_duration_seconds,
    summarization_tokens_used,
)

logger = logging.getLogger(__name__)


def extract_correlation_from_task(task_kwargs: Dict[str, Any]) -> tuple[str, Optional[str]]:
    """Extract or generate correlation IDs from Celery task kwargs.

    Args:
        task_kwargs: Task keyword arguments

    Returns:
        Tuple of (request_id, correlation_id)
    """
    # Check if correlation IDs were passed from API Gateway
    request_id = task_kwargs.get("request_id")
    correlation_id = task_kwargs.get("correlation_id")

    # Generate new request ID if not provided
    if not request_id:
        request_id = generate_request_id()

    return request_id, correlation_id


def setup_celery_signals(celery_app, service_name: str, version: str = "unknown"):
    """Set up Celery signals for wide-event logging.

    This installs signal handlers that set up correlation context for each task.

    Args:
        celery_app: The Celery app instance
        service_name: Service name (archive-worker, summarization-worker)
        version: Service version
    """
    from celery import signals

    @signals.task_prerun.connect
    def setup_correlation_context(task_id, task, args, kwargs, **signal_kwargs):
        """Set up correlation context before task execution."""
        request_id, correlation_id = extract_correlation_from_task(kwargs)

        # Set in context for this task
        set_request_id(request_id)
        if correlation_id:
            set_correlation_id(correlation_id)

        # Log task start
        logger.info(
            f"Task started: {task.name}",
            extra={
                "task_id": task_id,
                "task_name": task.name,
                "request_id": request_id,
                "correlation_id": correlation_id,
                "service": service_name,
            },
        )


class ArchiveTaskContext:
    """Context manager for archive task wide events."""

    def __init__(
        self,
        task_id: str,
        archiver: str,
        item_id: str,
        url: str,
        service_name: str,
        version: str,
    ):
        self.task_id = task_id
        self.archiver = archiver
        self.item_id = item_id
        self.url = url
        self.service_name = service_name
        self.version = version
        self.start_time = None
        self.event: Optional[ArchiveProcessingEvent] = None

    def __enter__(self):
        """Initialize wide event on task start."""
        from .correlation import get_request_id, get_correlation_id

        self.start_time = time.time()

        self.event = ArchiveProcessingEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            request_id=get_request_id() or "unknown",
            correlation_id=get_correlation_id(),
            service=self.service_name,
            version=self.version,
            task_id=self.task_id,
            archiver=self.archiver,
            article=ArticleContext(
                id=self.item_id,
                url=self.url,  # Should be sanitized by caller
            ),
        )

        return self

    def mark_success(
        self,
        exit_code: int = 0,
        gcs_path: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        upload_duration_ms: Optional[int] = None,
        command_duration_ms: Optional[int] = None,
    ):
        """Mark the task as successful with metrics."""
        from .events import CommandExecution, StorageMetrics

        duration_ms = int((time.time() - self.start_time) * 1000)
        duration_seconds = duration_ms / 1000.0

        self.event.outcome = Outcome.SUCCESS
        self.event.duration_ms = duration_ms
        self.event.processing = ProcessingContext(
            duration_ms=duration_ms,
            outcome=Outcome.SUCCESS,
            retry_attempt=0,  # TODO: Get from Celery task
            command=CommandExecution(
                exit_code=exit_code,
                duration_ms=command_duration_ms or duration_ms,
                timeout_ms=60000,  # TODO: Get from config
            ) if command_duration_ms else None,
            storage=StorageMetrics(
                gcs_path=gcs_path,
                file_size_bytes=file_size_bytes or 0,
                upload_duration_ms=upload_duration_ms or 0,
            ) if gcs_path else None,
        )

        # Emit Prometheus metrics
        archive_tasks_total.labels(archiver=self.archiver, status="success").inc()
        archive_task_duration_seconds.labels(archiver=self.archiver, status="success").observe(duration_seconds)
        if file_size_bytes:
            archive_file_size_bytes.labels(archiver=self.archiver).observe(file_size_bytes)

    def mark_error(
        self,
        error: Exception,
        error_code: str = "unknown_error",
        retriable: bool = True,
        exit_code: Optional[int] = None,
    ):
        """Mark the task as failed with error details."""
        duration_ms = int((time.time() - self.start_time) * 1000)
        duration_seconds = duration_ms / 1000.0

        self.event.outcome = Outcome.ERROR
        self.event.duration_ms = duration_ms
        self.event.error = ErrorDetails(
            type=type(error).__name__,
            message=str(error),
            code=error_code,
            retriable=retriable,
            command_exit_code=exit_code,
        )

        # Emit Prometheus metrics
        archive_tasks_total.labels(archiver=self.archiver, status="failed").inc()
        archive_task_duration_seconds.labels(archiver=self.archiver, status="failed").observe(duration_seconds)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Emit wide event on task completion."""
        if exc_type is not None and self.event.outcome != Outcome.ERROR:
            # Unhandled exception
            self.mark_error(exc_val, error_code="unhandled_exception", retriable=False)

        emit_wide_event(self.event)
        return False  # Don't suppress exceptions


class SummarizationTaskContext:
    """Context manager for summarization task wide events."""

    def __init__(
        self,
        task_id: str,
        item_id: str,
        service_name: str,
        version: str,
    ):
        self.task_id = task_id
        self.item_id = item_id
        self.service_name = service_name
        self.version = version
        self.start_time = None
        self.event: Optional[SummarizationEvent] = None

    def __enter__(self):
        """Initialize wide event on task start."""
        from .correlation import get_request_id, get_correlation_id

        self.start_time = time.time()

        self.event = SummarizationEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            request_id=get_request_id() or "unknown",
            correlation_id=get_correlation_id(),
            service=self.service_name,
            version=self.version,
            task_id=self.task_id,
            article=ArticleContext(
                id=self.item_id,
                url="",  # URL not always available in summarization context
            ),
        )

        return self

    def set_content_context(
        self,
        source: str,
        content_length_chars: int,
        word_count: Optional[int] = None,
    ):
        """Set content context being summarized."""
        self.event.content = ContentContext(
            source=source,
            content_length_chars=content_length_chars,
            word_count=word_count,
        )

    def mark_success(
        self,
        provider: str,
        model: str,
        tokens_used: Optional[int] = None,
        summary_length_chars: Optional[int] = None,
        entities_extracted: Optional[int] = None,
        tags_generated: Optional[int] = None,
    ):
        """Mark summarization as successful with metrics."""
        duration_ms = int((time.time() - self.start_time) * 1000)
        duration_seconds = duration_ms / 1000.0

        self.event.outcome = Outcome.SUCCESS
        self.event.duration_ms = duration_ms
        self.event.summarization = SummarizationMetrics(
            provider=provider,
            model=model,
            duration_ms=duration_ms,
            outcome=Outcome.SUCCESS,
            retry_attempt=0,  # TODO: Get from Celery task
            tokens_used=tokens_used,
            summary_length_chars=summary_length_chars,
            entities_extracted=entities_extracted,
            tags_generated=tags_generated,
        )

        # Emit Prometheus metrics
        summarization_tasks_total.labels(provider=provider, status="success").inc()
        summarization_task_duration_seconds.labels(provider=provider).observe(duration_seconds)
        if tokens_used:
            summarization_tokens_used.labels(provider=provider, model=model).observe(tokens_used)

    def mark_error(
        self,
        error: Exception,
        error_code: str = "unknown_error",
        retriable: bool = True,
        provider_error_code: Optional[str] = None,
        provider: str = "unknown",
    ):
        """Mark summarization as failed with error details."""
        duration_ms = int((time.time() - self.start_time) * 1000)
        duration_seconds = duration_ms / 1000.0

        self.event.outcome = Outcome.ERROR
        self.event.duration_ms = duration_ms
        self.event.error = ErrorDetails(
            type=type(error).__name__,
            message=str(error),
            code=error_code,
            retriable=retriable,
            provider_code=provider_error_code,
        )

        # Emit Prometheus metrics
        summarization_tasks_total.labels(provider=provider, status="failed").inc()
        summarization_task_duration_seconds.labels(provider=provider).observe(duration_seconds)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Emit wide event on task completion."""
        if exc_type is not None and self.event.outcome != Outcome.ERROR:
            # Unhandled exception
            self.mark_error(exc_val, error_code="unhandled_exception", retriable=False)

        emit_wide_event(self.event)
        return False  # Don't suppress exceptions
