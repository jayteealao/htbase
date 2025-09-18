from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.config import AppSettings
from core.utils import get_url_status
from db.repository import (
    finalize_save_result,
    find_existing_success_save,
    insert_pending_save,
    is_already_saved_success,
    record_http_failure,
)
from models import ArchiveResult

from .base import BackgroundTaskManager
from .summarization import SummarizationCoordinator


@dataclass
class BatchItem:
    item_id: str
    url: str
    rowid: int
    archiver_name: str


@dataclass
class BatchTask:
    task_id: str
    archiver_name: str
    items: List[BatchItem]


class ArchiverTaskManager(BackgroundTaskManager[BatchTask]):
    def __init__(
        self,
        settings: AppSettings,
        archivers: Dict[str, Any],
        *,
        summarization: SummarizationCoordinator | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.archivers = archivers
        self._summarization = summarization
        sources = getattr(settings, "summary_source_archivers", None) or []
        self.summary_source_archivers: set[str] = {
            str(name).strip() for name in sources if str(name).strip()
        }

    def enqueue(self, archiver_name: str, items: List[Dict[str, str]]) -> str:
        """Insert pending rows and enqueue async task; returns task_id."""

        task_id = uuid.uuid4().hex
        batch_items: List[BatchItem] = []
        if archiver_name == "all":
            archiver_order = list(self.archivers.keys())
        else:
            archiver_order = [archiver_name]

        for entry in items:
            item_id = str(entry["item_id"])
            url = str(entry["url"])
            for arch_name in archiver_order:
                if self.settings.skip_existing_saves and is_already_saved_success(
                    self.settings.resolved_db_path,
                    item_id=item_id,
                    url=url,
                    archiver=arch_name,
                ):
                    continue

                rowid = insert_pending_save(
                    db_path=self.settings.resolved_db_path,
                    item_id=item_id,
                    url=url,
                    task_id=task_id,
                    archiver_name=arch_name,
                )
                batch_items.append(
                    BatchItem(
                        item_id=item_id,
                        url=url,
                        rowid=rowid,
                        archiver_name=arch_name,
                    )
                )

        self.submit(BatchTask(task_id=task_id, archiver_name=archiver_name, items=batch_items))
        return task_id

    def process(self, task: BatchTask) -> None:  # type: ignore[override]
        for item in task.items:
            archiver = self.archivers.get(item.archiver_name)
            if archiver is None:
                finalize_save_result(
                    db_path=self.settings.resolved_db_path,
                    rowid=item.rowid,
                    success=False,
                    exit_code=127,
                    saved_path=None,
                )
                continue

            try:
                status = None
                try:
                    status = get_url_status(item.url)
                except Exception:
                    status = None
                if status == 404:
                    try:
                        record_http_failure(
                            db_path=self.settings.resolved_db_path,
                            rowid=item.rowid,
                            exit_code=404,
                        )
                    except Exception:
                        finalize_save_result(
                            db_path=self.settings.resolved_db_path,
                            rowid=item.rowid,
                            success=False,
                            exit_code=404,
                            saved_path=None,
                        )
                    continue

                if self.settings.skip_existing_saves:
                    existing = find_existing_success_save(
                        self.settings.resolved_db_path,
                        item_id=item.item_id,
                        url=item.url,
                        archiver=item.archiver_name,
                    )
                    if existing is not None:
                        finalize_save_result(
                            db_path=self.settings.resolved_db_path,
                            rowid=item.rowid,
                            success=True,
                            exit_code=0,
                            saved_path=existing.saved_path,
                        )
                        self._schedule_summary(
                            archived_url_id=existing.archived_url_id,
                            rowid=item.rowid,
                            source=item.archiver_name,
                            reason=f"task-existing-{item.archiver_name}",
                        )
                        continue

                result: ArchiveResult = archiver.archive(
                    url=item.url, item_id=item.item_id
                )
                finalize_save_result(
                    db_path=self.settings.resolved_db_path,
                    rowid=item.rowid,
                    success=result.success,
                    exit_code=result.exit_code,
                    saved_path=result.saved_path,
                )

                try:
                    from db.repository import insert_save_metadata

                    if (
                        getattr(result, "metadata", None)
                        and item.archiver_name == "readability"
                    ):
                        insert_save_metadata(
                            db_path=self.settings.resolved_db_path,
                            save_rowid=item.rowid,
                            data=result.metadata,  # type: ignore[arg-type]
                        )
                except Exception:
                    pass

                if result.success:
                    self._schedule_summary(
                        archived_url_id=getattr(result, "archived_url_id", None),
                        rowid=item.rowid,
                        source=item.archiver_name,
                        reason=f"task-{item.archiver_name}",
                    )
            except Exception:
                finalize_save_result(
                    db_path=self.settings.resolved_db_path,
                    rowid=item.rowid,
                    success=False,
                    exit_code=1,
                    saved_path=None,
                )

    def _schedule_summary(
        self,
        *,
        archived_url_id: Optional[int],
        rowid: Optional[int],
        source: str,
        reason: Optional[str],
    ) -> None:
        if source not in self.summary_source_archivers:
            return
        if not self._summarization:
            return

        resolved_reason = reason or f"task-{source}"
        self._summarization.schedule(
            rowid=rowid,
            archived_url_id=archived_url_id,
            reason=resolved_reason,
        )
