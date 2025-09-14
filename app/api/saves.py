from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request

from core.config import AppSettings, get_settings
from db.repository import init_db, insert_save_result, find_existing_success_save
from models import ArchiveResult, SaveRequest, SaveResponse, BatchCreateRequest, TaskAccepted
from core.utils import sanitize_filename


router = APIRouter()


def _archive_with(
    archiver_name: str,
    payload: SaveRequest,
    request: Request,
    settings: AppSettings,
) -> SaveResponse:
    # Registry lives on app.state
    registry: Dict[str, object] = getattr(request.app.state, "archivers", {})

    item_id = payload.id.strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="id is required")
    safe_id = sanitize_filename(item_id)

    # Optionally skip if already successfully saved
    if settings.skip_existing_saves:
        existing = find_existing_success_save(
            settings.resolved_db_path, item_id=safe_id, url=str(payload.url)
        )
        if existing is not None:
            return SaveResponse(
                ok=True,
                exit_code=0,
                saved_path=existing.saved_path,
                id=safe_id,
                db_rowid=int(existing.rowid) if getattr(existing, "rowid", None) is not None else None,
            )

    # Resolve archivers to run
    if archiver_name == "all":
        archiver_items = list(registry.items())
        if not archiver_items:
            raise HTTPException(status_code=500, detail="no archivers registered")
    else:
        archiver = registry.get(archiver_name)
        if archiver is None:
            raise HTTPException(status_code=404, detail=f"Unknown archiver: {archiver_name}")
        archiver_items = [(archiver_name, archiver)]

    last_result: ArchiveResult | None = None
    last_row_id: int | None = None
    # Run each archiver sequentially and record a row per run
    for name, archiver_obj in archiver_items:
        result: ArchiveResult = archiver_obj.archive(
            url=str(payload.url), item_id=safe_id, out_name=payload.name
        )
        last_result = result
        # Record to DB (best-effort)
        try:
            init_db(settings.resolved_db_path)
            last_row_id = insert_save_result(
                db_path=settings.resolved_db_path,
                item_id=safe_id,
                url=str(payload.url),
                success=result.success,
                exit_code=result.exit_code,
                saved_path=result.saved_path,
            )
        except Exception:
            last_row_id = None

    # If for some reason there was no archiver run, error
    if last_result is None:
        raise HTTPException(status_code=500, detail="no archiver executed")

    return SaveResponse(
        ok=last_result.success,
        exit_code=last_result.exit_code,
        saved_path=last_result.saved_path,
        id=safe_id,
        db_rowid=last_row_id,
    )


@router.post("/archive/{archiver}", response_model=SaveResponse)
def archive_with(
    archiver: str,
    payload: SaveRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
):
    return _archive_with(archiver, payload, request, settings)


@router.post("/save", response_model=TaskAccepted, status_code=202)
def save_default(
    payload: SaveRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
):
    # Enqueue a single item to run through the "all" pipeline
    item_id = payload.id.strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="id is required")
    safe_id = sanitize_filename(item_id)

    items = [{"item_id": safe_id, "url": str(payload.url), "name": payload.name}]

    # Optionally drop if already saved successfully
    if settings.skip_existing_saves:
        existing = find_existing_success_save(
            settings.resolved_db_path, item_id=safe_id, url=str(payload.url)
        )
        if existing is not None:
            items = []

    tm = getattr(request.app.state, "task_manager", None)
    if tm is None:
        raise HTTPException(status_code=500, detail="task manager not initialized")
    task_id = tm.enqueue("all", items)
    return TaskAccepted(task_id=task_id, count=len(items))
    # Run all archivers sequentially and return list of results
    # registry: Dict[str, object] = getattr(request.app.state, "archivers", {})
    # item_id = payload.id.strip()
    # if not item_id:
    #     raise HTTPException(status_code=400, detail="id is required")
    # safe_id = sanitize_filename(item_id)

    # # Optionally skip if already successfully saved (returns single result)
    # if settings.skip_existing_saves:
    #     existing = find_existing_success_save(
    #         settings.resolved_db_path, item_id=safe_id, url=str(payload.url)
    #     )
    #     if existing is not None:
    #         return [
    #             SaveResponse(
    #                 ok=True,
    #                 exit_code=0,
    #                 saved_path=existing.saved_path,
    #                 id=safe_id,
    #                 db_rowid=int(existing.rowid) if getattr(existing, "rowid", None) is not None else None,
    #             )
    #         ]

    # archiver_items = list(registry.items())
    # if not archiver_items:
    #     raise HTTPException(status_code=500, detail="no archivers registered")

    # results: List[SaveResponse] = []
    # for name, archiver_obj in archiver_items:
    #     result: ArchiveResult = archiver_obj.archive(
    #         url=str(payload.url), item_id=safe_id, out_name=payload.name
    #     )
    #     # Record to DB (best-effort)
    #     try:
    #         init_db(settings.resolved_db_path)
    #         row_id = insert_save_result(
    #             db_path=settings.resolved_db_path,
    #             item_id=safe_id,
    #             url=str(payload.url),
    #             success=result.success,
    #             exit_code=result.exit_code,
    #             saved_path=result.saved_path,
    #         )
    #     except Exception:
    #         row_id = None
    #     results.append(
    #         SaveResponse(
    #             ok=result.success,
    #             exit_code=result.exit_code,
    #             saved_path=result.saved_path,
    #             id=safe_id,
    #             db_rowid=row_id,
    #         )
    #     )
    # return results


@router.post("/archive/{archiver}/batch", response_model=TaskAccepted, status_code=202)
def archive_with_batch(
    archiver: str,
    payload: BatchCreateRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
):
    # Prepare items and enqueue async task
    items = []
    for it in payload.items:
        safe_id = sanitize_filename(it.id.strip())
        if not safe_id:
            raise HTTPException(status_code=400, detail="id is required for each item")
        items.append({"item_id": safe_id, "url": str(it.url), "name": it.name})

    # Optionally drop items already saved successfully
    if settings.skip_existing_saves:
        filtered: list[dict] = []
        for it in items:
            existing = find_existing_success_save(
                settings.resolved_db_path, item_id=str(it["item_id"]), url=str(it["url"])
            )
            if existing is None:
                filtered.append(it)
        items = filtered

    tm = getattr(request.app.state, "task_manager", None)
    if tm is None:
        raise HTTPException(status_code=500, detail="task manager not initialized")
    task_id = tm.enqueue(archiver, items)
    return TaskAccepted(task_id=task_id, count=len(items))


@router.post("/save/batch", response_model=TaskAccepted, status_code=202)
def save_default_batch(
    payload: BatchCreateRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
):
    # Default: run all archivers sequentially per item
    return archive_with_batch("all", payload, request, settings)
