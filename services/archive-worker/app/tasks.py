"""
Archive Worker Celery Tasks.

Defines Celery tasks for each archiver type with Firestore status tracking.

All archive tasks follow this pattern:
1. Update artifact status to "in_progress" in Firestore
2. Perform archiving operation (uploads directly to GCS)
3. Update artifact status to "success" or "failed" with GCS metadata
4. Return result

No local file storage - all artifacts are uploaded directly to GCS.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from celery import Task
from shared.infrastructure.celery import celery_app, configure_for_worker
from shared.config import get_settings, configure_logging
from shared.firestore import update_artifact, get_artifact
from shared.status import TaskStatus, ArchiveTaskResult
from shared.observability import (
    ArchiveTaskContext,
    set_request_id,
    set_correlation_id,
)
from shared.logging_utils import sanitize_url_for_logging

# Configure for archive worker
configure_for_worker("archive")

logger = logging.getLogger(__name__)


class ArchiveTask(Task):
    """Base class for archive tasks with common error handling."""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True
    max_retries = 3

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        logger.error(
            f"Archive task failed: {exc}",
            exc_info=True,
            extra={
                "task_id": task_id,
                "archiver": self.name.split("_")[-1],
                "kwargs": kwargs,
            },
        )

        # Update artifact status on final failure (after all retries exhausted)
        item_id = kwargs.get("item_id")
        archiver = self.name.split("_")[-1]

        if item_id and archiver:
            try:
                update_artifact(
                    item_id=item_id,
                    archiver=archiver,
                    status="failed",
                    exit_code=1,
                )
                logger.info(f"Updated artifact status to failed: {item_id}/{archiver}")
            except Exception as e:
                logger.error(f"Failed to update artifact status: {e}")


def _get_archiver(archiver_name: str):
    """Get archiver instance by name."""
    from app.archivers import get_archiver

    return get_archiver(archiver_name)


def _execute_archive_task(
    archiver_name: str,
    url: str,
    item_id: str,
    task_id: str,
) -> dict:
    """
    Execute archive task with Firestore status tracking.

    This function:
    1. Updates status to "in_progress" in Firestore
    2. Performs the archiving operation (uploads to GCS)
    3. Updates final status based on result
    4. Returns result dict

    Args:
        archiver_name: Name of archiver to use
        url: URL to archive
        item_id: Item identifier
        task_id: Celery task ID

    Returns:
        Archive result dictionary

    Raises:
        Exception: Any error during archiving
    """
    # Step 1: Update to in_progress
    update_artifact(
        item_id=item_id,
        archiver=archiver_name,
        status="in_progress",
    )

    # Step 2: Perform archiving (uploads directly to GCS)
    archiver = _get_archiver(archiver_name)
    result = archiver.archive_and_upload_to_gcs(url=url, item_id=item_id)

    # Step 3: Extract GCS metadata from result
    metadata = result.metadata or {}
    gcs_path = metadata.get("gcs_path")
    gcs_bucket = metadata.get("gcs_bucket")
    file_size = metadata.get("stored_size")

    # Step 4: Update final status in Firestore
    update_artifact(
        item_id=item_id,
        archiver=archiver_name,
        status="success" if result.success else "failed",
        gcs_path=gcs_path,
        gcs_bucket=gcs_bucket,
        file_size=file_size,
        exit_code=result.exit_code,
    )

    # Return result
    return {
        "success": result.success,
        "exit_code": result.exit_code,
        "gcs_path": gcs_path,
        "item_id": item_id,
        "archiver": archiver_name,
    }


def _store_readability_metadata(item_id: str, result: dict) -> None:
    """Post-processing hook for readability archiver to store metadata."""
    if not result["success"]:
        return

    try:
        archiver = _get_archiver("readability")
        # Get metadata from last run (stored in archiver instance)
        if hasattr(archiver, 'last_metadata') and archiver.last_metadata:
            from shared.firestore import update_metadata

            metadata = archiver.last_metadata
            update_metadata(
                item_id=item_id,
                word_count=metadata.get("word_count"),
                text_content=metadata.get("text"),
            )
            logger.info(f"Stored readability metadata for {item_id}")
    except Exception as e:
        logger.error(f"Failed to store metadata: {e}", exc_info=True)


def _create_archiver_task(archiver_name: str, post_process_hook=None):
    """Factory function to create archiver task functions.

    This eliminates duplication by creating tasks dynamically with the same pattern:
    1. Log start
    2. Execute archive task
    3. Run optional post-processing hook
    4. Log completion
    5. Return result

    Args:
        archiver_name: Name of archiver (e.g., 'singlefile', 'readability')
        post_process_hook: Optional function to call after successful archiving.
                          Signature: (item_id: str, result: dict) -> None

    Returns:
        Celery task function for the archiver
    """
    @celery_app.task(
        base=ArchiveTask,
        bind=True,
        name=f"services.archive_worker.tasks.archive_{archiver_name}"
    )
    def archiver_task(self, item_id: str, url: str, **kwargs) -> dict:
        """Archive URL using {archiver_name}.

        Uploads directly to GCS with no local file storage.

        Args:
            item_id: Item identifier
            url: URL to archive
            **kwargs: Additional arguments (request_id, correlation_id, etc.)

        Returns:
            Archive result dictionary
        """
        # Set up correlation context from kwargs
        request_id = kwargs.get("request_id")
        correlation_id = kwargs.get("correlation_id")

        if request_id:
            set_request_id(request_id)
        if correlation_id:
            set_correlation_id(correlation_id)

        # Create wide-event context manager
        with ArchiveTaskContext(
            task_id=self.request.id,
            archiver=archiver_name,
            item_id=item_id,
            url=sanitize_url_for_logging(url),
            service_name="archive-worker",
            version="2.0.0",
        ) as ctx:
            try:
                result = _execute_archive_task(
                    archiver_name=archiver_name,
                    url=url,
                    item_id=item_id,
                    task_id=self.request.id,
                )

                # Run post-processing hook if provided
                if post_process_hook and result["success"]:
                    try:
                        post_process_hook(item_id, result)
                    except Exception as e:
                        logger.error(
                            f"Post-processing failed for {archiver_name}: {e}",
                            exc_info=True
                        )

                # Mark success in wide event with metrics
                ctx.mark_success(
                    exit_code=result.get("exit_code", 0),
                    gcs_path=result.get("gcs_path"),
                    file_size_bytes=result.get("file_size"),
                )

                return result

            except Exception as e:
                # Mark error in wide event
                ctx.mark_error(
                    error=e,
                    error_code=type(e).__name__,
                    retriable=True,
                )
                raise

    # Update docstring with actual archiver name
    archiver_task.__doc__ = f"""Archive URL using {archiver_name}.

    Uploads directly to GCS with no local file storage.

    Args:
        item_id: Item identifier
        url: URL to archive

    Returns:
        Archive result dictionary
    """

    return archiver_task


# Generate archiver tasks using the factory pattern
# This eliminates code duplication - all tasks now share the same implementation
archive_singlefile = _create_archiver_task("singlefile")
archive_monolith = _create_archiver_task("monolith")
archive_readability = _create_archiver_task("readability", post_process_hook=_store_readability_metadata)
archive_pdf = _create_archiver_task("pdf")
archive_screenshot = _create_archiver_task("screenshot")
