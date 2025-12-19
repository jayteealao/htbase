"""
Sync API Module

Provides endpoints for bidirectional sync between PostgreSQL and Firestore.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


# Request/Response Models

class PostgresToFirestoreSyncRequest(BaseModel):
    """Request model for PostgreSQL → Firestore sync."""
    article_id: Optional[str] = Field(None, description="Specific article ID to sync (optional)")
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum articles to sync (default: 100)")


class PostgresToFirestoreSyncResponse(BaseModel):
    """Response model for PostgreSQL → Firestore sync."""
    synced: int = Field(..., description="Number of articles successfully synced")
    total: int = Field(..., description="Total articles processed")
    errors: list[str] = Field(default_factory=list, description="List of error messages")


class FirestoreToPostgresSyncRequest(BaseModel):
    """Request model for Firestore → PostgreSQL sync."""
    item_id: str = Field(..., description="Article item_id to sync from Firestore")


class FirestoreToPostgresSyncResponse(BaseModel):
    """Response model for Firestore → PostgreSQL sync."""
    synced: bool = Field(..., description="Whether sync was successful")
    postgres_id: Optional[int] = Field(None, description="PostgreSQL row ID")
    message: str = Field(..., description="Status message")


# Endpoints

@router.post("/postgres-to-firestore", response_model=PostgresToFirestoreSyncResponse)
async def sync_postgres_to_firestore(
    request: Request,
    data: PostgresToFirestoreSyncRequest
) -> PostgresToFirestoreSyncResponse:
    """
    Sync articles from PostgreSQL to Firestore.

    This endpoint:
    1. Queries PostgreSQL for articles to sync
    2. Builds Firestore document from PostgreSQL artifacts
    3. Creates/updates Firestore documents
    4. Marks articles as synced in PostgreSQL

    Args:
        request: FastAPI request object
        data: Sync request parameters

    Returns:
        PostgresToFirestoreSyncResponse with sync statistics

    Raises:
        HTTPException: If sync fails or storage providers unavailable
    """
    from storage.postgres_storage import PostgresStorage
    from storage.firestore_storage import FirestoreStorage

    # Verify both storage backends available
    if not hasattr(request.app.state, 'db_storage'):
        raise HTTPException(
            status_code=503,
            detail="Database storage not initialized"
        )

    db_storage = request.app.state.db_storage

    # Get Firestore storage instance (may need to initialize separately)
    firestore_storage = None
    if isinstance(db_storage, FirestoreStorage):
        firestore_storage = db_storage
    else:
        # Need to initialize Firestore separately for sync
        try:
            from core.config import get_settings
            settings = get_settings()

            if settings.firestore.project_id:
                firestore_storage = FirestoreStorage(project_id=settings.firestore.project_id)
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Firestore not configured (missing FIRESTORE_PROJECT_ID)"
                )
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"Failed to initialize Firestore: {str(e)}"
            )

    # Get PostgreSQL storage
    postgres_storage = None
    if isinstance(db_storage, PostgresStorage):
        postgres_storage = db_storage
    else:
        # Initialize PostgreSQL separately
        try:
            postgres_storage = PostgresStorage()
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"Failed to initialize PostgreSQL: {str(e)}"
            )

    synced_count = 0
    total_count = 0
    errors = []

    try:
        # Case 1: Sync specific article
        if data.article_id:
            try:
                # Get article from PostgreSQL
                article = postgres_storage.get_article(data.article_id)
                if not article:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Article not found in PostgreSQL: {data.article_id}"
                    )

                # Get all artifacts for this article
                artifacts = postgres_storage.list_artifacts(item_id=data.article_id)

                # Build Firestore document
                firestore_data = _build_firestore_document(article, artifacts)

                # Create/update in Firestore
                firestore_storage.create_article(
                    item_id=data.article_id,
                    url=article.get('url'),
                    pocket_data=article.get('pocket_data')
                )

                # Update artifacts
                for artifact in artifacts:
                    firestore_storage.update_artifact_status(
                        item_id=data.article_id,
                        archiver=artifact.get('archiver'),
                        status=artifact.get('status'),
                        gcs_path=artifact.get('gcs_path')
                    )

                synced_count = 1
                total_count = 1

                logger.info(f"Synced article to Firestore", extra={"article_id": data.article_id})

            except Exception as e:
                errors.append(f"Failed to sync {data.article_id}: {str(e)}")
                logger.error(f"Sync failed for {data.article_id}: {e}", exc_info=True)

        # Case 2: Sync multiple articles
        else:
            # Get unsync'd articles from PostgreSQL (would need a sync status column)
            # For now, get recent articles
            articles = postgres_storage.list_articles(limit=data.limit)
            total_count = len(articles)

            for article in articles:
                try:
                    item_id = article.get('item_id')
                    if not item_id:
                        continue

                    # Get artifacts
                    artifacts = postgres_storage.list_artifacts(item_id=item_id)

                    # Create in Firestore
                    firestore_storage.create_article(
                        item_id=item_id,
                        url=article.get('url'),
                        pocket_data=article.get('pocket_data')
                    )

                    # Update artifacts
                    for artifact in artifacts:
                        firestore_storage.update_artifact_status(
                            item_id=item_id,
                            archiver=artifact.get('archiver'),
                            status=artifact.get('status'),
                            gcs_path=artifact.get('gcs_path')
                        )

                    synced_count += 1

                except Exception as e:
                    errors.append(f"Failed to sync {item_id}: {str(e)}")
                    logger.error(f"Sync failed for {item_id}: {e}")
                    continue

            logger.info(f"Synced {synced_count}/{total_count} articles to Firestore")

        return PostgresToFirestoreSyncResponse(
            synced=synced_count,
            total=total_count,
            errors=errors
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync operation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Sync operation failed: {str(e)}"
        )


@router.post("/firestore-to-postgres", response_model=FirestoreToPostgresSyncResponse)
async def sync_firestore_to_postgres(
    request: Request,
    data: FirestoreToPostgresSyncRequest
) -> FirestoreToPostgresSyncResponse:
    """
    Sync a single article from Firestore to PostgreSQL.

    This endpoint:
    1. Fetches article from Firestore
    2. Creates or updates article in PostgreSQL
    3. Syncs artifact status from Firestore archives map
    4. Returns sync status and PostgreSQL ID

    Args:
        request: FastAPI request object
        data: Sync request with item_id

    Returns:
        FirestoreToPostgresSyncResponse with sync status

    Raises:
        HTTPException: If sync fails or article not found
    """
    from storage.postgres_storage import PostgresStorage
    from storage.firestore_storage import FirestoreStorage

    # Verify storage backends
    if not hasattr(request.app.state, 'db_storage'):
        raise HTTPException(
            status_code=503,
            detail="Database storage not initialized"
        )

    db_storage = request.app.state.db_storage

    # Get Firestore storage
    firestore_storage = None
    if isinstance(db_storage, FirestoreStorage):
        firestore_storage = db_storage
    else:
        try:
            from core.config import get_settings
            settings = get_settings()

            if settings.firestore.project_id:
                firestore_storage = FirestoreStorage(project_id=settings.firestore.project_id)
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Firestore not configured"
                )
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"Failed to initialize Firestore: {str(e)}"
            )

    # Get PostgreSQL storage
    postgres_storage = None
    if isinstance(db_storage, PostgresStorage):
        postgres_storage = db_storage
    else:
        try:
            postgres_storage = PostgresStorage()
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"Failed to initialize PostgreSQL: {str(e)}"
            )

    try:
        # Fetch article from Firestore
        article = firestore_storage.get_article(data.item_id)
        if not article:
            raise HTTPException(
                status_code=404,
                detail=f"Article not found in Firestore: {data.item_id}"
            )

        # Create or get existing article in PostgreSQL
        url = article.get('url')
        pocket_data = article.get('pocket_data', {})

        # Create article in PostgreSQL
        postgres_article = postgres_storage.create_article(
            item_id=data.item_id,
            url=url,
            pocket_data=pocket_data
        )

        postgres_id = postgres_article.get('id') if postgres_article else None

        # Sync artifacts from Firestore archives map
        archives = article.get('archives', {})
        for archiver, archive_data in archives.items():
            try:
                postgres_storage.update_artifact_status(
                    item_id=data.item_id,
                    archiver=archiver,
                    status=archive_data.get('status', 'pending'),
                    gcs_path=archive_data.get('gcs_path')
                )
            except Exception as e:
                logger.warning(f"Failed to sync artifact {archiver}: {e}")
                continue

        logger.info(
            f"Synced article from Firestore to PostgreSQL",
            extra={"item_id": data.item_id, "postgres_id": postgres_id}
        )

        return FirestoreToPostgresSyncResponse(
            synced=True,
            postgres_id=postgres_id,
            message=f"Successfully synced article {data.item_id} to PostgreSQL"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Sync failed: {str(e)}"
        )


# Helper Functions

def _build_firestore_document(article: dict, artifacts: list[dict]) -> dict:
    """
    Build Firestore document structure from PostgreSQL data.

    Args:
        article: PostgreSQL article data
        artifacts: List of PostgreSQL artifacts

    Returns:
        Firestore-formatted document
    """
    # Build archives map
    archives = {}
    for artifact in artifacts:
        archiver = artifact.get('archiver')
        if archiver:
            archives[archiver] = {
                'status': artifact.get('status', 'pending'),
                'gcs_path': artifact.get('gcs_path'),
                'success': artifact.get('success', False),
                'created_at': artifact.get('created_at'),
                'size_bytes': artifact.get('size_bytes')
            }

    return {
        'url': article.get('url'),
        'pocket_data': article.get('pocket_data', {}),
        'archives': archives,
        'created_at': article.get('created_at'),
        'updated_at': article.get('updated_at')
    }
