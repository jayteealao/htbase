"""
Firebase API Module

Provides endpoints for Firebase/Firestore integration and Pocket article management.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/firebase", tags=["firebase"])


# Request/Response Models

class AddPocketArticleRequest(BaseModel):
    """Request model for adding a Pocket article."""
    user_id: str = Field(..., description="User identifier")
    url: str = Field(..., description="Article URL to archive")
    pocket_data: dict = Field(default_factory=dict, description="Pocket metadata (title, excerpt, tags, etc.)")
    archiver: str = Field(default="all", description="Archiver to use (monolith, singlefile, all, etc.)")


class AddPocketArticleResponse(BaseModel):
    """Response model for adding a Pocket article."""
    article_id: str = Field(..., description="Created article identifier")
    status: str = Field(..., description="Status (queued, processing, completed)")
    message: str = Field(..., description="Human-readable message")


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
    archiver: str = Field(default="all", description="Archiver to use (monolith, all, etc.)")


class ArchiveArticleResponse(BaseModel):
    """Response model for archive trigger."""
    item_id: str = Field(..., description="Article identifier")
    status: str = Field(..., description="Queued, processing, completed, or failed")
    message: str = Field(..., description="Status message")
    task_id: Optional[str] = Field(None, description="Background task ID if queued")


# Endpoints

@router.post("/add-pocket-article", response_model=AddPocketArticleResponse)
async def add_pocket_article(
    request: Request,
    data: AddPocketArticleRequest
) -> AddPocketArticleResponse:
    """
    Add a Pocket article to the archive system.

    This endpoint:
    1. Creates a Firestore document with Pocket metadata
    2. Stores article info in PostgreSQL
    3. Triggers archival via ArchiverTaskManager
    4. Returns article ID and status

    Args:
        request: FastAPI request object (provides app state)
        data: Pocket article data

    Returns:
        AddPocketArticleResponse with article_id, status, and message

    Raises:
        HTTPException: If Firestore backend not available or archival fails
    """
    from core.config import get_settings

    settings = get_settings()

    # Check if Firestore backend is available
    if not hasattr(request.app.state, 'db_storage'):
        raise HTTPException(
            status_code=503,
            detail="Database storage provider not initialized"
        )

    db_storage = request.app.state.db_storage
    if db_storage.provider_name != "firestore":
        logger.warning(f"add-pocket-article called with {db_storage.provider_name} backend, expected firestore")

    # Generate item_id from URL (sanitize for use as key)
    from core.utils import sanitize_filename
    import hashlib

    url_hash = hashlib.sha256(data.url.encode()).hexdigest()[:12]
    item_id = f"pocket_{url_hash}"

    try:
        # Create article in database storage with Pocket metadata
        article_data = {
            'url': data.url,
            'user_id': data.user_id,
            'pocket_data': data.pocket_data,
            'status': 'queued',
            'archiver': data.archiver
        }

        from storage.database_storage import ArticleMetadata

        metadata = ArticleMetadata(
            item_id=item_id,
            url=data.url
        )
        db_storage.create_article(metadata)

        # TODO: Store pocket_data separately if needed
        # (not part of ArticleMetadata schema currently)

        logger.info(
            f"Created Pocket article in {db_storage.provider_name}",
            extra={"item_id": item_id, "user_id": data.user_id, "url": data.url}
        )

        # Trigger archival if task manager available
        if hasattr(request.app.state, 'archiver_task_manager') and request.app.state.archiver_task_manager:
            # Queue archival task
            from task_manager.archiver import BatchItem, BatchTask
            import uuid

            # Create batch items (need rowid from database)
            # For now, use a placeholder rowid (task manager will handle it)
            batch_items = [BatchItem(
                item_id=item_id,
                url=data.url,
                rowid=0,  # Placeholder
                archiver_name=data.archiver
            )]

            # Create and submit batch task
            task = BatchTask(
                task_id=str(uuid.uuid4()),
                archiver_name=data.archiver,
                items=batch_items
            )

            request.app.state.archiver_task_manager.submit(task)

            logger.info(
                f"Queuing archival for Pocket article",
                extra={"item_id": item_id, "archiver": data.archiver}
            )

            return AddPocketArticleResponse(
                article_id=item_id,
                status="queued",
                message=f"Article queued for archival with archiver: {data.archiver}"
            )
        else:
            logger.warning("Task manager not available, article saved but not queued for archival")
            return AddPocketArticleResponse(
                article_id=item_id,
                status="saved",
                message="Article saved to database but archival not queued (task manager unavailable)"
            )

    except Exception as e:
        logger.error(f"Failed to add Pocket article: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add Pocket article: {str(e)}"
        )


@router.get("/download/{item_id}/{archiver}", response_model=DownloadURLResponse)
async def generate_download_url(
    request: Request,
    item_id: str,
    archiver: str,
    expiration_hours: int = 24
) -> DownloadURLResponse:
    """
    Generate a signed download URL for an archived article.

    This endpoint:
    1. Fetches article from database storage
    2. Gets GCS path for specified archiver
    3. Generates signed URL with expiration
    4. Returns download URL and metadata

    Args:
        request: FastAPI request object
        item_id: Article identifier
        archiver: Archiver type (monolith, singlefile, pdf, etc.)
        expiration_hours: URL expiration in hours (default: 24)

    Returns:
        DownloadURLResponse with signed download URL

    Raises:
        HTTPException: If article not found or archiver not available
    """
    from datetime import timedelta

    # Check if storage providers available
    if not hasattr(request.app.state, 'file_storage_providers') or not request.app.state.file_storage_providers:
        raise HTTPException(
            status_code=503,
            detail="File storage providers not initialized"
        )

    file_storage_providers = request.app.state.file_storage_providers

    try:
        # Get article from database
        db_storage = request.app.state.db_storage
        article = db_storage.get_article(item_id)

        if not article:
            raise HTTPException(
                status_code=404,
                detail=f"Article not found: {item_id}"
            )

        # Get artifact for specified archiver
        artifact = db_storage.get_artifact(item_id, archiver)

        if not artifact:
            raise HTTPException(
                status_code=404,
                detail=f"Artifact not found for archiver: {archiver}"
            )

        # Get storage path from artifact
        storage_uploads = artifact.get('storage_uploads', [])
        gcs_path = None

        # Find GCS upload in storage_uploads list
        for upload in storage_uploads:
            if upload.get('success') and upload.get('storage_uri'):
                # Extract GCS path from storage URI
                uri = upload.get('storage_uri', '')
                if uri.startswith('gs://'):
                    gcs_path = uri.replace('gs://', '').split('/', 1)[1]  # Remove bucket, keep path
                    break

        if not gcs_path:
            # Fallback to old gcs_path field
            gcs_path = artifact.get('gcs_path')

        if not gcs_path:
            raise HTTPException(
                status_code=404,
                detail=f"No GCS path found for archiver: {archiver}"
            )

        # Generate signed URL from any GCS provider
        signed_url = None
        for provider in file_storage_providers:
            if provider.supports_signed_urls:
                try:
                    signed_url = provider.generate_access_url(
                        storage_path=gcs_path,
                        expiration=timedelta(hours=expiration_hours)
                    )
                    break
                except Exception as e:
                    logger.warning(f"Failed to generate signed URL from {provider.provider_name}: {e}")
                    continue

        if not signed_url:
            raise HTTPException(
                status_code=503,
                detail="No storage provider supports signed URLs"
            )

        return DownloadURLResponse(
            download_url=signed_url,
            expires_in=expiration_hours * 3600,  # Convert to seconds
            archiver=archiver,
            gcs_path=gcs_path
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate download URL: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate download URL: {str(e)}"
        )


@router.post("/save", response_model=AddPocketArticleResponse)
async def save_article(
    request: Request,
    data: SaveArticleRequest
) -> AddPocketArticleResponse:
    """
    Save a basic article (non-Pocket).

    Similar to add-pocket-article but with minimal metadata.

    Args:
        request: FastAPI request object
        data: Article save data

    Returns:
        AddPocketArticleResponse with article_id and status
    """
    from core.utils import sanitize_filename
    import hashlib

    # Generate item_id from URL
    url_hash = hashlib.sha256(data.url.encode()).hexdigest()[:12]
    item_id = f"article_{url_hash}"

    try:
        # Check if database storage available
        if hasattr(request.app.state, 'db_storage'):
            db_storage = request.app.state.db_storage

            # Create article
            from storage.database_storage import ArticleMetadata

            article_metadata = ArticleMetadata(
                item_id=item_id,
                url=data.url,
                **data.metadata  # Unpack any additional metadata fields
            )
            db_storage.create_article(article_metadata)

            logger.info(f"Created article in {db_storage.provider_name}", extra={"item_id": item_id})

        # Queue archival if task manager available
        if hasattr(request.app.state, 'task_manager'):
            logger.info(f"Queuing archival", extra={"item_id": item_id, "archiver": data.archiver})

            return AddPocketArticleResponse(
                article_id=item_id,
                status="queued",
                message=f"Article queued for archival with archiver: {data.archiver}"
            )
        else:
            return AddPocketArticleResponse(
                article_id=item_id,
                status="saved",
                message="Article saved but not queued (task manager unavailable)"
            )

    except Exception as e:
        logger.error(f"Failed to save article: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save article: {str(e)}"
        )


@router.post("/archive", response_model=ArchiveArticleResponse)
async def archive_article(
    request: Request,
    data: ArchiveArticleRequest
) -> ArchiveArticleResponse:
    """
    Archive an article triggered by Cloud Function.

    This endpoint is called by the Firebase Cloud Function when a user saves
    an article and it doesn't exist in the shared collection yet.

    Flow:
    1. Create article record in database storage (Firestore/PostgreSQL)
    2. Queue archival task via ArchiverTaskManager
    3. Return immediately (processing happens async)
    4. Task manager updates Firestore when archival completes

    Args:
        request: FastAPI request object (provides app state)
        data: Archive request with item_id, url, archiver

    Returns:
        ArchiveArticleResponse with queued status

    Raises:
        HTTPException: If database or task manager unavailable
    """
    from core.config import get_settings

    settings = get_settings()

    # Check if database storage available
    if not hasattr(request.app.state, 'db_storage'):
        raise HTTPException(
            status_code=503,
            detail="Database storage provider not initialized"
        )

    db_storage = request.app.state.db_storage

    try:
        # Article should already exist in Firestore (created by Cloud Function trigger)
        # This just verifies it exists and updates metadata if needed
        article = db_storage.get_article(data.item_id)
        if not article:
            # Article not found - create it (fallback)
            from storage.database_storage import ArticleMetadata

            metadata = ArticleMetadata(
                item_id=data.item_id,
                url=data.url
            )
            db_storage.create_article(metadata)

        logger.info(
            f"Processing archive request in {db_storage.provider_name}",
            extra={"item_id": data.item_id, "url": data.url}
        )

        # Queue archival task if task manager available
        if hasattr(request.app.state, 'archiver_task_manager') and request.app.state.archiver_task_manager:
            from task_manager.archiver import BatchItem, BatchTask
            import uuid

            # Handle "all" archiver - queue each archiver separately
            if data.archiver == "all":
                archiver_names = list(request.app.state.archivers.keys())
            else:
                archiver_names = [data.archiver]

            # Create and submit a task for each archiver
            for archiver_name in archiver_names:
                batch_items = [BatchItem(
                    item_id=data.item_id,
                    url=data.url,
                    rowid=0,  # Placeholder
                    archiver_name=archiver_name
                )]

                task = BatchTask(
                    task_id=str(uuid.uuid4()),
                    archiver_name=archiver_name,
                    items=batch_items
                )

                request.app.state.archiver_task_manager.submit(task)

            logger.info(
                f"Queuing archival task(s)",
                extra={"item_id": data.item_id, "archiver": data.archiver, "tasks_queued": len(archiver_names)}
            )

            return ArchiveArticleResponse(
                item_id=data.item_id,
                status="queued",
                message=f"Article queued for archival with archiver: {data.archiver}",
                task_id=None  # Task manager doesn't return IDs currently
            )
        else:
            logger.warning("Task manager not available, article saved but not queued")
            return ArchiveArticleResponse(
                item_id=data.item_id,
                status="saved",
                message="Article saved to database but archival not queued (task manager unavailable)",
                task_id=None
            )

    except Exception as e:
        logger.error(f"Failed to archive article: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to archive article: {str(e)}"
        )
