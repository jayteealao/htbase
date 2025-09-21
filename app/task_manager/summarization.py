from __future__ import annotations

import queue
import traceback
from dataclasses import dataclass
from typing import Optional

from core.config import AppSettings
from db.repository import (
    get_metadata_for_archived_url,
    get_save_by_rowid,
)
from services.summarizer import SummaryService

from .base import BackgroundTaskManager


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
            print(
                "Summarization worker disabled; dropping task | "
                f"archived_url_id={task.archived_url_id} "
                f"rowid={task.rowid} reason={task.reason}"
            )
            return

        try:
            print(
                "Executing background summarization | "
                f"archived_url_id={task.archived_url_id} "
                f"rowid={task.rowid} reason={task.reason}"
            )
            summarizer.generate_for_archived_url(task.archived_url_id)
        except Exception:
            print(
                "Failed to run background summarization | "
                f"archived_url_id={task.archived_url_id} "
                f"rowid={task.rowid} reason={task.reason}"
            )
            traceback.print_exc()


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
            target_id = archived_url_id
            if target_id is None and rowid is not None:
                artifact = get_save_by_rowid(self.settings.resolved_db_path, rowid)
                if artifact is None:
                    print(
                        "Skipping summarization: artifact missing | "
                        f"rowid={rowid} reason={resolved_reason}"
                    )
                    return False
                target_id = artifact.archived_url_id

            if target_id is None:
                print(
                    "Skipping summarization: archived_url unresolved | "
                    f"rowid={rowid} reason={resolved_reason}"
                )
                return False

            metadata = get_metadata_for_archived_url(
                self.settings.resolved_db_path, target_id
            )
            text = getattr(metadata, "text", None)
            if metadata is None or not text or not str(text).strip():
                print(
                    "Skipping summarization: metadata unavailable | "
                    f"archived_url_id={target_id} rowid={rowid} "
                    f"reason={resolved_reason}"
                )
                return False

            inline = not self._use_background if force_inline is None else force_inline
            if inline:
                print(
                    "Triggering summarization inline | "
                    f"archived_url_id={target_id} rowid={rowid} reason={resolved_reason}"
                )
                summarizer.generate_for_archived_url(target_id)
                return True

            task = SummarizeTask(
                rowid=rowid,
                archived_url_id=target_id,
                reason=resolved_reason,
            )
            self._queue.put(task)
            print(
                "Enqueued summarization | "
                f"archived_url_id={target_id} rowid={rowid} reason={resolved_reason}"
            )
            return True
        except Exception:
            print(
                "Failed to schedule summarization | "
                f"archived_url_id={archived_url_id} rowid={rowid} "
                f"reason={resolved_reason}"
            )
            traceback.print_exc()
            return False
