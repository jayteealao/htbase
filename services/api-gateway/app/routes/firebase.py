"""
Firebase API routes.

Provides endpoints for Firebase/Firestore integration and Pocket article management.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shared.db import get_session, ArchivedUrl, ArchiveArtifact, UrlMetadata
from shared.celery_config import celery_app

logger = logging.getLogger(__name__)

router = APIRouter()


def get_db():
    """Database session dependency."""
    with get_session() as session:
        yield session


# Request/Response Models


class AddPocketArticleRequest(BaseModel):
    """Request model for adding a Pocket article."""

    user_id: str = Field(..., description="User identifier")
    url: str = Field(..., description="Article URL to archive")
    pocket_data: dict = Field(
        default_factory=dict, description="Pocket metadata (title, excerpt, tags, etc.)"
    )
    archiver: str = Field(
        default="all", description="Archiver to use (monolith, singlefile, all, etc.)"
    )


class AddPocketArticleResponse(BaseModel):
    """Response model for adding a Pocket article."""

    article_id: str = Field(..., description="Created article identifier")
    status: str = Field(..., description="Status (queued, processing, completed)")
    message: str = Field(..., description="Human-readable message")
    task_id: Optional[str] = Field(None, description="Background task ID if queued")


class DownloadURLResponse(BaseModel):
    """Response model for download URL generation."""

    download_url: str = Field(..., description="Signed download URL")
    expires_in: int = Field(..., description="URL expiration in seconds")
    archiver: str = Field(..., description="Archiver type")
    gcs_path: Optional[str] = Field(None, description="GCS storage path")


class SaveArticleRequest(BaseModel):
    """Request model for saving a basic article."""

    url: str = Field(..., description="Article URL to archive")
    archiver: str = Field(default="all", description="Archiver to use")
    metadata: dict = Field(default_factory=dict, description="Optional metadata")


class ArchiveArticleRequest(BaseModel):
    """Request model for archiving an article triggered by Cloud Function."""

    item_id: str = Field(..., description="Article item_id")
    url: str = Field(..., description="Article URL to archive")
    archiver: str = Field(
        default="all", description="Archiver to use (monolith, all, etc.)"
    )


class ArchiveArticleResponse(BaseModel):
    """Response model for archive trigger."""

    item_id: str = Field(..., description="Article identifier")
    status: str = Field(..., description="Queued, processing, completed, or failed")
    message: str = Field(..., description="Status message")
    task_id: Optional[str] = Field(None, description="Background task ID if queued")


# Available archivers
AVAILABLE_ARCHIVERS = ["singlefile", "monolith", "readability", "pdf", "screenshot"]


def _generate_item_id(url: str, prefix: str = "pocket") -> str:
    """Generate item_id from URL hash."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    return f"{prefix}_{url_hash}"


def _dispatch_archive_tasks(
    item_id: str,
    url: str,
    archived_url_id: int,
    archivers: list[str],
    db: Session,
) -> tuple[str, list[int]]:
    """
    Dispatch archive tasks to Celery workers.

    Returns task_id and list of artifact IDs.
    """
    from shared.utils import rewrite_paywalled_url, sanitize_filename

    task_id = uuid.uuid4().hex
    artifact_ids = []

    fetch_url = rewrite_paywalled_url(url)

    for archiver in archivers:
        # Create artifact record
        artifact = ArchiveArtifact(
            archived_url_id=archived_url_id,
            archiver=archiver,
            status="pending",
            task_id=task_id,
        )
        db.add(artifact)
        db.flush()
        artifact_ids.append(artifact.id)

        # Dispatch to worker
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

    db.commit()
    return task_id, artifact_ids


@router.post("/add-pocket-article", response_model=AddPocketArticleResponse)
async def add_pocket_article(
    data: AddPocketArticleRequest,
    db: Session = Depends(get_db),
) -> AddPocketArticleResponse:
    """
    Add a Pocket article to the archive system.

    This endpoint:
    1. Creates a database record with Pocket metadata
    2. Creates article in Firestore (if configured)
    3. Triggers archival via Celery workers
    4. Returns article ID and status
    """
    from shared.config import get_settings
    from shared.utils import sanitize_filename

    settings = get_settings()

    # Generate item_id from URL
    item_id = _generate_item_id(data.url, "pocket")

    try:
        # Check if article already exists
        existing = db.query(ArchivedUrl).filter(ArchivedUrl.item_id == item_id).first()

        if existing:
            # Article exists - check if we need to re-queue
            logger.info(
                "Article already exists",
                extra={"item_id": item_id, "archived_url_id": existing.id},
            )
            return AddPocketArticleResponse(
                article_id=item_id,
                status="exists",
                message="Article already exists in the system",
                task_id=None,
            )

        # Create new archived URL record
        archived_url = ArchivedUrl(
            item_id=item_id,
            url=data.url,
            name=data.pocket_data.get("title", ""),
        )
        db.add(archived_url)
        db.flush()

        # Create metadata record
        metadata = UrlMetadata(
            archived_url_id=archived_url.id,
            title=data.pocket_data.get("title"),
            byline=data.pocket_data.get("author"),
            description=data.pocket_data.get("excerpt"),  # Map excerpt to description column
            word_count=data.pocket_data.get("word_count"),
        )
        db.add(metadata)

        # Write to Firestore if configured
        if settings.firestore.project_id:
            try:
                from shared.storage.firestore_storage import FirestoreStorage
                from shared.storage.database_storage import ArticleMetadata

                firestore_storage = FirestoreStorage(project_id=settings.firestore.project_id)
                article_metadata = ArticleMetadata(
                    item_id=item_id,
                    url=data.url,
                    title=data.pocket_data.get("title"),
                    byline=data.pocket_data.get("author"),
                    excerpt=data.pocket_data.get("excerpt"),
                    word_count=data.pocket_data.get("word_count"),
                )
                firestore_storage.create_article(article_metadata)
                logger.info("Created article in Firestore", extra={"item_id": item_id})
            except Exception as e:
                logger.warning(f"Failed to create Firestore document: {e}")

        # Determine archivers to use
        if data.archiver == "all":
            archivers = AVAILABLE_ARCHIVERS
        else:
            archivers = [data.archiver]

        # Dispatch archive tasks
        task_id, artifact_ids = _dispatch_archive_tasks(
            item_id=item_id,
            url=data.url,
            archived_url_id=archived_url.id,
            archivers=archivers,
            db=db,
        )

        logger.info(
            "Pocket article queued for archival",
            extra={
                "item_id": item_id,
                "user_id": data.user_id,
                "archivers": archivers,
                "task_id": task_id,
            },
        )

        return AddPocketArticleResponse(
            article_id=item_id,
            status="queued",
            message=f"Article queued for archival with {len(archivers)} archiver(s)",
            task_id=task_id,
        )

    except Exception as e:
        logger.error(f"Failed to add Pocket article: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to add Pocket article: {str(e)}"
        )


@router.get("/download/{item_id}/{archiver}", response_model=DownloadURLResponse)
async def generate_download_url(
    item_id: str,
    archiver: str,
    expiration_hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> DownloadURLResponse:
    """
    Generate a signed download URL for an archived article.

    This endpoint:
    1. Fetches article from database
    2. Gets GCS path for specified archiver
    3. Generates signed URL with expiration
    4. Returns download URL and metadata
    """
    from shared.config import get_settings

    settings = get_settings()

    # Find archived URL
    archived_url = (
        db.query(ArchivedUrl).filter(ArchivedUrl.item_id == item_id).first()
    )

    if not archived_url:
        raise HTTPException(status_code=404, detail=f"Article not found: {item_id}")

    # Find artifact for specified archiver
    artifact = (
        db.query(ArchiveArtifact)
        .filter(
            ArchiveArtifact.archived_url_id == archived_url.id,
            ArchiveArtifact.archiver == archiver,
            ArchiveArtifact.success == True,
        )
        .first()
    )

    if not artifact:
        raise HTTPException(
            status_code=404,
            detail=f"No successful artifact found for archiver: {archiver}",
        )

    # Get GCS path from storage_uploads or gcs_path field
    gcs_path = None

    if artifact.storage_uploads:
        for upload in artifact.storage_uploads:
            if upload.get("success") and upload.get("storage_uri"):
                uri = upload.get("storage_uri", "")
                if uri.startswith("gs://"):
                    # Extract path from gs://bucket/path
                    parts = uri.replace("gs://", "").split("/", 1)
                    if len(parts) == 2:
                        gcs_path = parts[1]
                        break

    if not gcs_path and artifact.gcs_path:
        gcs_path = artifact.gcs_path

    if not gcs_path:
        raise HTTPException(
            status_code=404,
            detail=f"No cloud storage path found for archiver: {archiver}",
        )

    # Generate signed URL
    try:
        from shared.storage.gcs_file_storage import GCSFileStorage

        gcs = GCSFileStorage(
            bucket_name=settings.gcs.bucket,
            project_id=settings.gcs.project_id,
        )

        signed_url = gcs.generate_access_url(
            storage_path=gcs_path,
            expiration=timedelta(hours=expiration_hours),
        )

        return DownloadURLResponse(
            download_url=signed_url,
            expires_in=expiration_hours * 3600,
            archiver=archiver,
            gcs_path=gcs_path,
        )

    except Exception as e:
        logger.error(f"Failed to generate signed URL: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to generate download URL: {str(e)}"
        )


@router.post("/save", response_model=AddPocketArticleResponse)
async def save_article(
    data: SaveArticleRequest,
    db: Session = Depends(get_db),
) -> AddPocketArticleResponse:
    """
    Save a basic article (non-Pocket).

    Similar to add-pocket-article but with minimal metadata.
    """
    # Generate item_id from URL
    item_id = _generate_item_id(data.url, "article")

    try:
        # Check if article already exists
        existing = db.query(ArchivedUrl).filter(ArchivedUrl.item_id == item_id).first()

        if existing:
            return AddPocketArticleResponse(
                article_id=item_id,
                status="exists",
                message="Article already exists in the system",
                task_id=None,
            )

        # Create new archived URL record
        archived_url = ArchivedUrl(
            item_id=item_id,
            url=data.url,
            name=data.metadata.get("title", ""),
        )
        db.add(archived_url)
        db.flush()

        # Create metadata if provided
        if data.metadata:
            metadata = UrlMetadata(
                archived_url_id=archived_url.id,
                title=data.metadata.get("title"),
                byline=data.metadata.get("author"),
                description=data.metadata.get("excerpt"),  # Map excerpt to description column
            )
            db.add(metadata)

        # Determine archivers to use
        if data.archiver == "all":
            archivers = AVAILABLE_ARCHIVERS
        else:
            archivers = [data.archiver]

        # Dispatch archive tasks
        task_id, artifact_ids = _dispatch_archive_tasks(
            item_id=item_id,
            url=data.url,
            archived_url_id=archived_url.id,
            archivers=archivers,
            db=db,
        )

        logger.info(
            "Article queued for archival",
            extra={"item_id": item_id, "archivers": archivers, "task_id": task_id},
        )

        return AddPocketArticleResponse(
            article_id=item_id,
            status="queued",
            message=f"Article queued for archival with {len(archivers)} archiver(s)",
            task_id=task_id,
        )

    except Exception as e:
        logger.error(f"Failed to save article: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to save article: {str(e)}"
        )


@router.post("/archive", response_model=ArchiveArticleResponse)
async def archive_article(
    data: ArchiveArticleRequest,
    db: Session = Depends(get_db),
) -> ArchiveArticleResponse:
    """
    Archive an article triggered by Cloud Function.

    This endpoint is called by the Firebase Cloud Function when a user saves
    an article and it doesn't exist in the shared collection yet.

    Flow:
    1. Create article record in database (if not exists)
    2. Queue archival task via Celery
    3. Return immediately (processing happens async)
    """
    from shared.config import get_settings

    settings = get_settings()

    try:
        # Check if article exists
        archived_url = (
            db.query(ArchivedUrl).filter(ArchivedUrl.item_id == data.item_id).first()
        )

        if not archived_url:
            # Create new archived URL record
            archived_url = ArchivedUrl(
                item_id=data.item_id,
                url=data.url,
                name="",
            )
            db.add(archived_url)
            db.flush()

        # Determine archivers to use
        if data.archiver == "all":
            archivers = AVAILABLE_ARCHIVERS
        else:
            archivers = [data.archiver]

        # Check for existing pending/in_progress artifacts
        existing_artifacts = (
            db.query(ArchiveArtifact)
            .filter(
                ArchiveArtifact.archived_url_id == archived_url.id,
                ArchiveArtifact.status.in_(["pending", "in_progress"]),
            )
            .all()
        )

        existing_archivers = {a.archiver for a in existing_artifacts}
        archivers_to_queue = [a for a in archivers if a not in existing_archivers]

        if not archivers_to_queue:
            return ArchiveArticleResponse(
                item_id=data.item_id,
                status="already_queued",
                message="Archive tasks already pending for all requested archivers",
                task_id=None,
            )

        # Dispatch archive tasks
        task_id, artifact_ids = _dispatch_archive_tasks(
            item_id=data.item_id,
            url=data.url,
            archived_url_id=archived_url.id,
            archivers=archivers_to_queue,
            db=db,
        )

        # Update Firestore if configured
        if settings.firestore.project_id:
            try:
                from shared.storage.firestore_storage import FirestoreStorage
                from shared.storage.database_storage import ArchiveStatus

                firestore_storage = FirestoreStorage(project_id=settings.firestore.project_id)

                # Update archive status for each archiver
                for archiver in archivers_to_queue:
                    firestore_storage.update_artifact_status(
                        item_id=data.item_id,
                        archiver=archiver,
                        status=ArchiveStatus.PENDING,
                    )
            except Exception as e:
                logger.warning(f"Failed to update Firestore: {e}")

        logger.info(
            "Archive tasks queued",
            extra={
                "item_id": data.item_id,
                "archivers": archivers_to_queue,
                "task_id": task_id,
            },
        )

        return ArchiveArticleResponse(
            item_id=data.item_id,
            status="queued",
            message=f"Archive tasks queued for {len(archivers_to_queue)} archiver(s)",
            task_id=task_id,
        )

    except Exception as e:
        logger.error(f"Failed to archive article: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to archive article: {str(e)}"
        )
