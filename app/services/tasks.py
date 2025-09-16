from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from typing import TYPE_CHECKING
from db.repository import (
    insert_pending_save,
    finalize_save_result,
    is_already_saved_success,
    find_existing_success_save,
)
from models import ArchiveResult

if TYPE_CHECKING:
    from core.config import AppSettings


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


class TaskManager:
    def __init__(self, settings: "AppSettings", archivers: Dict[str, Any]):
        self.settings = settings
        self.archivers = archivers
        self.q: "queue.Queue[BatchTask]" = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self.worker and self.worker.is_alive():
                return
            self.worker = threading.Thread(target=self._run, daemon=True)
            self.worker.start()

    def enqueue(self, archiver_name: str, items: List[Dict[str, str]]) -> str:
        """Insert pending rows and enqueue async task; returns task_id.

        items: list of dicts with keys: item_id, url
        """
        task_id = uuid.uuid4().hex
        batch_items: List[BatchItem] = []
        # Determine which archivers to run per item
        if archiver_name == "all":
            archiver_order = list(self.archivers.keys())
        else:
            archiver_order = [archiver_name]

        for it in items:
            iid = str(it["item_id"])
            url = str(it["url"])
            # Insert one pending row per archiver in the pipeline
            for arch_name in archiver_order:
                if self.settings.skip_existing_saves and is_already_saved_success(
                    self.settings.resolved_db_path, item_id=iid, url=url, archiver=arch_name
                ):
                    # Skip inserting pending row if already saved successfully
                    continue
                    
                rowid = insert_pending_save(
                    db_path=self.settings.resolved_db_path,
                    item_id=iid,
                    url=url,
                    task_id=task_id,
                    archiver_name=arch_name,
                )
                batch_items.append(
                    BatchItem(
                        item_id=iid,
                        url=url,
                        rowid=rowid,
                        archiver_name=arch_name,
                    )
                )

        # Ensure processing order: for each input item, run each archiver in registration order
        # Items were appended in that order above, so just enqueue as-is
        self.q.put(BatchTask(task_id=task_id, archiver_name=archiver_name, items=batch_items))
        self.start()
        return task_id

    def _run(self):
        while True:
            task: BatchTask = self.q.get()
            try:
                for it in task.items:
                    archiver = self.archivers.get(it.archiver_name)
                    if archiver is None:
                        finalize_save_result(
                            db_path=self.settings.resolved_db_path,
                            rowid=it.rowid,
                            success=False,
                            exit_code=127,
                            saved_path=None,
                        )
                        continue
                    try:
                        # Double-check skip condition at execution time
                        if self.settings.skip_existing_saves:
                            existing = find_existing_success_save(
                                self.settings.resolved_db_path, item_id=it.item_id, url=it.url, archiver=it.archiver_name
                            )
                            if existing is not None:
                                finalize_save_result(
                                    db_path=self.settings.resolved_db_path,
                                    rowid=it.rowid,
                                    success=True,
                                    exit_code=0,
                                    saved_path=existing.saved_path,
                                )
                                continue
                        result: ArchiveResult = archiver.archive(
                            url=it.url, item_id=it.item_id
                        )
                        finalize_save_result(
                            db_path=self.settings.resolved_db_path,
                            rowid=it.rowid,
                            success=result.success,
                            exit_code=result.exit_code,
                            saved_path=result.saved_path,
                        )
                        # Persist any metadata returned by the archiver
                        try:
                            from db.repository import insert_save_metadata

                            if getattr(result, "metadata", None) and it.archiver_name == "readability":
                                insert_save_metadata(
                                    db_path=self.settings.resolved_db_path,
                                    save_rowid=it.rowid,
                                    data=result.metadata,  # type: ignore[arg-type]
                                )
                        except Exception:
                            pass
                    except Exception:
                        finalize_save_result(
                            db_path=self.settings.resolved_db_path,
                            rowid=it.rowid,
                            success=False,
                            exit_code=1,
                            saved_path=None,
                        )
            finally:
                self.q.task_done()
