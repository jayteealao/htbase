"""
Webhook notification tasks for async completion callbacks.

This module provides Celery tasks for notifying external systems when
archive workflows complete, fail, or reach other important states.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime
from typing import Any, Optional

from celery import Task

from shared.infrastructure.celery import celery_app, configure_for_worker
from shared.firestore import get_article

# Configure for archive worker
configure_for_worker("archive")

logger = logging.getLogger(__name__)


class WebhookEvent:
    """Webhook event types."""
    TASK_CREATED = "task.created"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    ARCHIVE_SUCCESS = "archive.success"
    ARCHIVE_FAILED = "archive.failed"


def _generate_signature(payload: dict, secret: str) -> str:
    """
    Generate HMAC-SHA256 signature for webhook payload.

    Args:
        payload: The JSON payload to sign
        secret: The webhook secret

    Returns:
        Signature in format "sha256=<hexdigest>"
    """
    # Sort keys for consistent signature
    payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')
    signature = hmac.new(
        secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"


class WebhookTask(Task):
    """Base class for webhook tasks with specialized error handling."""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600  # 10 minutes
    retry_jitter = True
    max_retries = 5
    default_retry_delay = 60  # 1 minute

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle webhook delivery failure."""
        logger.error(
            f"Webhook delivery failed after all retries: {exc}",
            exc_info=True,
            extra={
                "task_id": task_id,
                "webhook_url": kwargs.get("webhook_url"),
                "event": kwargs.get("event_type"),
            },
        )


@celery_app.task(
    base=WebhookTask,
    bind=True,
    name="services.archive_worker.tasks.notify_webhook"
)
def notify_webhook(
    self,
    workflow_id: str,
    webhook_url: str,
    webhook_secret: Optional[str],
    status_data: dict,
    event_type: str = WebhookEvent.TASK_COMPLETED,
) -> dict:
    """
    Send webhook notification when task completes.

    This task is called at the end of a workflow chain to notify
    external systems of completion status. It includes retry logic
    with exponential backoff for transient failures.

    Args:
        self: Celery task context (injected by bind=True)
        workflow_id: The workflow/task ID
        webhook_url: URL to POST the webhook to
        webhook_secret: HMAC secret for signing (optional but recommended)
        status_data: Status information from gather_status task
        event_type: Type of webhook event (default: task.completed)

    Returns:
        Dictionary with delivery status

    Raises:
        Exception: On delivery failure (triggers retry)
    """
    try:
        import httpx
    except ImportError:
        logger.error("httpx not installed, cannot send webhooks")
        raise ImportError("httpx is required for webhook delivery")

    logger.info(
        "Sending webhook notification",
        extra={
            "workflow_id": workflow_id,
            "webhook_url": webhook_url,
            "event": event_type,
            "has_secret": bool(webhook_secret),
        },
    )

    # Build webhook payload
    payload: dict[str, Any] = {
        "event": event_type,
        "task_id": workflow_id,
        "status": status_data.get("status", "unknown"),
        "items": status_data.get("items", []),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    # Generate signature if secret provided
    headers = {
        "Content-Type": "application/json",
        "X-HTBase-Event": event_type,
        "User-Agent": "HTBase-Webhook/1.0",
    }

    if webhook_secret:
        signature = _generate_signature(payload, webhook_secret)
        headers["X-HTBase-Signature"] = signature

    # Send webhook with timeout
    try:
        with httpx.Client() as client:
            response = client.post(
                webhook_url,
                json=payload,
                headers=headers,
                timeout=10.0,  # 10 second timeout
                follow_redirects=False,  # Don't follow redirects for security
            )

            # Check response status
            if response.status_code >= 500:
                # Server error - retry
                logger.warning(
                    f"Webhook endpoint returned {response.status_code}, retrying",
                    extra={
                        "status_code": response.status_code,
                        "webhook_url": webhook_url,
                        "attempt": self.request.retries + 1,
                    },
                )
                raise self.retry(exc=Exception(f"Server error: {response.status_code}"))

            elif response.status_code >= 400:
                # Client error - don't retry
                logger.error(
                    f"Webhook rejected by endpoint: {response.status_code}",
                    extra={
                        "status_code": response.status_code,
                        "webhook_url": webhook_url,
                        "response_body": response.text[:500],
                    },
                )
                # Don't raise - accept 4xx as permanent failure
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": f"Client error: {response.status_code}",
                }

            # Success
            logger.info(
                "Webhook delivered successfully",
                extra={
                    "webhook_url": webhook_url,
                    "status_code": response.status_code,
                    "workflow_id": workflow_id,
                },
            )

            return {
                "success": True,
                "status_code": response.status_code,
                "workflow_id": workflow_id,
            }

    except httpx.TimeoutException as e:
        logger.warning(
            f"Webhook delivery timed out, retrying",
            extra={
                "webhook_url": webhook_url,
                "attempt": self.request.retries + 1,
            },
        )
        raise self.retry(exc=e)

    except httpx.RequestError as e:
        logger.warning(
            f"Webhook delivery failed with network error, retrying: {e}",
            extra={
                "webhook_url": webhook_url,
                "attempt": self.request.retries + 1,
                "error_type": type(e).__name__,
            },
        )
        raise self.retry(exc=e)

    except Exception as e:
        logger.error(
            f"Unexpected error during webhook delivery: {e}",
            exc_info=True,
            extra={"webhook_url": webhook_url},
        )
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    name="services.archive_worker.tasks.gather_status"
)
def gather_status(
    self,
    previous_results: Any,
    item_id: str,
) -> dict:
    """
    Gather workflow status from Firestore for webhook payload.

    This task is called in a Celery chain after the archive tasks complete.
    It queries Firestore to collect the results of all archive operations
    for the given article.

    NOTE: This function was refactored to use Firestore instead of PostgreSQL.
    The signature changed from task_id to item_id. Callers in archives.py
    need to pass item_id instead of workflow_id/task_id.

    Args:
        self: Celery task context
        previous_results: Results from previous tasks in chain (ignored)
        item_id: The article item_id to gather status for

    Returns:
        Dictionary with status data suitable for webhook payload
    """
    logger.info(
        "Gathering workflow status from Firestore",
        extra={"item_id": item_id},
    )

    try:
        # Get article from Firestore
        article = get_article(item_id)

        if not article:
            logger.warning(
                f"No article found for item_id {item_id}",
                extra={"item_id": item_id},
            )
            return {
                "status": "unknown",
                "items": [],
                "task_id": item_id,  # Keep for backward compatibility
            }

        # Extract archive statuses from archives map
        archives = article.get("archives", {})

        if not archives:
            logger.warning(
                f"No archives found for article {item_id}",
                extra={"item_id": item_id},
            )
            return {
                "status": "unknown",
                "items": [],
                "task_id": item_id,
            }

        # Build status data
        items = []
        all_success = True
        any_success = False

        for archiver_name, artifact_data in archives.items():
            # Determine artifact status
            is_success = artifact_data.get("success") or artifact_data.get("status") == "success"

            item_status = {
                "url": article.get("url"),
                "id": item_id,
                "archiver": archiver_name,
                "status": "success" if is_success else "failed",
                "exit_code": artifact_data.get("exit_code"),
                "saved_path": artifact_data.get("gcs_path") or artifact_data.get("saved_path"),
            }

            items.append(item_status)

            if is_success:
                any_success = True
            else:
                all_success = False

        # Determine overall status
        if all_success:
            overall_status = "completed"
        elif any_success:
            overall_status = "partial"
        else:
            overall_status = "failed"

        status_data = {
            "status": overall_status,
            "items": items,
            "task_id": item_id,  # Keep for backward compatibility
        }

        logger.info(
            "Status gathered from Firestore",
            extra={
                "item_id": item_id,
                "status": overall_status,
                "item_count": len(items),
            },
        )

        return status_data

    except Exception as e:
        logger.error(
            f"Failed to gather status: {e}",
            exc_info=True,
            extra={"item_id": item_id},
        )
        # Return error status
        return {
            "status": "error",
            "items": [],
            "task_id": item_id,
            "error": str(e),
        }
