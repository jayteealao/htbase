"""Background task manager for file cleanup operations."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import AppSettings

from db.models import ArchiveArtifact
from db.session import get_session

from .base import BackgroundTaskManager

logger = logging.getLogger(__name__)


@dataclass
class CleanupTask:
    """Represents a file cleanup task."""
    local_path: Path
    artifact_id: int
    scheduled_for: datetime  # When to execute cleanup


class CleanupTaskManager(BackgroundTaskManager[CleanupTask]):
    """Manages cleanup of local workspace files after retention period."""

    def __init__(self, settings: "AppSettings"):
        super().__init__()
        self.settings = settings

    def schedule_cleanup(
        self,
        local_path: Path,
        artifact_id: int,
        delay_hours: int
    ) -> None:
        """Schedule a cleanup task with delay.

        Args:
            local_path: Path to file to clean up
            artifact_id: Artifact database ID for tracking
            delay_hours: Hours to wait before cleanup
        """
        scheduled_for = datetime.utcnow() + timedelta(hours=delay_hours)

        task = CleanupTask(
            local_path=local_path,
            artifact_id=artifact_id,
            scheduled_for=scheduled_for
        )

        self.submit(task)
        logger.info(
            f"Scheduled cleanup for {local_path} at {scheduled_for}",
            extra={"artifact_id": artifact_id, "delay_hours": delay_hours}
        )

    def process(self, task: CleanupTask) -> None:
        """Process a cleanup task (called by BackgroundTaskManager)."""
        # Wait until scheduled time
        now = datetime.utcnow()
        if task.scheduled_for > now:
            wait_seconds = (task.scheduled_for - now).total_seconds()
            logger.debug(f"Waiting {wait_seconds}s before cleanup of {task.local_path}")
            time.sleep(wait_seconds)

        # Execute cleanup
        self._cleanup_file(task)

    def _cleanup_file(self, task: CleanupTask) -> None:
        """Actually delete the file and update database."""
        try:
            # Delete file
            if task.local_path.exists():
                task.local_path.unlink()
                logger.info(f"Deleted local file: {task.local_path}")

                # Clean up empty parent directories
                parent = task.local_path.parent
                while parent != self.settings.data_dir:
                    try:
                        if parent.exists() and not any(parent.iterdir()):
                            parent.rmdir()
                            logger.debug(f"Removed empty directory: {parent}")
                            parent = parent.parent
                        else:
                            break
                    except OSError:
                        break

            # Update database
            with get_session(self.settings.database.resolved_path(self.settings.data_dir)) as session:
                artifact = session.get(ArchiveArtifact, task.artifact_id)
                if artifact:
                    artifact.local_file_deleted = True
                    artifact.local_file_deleted_at = datetime.utcnow()
                    session.commit()
                    logger.info(f"Updated artifact {task.artifact_id} cleanup status")

        except Exception as e:
            logger.error(f"Failed to cleanup {task.local_path}: {e}")

    def cleanup_failed_outputs(self, retention_days: int) -> int:
        """Clean up failed archival outputs older than retention period.

        Args:
            retention_days: Number of days to keep failed outputs

        Returns:
            Number of files cleaned up
        """
        from sqlalchemy import and_

        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        cleaned_count = 0

        try:
            with get_session(self.settings.database.resolved_path(self.settings.data_dir)) as session:
                failed_artifacts = session.query(ArchiveArtifact).filter(
                    and_(
                        ArchiveArtifact.success == False,  # noqa: E712
                        ArchiveArtifact.created_at < cutoff_date,
                        ArchiveArtifact.local_file_deleted == False,  # noqa: E712
                        ArchiveArtifact.saved_path.isnot(None)
                    )
                ).all()

                for artifact in failed_artifacts:
                    if artifact.saved_path:
                        file_path = Path(artifact.saved_path)
                        if file_path.exists():
                            file_path.unlink()
                            cleaned_count += 1
                            logger.info(f"Cleaned up failed output: {file_path}")

                        artifact.local_file_deleted = True
                        artifact.local_file_deleted_at = datetime.utcnow()

                session.commit()

        except Exception as e:
            logger.error(f"Failed output cleanup error: {e}")

        return cleaned_count
