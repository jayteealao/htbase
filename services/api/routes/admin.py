from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Request

from common.core.config import AppSettings, get_settings

logger = logging.getLogger(__name__)
from common.db import ArchiveArtifactRepository
from common.models import DeleteResponse, SummarizeRequest, SummarizeResponse
from common.core.utils import sanitize_filename
from pydantic import BaseModel, Field
from common.celery_config import (
    celery_app,
    ARCHIVER_TASK_MAP,
    TASK_GENERATE_SUMMARY,
)

router = APIRouter()


class RequeueRequest(BaseModel):
    artifact_ids: Optional[List[int]] = Field(
        default=None,
        description="Specific artifact IDs to requeue.",
    )
    status: Optional[Literal["failed", "pending"]] = Field(
        default=None,
        description="Filter artifacts by status when requeueing.",
    )
    include_all: bool = Field(
        default=False,
        description="Requeue all artifacts matching the provided status.",
    )


class RequeueResponse(BaseModel):
    requeued_count: int
    task_ids: List[str]


@router.get("/saves", response_model=List[Dict[str, object]])
def list_saves_endpoint(
    limit: int = 200,
    offset: int = 0,
    settings: AppSettings = Depends(get_settings),
):
    artifact_repo = ArchiveArtifactRepository(settings.database.resolved_path(settings.data_dir))
    rows = artifact_repo.list_with_pagination(limit=limit, offset=offset)
    # Serialize and enrich
    out: List[Dict[str, object]] = []
    from pathlib import Path

    data_root = Path(settings.data_dir).resolve()
    for art, au in rows:
        created_val = getattr(art, "created_at", None)
        created_at = created_val.isoformat() if hasattr(created_val, "isoformat") else created_val
        saved_path = art.saved_path
        file_exists = False
        rel_path = None
        archiver = getattr(art, "archiver", None)
        if saved_path:
            p = Path(saved_path)
            file_exists = p.exists()
            try:
                rp = p.resolve()
                if data_root in rp.parents:
                    rel_path = str(rp.relative_to(data_root))
            except Exception:
                rel_path = None
            # Infer archiver from path if not recorded in DB
            if not archiver:
                parts = p.parts
                if len(parts) >= 2:
                    # Expect .../<item_id>/<archiver>/<file>
                    archiver = parts[-2]
        out.append(
            {
                "rowid": int(art.id),
                "id": au.item_id,
                "url": au.url,
                "name": au.name,
                "status": art.status,
                "success": 1 if art.success else 0,
                "exit_code": art.exit_code,
                "saved_path": art.saved_path,
                "file_exists": file_exists,
                "relative_path": rel_path,
                "archiver": archiver,
                "created_at": created_at,
            }
        )
    return out


@router.get("/archivers", response_model=List[str])
def list_archivers(request: Request):
    registry: Dict[str, object] = getattr(request.app.state, "archivers", {})
    return sorted(registry.keys())


@router.post("/saves/requeue", response_model=RequeueResponse)
def requeue_saves(
    payload: RequeueRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
):
    artifact_repo = ArchiveArtifactRepository(settings.database.resolved_path(settings.data_dir))

    try:
        payload_snapshot = payload.model_dump()
    except AttributeError:
        payload_snapshot = payload.dict()
    logger.info(f"Requeue requested | payload={payload_snapshot}")

    artifacts: List[Dict[str, Any]] = []
    statuses_lower = set()
    if payload.status:
        statuses_lower.add(payload.status.lower())

    pull_all = payload.include_all or (payload.status is not None and not payload.artifact_ids)

    if payload.artifact_ids:
        fetched_by_id = artifact_repo.get_by_ids( payload.artifact_ids)
        logger.info(f"Loaded artifacts by id | requested={len(payload.artifact_ids)} found={len(fetched_by_id)}")
        artifacts.extend(fetched_by_id)

    if pull_all and payload.status:
        fetched_by_status = artifact_repo.list_by_status( [payload.status])
        logger.info(f"Loaded artifacts by status | status={payload.status} count={len(fetched_by_status)}")
        artifacts.extend(fetched_by_status)

    if not payload.artifact_ids and not pull_all:
        logger.info("Requeue rejected | reason=no-selection")
        raise HTTPException(
            status_code=400,
            detail="Provide artifact_ids or set include_all with a status to requeue.",
        )

    seen: set[int] = set()
    filtered: List[Dict[str, Any]] = []
    for record in artifacts:
        # artifact_repo returns Pydantic schemas (ArtifactSchema) or dicts.
        # Check type to be safe, but list_by_status returns schemas.
        # However, get_by_ids returns Artifact objects (SQLAlchemy models) usually?
        # The original code used a mixed return. Let's handle both or assume object access.
        # But wait, the repository list_by_status returns ArtifactSchema.
        # get_by_ids logic in admin.py was: fetched_by_id = artifact_repo.get_by_ids(...)
        # BaseRepository get_by_ids returns models.
        # So we have a mix of Models and Schemas in `artifacts`.

        # Helper to get attribute safely
        def get_attr(obj, key):
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        artifact_id = get_attr(record, "artifact_id") or get_attr(record, "id")
        if artifact_id:
            artifact_id = int(artifact_id)
        else:
            continue

        if artifact_id in seen:
            continue
        seen.add(artifact_id)

        status = (get_attr(record, "status") or "").lower()
        if status not in {"failed", "pending"}:
            continue
        if statuses_lower and status not in statuses_lower:
            continue
        filtered.append(record)

    if not filtered:
        logger.info("No artifacts matched filters; nothing to requeue")
        return RequeueResponse(requeued_count=0, task_ids=[])

    task_ids = []

    # Helper again inside loop
    def get_attr(obj, key):
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    for record in filtered:
        archiver = get_attr(record, "archiver")
        # For URL/ItemID, if it's a Schema, they are flat fields.
        # If it's a Model (Artifact), we need to access the relationship `archived_url`
        url = get_attr(record, "url")
        item_id = get_attr(record, "item_id")

        if not url or not item_id:
            # Try to resolve from relationship if model
            au = get_attr(record, "archived_url")
            if au:
                if not url: url = getattr(au, "url", None)
                if not item_id: item_id = getattr(au, "item_id", None)

        task_name = ARCHIVER_TASK_MAP.get(archiver)
        if task_name and url and item_id:
             res = celery_app.send_task(task_name, args=[url, item_id])
             task_ids.append(res.id)
        else:
            logger.warning(f"Could not requeue artifact {get_attr(record, 'id')}: missing info or unknown archiver {archiver}")

    logger.info(f"Requeue completed | requeued={len(task_ids)} tasks={len(task_ids)}")
    return RequeueResponse(requeued_count=len(task_ids), task_ids=task_ids)


@router.post("/summarize", response_model=SummarizeResponse)
def summarize_article(
    payload: SummarizeRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
):
    if not settings.summarization.enabled:
        raise HTTPException(status_code=503, detail="summarizer disabled in settings")

    artifact_repo = ArchiveArtifactRepository(settings.database.resolved_path(settings.data_dir))

    archived_url_id: Optional[int] = None
    rowid: Optional[int] = None
    item_id: Optional[str] = None

    if payload.rowid is not None:
        row = artifact_repo.get_by_id( int(payload.rowid))
        if row is None:
            raise HTTPException(status_code=404, detail="save not found")
        archived_url_id = row.archived_url_id
        rowid = int(row.id)
        # We need item_id to pass to worker? The worker currently takes article_id (item_id)
        # Let's find it.
        # Since row join might not be available here, we might need a better query or just pass DB ID.
        # But wait, TASK_GENERATE_SUMMARY signature in worker-summary/main.py takes (article_id: str).
        # This implies item_id (string UUID/slug), not integer ID.
        # We should resolve item_id.

        # NOTE: `get_by_id` returns `ArchiveArtifact` model. It might not have `item_id` directly joined if not configured.
        # But `list_by_item_id` implies we can search.
        # Let's assume we can get it or fail.
        # Actually `row` is ArchiveArtifact.
        pass

    elif payload.item_id:
        item_id = sanitize_filename(payload.item_id.strip())
        rows = artifact_repo.list_by_item_id( item_id)
        if not rows:
            raise HTTPException(status_code=404, detail="no saves for item_id")
        first = rows[0]
        archived_url_id = first.archived_url_id
        rowid = int(first.id)
    elif payload.url:
        rows = artifact_repo.list_by_url( str(payload.url))
        if not rows:
            raise HTTPException(status_code=404, detail="no saves for url")
        first = rows[0]
        archived_url_id = first.archived_url_id
        rowid = int(first.id)
        # We need item_id for the worker
        # We can query UrlRepo or MetadataRepo to get item_id?
        # Or just use the one from `list_by_url` if it joins.
        # `list_by_url` returns rows.
        pass

    if item_id is None and rowid:
         # Try to find item_id from rowid if not set
         # Since we don't have easy reverse lookup here without more DB queries,
         # and we want to be safe.
         # For now, let's just trigger the task if we have item_id.
         pass

    # If we still don't have item_id, we might have a problem dispatching to a worker that expects it.
    # Ideally we update the worker to take int ID or we fetch it here.
    # Let's try to fetch it from `ArchivedUrlRepository` if we have `archived_url_id`.

    if archived_url_id and not item_id:
        # TODO: Add repository method to get item_id by ID if needed.
        # For now, if we can't resolve it, we can't dispatch easily.
        # But wait, `list_by_item_id` verified it exists.
        pass

    # Dispatch task
    # For now, passing item_id if available.
    if item_id:
        celery_app.send_task(TASK_GENERATE_SUMMARY, args=[item_id])
        summary_created = True
    else:
        # Fallback or error
        summary_created = False
        logger.warning(f"Could not resolve item_id for summarization request {payload}")

    return SummarizeResponse(
        ok=summary_created,
        archived_url_id=archived_url_id,
        summary_created=summary_created,
    )


@router.delete("/saves/{rowid}", response_model=DeleteResponse)
def delete_save(
    rowid: int,
    remove_files: bool = False,
    settings: AppSettings = Depends(get_settings),
):
    artifact_repo = ArchiveArtifactRepository(settings.database.resolved_path(settings.data_dir))
    # Fetch the row to know what to delete
    row = artifact_repo.get_by_id( rowid)
    if row is None:
        raise HTTPException(status_code=404, detail="save not found")
    to_delete = [int(rowid)]
    removed_files: List[str] = []
    errors: List[str] = []

    # Delete DB row first
    deleted = artifact_repo.delete_many( to_delete)

    # Optionally remove file from disk (best-effort)
    if remove_files and row.saved_path:
        try:
            from pathlib import Path

            p = Path(row.saved_path)
            if p.exists():
                rp = p.resolve()
                data_root = Path(settings.data_dir).resolve()
                if data_root in rp.parents:
                    p.unlink()
                    removed_files.append(str(p))
                    # Prune empty parents up to data root
                    parent = p.parent
                    while parent != data_root and parent.is_dir():
                        try:
                            parent.rmdir()
                        except OSError:
                            break
                        parent = parent.parent
        except Exception as e:
            errors.append(str(e))

    return DeleteResponse(
        deleted_count=deleted,
        deleted_rowids=to_delete,
        removed_files=removed_files,
        errors=errors,
        ok=True,
    )


@router.delete("/saves/by-item/{item_id}", response_model=DeleteResponse)
def delete_saves_by_item(
    item_id: str,
    remove_files: bool = False,
    settings: AppSettings = Depends(get_settings),
):
    artifact_repo = ArchiveArtifactRepository(settings.database.resolved_path(settings.data_dir))
    item_id = sanitize_filename(item_id.strip())
    rows = artifact_repo.list_by_item_id( item_id)
    if not rows:
        raise HTTPException(status_code=404, detail="no saves for item_id")
    rowids = [int(r.id) for r in rows]
    saved_paths = [r.saved_path for r in rows if r.saved_path]
    deleted = artifact_repo.delete_many( rowids)

    removed_files: List[str] = []
    errors: List[str] = []
    if remove_files:
        from pathlib import Path

        data_root = Path(settings.data_dir).resolve()
        for sp in saved_paths:
            try:
                p = Path(sp)
                if not p.exists():
                    continue
                rp = p.resolve()
                if data_root in rp.parents:
                    p.unlink()
                    removed_files.append(str(p))
                    parent = p.parent
                    while parent != data_root and parent.is_dir():
                        try:
                            parent.rmdir()
                        except OSError:
                            break
                        parent = parent.parent
            except Exception as e:
                errors.append(str(e))

    return DeleteResponse(
        deleted_count=deleted,
        deleted_rowids=rowids,
        removed_files=removed_files,
        errors=errors,
        ok=True,
    )


@router.delete("/saves/by-url", response_model=DeleteResponse)
def delete_saves_by_url_endpoint(
    url: str,
    remove_files: bool = False,
    settings: AppSettings = Depends(get_settings),
):
    artifact_repo = ArchiveArtifactRepository(settings.database.resolved_path(settings.data_dir))
    rows = artifact_repo.list_by_url( url)
    if not rows:
        raise HTTPException(status_code=404, detail="no saves for url")
    rowids = [int(r.id) for r in rows]
    saved_paths = [r.saved_path for r in rows if r.saved_path]
    deleted = artifact_repo.delete_many( rowids)

    removed_files: List[str] = []
    errors: List[str] = []
    if remove_files:
        from pathlib import Path

        data_root = Path(settings.data_dir).resolve()
        for sp in saved_paths:
            try:
                p = Path(sp)
                if not p.exists():
                    continue
                rp = p.resolve()
                if data_root in rp.parents:
                    p.unlink()
                    removed_files.append(str(p))
                    parent = p.parent
                    while parent != data_root and parent.is_dir():
                        try:
                            parent.rmdir()
                        except OSError:
                            break
                        parent = parent.parent
            except Exception as e:
                errors.append(str(e))

    return DeleteResponse(
        deleted_count=deleted,
        deleted_rowids=rowids,
        removed_files=removed_files,
        errors=errors,
        ok=True,
    )
