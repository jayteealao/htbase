from __future__ import annotations

import logging
import mimetypes
import tarfile
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from common.core.config import AppSettings, get_settings
from common.db import (
    ArchiveArtifactRepository,
    ArchivedUrlRepository,
    UrlMetadataRepository,
)

from common.db.repository import insert_save_result, record_http_failure
from common.models import (
    ArchiveResult,
    ArchiveRetrieveRequest,
    SaveRequest,
    SaveResponse,
    BatchCreateRequest,
    TaskAccepted,
)
from common.core.utils import sanitize_filename, check_url_archivability, rewrite_paywalled_url
from common.celery_config import (
    celery_app,
    ARCHIVER_TASK_MAP,
)

logger = logging.getLogger(__name__)

router = APIRouter()

artifact_repo = ArchiveArtifactRepository()
url_repo = ArchivedUrlRepository()
metadata_repo = UrlMetadataRepository()


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
            artifact = artifact_repo.find_successful(
                settings.database.resolved_path(settings.data_dir),
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
            artifact_repo.list_by_item_id( item_id=safe_id)
        )
    if url:
        artifacts.extend(
            artifact_repo.list_by_url( url=url)
        )
    return _latest_successful_artifacts(artifacts)



def _archive_with(
    archiver_name: str,
    payload: SaveRequest,
    request: Request,
    settings: AppSettings,
) -> SaveResponse:
    try:
        payload_snapshot = payload.model_dump()
    except AttributeError:
        payload_snapshot = payload.dict()
    logger.info("Archive request received", extra={"archiver": archiver_name, "payload": payload_snapshot})

    item_id = payload.id.strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="id is required")
    safe_id = sanitize_filename(item_id)
    original_url = str(payload.url)

    # Determine which task(s) to run
    tasks_to_run = []
    if archiver_name == "all":
        # Run all known archivers
        for name, task_name in ARCHIVER_TASK_MAP.items():
            if name != "singlefile-cli": # skip alias duplication
                tasks_to_run.append((name, task_name))
    else:
        task_name = ARCHIVER_TASK_MAP.get(archiver_name)
        if not task_name:
             raise HTTPException(status_code=404, detail=f"Unknown or unsupported archiver in worker mode: {archiver_name}")
        tasks_to_run.append((archiver_name, task_name))

    if not tasks_to_run:
        raise HTTPException(status_code=500, detail="No valid archivers found to run")

    # In legacy synchronous mode (implied by SaveResponse return type), we usually only wait for ONE result if specific archiver requested.
    # If "all" is requested, the old code ran all sequentially and returned the LAST result.
    # We will trigger all via Celery.

    last_result = None
    last_row_id = None

    # Trigger tasks
    for name, task_signature in tasks_to_run:
        logger.info(f"Triggering Celery task | archiver={name} task={task_signature} item_id={safe_id}")

        # Send task to Celery
        # We pass arguments matching the task definition: (url, item_id)
        async_result = celery_app.send_task(
            task_signature,
            args=[original_url, safe_id],
            kwargs={}
        )

        # For the synchronous API contract, we must wait for the result
        # Note: This blocks the API thread, which is suboptimal but required for compatibility
        try:
            # Wait up to 300 seconds (5 minutes)
            result_data = async_result.get(timeout=300)

            # The task should return a dict or ArchiveResult-like structure
            # We reconstruct ArchiveResult from the dict
            if isinstance(result_data, dict):
                # Assuming worker returns serialized ArchiveResult
                last_result = ArchiveResult(
                    success=result_data.get("success", False),
                    exit_code=result_data.get("exit_code", 1),
                    saved_path=result_data.get("saved_path"),
                )
                # The worker should have handled DB insertion, but we might need the row_id
                # Ideally the worker returns the row_id too.
                # If the worker logic mirrors the old logic, it should return { ... "db_rowid": ... } if we modify it to do so.
                # For now, let's assume the worker does the DB insert.
                # If we need 'db_rowid' for the response, we might need to query it or have the worker return it.

                # Check if we can get row_id from DB if not returned
                # This is a bit race-y if multiple saves happen
                last_row_id = result_data.get("db_rowid")
            else:
                # Unexpected result format
                logger.error(f"Unexpected result from task {task_signature}: {result_data}")
                last_result = ArchiveResult(success=False, exit_code=500, saved_path=None)

        except Exception as e:
            logger.error(f"Error waiting for task {task_signature}: {e}")
            last_result = ArchiveResult(success=False, exit_code=500, saved_path=None)

    if last_result is None:
         raise HTTPException(status_code=500, detail="Task execution failed or timed out")

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

    # Lazy migration: if article exists in PostgreSQL but not Firestore, migrate it
    if settings.enable_lazy_migration and hasattr(request.app.state, 'firestore_storage'):
        firestore = request.app.state.firestore_storage
        postgres = request.app.state.postgres_storage

        if firestore and postgres and safe_id:
            try:
                # Check if article exists in Firestore
                fs_article = firestore.get_article(safe_id)

                if not fs_article and artifacts:
                    # Article exists in PostgreSQL but not in Firestore - migrate it
                    logger.info(f"Lazy migrating article {safe_id} to Firestore")

                    # Get article from PostgreSQL
                    pg_article = postgres.get_article(safe_id)
                    if pg_article:
                        # Import SyncFilter for data filtering
                        from common.storage.sync_filter import SyncFilter
                        sync_filter = SyncFilter()

                        # Filter data for Firestore
                        fs_data = sync_filter.filter_for_firestore(pg_article)

                        # Create article in Firestore
                        firestore.create_article(pg_article.metadata)

                        # Sync pocket data if present
                        if pg_article.pocket:
                            firestore.create_pocket_data(pg_article.pocket)

                        # Sync artifacts
                        for artifact in pg_article.archives:
                            firestore.create_artifact(artifact)

                        logger.info(f"Lazily migrated {safe_id} to Firestore ({len(pg_article.archives)} artifacts)")
            except Exception as e:
                logger.error(f"Lazy migration failed for {safe_id}: {e}")
                # Continue with normal retrieval even if migration fails

    if archiver_name != "all":
        if not artifacts:
            raise HTTPException(status_code=404, detail="url not archived")
        artifact = artifacts[-1]
        saved_path = getattr(artifact, "saved_path", None)
        if not saved_path:
            raise HTTPException(status_code=404, detail="url not archived")

        # Storage-aware file serving - works with any backend
        archiver_label = getattr(artifact, "archiver", archiver_name)
        base_label = safe_id or sanitize_filename(url_str or "archive")

        # Try to determine media type from path or default to octet-stream
        media_type, _ = mimetypes.guess_type(str(saved_path))
        media_type = media_type or "application/octet-stream"

        # Generate appropriate filename based on archiver and file type
        extension = Path(saved_path).suffix or infer_extension_from_archiver(archiver_label)
        filename = f"{base_label}-{archiver_label}{extension}"

        # Check if we have storage providers available
        if hasattr(request.app.state, 'file_storage_providers') and request.app.state.file_storage_providers:
            # Try to retrieve from any storage provider
            for provider in request.app.state.file_storage_providers:
                try:
                    # Check if file exists in this provider
                    storage_path = saved_path.replace(str(settings.data_dir), "archives")
                    if provider.exists(storage_path):
                        logger.info(
                            f"Serving archived artifact via {provider.provider_name}",
                            extra={"archiver": archiver_label, "item_id": safe_id, "storage_path": storage_path},
                        )
                        return provider.serve_file(
                            storage_path=storage_path,
                            filename=filename,
                            media_type=media_type
                        )
                except Exception as e:
                    logger.warning(f"Failed to serve from {provider.provider_name}: {e}")
                    continue

        # Fallback to local file serving if exists
        file_path = Path(saved_path)
        if file_path.exists():
            logger.info(
                "Serving archived artifact via local filesystem",
                extra={"archiver": archiver_label, "item_id": safe_id, "path": str(file_path)},
            )
            return FileResponse(
                path=str(file_path),
                media_type=media_type,
                filename=filename,
            )

    files: list[tuple[str, Path]] = []
    temp_files: list[Path] = []  # Track temporary files for cleanup

    for artifact in artifacts:
        saved_path = getattr(artifact, "saved_path", None)
        archiver_label = getattr(artifact, "archiver", "artifact")
        if not saved_path:
            continue

        # Check if we have storage providers available
        if hasattr(request.app.state, 'file_storage_providers') and request.app.state.file_storage_providers:
            # Try to download from any storage provider
            downloaded = False
            for provider in request.app.state.file_storage_providers:
                try:
                    storage_path = saved_path.replace(str(settings.data_dir), "archives")
                    if provider.exists(storage_path):
                        temp_file = provider.download_to_temp(storage_path)
                        files.append((archiver_label, temp_file))
                        temp_files.append(temp_file)
                        downloaded = True
                        break
                except Exception as e:
                    logger.warning(f"Failed to download from {provider.provider_name}: {e}")
                    continue

            if downloaded:
                continue

        # Fallback to local file serving
        file_path = Path(saved_path)
        if file_path.exists():
                files.append((archiver_label, file_path))

    if not files:
        raise HTTPException(status_code=404, detail="url not archived")

    try:
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
    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            try:
                temp_file.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file {temp_file}: {e}")


@router.post("/save", response_model=TaskAccepted, status_code=202)
def save_default(
    payload: SaveRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
):
    try:
        payload_snapshot = payload.model_dump()
    except AttributeError:
        payload_snapshot = payload.dict()
    logger.info(f"/save requested | payload={payload_snapshot}")

    item_id = payload.id.strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="id is required")
    safe_id = sanitize_filename(item_id)
    url = str(payload.url)

    # Fan-out: Trigger all supported archivers
    # We use a group or just fire and forget.
    # Returning a single task_id is tricky if we fire multiple.
    # We will return the task_id of the first one or a generated ID.

    first_task_id = None
    count = 0

    for name, task_signature in ARCHIVER_TASK_MAP.items():
        if name == "singlefile-cli": continue

        async_result = celery_app.send_task(
            task_signature,
            args=[url, safe_id],
            kwargs={}
        )
        if not first_task_id:
            first_task_id = async_result.id
        count += 1

    logger.info(f"/save enqueued | task_id={first_task_id} archiver_count={count}")
    return TaskAccepted(task_id=first_task_id or "batch-submitted", count=1)


@router.post("/archive/{archiver}/batch", response_model=TaskAccepted, status_code=202)
def archive_with_batch(
    archiver: str,
    payload: BatchCreateRequest,
    request: Request,
    settings: AppSettings = Depends(get_settings),
):
    # This endpoint used to take a list of items and an archiver.
    # We iterate and fire tasks.

    task_name = ARCHIVER_TASK_MAP.get(archiver)
    if archiver == "all":
        # Handle all
        pass
    elif not task_name:
         raise HTTPException(status_code=404, detail=f"Unknown archiver: {archiver}")

    first_task_id = None
    count = 0

    for item in payload.items:
        safe_id = sanitize_filename(item.id.strip())
        url = str(item.url)

        if archiver == "all":
            for _, sig in ARCHIVER_TASK_MAP.items():
                res = celery_app.send_task(sig, args=[url, safe_id])
                if not first_task_id: first_task_id = res.id
        else:
            res = celery_app.send_task(task_name, args=[url, safe_id])
            if not first_task_id: first_task_id = res.id

        count += 1

    return TaskAccepted(task_id=first_task_id or "batch-submitted", count=count)


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
    archived_url = url_repo.get_by_id( archived_url_id)
    if not archived_url:
        raise HTTPException(status_code=404, detail="Archived URL not found")

    # Get size statistics
    size_stats = artifact_repo.get_size_stats(
        settings.database.resolved_path(settings.data_dir),
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


def infer_extension_from_archiver(archiver_name: str) -> str:
    """Infer file extension based on archiver name."""
    archiver_extensions = {
        "monolith": ".html",
        "singlefile": ".html",
        "readability": ".html",
        "pdf": ".pdf",
        "screenshot": ".png",
        "singlefile-cli": ".html",
    }
    return archiver_extensions.get(archiver_name.lower(), "")
