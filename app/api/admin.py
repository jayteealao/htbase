from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request

from core.config import AppSettings, get_settings
from db.repository import (
    list_saves,
    get_save_by_rowid,
    get_saves_by_item_id,
    get_saves_by_url,
    delete_saves_by_rowids,
)
from models import DeleteResponse
from core.utils import sanitize_filename


router = APIRouter()


@router.get("/saves", response_model=List[Dict[str, object]])
def list_saves_endpoint(
    limit: int = 200,
    offset: int = 0,
    settings: AppSettings = Depends(get_settings),
):
    rows = list_saves(settings.resolved_db_path, limit=limit, offset=offset)
    # Serialize and enrich
    out: List[Dict[str, object]] = []
    from pathlib import Path

    data_root = Path(settings.data_dir).resolve()
    for r in rows:
        created_val = getattr(r, "created_at", None)
        created_at = created_val.isoformat() if hasattr(created_val, "isoformat") else created_val
        saved_path = r.saved_path
        file_exists = False
        rel_path = None
        archiver = None
        if saved_path:
            p = Path(saved_path)
            file_exists = p.exists()
            try:
                rp = p.resolve()
                if data_root in rp.parents:
                    rel_path = str(rp.relative_to(data_root))
            except Exception:
                rel_path = None
            # Infer archiver from path segment if present
            parts = p.parts
            if len(parts) >= 2:
                # Expect .../<item_id>/<archiver>/<file>
                archiver = parts[-2]
        out.append(
            {
                "rowid": int(r.rowid),
                "id": r.item_id,
                "url": r.url,
                "name": r.name,
                "status": r.status,
                "success": 1 if r.success else 0,
                "exit_code": r.exit_code,
                "saved_path": r.saved_path,
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


@router.delete("/saves/{rowid}", response_model=DeleteResponse)
def delete_save(
    rowid: int,
    remove_files: bool = False,
    settings: AppSettings = Depends(get_settings),
):
    # Fetch the row to know what to delete
    row = get_save_by_rowid(settings.resolved_db_path, rowid)
    if row is None:
        raise HTTPException(status_code=404, detail="save not found")
    to_delete = [int(rowid)]
    removed_files: List[str] = []
    errors: List[str] = []

    # Delete DB row first
    deleted = delete_saves_by_rowids(settings.resolved_db_path, to_delete)

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
    item_id = sanitize_filename(item_id.strip())
    rows = get_saves_by_item_id(settings.resolved_db_path, item_id)
    if not rows:
        raise HTTPException(status_code=404, detail="no saves for item_id")
    rowids = [int(r.rowid) for r in rows]
    saved_paths = [r.saved_path for r in rows if r.saved_path]
    deleted = delete_saves_by_rowids(settings.resolved_db_path, rowids)

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
    rows = get_saves_by_url(settings.resolved_db_path, url)
    if not rows:
        raise HTTPException(status_code=404, detail="no saves for url")
    rowids = [int(r.rowid) for r in rows]
    saved_paths = [r.saved_path for r in rows if r.saved_path]
    deleted = delete_saves_by_rowids(settings.resolved_db_path, rowids)

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
