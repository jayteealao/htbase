"""
Archive Worker Celery Tasks.

Defines Celery tasks for each archiver type.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from celery import Task
from shared.celery_config import celery_app, configure_for_worker
from shared.config import get_settings, configure_logging
from shared.db import get_session, ArchiveArtifact
from shared.status import TaskStatus, ArchiveTaskResult

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

        # Update artifact status
        artifact_id = kwargs.get("artifact_id")
        if artifact_id:
            try:
                with get_session() as session:
                    artifact = session.query(ArchiveArtifact).get(artifact_id)
                    if artifact:
                        artifact.status = "failed"
                        artifact.success = False
                        artifact.updated_at = datetime.utcnow()
            except Exception as e:
                logger.error(f"Failed to update artifact status: {e}")


def _update_artifact_status(
    artifact_id: int,
    status: str,
    success: bool = False,
    exit_code: Optional[int] = None,
    saved_path: Optional[str] = None,
    size_bytes: Optional[int] = None,
) -> None:
    """Update artifact status in database."""
    with get_session() as session:
        artifact = session.query(ArchiveArtifact).get(artifact_id)
        if artifact:
            artifact.status = status
            artifact.success = success
            artifact.exit_code = exit_code
            artifact.saved_path = saved_path
            artifact.size_bytes = size_bytes
            artifact.updated_at = datetime.utcnow()


def _get_archiver(archiver_name: str):
    """Get archiver instance by name."""
    from app.archivers import get_archiver

    return get_archiver(archiver_name)


@celery_app.task(base=ArchiveTask, bind=True, name="services.archive_worker.tasks.archive_singlefile")
def archive_singlefile(
    self,
    item_id: str,
    url: str,
    archived_url_id: int,
    artifact_id: int,
) -> dict:
    """
    Archive URL using SingleFile CLI.

    Args:
        item_id: Item identifier
        url: URL to archive
        archived_url_id: Database ID of archived URL
        artifact_id: Database ID of artifact record

    Returns:
        Archive result dictionary
    """
    logger.info(
        "Starting singlefile archive",
        extra={
            "task_id": self.request.id,
            "item_id": item_id,
            "url": url,
        },
    )

    # Update status to in_progress
    _update_artifact_status(artifact_id, "in_progress")

    try:
        archiver = _get_archiver("singlefile")
        result = archiver.archive(url=url, item_id=item_id)

        # Calculate file size
        size_bytes = None
        if result.success and result.saved_path:
            path = Path(result.saved_path)
            if path.exists():
                size_bytes = path.stat().st_size

        _update_artifact_status(
            artifact_id,
            status="success" if result.success else "failed",
            success=result.success,
            exit_code=result.exit_code,
            saved_path=result.saved_path,
            size_bytes=size_bytes,
        )

        logger.info(
            "Singlefile archive completed",
            extra={
                "task_id": self.request.id,
                "success": result.success,
                "saved_path": result.saved_path,
            },
        )

        return {
            "success": result.success,
            "exit_code": result.exit_code,
            "saved_path": result.saved_path,
            "item_id": item_id,
            "archiver": "singlefile",
        }

    except Exception as e:
        _update_artifact_status(artifact_id, "failed", success=False)
        raise


@celery_app.task(base=ArchiveTask, bind=True, name="services.archive_worker.tasks.archive_monolith")
def archive_monolith(
    self,
    item_id: str,
    url: str,
    archived_url_id: int,
    artifact_id: int,
) -> dict:
    """Archive URL using Monolith."""
    logger.info(
        "Starting monolith archive",
        extra={"task_id": self.request.id, "item_id": item_id},
    )

    _update_artifact_status(artifact_id, "in_progress")

    try:
        archiver = _get_archiver("monolith")
        result = archiver.archive(url=url, item_id=item_id)

        size_bytes = None
        if result.success and result.saved_path:
            path = Path(result.saved_path)
            if path.exists():
                size_bytes = path.stat().st_size

        _update_artifact_status(
            artifact_id,
            status="success" if result.success else "failed",
            success=result.success,
            exit_code=result.exit_code,
            saved_path=result.saved_path,
            size_bytes=size_bytes,
        )

        return {
            "success": result.success,
            "exit_code": result.exit_code,
            "saved_path": result.saved_path,
            "item_id": item_id,
            "archiver": "monolith",
        }

    except Exception as e:
        _update_artifact_status(artifact_id, "failed", success=False)
        raise


@celery_app.task(base=ArchiveTask, bind=True, name="services.archive_worker.tasks.archive_readability")
def archive_readability(
    self,
    item_id: str,
    url: str,
    archived_url_id: int,
    artifact_id: int,
) -> dict:
    """Archive URL using Readability."""
    logger.info(
        "Starting readability archive",
        extra={"task_id": self.request.id, "item_id": item_id},
    )

    _update_artifact_status(artifact_id, "in_progress")

    try:
        archiver = _get_archiver("readability")
        result = archiver.archive(url=url, item_id=item_id)

        size_bytes = None
        if result.success and result.saved_path:
            path = Path(result.saved_path)
            if path.exists():
                size_bytes = path.stat().st_size

        _update_artifact_status(
            artifact_id,
            status="success" if result.success else "failed",
            success=result.success,
            exit_code=result.exit_code,
            saved_path=result.saved_path,
            size_bytes=size_bytes,
        )

        # Store metadata if available
        if result.success and result.metadata:
            _store_metadata(archived_url_id, result.metadata)

        return {
            "success": result.success,
            "exit_code": result.exit_code,
            "saved_path": result.saved_path,
            "item_id": item_id,
            "archiver": "readability",
            "metadata": result.metadata,
        }

    except Exception as e:
        _update_artifact_status(artifact_id, "failed", success=False)
        raise


@celery_app.task(base=ArchiveTask, bind=True, name="services.archive_worker.tasks.archive_pdf")
def archive_pdf(
    self,
    item_id: str,
    url: str,
    archived_url_id: int,
    artifact_id: int,
) -> dict:
    """Archive URL as PDF."""
    logger.info(
        "Starting pdf archive",
        extra={"task_id": self.request.id, "item_id": item_id},
    )

    _update_artifact_status(artifact_id, "in_progress")

    try:
        archiver = _get_archiver("pdf")
        result = archiver.archive(url=url, item_id=item_id)

        size_bytes = None
        if result.success and result.saved_path:
            path = Path(result.saved_path)
            if path.exists():
                size_bytes = path.stat().st_size

        _update_artifact_status(
            artifact_id,
            status="success" if result.success else "failed",
            success=result.success,
            exit_code=result.exit_code,
            saved_path=result.saved_path,
            size_bytes=size_bytes,
        )

        return {
            "success": result.success,
            "exit_code": result.exit_code,
            "saved_path": result.saved_path,
            "item_id": item_id,
            "archiver": "pdf",
        }

    except Exception as e:
        _update_artifact_status(artifact_id, "failed", success=False)
        raise


@celery_app.task(base=ArchiveTask, bind=True, name="services.archive_worker.tasks.archive_screenshot")
def archive_screenshot(
    self,
    item_id: str,
    url: str,
    archived_url_id: int,
    artifact_id: int,
) -> dict:
    """Archive URL as screenshot."""
    logger.info(
        "Starting screenshot archive",
        extra={"task_id": self.request.id, "item_id": item_id},
    )

    _update_artifact_status(artifact_id, "in_progress")

    try:
        archiver = _get_archiver("screenshot")
        result = archiver.archive(url=url, item_id=item_id)

        size_bytes = None
        if result.success and result.saved_path:
            path = Path(result.saved_path)
            if path.exists():
                size_bytes = path.stat().st_size

        _update_artifact_status(
            artifact_id,
            status="success" if result.success else "failed",
            success=result.success,
            exit_code=result.exit_code,
            saved_path=result.saved_path,
            size_bytes=size_bytes,
        )

        return {
            "success": result.success,
            "exit_code": result.exit_code,
            "saved_path": result.saved_path,
            "item_id": item_id,
            "archiver": "screenshot",
        }

    except Exception as e:
        _update_artifact_status(artifact_id, "failed", success=False)
        raise


def _store_metadata(archived_url_id: int, metadata: dict) -> None:
    """Store metadata from readability extraction."""
    from shared.db import UrlMetadata

    with get_session() as session:
        existing = (
            session.query(UrlMetadata)
            .filter(UrlMetadata.archived_url_id == archived_url_id)
            .first()
        )

        if existing:
            # Update existing
            for key, value in metadata.items():
                if hasattr(existing, key) and value is not None:
                    setattr(existing, key, value)
        else:
            # Create new
            url_metadata = UrlMetadata(
                archived_url_id=archived_url_id,
                title=metadata.get("title"),
                byline=metadata.get("byline"),
                site_name=metadata.get("site_name"),
                description=metadata.get("description"),
                text=metadata.get("text"),
                word_count=metadata.get("word_count"),
            )
            session.add(url_metadata)
