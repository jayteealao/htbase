from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from config import AppSettings, get_settings
from db import init_db, insert_save_result, get_task_rows
from models import (
    ArchiveResult,
    SaveRequest,
    SaveResponse,
    BatchCreateRequest,
    TaskAccepted,
    TaskStatusResponse,
    TaskItemStatus,
)
from utils import sanitize_filename


router = APIRouter()


def _archive_with(
    archiver_name: str,
    payload: SaveRequest,
    request: Request,
    settings: AppSettings,
) -> SaveResponse:
    # Registry lives on app.state
    registry: Dict[str, object] = getattr(request.app.state, "archivers", {})
    archiver = registry.get(archiver_name)
    if archiver is None:
        raise HTTPException(status_code=404, detail=f"Unknown archiver: {archiver_name}")

    item_id = payload.id.strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="id is required")
    safe_id = sanitize_filename(item_id)

    # Run archive
    result: ArchiveResult = archiver.archive(url=str(payload.url), item_id=safe_id, out_name=payload.name)

    # Record to DB (best-effort)
    try:
        init_db(settings.resolved_db_path)
        row_id = insert_save_result(
            db_path=settings.resolved_db_path,
            item_id=safe_id,
            url=str(payload.url),
            success=result.success,
            exit_code=result.exit_code,
            saved_path=result.saved_path,
        )
    except Exception:
        row_id = None

    return SaveResponse(
        ok=result.success,
        exit_code=result.exit_code,
        saved_path=result.saved_path,
        ht_preview_url=f"http://{settings.ht_listen}",
        id=safe_id,
        db_rowid=row_id,
    )


@router.post("/archive/{archiver}", response_model=SaveResponse)
def archive_with(
    archiver: str,
    payload: SaveRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
):
    return _archive_with(archiver, payload, request, settings)


@router.post("/save", response_model=SaveResponse)
def save_default(
    payload: SaveRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
):
    # Backwards-compatible default archiver
    return _archive_with("monolith", payload, request, settings)


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


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
    return archive_with_batch("monolith", payload, request, settings)


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str, settings: AppSettings = Depends(get_settings)):
    rows = get_task_rows(settings.resolved_db_path, task_id)
    if not rows:
        raise HTTPException(status_code=404, detail="task not found")
    items: list[TaskItemStatus] = []
    for r in rows:
        # prefer explicit status if present, fallback to success int
        status_val = r.get("status")
        if not status_val:
            status_val = "success" if int(r.get("success", 0) or 0) == 1 else "failed"
        item_id = r.get("item_id") or r.get("user_id") or ""
        items.append(
            TaskItemStatus(
                url=r.get("url"),
                id=item_id,
                name=r.get("name"),
                status=status_val,
                exit_code=r.get("exit_code"),
                saved_path=r.get("saved_path"),
                db_rowid=r.get("rowid"),
            )
        )
    # Aggregate overall status
    overall = "pending" if any(i.status == "pending" for i in items) else (
        "failed" if any(i.status == "failed" for i in items) else "success"
    )
    return TaskStatusResponse(task_id=task_id, status=overall, items=items)
