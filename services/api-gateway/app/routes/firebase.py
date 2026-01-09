"""
Firebase API routes.

Provides endpoints for Firebase/Firestore integration and Pocket article management.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shared.auth import verify_api_key
from shared.rate_limit import rate_limit_archive, rate_limit_download
from shared.db import get_session, ArchivedUrl, ArchiveArtifact, UrlMetadata
from shared.celery_config import celery_app

logger = logging.getLogger(__name__)

router = APIRouter()


def get_db():
    """Database session dependency."""
    with get_session() as session:
        yield session


# Request/Response Models


class DownloadURLResponse(BaseModel):
    """Response model for download URL generation."""

    download_url: str = Field(..., description="Signed download URL")
    expires_in: int = Field(..., description="URL expiration in seconds")
    archiver: str = Field(..., description="Archiver type")
    gcs_path: Optional[str] = Field(None, description="GCS storage path")


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


class AddArticleRequest(BaseModel):
    """
    Consolidated request model for adding articles.

    Replaces add-pocket-article and save endpoints.
    Supports custom item_id, Pocket metadata, generic metadata, and Firestore sync.
    """

    # Core fields
    url: str = Field(..., description="Article URL to archive")
    archiver: str = Field(default="all", description="Archiver to use (all, monolith, readability, etc.)")

    # NEW: Custom item_id support
    item_id: Optional[str] = Field(None, description="Custom article identifier (alphanumeric, underscore, hyphen only)")

    # From add-pocket-article
    user_id: Optional[str] = Field(None, description="User identifier (for Pocket integration)")
    pocket_data: Optional[dict] = Field(None, description="Pocket metadata (title, excerpt, tags, word_count, etc.)")

    # From save (generic metadata)
    metadata: Optional[dict] = Field(None, description="Generic metadata (title, author, excerpt)")

    # Control Firestore sync
    enable_firestore_sync: bool = Field(True, description="Enable Firestore write (default: true)")


class AddArticleResponse(BaseModel):
    """Response model for consolidated add-article endpoint."""

    item_id: str = Field(..., description="Article identifier (user-provided or auto-generated)")
    status: str = Field(..., description="Status (queued, exists, processing, completed)")
    message: str = Field(..., description="Human-readable status message")
    task_id: Optional[str] = Field(None, description="Background task ID if queued")


# Available archivers
AVAILABLE_ARCHIVERS = ["singlefile", "monolith", "readability", "pdf", "screenshot"]


def _generate_item_id(url: str, prefix: str = "pocket") -> str:
    """Generate item_id from URL hash."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    return f"{prefix}_{url_hash}"


def validate_item_id(item_id: str) -> bool:
    """
    Validate item_id format: alphanumeric + underscore/hyphen only, max 255 chars.

    Returns True if valid, False otherwise.
    """
    if not item_id or len(item_id) > 255:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', item_id))


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


@router.get("/download/{item_id}/{archiver}", response_model=DownloadURLResponse, dependencies=[Depends(rate_limit_download)])
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


@router.post("/archive", response_model=ArchiveArticleResponse, dependencies=[Depends(rate_limit_archive)])
async def archive_article(
    data: ArchiveArticleRequest,
    db: Session = Depends(get_db),
) -> ArchiveArticleResponse:
    """
    Archive an article triggered by Cloud Function.

    This endpoint is called by the Firebase Cloud Function when a user saves
    an article and it doesn't exist in the shared collection yet.

    Supports custom item_id (user-provided or auto-generated).

    Flow:
    1. Validate item_id format (if provided)
    2. Create article record in database (if not exists)
    3. Queue archival task via Celery
    4. Return immediately (processing happens async)
    """
    from shared.config import get_settings

    settings = get_settings()

    try:
        # Validate item_id format
        if data.item_id and not validate_item_id(data.item_id):
            raise HTTPException(
                status_code=400,
                detail="Invalid item_id format. Use alphanumeric, underscore, and hyphen only (max 255 chars)"
            )

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


@router.post("/add-article", response_model=AddArticleResponse, dependencies=[Depends(rate_limit_archive)])
async def add_article(
    data: AddArticleRequest,
    db: Session = Depends(get_db),
) -> AddArticleResponse:
    """
    Add article for archiving with optional custom item_id.

    This consolidated endpoint replaces /add-pocket-article and /save.
    Supports all features from both endpoints:
    - Custom item_id (optional)
    - Pocket metadata (title, excerpt, author, word_count, tags, etc.)
    - Generic metadata (title, author, excerpt)
    - User tracking (user_id for Pocket integration)
    - Firestore sync (enabled by default, can be disabled)

    Flow:
    1. Validate and determine item_id (user-provided or auto-generated)
    2. Check for existing article by URL (URL is unique constraint)
    3. Create article record with metadata
    4. Write to Firestore if enabled
    5. Queue archival tasks
    """
    from shared.config import get_settings

    settings = get_settings()

    try:
        # 1. Validate and determine item_id
        if data.item_id:
            # User provided custom item_id - validate it
            if not validate_item_id(data.item_id):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid item_id format. Use alphanumeric, underscore, and hyphen only (max 255 chars)"
                )
            item_id = data.item_id
        else:
            # Auto-generate with prefix based on metadata source
            prefix = "pocket" if data.pocket_data else "article"
            item_id = _generate_item_id(data.url, prefix)

        # 2. Check existing by URL (URL is unique constraint)
        existing = db.query(ArchivedUrl).filter(ArchivedUrl.url == data.url).first()

        if existing:
            # Conflict resolution: use existing item_id
            if data.item_id and data.item_id != existing.item_id:
                logger.warning(
                    f"item_id mismatch for url={data.url}: "
                    f"requested={data.item_id}, existing={existing.item_id}. "
                    f"Using existing item_id."
                )
            return AddArticleResponse(
                item_id=existing.item_id,
                status="exists",
                message=f"Article already archived with item_id={existing.item_id}",
                task_id=None,
            )

        # 3. Create article with item_id
        title = None
        if data.pocket_data:
            title = data.pocket_data.get("title")
        elif data.metadata:
            title = data.metadata.get("title")

        archived_url = ArchivedUrl(
            item_id=item_id,
            url=data.url,
            name=title or "",
        )
        db.add(archived_url)
        db.flush()  # Get ID for metadata

        # 4. Add metadata if provided (Pocket or generic)
        if data.pocket_data:
            metadata = UrlMetadata(
                archived_url_id=archived_url.id,
                title=data.pocket_data.get("title"),
                byline=data.pocket_data.get("author"),
                description=data.pocket_data.get("excerpt"),
                word_count=data.pocket_data.get("word_count"),
            )
            db.add(metadata)
        elif data.metadata:
            metadata = UrlMetadata(
                archived_url_id=archived_url.id,
                title=data.metadata.get("title"),
                byline=data.metadata.get("author"),
                description=data.metadata.get("excerpt"),
            )
            db.add(metadata)

        # 5. Firestore sync (if enabled)
        if data.enable_firestore_sync and settings.firestore.project_id:
            try:
                from shared.storage.firestore_storage import FirestoreStorage
                from shared.storage.database_storage import ArticleMetadata

                firestore_storage = FirestoreStorage(project_id=settings.firestore.project_id)

                # Build article metadata for Firestore
                article_metadata = ArticleMetadata(
                    item_id=item_id,
                    url=data.url,
                    title=title,
                    byline=data.pocket_data.get("author") if data.pocket_data else data.metadata.get("author") if data.metadata else None,
                    excerpt=data.pocket_data.get("excerpt") if data.pocket_data else data.metadata.get("excerpt") if data.metadata else None,
                    word_count=data.pocket_data.get("word_count") if data.pocket_data else None,
                )

                firestore_storage.create_article(article_metadata)
                logger.info("Created article in Firestore", extra={"item_id": item_id})
            except Exception as e:
                logger.warning(f"Firestore sync failed for {item_id}: {e}")
                # Continue - Firestore is best-effort

        # 6. Queue archive tasks
        if data.archiver == "all":
            archivers = AVAILABLE_ARCHIVERS
        else:
            archivers = [data.archiver]

        task_id, artifact_ids = _dispatch_archive_tasks(
            item_id=item_id,
            url=data.url,
            archived_url_id=archived_url.id,
            archivers=archivers,
            db=db,
        )

        logger.info(
            "Article queued for archival",
            extra={
                "item_id": item_id,
                "user_id": data.user_id,
                "archivers": archivers,
                "task_id": task_id,
                "custom_item_id": bool(data.item_id),
            },
        )

        return AddArticleResponse(
            item_id=item_id,
            status="queued",
            message=f"Article queued for archiving with {len(archivers)} archiver(s)",
            task_id=task_id,
        )

    except HTTPException:
        # Re-raise HTTP exceptions (validation errors, etc.)
        raise
    except Exception as e:
        logger.error(f"Failed to add article: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to add article: {str(e)}"
        )
