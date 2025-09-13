from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from config import AppSettings, get_settings
from db import init_db, insert_save_result
from models import ArchiveResult, SaveRequest, SaveResponse
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
