from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from threading import Event
from typing import Any, Dict, List, Optional, Sequence

from core.config import AppSettings
from core.utils import check_url_archivability, rewrite_paywalled_url, sanitize_filename, get_directory_size, extract_original_url
from db import (
    ArchiveArtifactRepository,
    ArchivedUrlRepository,
    UrlMetadataRepository,
)
from models import ArchiveResult

from .base import BackgroundTaskManager
from .summarization import SummarizationCoordinator

DEFAULT_REQUEUE_PRIORITIES: tuple[str, ...] = ("singlefile-cli", "monolith", "readability", "pdf", "screenshot")
DEFAULT_REQUEUE_CHUNK_SIZE = 10


logger = logging.getLogger(__name__)


@dataclass
class BatchItem:
    item_id: str
    url: str  # Original URL (stored in DB)
    rowid: int
    archiver_name: str
    rewritten_url: str | None = None  # Freedium URL (used for archiving)


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

        # Repository instances
        self.artifact_repo = ArchiveArtifactRepository(settings.resolved_db_path)
        self.url_repo = ArchivedUrlRepository(settings.resolved_db_path)
        self.metadata_repo = UrlMetadataRepository(settings.resolved_db_path)
        sources = getattr(settings, "summary_source_archivers", None) or []
        self.summary_source_archivers: set[str] = {
            str(name).strip() for name in sources if str(name).strip()
        }
        resolved_priorities = requeue_priorities or DEFAULT_REQUEUE_PRIORITIES
        self.requeue_priorities: List[str] = [
            str(name).strip() for name in resolved_priorities if str(name).strip()
        ]
        self.requeue_chunk_size = max(int(requeue_chunk_size), 1)

    def _insert_pending_artifact(
        self, item_id: str, url: str, task_id: str, archiver_name: str, name: Optional[str] = None
    ) -> int:
        """Create or update artifact record as pending.

        Handles the two-step process of creating archived_url then artifact.
        Returns artifact ID.
        """
        # Get or create the URL record
        archived_url = self.url_repo.get_or_create(url=url, item_id=item_id, name=name)

        # Get or create the artifact
        from db.schemas import ArtifactStatus
        artifact = self.artifact_repo.get_or_create(
            archived_url_id=archived_url.id,
            archiver=archiver_name,
            task_id=task_id,
        )
        return artifact.id

    def _resolve_priorities(self, priorities: Optional[Sequence[str]]) -> List[str]:
        source = priorities if priorities is not None else self.requeue_priorities
        return [str(name).strip() for name in source if str(name).strip()]


    def enqueue(self, archiver_name: str, items: List[Dict[str, str]]) -> str:
        """Insert pending rows and enqueue async task; returns task_id."""
        logger.info("Enqueue requested", extra={"archiver": archiver_name, "item_count": len(items)})

        task_id = uuid.uuid4().hex
        batch_items: List[BatchItem] = []
        if archiver_name == "all":
            archiver_order = list(self.archivers.keys())
        else:
            archiver_order = [archiver_name]

        for entry in items:
            item_id = str(entry["item_id"])
            original_url = str(entry["url"])
            rewritten_url = rewrite_paywalled_url(original_url)
            if rewritten_url != original_url:
                logger.debug(
                    "Rewriting URL for paywall bypass",
                    extra={
                        "item_id": item_id,
                        "original_url": original_url,
                        "rewritten_url": rewritten_url,
                    },
                )
            logger.debug("Planning archiving run", extra={"item_id": item_id, "url": original_url})
            for arch_name in archiver_order:
                # Check for existing saves against ORIGINAL URL only (what's stored in DB)
                if self.settings.skip_existing_saves:
                    already_saved = self.artifact_repo.find_successful(
                        
                        item_id=item_id,
                        url=original_url,  # Changed: check original URL
                        archiver=arch_name,
                    )
                    if already_saved:
                        logger.info("Skipping existing save", extra={"archiver": arch_name, "item_id": item_id, "url": original_url})
                        continue

                # Store ORIGINAL URL in database, but we'll use rewritten URL for archiving
                rowid = self._insert_pending_artifact(
                    
                    item_id=item_id,
                    url=original_url,  # Changed: store original URL
                    task_id=task_id,
                    archiver_name=arch_name,
                )
                logger.debug("Inserted pending save", extra={"rowid": rowid, "task_id": task_id, "archiver": arch_name})
                batch_items.append(
                    BatchItem(
                        item_id=item_id,
                        url=original_url,  # Changed: original URL
                        rowid=rowid,
                        archiver_name=arch_name,
                        rewritten_url=rewritten_url if rewritten_url != original_url else None,
                    )
                )

        self.submit(BatchTask(task_id=task_id, archiver_name=archiver_name, items=batch_items))
        logger.info("Task queued", extra={"task_id": task_id, "archiver": archiver_name, "item_count": len(batch_items)})
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
            logger.info(
                "Processing chunk",
                extra={
                    "chunk_number": (chunk_start // resolved_chunk_size) + 1,
                    "chunk_size": len(chunk),
                    "wait": True,
                }
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
            logger.warning("Resume skipped: no statuses provided")
            return []

        try:
            pending_schemas = self.artifact_repo.list_by_status(
                target_statuses,
            )
            # Convert Pydantic schemas to dicts for backward compatibility
            pending_records = [schema.model_dump() for schema in pending_schemas]
        except Exception as exc:
            logger.error("Failed to load pending artifacts", extra={"error": str(exc)}, exc_info=True)
            return []

        logger.info(
            "Resume check",
            extra={"statuses": target_statuses, "artifact_count": len(pending_records)}
        )

        if not pending_records:
            return []

        task_ids = self.enqueue_artifacts_and_wait(
            pending_records,
            chunk_size=self.requeue_chunk_size,
            priorities=self.requeue_priorities,
        )

        logger.info(
            "Resume complete",
            extra={"artifact_count": len(pending_records), "task_count": len(task_ids)}
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

        logger.info(
            "Enqueue artifacts requested",
            extra={"total_artifacts": len(artifacts), "wait": wait_for_completion}
        )

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for record in artifacts:
            archiver_name = (record.get("archiver") or "unknown").strip()
            artifact_id = record.get("artifact_id")
            if archiver_name not in self.archivers:
                logger.warning(
                    "Cannot requeue artifact: unknown archiver",
                    extra={"archiver": archiver_name, "artifact_id": artifact_id}
                )
                if artifact_id is not None:
                    self.artifact_repo.finalize_result(
                        
                        rowid=int(artifact_id),
                        success=False,
                        exit_code=127,
                        saved_path=None,
                    )
                continue
            grouped.setdefault(archiver_name, []).append(record)
            logger.debug(
                "Prepared artifact for requeue",
                extra={"archiver": archiver_name, "artifact_id": artifact_id}
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
            logger.debug(
                "Building requeue task",
                extra={"archiver": archiver_name, "record_count": len(records)}
            )
            task_id = uuid.uuid4().hex
            batch_items: List[BatchItem] = []
            for record in records:
                raw_url = record.get("url")
                if not raw_url:
                    continue
                original_url = str(raw_url)
                rewritten_url = rewrite_paywalled_url(original_url)
                if rewritten_url != original_url:
                    logger.debug(
                        "Rewriting URL for paywall bypass",
                        extra={
                            "archiver": archiver_name,
                            "artifact_id": record.get("artifact_id"),
                            "original_url": original_url,
                            "rewritten_url": rewritten_url,
                        },
                    )
                raw_item_id = record.get("item_id")
                safe_item_id = raw_item_id or sanitize_filename(original_url)
                if not safe_item_id:
                    safe_item_id = f"artifact-{record.get('artifact_id', uuid.uuid4().hex)}"
                logger.debug(
                    "Requeue artifact resolved",
                    extra={
                        "archiver": archiver_name,
                        "artifact_id": record.get("artifact_id"),
                        "item_id": safe_item_id,
                        "url": original_url
                    }
                )

                # Use existing artifact_id as rowid if available (don't create duplicate)
                existing_rowid = record.get("artifact_id")
                if existing_rowid:
                    rowid = int(existing_rowid)
                    logger.debug(
                        "Reusing existing artifact rowid",
                        extra={"rowid": rowid, "archiver": archiver_name}
                    )
                else:
                    # Only create new pending save if no existing rowid
                    rowid = self._insert_pending_artifact(
                        
                        item_id=safe_item_id,
                        url=original_url,  # Changed: store original URL
                        task_id=task_id,
                        archiver_name=archiver_name,
                    )
                    logger.debug(
                        "Requeue inserted pending save",
                        extra={"rowid": rowid, "archiver": archiver_name, "item_id": safe_item_id}
                    )

                batch_items.append(
                    BatchItem(
                        item_id=safe_item_id,
                        url=original_url,  # Changed: original URL
                        rowid=rowid,
                        archiver_name=archiver_name,
                        rewritten_url=rewritten_url if rewritten_url != original_url else None,
                    )
                )
                logger.debug(
                    "Requeue queued batch item",
                    extra={"task_id": task_id, "rowid": rowid}
                )

            if not batch_items:
                logger.warning("No valid artifacts for task", extra={"archiver": archiver_name})
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
            logger.info(
                "Requeue task submitted",
                extra={"task_id": task_id, "archiver": archiver_name, "batch_count": len(batch_items)}
            )
            task_ids.append(task_id)
            if event is not None:
                completion_events.append(event)

        if wait_for_completion and completion_events:
            logger.info("Waiting for tasks to complete", extra={"task_count": len(completion_events)})
            for event in completion_events:
                event.wait()

        logger.info(
            "Enqueue artifacts completed",
            extra={"task_ids": task_ids, "wait": wait_for_completion}
        )
        return task_ids

    def process(self, task: BatchTask) -> None:  # type: ignore[override]
        for item in task.items:
            # Use rewritten URL for fetching, original URL for storage/checks
            fetch_url = item.rewritten_url or item.url
            logger.info(
                "Processing artifact",
                extra={
                    "task_id": task.task_id,
                    "rowid": item.rowid,
                    "archiver": item.archiver_name,
                    "url": item.url,
                    "fetch_url": fetch_url if fetch_url != item.url else None
                }
            )
            archiver = self.archivers.get(item.archiver_name)
            if archiver is None:
                logger.error("Archiver missing", extra={"archiver": item.archiver_name, "rowid": item.rowid})
                self.artifact_repo.finalize_result(
                    
                    rowid=item.rowid,
                    success=False,
                    exit_code=127,
                    saved_path=None,
                )
                continue

            try:
                url_check = check_url_archivability(fetch_url)
                logger.debug("URL status check", extra={"rowid": item.rowid, "status": url_check.status_code, "should_archive": url_check.should_archive, "url": fetch_url})
                if not url_check.should_archive:
                    logger.warning("URL returned 404", extra={"rowid": item.rowid, "url": fetch_url})
                    try:
                        self.artifact_repo.finalize_result(
                            
                            rowid=item.rowid,
                            exit_code=404,
                        )
                    except Exception:
                        self.artifact_repo.finalize_result(
                            
                            rowid=item.rowid,
                            success=False,
                            exit_code=404,
                            saved_path=None,
                        )
                    continue

                if self.settings.skip_existing_saves:
                    existing = None

                    # First check: Database lookup by ORIGINAL URL
                    existing = self.artifact_repo.find_successful(
                        
                        item_id=item.item_id,
                        url=item.url,  # Original URL (what's stored in DB)
                        archiver=item.archiver_name,
                    )

                    # Second check: File system check (catches cases where DB is out of sync)
                    if existing is None:
                        try:
                            existing_file = archiver.has_existing_output(item.item_id)
                            if existing_file:
                                from pathlib import Path
                                logger.info(
                                    "Found existing file on disk (not in DB)",
                                    extra={
                                        "archiver": item.archiver_name,
                                        "item_id": item.item_id,
                                        "path": str(existing_file)
                                    }
                                )
                                # Create a mock existing object
                                class MockExisting:
                                    def __init__(self, path):
                                        self.saved_path = str(path)
                                        self.archived_url_id = None
                                existing = MockExisting(existing_file)
                        except Exception as e:
                            logger.debug(
                                "File system check failed",
                                extra={"archiver": item.archiver_name, "item_id": item.item_id, "error": str(e)}
                            )

                    # Verify file exists before reusing
                    if existing is not None:
                        from pathlib import Path
                        saved_path_obj = Path(existing.saved_path) if existing.saved_path else None
                        if saved_path_obj and saved_path_obj.exists():
                            logger.info(
                                "Reusing existing save",
                                extra={
                                    "rowid": item.rowid,
                                    "archiver": item.archiver_name,
                                    "saved_path": existing.saved_path
                                }
                            )
                            self.artifact_repo.finalize_result(
                                
                                rowid=item.rowid,
                                success=True,
                                exit_code=0,
                                saved_path=existing.saved_path,
                            )
                            if hasattr(existing, 'archived_url_id'):
                                self._schedule_summary(
                                    archived_url_id=existing.archived_url_id,
                                    rowid=item.rowid,
                                    source=item.archiver_name,
                                    reason=f"task-existing-{item.archiver_name}",
                                )
                            continue
                        else:
                            logger.warning(
                                "Existing artifact found but file missing - will re-archive",
                                extra={
                                    "rowid": item.rowid,
                                    "archiver": item.archiver_name,
                                    "saved_path": existing.saved_path
                                }
                            )

                logger.info(
                    "Invoking archiver",
                    extra={"archiver": item.archiver_name, "rowid": item.rowid, "url": fetch_url}
                )
                result: ArchiveResult = archiver.archive(
                    url=fetch_url, item_id=item.item_id  # Use rewritten URL for fetching
                )

                # Calculate size if save was successful
                size_bytes = None
                archived_url_id = None
                if result.success and result.saved_path:
                    from pathlib import Path
                    try:
                        saved_path = Path(result.saved_path)
                        # Calculate size of the archiver output directory
                        if saved_path.exists():
                            archiver_dir = saved_path.parent
                            size_bytes = get_directory_size(archiver_dir)
                            logger.debug(
                                "Calculated artifact size",
                                extra={
                                    "rowid": item.rowid,
                                    "archiver": item.archiver_name,
                                    "size_bytes": size_bytes,
                                    "path": str(archiver_dir)
                                }
                            )

                        # Get archived_url_id for updating total size
                        artifact = self.artifact_repo.get_by_id( item.rowid)
                        if artifact:
                            archived_url_id = artifact.archived_url_id
                    except Exception as exc:
                        logger.warning(
                            "Failed to calculate size",
                            extra={"rowid": item.rowid, "error": str(exc)}
                        )

                self.artifact_repo.finalize_result(
                    
                    rowid=item.rowid,
                    success=result.success,
                    exit_code=result.exit_code,
                    saved_path=result.saved_path,
                    size_bytes=size_bytes,
                )

                # Update total size for the URL
                if archived_url_id is not None:
                    try:
                        self.url_repo.update_total_size(
                            
                            archived_url_id=archived_url_id
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to update total size",
                            extra={"archived_url_id": archived_url_id, "error": str(exc)}
                        )

                logger.info(
                    f"Finalized save ({'success' if result.success else 'failure'})",
                    extra={
                        "rowid": item.rowid,
                        "success": result.success,
                        "exit_code": result.exit_code,
                        "saved_path": result.saved_path,
                        "size_bytes": size_bytes
                    }
                )

                try:
                    if (
                        getattr(result, "metadata", None)
                        and item.archiver_name == "readability"
                    ):
                        self.metadata_repo.upsert(
                            
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
            except Exception as exc:
                logger.error(
                    "Archiving failed with exception",
                    extra={"rowid": item.rowid, "archiver": item.archiver_name, "error": str(exc)},
                    exc_info=True
                )
                self.artifact_repo.finalize_result(
                    
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
            logger.debug(
                "Summary skipped: not configured for this archiver",
                extra={"source": source, "rowid": rowid}
            )
            return
        if not self._summarization:
            logger.debug(
                "Summary skipped: summarization manager missing",
                extra={"source": source, "rowid": rowid}
            )
            return

        resolved_reason = reason or f"task-{source}"
        logger.info(
            "Scheduling summary",
            extra={
                "source": source,
                "rowid": rowid,
                "archived_url_id": archived_url_id,
                "reason": resolved_reason
            }
        )
        self._summarization.schedule(
            rowid=rowid,
            archived_url_id=archived_url_id,
            reason=resolved_reason,
        )
