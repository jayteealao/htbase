from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from config import AppSettings
from db import insert_pending_save, finalize_save_result
from models import ArchiveResult


@dataclass
class BatchItem:
    item_id: str
    url: str
    name: Optional[str]
    rowid: int


@dataclass
class BatchTask:
    task_id: str
    archiver_name: str
    items: List[BatchItem]


class TaskManager:
    def __init__(self, settings: AppSettings, archivers: Dict[str, Any]):
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

    def enqueue(self, archiver_name: str, items: List[Dict[str, Optional[str]]]) -> str:
        """Insert pending rows and enqueue async task; returns task_id.

        items: list of dicts with keys: item_id, url, name
        """
        task_id = uuid.uuid4().hex
        batch_items: List[BatchItem] = []
        for it in items:
            rowid = insert_pending_save(
                db_path=self.settings.resolved_db_path,
                item_id=str(it["item_id"]),
                url=str(it["url"]),
                task_id=task_id,
                name=it.get("name"),
            )
            batch_items.append(
                BatchItem(
                    item_id=str(it["item_id"]),
                    url=str(it["url"]),
                    name=it.get("name"),
                    rowid=rowid,
                )
            )
        self.q.put(BatchTask(task_id=task_id, archiver_name=archiver_name, items=batch_items))
        self.start()
        return task_id

    def _run(self):
        while True:
            task: BatchTask = self.q.get()
            try:
                archiver = self.archivers.get(task.archiver_name)
                if archiver is None:
                    # mark all items failed
                    for it in task.items:
                        finalize_save_result(
                            db_path=self.settings.resolved_db_path,
                            rowid=it.rowid,
                            success=False,
                            exit_code=127,
                            saved_path=None,
                        )
                    continue
                for it in task.items:
                    try:
                        result: ArchiveResult = archiver.archive(
                            url=it.url, item_id=it.item_id, out_name=it.name
                        )
                        finalize_save_result(
                            db_path=self.settings.resolved_db_path,
                            rowid=it.rowid,
                            success=result.success,
                            exit_code=result.exit_code,
                            saved_path=result.saved_path,
                        )
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

