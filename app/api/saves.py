from __future__ import annotations

import logging
import mimetypes
import tarfile
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from core.config import AppSettings, get_settings
from db.repository import (
    init_db,
    insert_save_result,
    find_existing_success_save,
    record_http_failure,
    insert_save_metadata,
    get_saves_by_item_id,
    get_saves_by_url,
    get_size_stats_by_archived_url_id,
    get_archived_url_by_id,
)
from models import (
    ArchiveResult,
    ArchiveRetrieveRequest,
    SaveRequest,
    SaveResponse,
    BatchCreateRequest,
    TaskAccepted,
)
from core.utils import sanitize_filename, get_url_status, rewrite_paywalled_url, extract_original_url

logger = logging.getLogger(__name__)

router = APIRouter()


def _sanitize_optional_id(raw_id: Optional[str]) -> Optional[str]:
    if raw_id is None:
        return None
    stripped = raw_id.strip()
    if not stripped:
        return None
    return sanitize_filename(stripped)


def _latest_successful_artifacts(artifacts: List[object]) -> List[object]:
    latest: dict[str, object] = {}
    for artifact in artifacts:
        if not getattr(artifact, "success", False):
            continue
        saved_path = getattr(artifact, "saved_path", None)
        if not saved_path:
            continue
        archiver = getattr(artifact, "archiver", "")
        current = latest.get(archiver)
        current_id = getattr(current, "id", 0) if current is not None else 0
        candidate_id = getattr(artifact, "id", 0)
        if current is None or candidate_id >= current_id:
            latest[archiver] = artifact
    return list(latest.values())


def _collect_existing_artifacts(
    *,
    archiver: str,
    safe_id: Optional[str],
    url: Optional[str],
    settings: AppSettings,
) -> List[object]:
    if archiver != "all":
        try:
            artifact = find_existing_success_save(
                settings.resolved_db_path,
                item_id=safe_id or "",
                url=url or "",
                archiver=archiver,
            )
        except Exception:
            artifact = None
        return [artifact] if artifact and getattr(artifact, "saved_path", None) else []

    artifacts: List[object] = []
    if safe_id:
        artifacts.extend(
            get_saves_by_item_id(settings.resolved_db_path, item_id=safe_id)
        )
    if url:
        artifacts.extend(
            get_saves_by_url(settings.resolved_db_path, url=url)
        )
    return _latest_successful_artifacts(artifacts)



def _archive_with(
    archiver_name: str,
    payload: SaveRequest,
    request: Request,
    settings: AppSettings,
) -> SaveResponse:
    # Registry lives on app.state
    registry: Dict[str, object] = getattr(request.app.state, "archivers", {})
    try:
        payload_snapshot = payload.model_dump()  # type: ignore[attr-defined]
    except AttributeError:
        payload_snapshot = payload.dict()  # type: ignore[attr-defined]
    logger.info(f"Archive request received", extra={"archiver": archiver_name, "payload": payload_snapshot})

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
    summarization = getattr(request.app.state, "summarization", None)

    # Apply paywall URL rewriting
    original_url = str(payload.url)
    rewritten_url = rewrite_paywalled_url(original_url)
    if rewritten_url != original_url:
        logger.info(f"Rewriting URL for paywall bypass | original={original_url} rewritten={rewritten_url}")

    # Run each archiver sequentially and record a row per run
    for name, archiver_obj in archiver_items:
        logger.info(f"Starting archiver run | archiver={name} item_id={safe_id} url={rewritten_url}")
        # Pre-check URL reachability and map 404 -> immediate failure
        try:
            status = get_url_status(rewritten_url)
        except Exception:
            status = None
        logger.info(f"URL status probe | archiver={name} item_id={safe_id} status={status}")
        if status == 404:
            logger.info(f"URL responded 404 | archiver={name} item_id={safe_id} url={rewritten_url}")
            # Record failed result with exit_code=404 via central helper
            try:
                last_row_id = record_http_failure(
                    db_path=settings.resolved_db_path,
                    item_id=safe_id,
                    url=rewritten_url,
                    archiver_name=name,
                    exit_code=404,
                )
            except Exception:
                last_row_id = None
            last_result = ArchiveResult(success=False, exit_code=404, saved_path=None)
            continue
        # Optional per-archiver skip - check both rewritten and original URLs
        if settings.skip_existing_saves:
            try:
                # Check rewritten URL first
                existing = find_existing_success_save(
                    settings.resolved_db_path,
                    item_id=safe_id,
                    url=rewritten_url,
                    archiver=name,
                )
                # Also check original URL if this is a freedium URL
                if existing is None:
                    extracted_original = extract_original_url(rewritten_url)
                    if extracted_original:
                        existing = find_existing_success_save(
                            settings.resolved_db_path,
                            item_id=safe_id,
                            url=extracted_original,
                            archiver=name,
                        )
            except Exception:
                existing = None
            if existing is not None:
                logger.info(f"Reusing existing artifact | archiver={name} item_id={safe_id} saved_path={existing.saved_path}")
                last_result = ArchiveResult(
                    success=True, exit_code=0, saved_path=existing.saved_path
                )
                try:
                    init_db(settings.resolved_db_path)
                    last_row_id = insert_save_result(
                        db_path=settings.resolved_db_path,
                        item_id=safe_id,
                        url=rewritten_url,
                        success=True,
                        exit_code=0,
                        saved_path=existing.saved_path,
                        archiver_name=name,
                    )
                    if (
                        last_row_id is not None
                        and name == "readability"
                        and summarization is not None
                    ):
                        summarization.schedule(
                            rowid=last_row_id,
                            archived_url_id=existing.archived_url_id,
                            reason=f"api-existing-{name}",
                        )
                        logger.info(f"Scheduled summarization | archiver={name} rowid={last_row_id} reason=api-existing-{name}")
                except Exception:
                    logger.info(f"Failed to persist save result | archiver={name} item_id={safe_id}")
                    last_row_id = None
                continue

        result: ArchiveResult = archiver_obj.archive(
            url=rewritten_url, item_id=safe_id
        )
        last_result = result
        logger.info(f"Archiver completed | archiver={name} item_id={safe_id} success={result.success} exit_code={result.exit_code} saved_path={result.saved_path}")
        # Record to DB (best-effort)
        try:
            init_db(settings.resolved_db_path)
            last_row_id = insert_save_result(
                db_path=settings.resolved_db_path,
                item_id=safe_id,
                url=rewritten_url,
                success=result.success,
                exit_code=result.exit_code,
                saved_path=result.saved_path,
                archiver_name=name,
            )
            logger.info(f"Persisted save result | archiver={name} item_id={safe_id} rowid={last_row_id}")
            if (
                result.success
                and getattr(result, "metadata", None)
                and name == "readability"
                and last_row_id is not None
            ):
                try:
                    logger.info(f"Persisting readability metadata | rowid={last_row_id}")
                    insert_save_metadata(
                        db_path=settings.resolved_db_path,
                        save_rowid=last_row_id,
                        data=result.metadata,  # type: ignore[arg-type]
                    )
                except Exception as exc:
                    logger.error(
                        f"Failed to persist readability metadata (rowid={last_row_id}): {exc}"
                    )

            if (
                result.success
                and last_row_id is not None
                and name == "readability"
                and summarization is not None
            ):
                summarization.schedule(
                    rowid=last_row_id,
                    reason=f"api-{name}",
                )
                logger.info(f"Scheduled summarization | archiver={name} rowid={last_row_id} reason=api-{name}")
        except Exception:
            last_row_id = None

    # If for some reason there was no archiver run, error
    if last_result is None:
        raise HTTPException(status_code=500, detail="no archiver executed")

    logger.info(f"Returning archive response | archiver={archiver_name} item_id={safe_id} ok={last_result.success} exit_code={last_result.exit_code} rowid={last_row_id}")
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
    logger.info(f"/archive/{archiver} invoked")
    response = _archive_with(archiver, payload, request, settings)
    logger.info(f"/archive/{archiver} response | ok={response.ok} exit_code={response.exit_code} rowid={response.db_rowid}")
    return response


@router.post("/archive/retrieve")
def retrieve_archive(
    payload: ArchiveRetrieveRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
):
    archiver_name = (payload.archiver or "all").strip().lower() or "all"
    safe_id = _sanitize_optional_id(payload.id)
    url_str = str(payload.url) if payload.url else None

    logger.info(
        "/archive/retrieve invoked",
        extra={"archiver": archiver_name, "item_id": safe_id, "url": url_str},
    )

    artifacts = _collect_existing_artifacts(
        archiver=archiver_name,
        safe_id=safe_id,
        url=url_str,
        settings=settings,
    )

    if archiver_name != "all":
        if not artifacts:
            raise HTTPException(status_code=404, detail="url not archived")
        artifact = artifacts[-1]
        saved_path = getattr(artifact, "saved_path", None)
        if not saved_path:
            raise HTTPException(status_code=404, detail="url not archived")
        file_path = Path(saved_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="archived file not available")
        media_type, _ = mimetypes.guess_type(str(file_path))
        media_type = media_type or "application/octet-stream"
        archiver_label = getattr(artifact, "archiver", archiver_name)
        base_label = safe_id or sanitize_filename(url_str or file_path.stem)
        filename = (
            f"{base_label}-{archiver_label}{file_path.suffix}"
            if file_path.suffix
            else f"{base_label}-{archiver_label}"
        )
        logger.info(
            "Returning archived artifact",
            extra={"archiver": archiver_label, "item_id": safe_id, "path": str(file_path)},
        )
        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=filename,
        )

    files: list[tuple[str, Path]] = []
    for artifact in artifacts:
        saved_path = getattr(artifact, "saved_path", None)
        archiver_label = getattr(artifact, "archiver", "artifact")
        if not saved_path:
            continue
        file_path = Path(saved_path)
        if file_path.exists():
            files.append((archiver_label, file_path))
    if not files:
        raise HTTPException(status_code=404, detail="url not archived")

    bundle_label = safe_id or sanitize_filename(url_str or "archive")
    filename = f"{bundle_label}-artifacts.tar.gz"
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for archiver_label, file_path in files:
            arcname = f"{archiver_label}/{file_path.name}"
            tar.add(str(file_path), arcname=arcname)
    buffer.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    logger.info(
        "Returning archived bundle",
        extra={"item_id": safe_id, "file_count": len(files), "filename": filename},
    )
    return StreamingResponse(buffer, media_type="application/gzip", headers=headers)


@router.post("/save", response_model=TaskAccepted, status_code=202)
def save_default(
    payload: SaveRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
):
    # Enqueue a single item to run through the "all" pipeline
    try:
        payload_snapshot = payload.model_dump()  # type: ignore[attr-defined]
    except AttributeError:
        payload_snapshot = payload.dict()  # type: ignore[attr-defined]
    logger.info(f"/save requested | payload={payload_snapshot}")
    item_id = payload.id.strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="id is required")
    safe_id = sanitize_filename(item_id)

    items = [{"item_id": safe_id, "url": str(payload.url)}]
    logger.info(f"Queueing default save | item_id={safe_id} url={payload.url}")

    # Let the archiver task manager handle per-archiver skip logic instead of dropping upfront

    tm = getattr(request.app.state, "task_manager", None)
    if tm is None:
        raise HTTPException(status_code=500, detail="task manager not initialized")
    task_id = tm.enqueue("all", items)
    logger.info(f"/save enqueued | task_id={task_id} item_count={len(items)}")
    return TaskAccepted(task_id=task_id, count=len(items))


@router.post("/archive/{archiver}/batch", response_model=TaskAccepted, status_code=202)
def archive_with_batch(
    archiver: str,
    payload: BatchCreateRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
):
    # Prepare items and enqueue async task
    try:
        payload_snapshot = payload.model_dump()  # type: ignore[attr-defined]
    except AttributeError:
        payload_snapshot = payload.dict()  # type: ignore[attr-defined]
    logger.info(f"/archive/{archiver}/batch requested | count={len(payload.items)} payload={payload_snapshot}")
    items = []
    for it in payload.items:
        safe_id = sanitize_filename(it.id.strip())
        if not safe_id:
            raise HTTPException(status_code=400, detail="id is required for each item")
        items.append({"item_id": safe_id, "url": str(it.url)})
        logger.info(f"Prepared batch item | archiver={archiver} item_id={safe_id} url={it.url}")

    # Let the archiver task manager handle per-archiver skip logic
    logger.info(f"Prepared batch enqueue | archiver={archiver} count={len(items)}")

    tm = getattr(request.app.state, "task_manager", None)
    if tm is None:
        raise HTTPException(status_code=500, detail="task manager not initialized")
    task_id = tm.enqueue(archiver, items)
    logger.info(f"/archive/{archiver}/batch enqueued | task_id={task_id} item_count={len(items)}")
    return TaskAccepted(task_id=task_id, count=len(items))


@router.post("/save/batch", response_model=TaskAccepted, status_code=202)
def save_default_batch(
    payload: BatchCreateRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
):
    # Default: run all archivers sequentially per item
    logger.info("/save/batch requested")
    response = archive_with_batch("all", payload, request, settings)
    logger.info(f"/save/batch response | task_id={response.task_id} count={response.count}")
    return response


@router.get("/archive/{archived_url_id}/size")
def get_archive_size(
    archived_url_id: int,
    settings: AppSettings = Depends(get_settings),
):
    """Get size statistics for an archived URL by its ID.

    Returns:
        - total_size_bytes: Total size across all artifacts for this URL
        - artifacts: List of {archiver, size_bytes, saved_path} for each artifact
    """
    logger.info(f"/archive/{archived_url_id}/size requested")

    # Verify the archived URL exists
    archived_url = get_archived_url_by_id(settings.resolved_db_path, archived_url_id)
    if not archived_url:
        raise HTTPException(status_code=404, detail="Archived URL not found")

    # Get size statistics
    size_stats = get_size_stats_by_archived_url_id(
        settings.resolved_db_path,
        archived_url_id
    )

    logger.info(
        f"/archive/{archived_url_id}/size response",
        extra={
            "archived_url_id": archived_url_id,
            "total_size_bytes": size_stats.get("total_size_bytes"),
            "artifact_count": len(size_stats.get("artifacts", []))
        }
    )

    return size_stats


