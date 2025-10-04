from __future__ import annotations

import uuid
from dataclasses import dataclass
from threading import Event
from typing import Any, Dict, List, Optional, Sequence

from core.config import AppSettings
from core.utils import get_url_status, sanitize_filename
from db.repository import (
    finalize_save_result,
    find_existing_success_save,
    insert_pending_save,
    is_already_saved_success,
    list_artifacts_by_status,
    record_http_failure,
)
from models import ArchiveResult

DEFAULT_REQUEUE_PRIORITIES: tuple[str, ...] = ("singlefile-cli", "monolith", "readability", "pdf", "screenshot")
DEFAULT_REQUEUE_CHUNK_SIZE = 10

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
    completion_event: Optional[Event] = None


class ArchiverTaskManager(BackgroundTaskManager[BatchTask]):
    def __init__(
        self,
        settings: AppSettings,
        archivers: Dict[str, Any],
        *,
        summarization: SummarizationCoordinator | None = None,
        requeue_priorities: Optional[Sequence[str]] = None,
        requeue_chunk_size: int = DEFAULT_REQUEUE_CHUNK_SIZE,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.archivers = archivers
        self._summarization = summarization
        sources = getattr(settings, "summary_source_archivers", None) or []
        self.summary_source_archivers: set[str] = {
            str(name).strip() for name in sources if str(name).strip()
        }
        resolved_priorities = requeue_priorities or DEFAULT_REQUEUE_PRIORITIES
        self.requeue_priorities: List[str] = [
            str(name).strip() for name in resolved_priorities if str(name).strip()
        ]
        self.requeue_chunk_size = max(int(requeue_chunk_size), 1)

    def _resolve_priorities(self, priorities: Optional[Sequence[str]]) -> List[str]:
        source = priorities if priorities is not None else self.requeue_priorities
        return [str(name).strip() for name in source if str(name).strip()]


    def enqueue(self, archiver_name: str, items: List[Dict[str, str]]) -> str:
        """Insert pending rows and enqueue async task; returns task_id."""
        print(f'[ArchiverTaskManager] enqueue requested | archiver={archiver_name} items={len(items)}')

        task_id = uuid.uuid4().hex
        batch_items: List[BatchItem] = []
        if archiver_name == "all":
            archiver_order = list(self.archivers.keys())
        else:
            archiver_order = [archiver_name]

        for entry in items:
            item_id = str(entry["item_id"])
            url = str(entry["url"])
            print(f'[ArchiverTaskManager] Planning run | item_id={item_id} url={url}')
            for arch_name in archiver_order:
                if self.settings.skip_existing_saves and is_already_saved_success(
                    self.settings.resolved_db_path,
                    item_id=item_id,
                    url=url,
                    archiver=arch_name,
                ):
                    print(f'[ArchiverTaskManager] Skipping existing save | archiver={arch_name} item_id={item_id} url={url}')
                    continue

                rowid = insert_pending_save(
                    db_path=self.settings.resolved_db_path,
                    item_id=item_id,
                    url=url,
                    task_id=task_id,
                    archiver_name=arch_name,
                )
                print(f'[ArchiverTaskManager] Inserted pending save | rowid={rowid} task_id={task_id} archiver={arch_name}')
                batch_items.append(
                    BatchItem(
                        item_id=item_id,
                        url=url,
                        rowid=rowid,
                        archiver_name=arch_name,
                    )
                )

        self.submit(BatchTask(task_id=task_id, archiver_name=archiver_name, items=batch_items))
        print(f'[ArchiverTaskManager] Task {task_id} queued | archiver={archiver_name} item_count={len(batch_items)}')
        return task_id

    def enqueue_artifacts(
        self,
        artifacts: Sequence[Dict[str, Any]],
        priorities: Optional[Sequence[str]] = None,
    ) -> List[str]:
        resolved_priorities = self._resolve_priorities(priorities)
        return self._submit_artifact_records(
            list(artifacts),
            wait_for_completion=False,
            priorities=resolved_priorities,
        )

    def enqueue_artifacts_and_wait(
        self,
        artifacts: Sequence[Dict[str, Any]],
        *,
        chunk_size: Optional[int] = None,
        priorities: Optional[Sequence[str]] = None,
    ) -> List[str]:
        if not artifacts:
            return []

        resolved_chunk_size = max(int(chunk_size or self.requeue_chunk_size), 1)
        resolved_priorities = self._resolve_priorities(priorities)

        priority_index = {
            name: idx for idx, name in enumerate(resolved_priorities)
        }

        def sort_key(record: Dict[str, Any]) -> tuple[int, Any]:
            arch = (record.get("archiver") or "").strip()
            rank = priority_index.get(arch, len(priority_index))
            artifact_id = record.get("artifact_id")
            return (rank, artifact_id if artifact_id is not None else float("inf"))

        ordered = sorted(artifacts, key=sort_key) if priority_index else list(artifacts)

        task_ids: List[str] = []
        for chunk_start in range(0, len(ordered), resolved_chunk_size):
            chunk = ordered[chunk_start : chunk_start + resolved_chunk_size]
            print(
                f'[ArchiverTaskManager] Processing chunk {(chunk_start // resolved_chunk_size) + 1} | size={len(chunk)} wait=True'
            )
            task_ids.extend(
                self._submit_artifact_records(
                    chunk,
                    wait_for_completion=True,
                    priorities=resolved_priorities,
                )
            )

        return task_ids

    def resume_pending_artifacts(
        self,
        *,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[str]:
        target_statuses = [
            str(status).strip() for status in (statuses or ["pending"]) if str(status).strip()
        ]
        if not target_statuses:
            print('[ArchiverTaskManager] Resume skipped | reason=no-statuses')
            return []

        try:
            pending_records = list_artifacts_by_status(
                self.settings.resolved_db_path,
                target_statuses,
            )
        except Exception as exc:
            print(f'[ArchiverTaskManager] Failed to load pending artifacts | error={exc}')
            return []

        print(
            f'[ArchiverTaskManager] Resume check | statuses={target_statuses} count={len(pending_records)}'
        )

        if not pending_records:
            return []

        task_ids = self.enqueue_artifacts_and_wait(
            pending_records,
            chunk_size=self.requeue_chunk_size,
            priorities=self.requeue_priorities,
        )

        print(
            f'[ArchiverTaskManager] Resume complete | artifacts={len(pending_records)} tasks={len(task_ids)}'
        )
        return task_ids

    def _submit_artifact_records(
            self,
            artifacts: Sequence[Dict[str, Any]],
            *,
            wait_for_completion: bool,
            priorities: Optional[Sequence[str]] = None,
    ) -> List[str]:
        resolved_priorities = self._resolve_priorities(priorities)
        priority_index = {name: idx for idx, name in enumerate(resolved_priorities)}

        print(
            f'[ArchiverTaskManager] enqueue_artifacts requested | total={len(artifacts)} wait={wait_for_completion}'
        )

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for record in artifacts:
            archiver_name = (record.get("archiver") or "unknown").strip()
            artifact_id = record.get("artifact_id")
            if archiver_name not in self.archivers:
                print(
                    f'[ArchiverTaskManager] Cannot requeue artifact | reason=unknown-archiver archiver={archiver_name} artifact_id={artifact_id}'
                )
                if artifact_id is not None:
                    finalize_save_result(
                        db_path=self.settings.resolved_db_path,
                        rowid=int(artifact_id),
                        success=False,
                        exit_code=127,
                        saved_path=None,
                    )
                continue
            grouped.setdefault(archiver_name, []).append(record)
            print(
                f'[ArchiverTaskManager] Prepared artifact for requeue | archiver={archiver_name} artifact_id={artifact_id}'
            )

        task_ids: List[str] = []
        completion_events: List[Event] = []
        ordered_archivers = (
            sorted(
                grouped.items(),
                key=lambda item: priority_index.get(item[0], len(priority_index)),
            )
            if priority_index
            else list(grouped.items())
        )

        for archiver_name, records in ordered_archivers:
            print(
                f'[ArchiverTaskManager] Building requeue task | archiver={archiver_name} count={len(records)}'
            )
            task_id = uuid.uuid4().hex
            batch_items: List[BatchItem] = []
            for record in records:
                url = record.get("url")
                if not url:
                    continue
                raw_item_id = record.get("item_id")
                safe_item_id = raw_item_id or sanitize_filename(url)
                if not safe_item_id:
                    safe_item_id = f"artifact-{record.get('artifact_id', uuid.uuid4().hex)}"
                print(
                    f'[ArchiverTaskManager] Requeue artifact resolved | archiver={archiver_name} artifact_id={record.get("artifact_id")} item_id={safe_item_id} url={url}'
                )

                rowid = insert_pending_save(
                    db_path=self.settings.resolved_db_path,
                    item_id=safe_item_id,
                    url=url,
                    task_id=task_id,
                    archiver_name=archiver_name,
                )
                print(
                    f'[ArchiverTaskManager] Requeue inserted pending save | rowid={rowid} archiver={archiver_name} item_id={safe_item_id}'
                )

                batch_items.append(
                    BatchItem(
                        item_id=safe_item_id,
                        url=url,
                        rowid=rowid,
                        archiver_name=archiver_name,
                    )
                )
                print(
                    f'[ArchiverTaskManager] Requeue queued batch item | task_id={task_id} rowid={rowid}'
                )

            if not batch_items:
                print(f'[ArchiverTaskManager] No valid artifacts for task | archiver={archiver_name}')
                continue

            event = Event() if wait_for_completion else None
            self.submit(
                BatchTask(
                    task_id=task_id,
                    archiver_name=archiver_name,
                    items=batch_items,
                    completion_event=event,
                )
            )
            print(
                f'[ArchiverTaskManager] Requeue task submitted | task_id={task_id} archiver={archiver_name} batch_count={len(batch_items)}'
            )
            task_ids.append(task_id)
            if event is not None:
                completion_events.append(event)

        if wait_for_completion and completion_events:
            print(f'[ArchiverTaskManager] Waiting for {len(completion_events)} task(s) to complete...')
            for event in completion_events:
                event.wait()

        print(
            f'[ArchiverTaskManager] enqueue_artifacts completed | tasks={task_ids} wait={wait_for_completion}'
        )
        return task_ids

    def process(self, task: BatchTask) -> None:  # type: ignore[override]
        for item in task.items:
            print(f'[ArchiverTaskManager] Processing artifact | task_id={task.task_id} rowid={item.rowid} archiver={item.archiver_name} url={item.url}')
            archiver = self.archivers.get(item.archiver_name)
            if archiver is None:
                print(f'[ArchiverTaskManager] Archiver missing | archiver={item.archiver_name} rowid={item.rowid}')
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
                print(f'[ArchiverTaskManager] URL status | rowid={item.rowid} status={status}')
                if status == 404:
                    print(f'[ArchiverTaskManager] URL returned 404 | rowid={item.rowid} url={item.url}')
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
                        print(f'[ArchiverTaskManager] Reusing existing save | rowid={item.rowid} archiver={item.archiver_name} saved_path={existing.saved_path}')
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

                print(f'[ArchiverTaskManager] Invoking archiver | archiver={item.archiver_name} rowid={item.rowid} url={item.url}')
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
                print(f'[ArchiverTaskManager] Finalized save | rowid={item.rowid} success={result.success} exit_code={result.exit_code} saved_path={result.saved_path}')

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
                print(f'[ArchiverTaskManager] Archiving failed with exception | rowid={item.rowid} archiver={item.archiver_name}')
                finalize_save_result(
                    db_path=self.settings.resolved_db_path,
                    rowid=item.rowid,
                    success=False,
                    exit_code=1,
                    saved_path=None,
                )

        if task.completion_event is not None:
            task.completion_event.set()


    def _schedule_summary(
        self,
        *,
        archived_url_id: Optional[int],
        rowid: Optional[int],
        source: str,
        reason: Optional[str],
    ) -> None:
        if source not in self.summary_source_archivers:
            print(f'[ArchiverTaskManager] Summary skipped | source={source} reason=not-configured rowid={rowid}')
            return
        if not self._summarization:
            print(f'[ArchiverTaskManager] Summary skipped | source={source} reason=manager-missing rowid={rowid}')
            return

        resolved_reason = reason or f"task-{source}"
        print(f'[ArchiverTaskManager] Scheduling summary | source={source} rowid={rowid} archived_url_id={archived_url_id} reason={resolved_reason}')
        self._summarization.schedule(
            rowid=rowid,
            archived_url_id=archived_url_id,
            reason=resolved_reason,
        )
