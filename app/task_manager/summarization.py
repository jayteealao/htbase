from __future__ import annotations

import logging
import queue
from dataclasses import dataclass
from typing import Optional

from core.config import AppSettings
from db import ArchiveArtifactRepository, UrlMetadataRepository
from services.summarizer import SummaryService

from .base import BackgroundTaskManager

logger = logging.getLogger(__name__)


@dataclass
class SummarizeTask:
    rowid: Optional[int]
    archived_url_id: int
    reason: str


class SummarizationTaskManager(BackgroundTaskManager[SummarizeTask]):
    def __init__(
        self,
        settings: AppSettings,
        summarizer: SummaryService | None,
        *,
        task_queue: "queue.Queue[SummarizeTask]" | None = None,
    ) -> None:
        super().__init__(task_queue=task_queue)
        self.settings = settings
        self._summarizer = summarizer

    def process(self, task: SummarizeTask) -> None:  # type: ignore[override]
        summarizer = self._summarizer
        if summarizer is None or not summarizer.is_enabled:
            logger.warning(
                "Summarization worker disabled; dropping task",
                extra={
                    "archived_url_id": task.archived_url_id,
                    "rowid": task.rowid,
                    "reason": task.reason
                }
            )
            return

        try:
            logger.info(
                "Executing background summarization",
                extra={
                    "archived_url_id": task.archived_url_id,
                    "rowid": task.rowid,
                    "reason": task.reason
                }
            )
            summarizer.generate_for_archived_url(task.archived_url_id)
        except Exception:
            logger.error(
                "Failed to run background summarization",
                extra={
                    "archived_url_id": task.archived_url_id,
                    "rowid": task.rowid,
                    "reason": task.reason
                },
                exc_info=True
            )


class SummarizationCoordinator:
    """Gatekeeper that validates metadata before enqueuing summaries."""

    def __init__(
        self,
        settings: AppSettings,
        summarizer: SummaryService | None,
        *,
        task_queue: "queue.Queue[SummarizeTask]" | None = None,
        use_background: bool = True,
    ) -> None:
        self.settings = settings
        self._summarizer = summarizer
        self._queue: "queue.Queue[SummarizeTask]" = task_queue or queue.Queue()
        self._use_background = use_background

    @property
    def queue(self) -> "queue.Queue[SummarizeTask]":
        return self._queue

    @property
    def is_enabled(self) -> bool:
        summarizer = self._summarizer
        return bool(summarizer and summarizer.is_enabled)

    def schedule(
        self,
        *,
        rowid: Optional[int] = None,
        archived_url_id: Optional[int] = None,
        reason: str | None = None,
        force_inline: bool | None = None,
    ) -> bool:
        summarizer = self._summarizer
        if summarizer is None or not summarizer.is_enabled:
            return False

        resolved_reason = reason or "unspecified"
        try:
            artifact_repo = ArchiveArtifactRepository(self.settings.database.resolved_path(self.settings.data_dir))
            metadata_repo = UrlMetadataRepository(self.settings.database.resolved_path(self.settings.data_dir))

            target_id = archived_url_id
            if target_id is None and rowid is not None:
                artifact = artifact_repo.get_by_id(rowid)
                if artifact is None:
                    logger.warning(
                        "Skipping summarization: artifact missing",
                        extra={"rowid": rowid, "reason": resolved_reason}
                    )
                    return False
                target_id = artifact.archived_url_id

            if target_id is None:
                logger.warning(
                    "Skipping summarization: archived_url unresolved",
                    extra={"rowid": rowid, "reason": resolved_reason}
                )
                return False

            metadata = metadata_repo.get_by_archived_url(target_id)
            text = getattr(metadata, "text", None)
            if metadata is None or not text or not str(text).strip():
                logger.warning(
                    "Skipping summarization: metadata unavailable",
                    extra={
                        "archived_url_id": target_id,
                        "rowid": rowid,
                        "reason": resolved_reason
                    }
                )
                return False

            inline = not self._use_background if force_inline is None else force_inline
            if inline:
                logger.info(
                    "Triggering summarization inline",
                    extra={
                        "archived_url_id": target_id,
                        "rowid": rowid,
                        "reason": resolved_reason
                    }
                )
                summarizer.generate_for_archived_url(target_id)
                return True

            task = SummarizeTask(
                rowid=rowid,
                archived_url_id=target_id,
                reason=resolved_reason,
            )
            self._queue.put(task)
            logger.info(
                "Enqueued summarization",
                extra={
                    "archived_url_id": target_id,
                    "rowid": rowid,
                    "reason": resolved_reason
                }
            )
            return True
        except Exception:
            logger.error(
                "Failed to schedule summarization",
                extra={
                    "archived_url_id": archived_url_id,
                    "rowid": rowid,
                    "reason": resolved_reason
                },
                exc_info=True
            )
            return False
