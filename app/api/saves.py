from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request

from core.config import AppSettings, get_settings
from db.repository import (
    init_db,
    insert_save_result,
    find_existing_success_save,
    record_http_failure,
    insert_save_metadata,
)
from services.summarizer import trigger_summarization_if_ready
from models import (
    ArchiveResult,
    SaveRequest,
    SaveResponse,
    BatchCreateRequest,
    TaskAccepted,
)
from core.utils import sanitize_filename
from core.utils import get_url_status


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

    # For direct single-archiver endpoint, optionally skip if already saved for that archiver
    # For archiver=="all", we handle per-archiver skipping inside the loop below

    # Resolve archivers to run
    if archiver_name == "all":
        archiver_items = list(registry.items())
        if not archiver_items:
            raise HTTPException(status_code=500, detail="no archivers registered")
    else:
        archiver = registry.get(archiver_name)
        if archiver is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown archiver: {archiver_name}"
            )
        archiver_items = [(archiver_name, archiver)]

    last_result: ArchiveResult | None = None
    last_row_id: int | None = None
    summarizer = getattr(request.app.state, "summarizer", None)

    # Run each archiver sequentially and record a row per run
    for name, archiver_obj in archiver_items:
        # Pre-check URL reachability and map 404 -> immediate failure
        try:
            status = get_url_status(str(payload.url))
        except Exception:
            status = None
        if status == 404:
            # Record failed result with exit_code=404 via central helper
            try:
                last_row_id = record_http_failure(
                    db_path=settings.resolved_db_path,
                    item_id=safe_id,
                    url=str(payload.url),
                    archiver_name=name,
                    exit_code=404,
                )
            except Exception:
                last_row_id = None
            last_result = ArchiveResult(success=False, exit_code=404, saved_path=None)
            continue
        # Optional per-archiver skip
        if settings.skip_existing_saves:
            try:
                existing = find_existing_success_save(
                    settings.resolved_db_path,
                    item_id=safe_id,
                    url=str(payload.url),
                    archiver=name,
                )
            except Exception:
                existing = None
            if existing is not None:
                last_result = ArchiveResult(
                    success=True, exit_code=0, saved_path=existing.saved_path
                )
                try:
                    init_db(settings.resolved_db_path)
                    last_row_id = insert_save_result(
                        db_path=settings.resolved_db_path,
                        item_id=safe_id,
                        url=str(payload.url),
                        success=True,
                        exit_code=0,
                        saved_path=existing.saved_path,
                        archiver_name=name,
                    )
                    if last_row_id is not None and name == "readability":
                        trigger_summarization_if_ready(
                            summarizer,
                            settings=settings,
                            rowid=last_row_id,
                            archived_url_id=existing.archived_url_id,
                            reason=f"api-existing-{name}",
                        )
                except Exception:
                    last_row_id = None
                continue

        result: ArchiveResult = archiver_obj.archive(
            url=str(payload.url), item_id=safe_id
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
                archiver_name=name,
            )
            if (
                result.success
                and getattr(result, "metadata", None)
                and name == "readability"
                and last_row_id is not None
            ):
                try:
                    insert_save_metadata(
                        db_path=settings.resolved_db_path,
                        save_rowid=last_row_id,
                        data=result.metadata,  # type: ignore[arg-type]
                    )
                except Exception as exc:
                    print(
                        f"Failed to persist readability metadata (rowid={last_row_id}): {exc}"
                    )

            if result.success and last_row_id is not None and name == "readability":
                trigger_summarization_if_ready(
                    summarizer,
                    settings=settings,
                    rowid=last_row_id,
                    reason=f"api-{name}",
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

    items = [{"item_id": safe_id, "url": str(payload.url)}]

    # Let TaskManager handle per-archiver skip logic instead of dropping upfront

    tm = getattr(request.app.state, "task_manager", None)
    if tm is None:
        raise HTTPException(status_code=500, detail="task manager not initialized")
    task_id = tm.enqueue("all", items)
    return TaskAccepted(task_id=task_id, count=len(items))


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
        items.append({"item_id": safe_id, "url": str(it.url)})

    # Let TaskManager handle per-archiver skip logic

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


