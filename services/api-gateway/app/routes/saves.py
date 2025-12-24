"""
Saves API routes.

Handles URL archiving requests by dispatching to Celery workers.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from celery import chain, chord, group
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from shared.celery_config import celery_app
from shared.db import get_session_dependency, ArchivedUrl, ArchiveArtifact
from shared.models import (
    SaveRequest,
    BatchSaveRequest,
    ArchiveRetrieveRequest,
    SaveResponse,
    TaskAccepted,
    ArchiveWorkflowRequest,
)
from shared.utils import sanitize_filename, rewrite_paywalled_url

logger = logging.getLogger(__name__)

router = APIRouter()

# Available archivers
AVAILABLE_ARCHIVERS = ["singlefile", "monolith", "readability", "pdf", "screenshot"]


def get_db():
    """Database session dependency."""
    from shared.db import get_session

    with get_session() as session:
        yield session


@router.post("/save", response_model=TaskAccepted)
async def save_url(
    request: SaveRequest,
    db: Session = Depends(get_db),
):
    """
    Archive a single URL.

    Dispatches archive tasks to Celery workers for the specified archivers.
    Returns a task ID that can be used to track progress.
    """
    url = str(request.url)
    item_id = request.id
    archivers = request.archivers or AVAILABLE_ARCHIVERS

    logger.info(
        "Save request received",
        extra={"url": url, "item_id": item_id, "archivers": archivers},
    )

    # Validate archivers
    invalid_archivers = [a for a in archivers if a not in AVAILABLE_ARCHIVERS and a != "all"]
    if invalid_archivers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid archivers: {invalid_archivers}. Valid options: {AVAILABLE_ARCHIVERS}",
        )

    if "all" in archivers:
        archivers = AVAILABLE_ARCHIVERS

    # Check for existing URL
    existing = db.query(ArchivedUrl).filter(ArchivedUrl.url == url).first()
    if existing:
        archived_url_id = existing.id
    else:
        # Create new archived URL record
        archived_url = ArchivedUrl(
            url=url,
            item_id=item_id,
        )
        db.add(archived_url)
        db.flush()
        archived_url_id = archived_url.id

    # Create artifact records for each archiver
    workflow_id = uuid.uuid4().hex
    tasks = []

    for archiver in archivers:
        # Check for existing successful artifact
        existing_artifact = (
            db.query(ArchiveArtifact)
            .filter(
                ArchiveArtifact.archived_url_id == archived_url_id,
                ArchiveArtifact.archiver == archiver,
                ArchiveArtifact.success == True,
            )
            .first()
        )

        if existing_artifact:
            logger.info(
                "Skipping existing archive",
                extra={"archiver": archiver, "item_id": item_id},
            )
            continue

        # Create or get artifact record
        artifact = (
            db.query(ArchiveArtifact)
            .filter(
                ArchiveArtifact.archived_url_id == archived_url_id,
                ArchiveArtifact.archiver == archiver,
            )
            .first()
        )

        if not artifact:
            artifact = ArchiveArtifact(
                archived_url_id=archived_url_id,
                archiver=archiver,
                status="pending",
                task_id=workflow_id,
            )
            db.add(artifact)
            db.flush()

        # Rewrite URL for paywall bypass if needed
        fetch_url = rewrite_paywalled_url(url)

        # Create Celery task
        task_name = f"services.archive_worker.tasks.archive_{archiver}"
        tasks.append(
            celery_app.signature(
                task_name,
                kwargs={
                    "item_id": item_id,
                    "url": fetch_url,
                    "archived_url_id": archived_url_id,
                    "artifact_id": artifact.id,
                },
            )
        )

    db.commit()

    if not tasks:
        return TaskAccepted(
            task_id=workflow_id,
            count=0,
            message="All archives already exist",
        )

    # Dispatch tasks as a group
    task_group = group(tasks)
    result = task_group.apply_async()

    logger.info(
        "Archive tasks dispatched",
        extra={
            "workflow_id": workflow_id,
            "task_count": len(tasks),
            "archivers": archivers,
        },
    )

    return TaskAccepted(
        task_id=workflow_id,
        count=len(tasks),
        message=f"Archive tasks dispatched for {len(tasks)} archiver(s)",
    )


@router.post("/save/batch", response_model=TaskAccepted)
async def save_batch(
    request: BatchSaveRequest,
    db: Session = Depends(get_db),
):
    """
    Archive multiple URLs in batch.

    Dispatches archive tasks for all URLs and archivers.
    Returns a batch task ID for tracking overall progress.
    """
    batch_id = uuid.uuid4().hex
    total_tasks = 0

    logger.info(
        "Batch save request received",
        extra={"batch_id": batch_id, "item_count": len(request.items)},
    )

    all_tasks = []

    for item in request.items:
        url = str(item.url)
        item_id = item.id
        archivers = item.archivers or AVAILABLE_ARCHIVERS

        if "all" in archivers:
            archivers = AVAILABLE_ARCHIVERS

        # Get or create archived URL
        existing = db.query(ArchivedUrl).filter(ArchivedUrl.url == url).first()
        if existing:
            archived_url_id = existing.id
        else:
            archived_url = ArchivedUrl(url=url, item_id=item_id)
            db.add(archived_url)
            db.flush()
            archived_url_id = archived_url.id

        for archiver in archivers:
            # Skip existing successful artifacts
            existing_artifact = (
                db.query(ArchiveArtifact)
                .filter(
                    ArchiveArtifact.archived_url_id == archived_url_id,
                    ArchiveArtifact.archiver == archiver,
                    ArchiveArtifact.success == True,
                )
                .first()
            )

            if existing_artifact:
                continue

            # Create artifact record
            artifact = ArchiveArtifact(
                archived_url_id=archived_url_id,
                archiver=archiver,
                status="pending",
                task_id=batch_id,
            )
            db.add(artifact)
            db.flush()

            fetch_url = rewrite_paywalled_url(url)

            task_name = f"services.archive_worker.tasks.archive_{archiver}"
            all_tasks.append(
                celery_app.signature(
                    task_name,
                    kwargs={
                        "item_id": item_id,
                        "url": fetch_url,
                        "archived_url_id": archived_url_id,
                        "artifact_id": artifact.id,
                    },
                )
            )
            total_tasks += 1

    db.commit()

    if all_tasks:
        task_group = group(all_tasks)
        task_group.apply_async()

    logger.info(
        "Batch archive tasks dispatched",
        extra={"batch_id": batch_id, "task_count": total_tasks},
    )

    return TaskAccepted(
        task_id=batch_id,
        count=total_tasks,
        message=f"Batch archive tasks dispatched ({total_tasks} tasks)",
    )


@router.post("/workflow", response_model=TaskAccepted)
async def archive_workflow(
    request: ArchiveWorkflowRequest,
    db: Session = Depends(get_db),
):
    """
    Execute complete archive workflow.

    This workflow:
    1. Archives URL with specified archivers
    2. Summarizes content (if enabled)
    3. Uploads to cloud storage (if enabled)
    """
    workflow_id = uuid.uuid4().hex
    url = request.url
    item_id = request.item_id
    archivers = request.archivers if request.archivers != ["all"] else AVAILABLE_ARCHIVERS

    logger.info(
        "Workflow request received",
        extra={
            "workflow_id": workflow_id,
            "url": url,
            "item_id": item_id,
            "summarize": request.summarize,
            "upload": request.upload_to_storage,
        },
    )

    # Get or create archived URL
    existing = db.query(ArchivedUrl).filter(ArchivedUrl.url == url).first()
    if existing:
        archived_url_id = existing.id
    else:
        archived_url = ArchivedUrl(url=url, item_id=item_id)
        db.add(archived_url)
        db.flush()
        archived_url_id = archived_url.id

    # Build workflow chain
    archive_tasks = []
    fetch_url = rewrite_paywalled_url(url)

    for archiver in archivers:
        artifact = ArchiveArtifact(
            archived_url_id=archived_url_id,
            archiver=archiver,
            status="pending",
            task_id=workflow_id,
        )
        db.add(artifact)
        db.flush()

        task_name = f"services.archive_worker.tasks.archive_{archiver}"
        archive_tasks.append(
            celery_app.signature(
                task_name,
                kwargs={
                    "item_id": item_id,
                    "url": fetch_url,
                    "archived_url_id": archived_url_id,
                    "artifact_id": artifact.id,
                },
            )
        )

    db.commit()

    # Build workflow
    workflow = group(archive_tasks)

    # Add summarization if enabled
    if request.summarize:
        summarize_task = celery_app.signature(
            "services.summarization_worker.tasks.summarize_article",
            kwargs={
                "item_id": item_id,
                "archived_url_id": archived_url_id,
            },
        )
        workflow = chain(workflow, summarize_task)

    # Add storage upload if enabled
    if request.upload_to_storage:
        storage_task = celery_app.signature(
            "services.storage_worker.tasks.upload_artifacts",
            kwargs={
                "item_id": item_id,
                "archived_url_id": archived_url_id,
            },
        )
        workflow = chain(workflow, storage_task)

    # Execute workflow
    workflow.apply_async()

    return TaskAccepted(
        task_id=workflow_id,
        count=len(archivers),
        message="Archive workflow started",
    )


@router.post("/archive/{archiver}", response_model=TaskAccepted)
async def archive_with_archiver(
    archiver: str,
    request: SaveRequest,
    db: Session = Depends(get_db),
):
    """
    Archive a URL with a specific archiver.

    This endpoint archives using only the specified archiver.
    """
    if archiver not in AVAILABLE_ARCHIVERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid archiver: {archiver}. Valid options: {AVAILABLE_ARCHIVERS}",
        )

    url = str(request.url)
    item_id = request.id

    logger.info(
        "Archive request with specific archiver",
        extra={"url": url, "item_id": item_id, "archiver": archiver},
    )

    # Get or create archived URL
    existing = db.query(ArchivedUrl).filter(ArchivedUrl.url == url).first()
    if existing:
        archived_url_id = existing.id
    else:
        archived_url = ArchivedUrl(url=url, item_id=item_id)
        db.add(archived_url)
        db.flush()
        archived_url_id = archived_url.id

    # Check for existing successful artifact
    existing_artifact = (
        db.query(ArchiveArtifact)
        .filter(
            ArchiveArtifact.archived_url_id == archived_url_id,
            ArchiveArtifact.archiver == archiver,
            ArchiveArtifact.success == True,
        )
        .first()
    )

    if existing_artifact:
        return TaskAccepted(
            task_id="existing",
            count=0,
            message=f"Archive already exists for archiver: {archiver}",
        )

    # Create artifact record
    task_id = uuid.uuid4().hex
    artifact = ArchiveArtifact(
        archived_url_id=archived_url_id,
        archiver=archiver,
        status="pending",
        task_id=task_id,
    )
    db.add(artifact)
    db.flush()

    fetch_url = rewrite_paywalled_url(url)

    db.commit()

    # Dispatch task
    task_name = f"services.archive_worker.tasks.archive_{archiver}"
    celery_app.send_task(
        task_name,
        kwargs={
            "item_id": item_id,
            "url": fetch_url,
            "archived_url_id": archived_url_id,
            "artifact_id": artifact.id,
        },
        queue=f"archive.{archiver}",
    )

    logger.info(
        "Archive task dispatched",
        extra={"task_id": task_id, "archiver": archiver, "item_id": item_id},
    )

    return TaskAccepted(
        task_id=task_id,
        count=1,
        message=f"Archive task dispatched for {archiver}",
    )


@router.post("/archive/{archiver}/batch", response_model=TaskAccepted)
async def archive_batch_with_archiver(
    archiver: str,
    request: BatchSaveRequest,
    db: Session = Depends(get_db),
):
    """
    Archive multiple URLs with a specific archiver.

    This endpoint archives all URLs using only the specified archiver.
    """
    if archiver not in AVAILABLE_ARCHIVERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid archiver: {archiver}. Valid options: {AVAILABLE_ARCHIVERS}",
        )

    batch_id = uuid.uuid4().hex
    tasks_created = 0

    logger.info(
        "Batch archive request with specific archiver",
        extra={
            "batch_id": batch_id,
            "archiver": archiver,
            "item_count": len(request.items),
        },
    )

    all_tasks = []

    for item in request.items:
        url = str(item.url)
        item_id = item.id

        # Get or create archived URL
        existing = db.query(ArchivedUrl).filter(ArchivedUrl.url == url).first()
        if existing:
            archived_url_id = existing.id
        else:
            archived_url = ArchivedUrl(url=url, item_id=item_id)
            db.add(archived_url)
            db.flush()
            archived_url_id = archived_url.id

        # Check for existing successful artifact
        existing_artifact = (
            db.query(ArchiveArtifact)
            .filter(
                ArchiveArtifact.archived_url_id == archived_url_id,
                ArchiveArtifact.archiver == archiver,
                ArchiveArtifact.success == True,
            )
            .first()
        )

        if existing_artifact:
            continue

        # Create artifact record
        artifact = ArchiveArtifact(
            archived_url_id=archived_url_id,
            archiver=archiver,
            status="pending",
            task_id=batch_id,
        )
        db.add(artifact)
        db.flush()

        fetch_url = rewrite_paywalled_url(url)

        task_name = f"services.archive_worker.tasks.archive_{archiver}"
        all_tasks.append(
            celery_app.signature(
                task_name,
                kwargs={
                    "item_id": item_id,
                    "url": fetch_url,
                    "archived_url_id": archived_url_id,
                    "artifact_id": artifact.id,
                },
                queue=f"archive.{archiver}",
            )
        )
        tasks_created += 1

    db.commit()

    if all_tasks:
        task_group = group(all_tasks)
        task_group.apply_async()

    logger.info(
        "Batch archive tasks dispatched",
        extra={"batch_id": batch_id, "archiver": archiver, "task_count": tasks_created},
    )

    return TaskAccepted(
        task_id=batch_id,
        count=tasks_created,
        message=f"Batch archive tasks dispatched for {archiver} ({tasks_created} tasks)",
    )


@router.get("/archive/{item_id}/size")
async def get_archive_size(
    item_id: str,
    archiver: str = Query("all", description="Archiver name"),
    db: Session = Depends(get_db),
):
    """
    Get the size of archived artifacts for an item.

    Returns size information for all or specific archivers.
    """
    archived_url = (
        db.query(ArchivedUrl).filter(ArchivedUrl.item_id == item_id).first()
    )

    if not archived_url:
        raise HTTPException(status_code=404, detail="Archive not found")

    query = db.query(ArchiveArtifact).filter(
        ArchiveArtifact.archived_url_id == archived_url.id,
        ArchiveArtifact.success == True,
    )

    if archiver != "all":
        query = query.filter(ArchiveArtifact.archiver == archiver)

    artifacts = query.all()

    if not artifacts:
        raise HTTPException(status_code=404, detail="No successful archives found")

    total_size = sum(a.size_bytes or 0 for a in artifacts)

    return {
        "item_id": item_id,
        "total_size_bytes": total_size,
        "archivers": {
            a.archiver: {
                "size_bytes": a.size_bytes,
                "saved_path": a.saved_path,
            }
            for a in artifacts
        },
    }


@router.get("/retrieve")
async def retrieve_archive(
    id: Optional[str] = Query(None, description="Item ID"),
    url: Optional[str] = Query(None, description="URL"),
    archiver: str = Query("all", description="Archiver name"),
    db: Session = Depends(get_db),
):
    """
    Retrieve archived content.

    Returns download URLs for archived artifacts.
    """
    if not id and not url:
        raise HTTPException(status_code=400, detail="id or url required")

    # Find archived URL
    query = db.query(ArchivedUrl)
    if id:
        query = query.filter(ArchivedUrl.item_id == id)
    if url:
        query = query.filter(ArchivedUrl.url == url)

    archived_url = query.first()
    if not archived_url:
        raise HTTPException(status_code=404, detail="Archive not found")

    # Get artifacts
    artifact_query = db.query(ArchiveArtifact).filter(
        ArchiveArtifact.archived_url_id == archived_url.id,
        ArchiveArtifact.success == True,
    )

    if archiver != "all":
        artifact_query = artifact_query.filter(ArchiveArtifact.archiver == archiver)

    artifacts = artifact_query.all()

    if not artifacts:
        raise HTTPException(status_code=404, detail="No successful archives found")

    return {
        "id": archived_url.item_id,
        "url": archived_url.url,
        "archives": [
            {
                "archiver": a.archiver,
                "saved_path": a.saved_path,
                "gcs_path": a.gcs_path,
                "size_bytes": a.size_bytes,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in artifacts
        ],
    }
