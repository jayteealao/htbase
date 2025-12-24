"""
Sync API routes.

Provides endpoints for bidirectional sync between PostgreSQL and Firestore.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shared.db import (
    get_session,
    ArchivedUrl,
    ArchiveArtifact,
    UrlMetadata,
    ArticleSummary,
    ArticleEntity,
    ArticleTag,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def get_db():
    """Database session dependency."""
    with get_session() as session:
        yield session


# Request/Response Models


class PostgresToFirestoreSyncRequest(BaseModel):
    """Request model for PostgreSQL → Firestore sync."""

    article_id: Optional[str] = Field(
        None, description="Specific article ID to sync (optional)"
    )
    limit: int = Field(
        default=100, ge=1, le=1000, description="Maximum articles to sync"
    )
    force: bool = Field(
        default=False, description="Force sync even if already synced"
    )


class PostgresToFirestoreSyncResponse(BaseModel):
    """Response model for PostgreSQL → Firestore sync."""

    synced: int = Field(..., description="Number of articles successfully synced")
    total: int = Field(..., description="Total articles processed")
    skipped: int = Field(default=0, description="Number of articles skipped")
    errors: list[str] = Field(default_factory=list, description="List of error messages")


class FirestoreToPostgresSyncRequest(BaseModel):
    """Request model for Firestore → PostgreSQL sync."""

    item_id: str = Field(..., description="Article item_id to sync from Firestore")


class FirestoreToPostgresSyncResponse(BaseModel):
    """Response model for Firestore → PostgreSQL sync."""

    synced: bool = Field(..., description="Whether sync was successful")
    postgres_id: Optional[int] = Field(None, description="PostgreSQL row ID")
    message: str = Field(..., description="Status message")


def _build_firestore_document(
    archived_url: ArchivedUrl,
    metadata: Optional[UrlMetadata],
    artifacts: list[ArchiveArtifact],
    summary: Optional[ArticleSummary],
    entities: list[ArticleEntity],
    tags: list[ArticleTag],
) -> dict:
    """
    Build Firestore document structure from PostgreSQL data.
    """
    # Build archives map
    archives = {}
    for artifact in artifacts:
        archives[artifact.archiver] = {
            "status": artifact.status,
            "success": artifact.success or False,
            "gcs_path": artifact.gcs_path,
            "size_bytes": artifact.size_bytes,
            "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
        }

    # Build document
    doc = {
        "url": archived_url.url,
        "name": archived_url.name,
        "created_at": archived_url.created_at.isoformat() if archived_url.created_at else None,
        "archives": archives,
    }

    # Add metadata if available
    if metadata:
        doc["metadata"] = {
            "title": metadata.title,
            "byline": metadata.byline,
            "excerpt": metadata.excerpt,
            "text_content": metadata.text_content[:5000] if metadata.text_content else None,
            "word_count": metadata.word_count,
            "site_name": metadata.site_name,
            "lang": metadata.lang,
        }

    # Add summary if available
    if summary:
        doc["summary"] = {
            "lede": summary.lede,
            "text": summary.summary_text,
            "created_at": summary.created_at.isoformat() if summary.created_at else None,
        }

    # Add entities
    if entities:
        doc["entities"] = [
            {"type": e.entity_type, "value": e.value}
            for e in entities
        ]

    # Add tags
    if tags:
        doc["tags"] = [t.tag for t in tags]

    return doc


@router.post("/postgres-to-firestore", response_model=PostgresToFirestoreSyncResponse)
async def sync_postgres_to_firestore(
    data: PostgresToFirestoreSyncRequest,
    db: Session = Depends(get_db),
) -> PostgresToFirestoreSyncResponse:
    """
    Sync articles from PostgreSQL to Firestore.

    This endpoint:
    1. Queries PostgreSQL for articles to sync
    2. Builds Firestore document from PostgreSQL data
    3. Creates/updates Firestore documents
    4. Returns sync statistics
    """
    from shared.config import get_settings
    from shared.storage.firestore_storage import FirestoreStorage

    settings = get_settings()

    if not settings.firestore.project_id:
        raise HTTPException(
            status_code=400,
            detail="Firestore not configured (missing FIRESTORE_PROJECT_ID)",
        )

    try:
        firestore = FirestoreStorage(project_id=settings.firestore.project_id)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to initialize Firestore: {str(e)}",
        )

    synced_count = 0
    skipped_count = 0
    total_count = 0
    errors = []

    try:
        # Case 1: Sync specific article
        if data.article_id:
            archived_url = (
                db.query(ArchivedUrl)
                .filter(ArchivedUrl.item_id == data.article_id)
                .first()
            )

            if not archived_url:
                raise HTTPException(
                    status_code=404,
                    detail=f"Article not found: {data.article_id}",
                )

            total_count = 1

            try:
                # Fetch related data
                metadata = (
                    db.query(UrlMetadata)
                    .filter(UrlMetadata.archived_url_id == archived_url.id)
                    .first()
                )
                artifacts = (
                    db.query(ArchiveArtifact)
                    .filter(ArchiveArtifact.archived_url_id == archived_url.id)
                    .all()
                )
                summary = (
                    db.query(ArticleSummary)
                    .filter(ArticleSummary.archived_url_id == archived_url.id)
                    .first()
                )
                entities = (
                    db.query(ArticleEntity)
                    .filter(ArticleEntity.archived_url_id == archived_url.id)
                    .all()
                )
                tags = (
                    db.query(ArticleTag)
                    .filter(ArticleTag.archived_url_id == archived_url.id)
                    .all()
                )

                # Build and sync document
                doc = _build_firestore_document(
                    archived_url, metadata, artifacts, summary, entities, tags
                )

                firestore.create_article(
                    item_id=data.article_id,
                    url=archived_url.url,
                    pocket_data=doc.get("metadata", {}),
                )

                # Sync artifacts
                for artifact in artifacts:
                    firestore.update_archive_status(
                        item_id=data.article_id,
                        archiver=artifact.archiver,
                        status=artifact.status,
                        gcs_path=artifact.gcs_path,
                    )

                synced_count = 1
                logger.info(f"Synced article to Firestore", extra={"item_id": data.article_id})

            except Exception as e:
                errors.append(f"Failed to sync {data.article_id}: {str(e)}")
                logger.error(f"Sync failed for {data.article_id}: {e}", exc_info=True)

        # Case 2: Sync multiple articles
        else:
            # Get articles to sync
            query = db.query(ArchivedUrl).order_by(ArchivedUrl.created_at.desc())

            if not data.force:
                # Only sync articles with completed artifacts
                query = query.join(ArchiveArtifact).filter(
                    ArchiveArtifact.success == True
                ).distinct()

            articles = query.limit(data.limit).all()
            total_count = len(articles)

            for archived_url in articles:
                try:
                    # Fetch related data
                    metadata = (
                        db.query(UrlMetadata)
                        .filter(UrlMetadata.archived_url_id == archived_url.id)
                        .first()
                    )
                    artifacts = (
                        db.query(ArchiveArtifact)
                        .filter(ArchiveArtifact.archived_url_id == archived_url.id)
                        .all()
                    )
                    summary = (
                        db.query(ArticleSummary)
                        .filter(ArticleSummary.archived_url_id == archived_url.id)
                        .first()
                    )
                    entities = (
                        db.query(ArticleEntity)
                        .filter(ArticleEntity.archived_url_id == archived_url.id)
                        .all()
                    )
                    tags = (
                        db.query(ArticleTag)
                        .filter(ArticleTag.archived_url_id == archived_url.id)
                        .all()
                    )

                    # Build and sync document
                    doc = _build_firestore_document(
                        archived_url, metadata, artifacts, summary, entities, tags
                    )

                    firestore.create_article(
                        item_id=archived_url.item_id,
                        url=archived_url.url,
                        pocket_data=doc.get("metadata", {}),
                    )

                    # Sync artifacts
                    for artifact in artifacts:
                        firestore.update_archive_status(
                            item_id=archived_url.item_id,
                            archiver=artifact.archiver,
                            status=artifact.status,
                            gcs_path=artifact.gcs_path,
                        )

                    synced_count += 1

                except Exception as e:
                    errors.append(f"Failed to sync {archived_url.item_id}: {str(e)}")
                    logger.error(f"Sync failed for {archived_url.item_id}: {e}")
                    continue

            logger.info(f"Synced {synced_count}/{total_count} articles to Firestore")

        return PostgresToFirestoreSyncResponse(
            synced=synced_count,
            total=total_count,
            skipped=skipped_count,
            errors=errors,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync operation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Sync operation failed: {str(e)}",
        )


@router.post("/firestore-to-postgres", response_model=FirestoreToPostgresSyncResponse)
async def sync_firestore_to_postgres(
    data: FirestoreToPostgresSyncRequest,
    db: Session = Depends(get_db),
) -> FirestoreToPostgresSyncResponse:
    """
    Sync a single article from Firestore to PostgreSQL.

    This endpoint:
    1. Fetches article from Firestore
    2. Creates or updates article in PostgreSQL
    3. Syncs artifact status from Firestore archives map
    4. Returns sync status and PostgreSQL ID
    """
    from shared.config import get_settings
    from shared.storage.firestore_storage import FirestoreStorage

    settings = get_settings()

    if not settings.firestore.project_id:
        raise HTTPException(
            status_code=400,
            detail="Firestore not configured",
        )

    try:
        firestore = FirestoreStorage(project_id=settings.firestore.project_id)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to initialize Firestore: {str(e)}",
        )

    try:
        # Fetch article from Firestore
        article = firestore.get_article(data.item_id)
        if not article:
            raise HTTPException(
                status_code=404,
                detail=f"Article not found in Firestore: {data.item_id}",
            )

        # Check if article exists in PostgreSQL
        existing = (
            db.query(ArchivedUrl).filter(ArchivedUrl.item_id == data.item_id).first()
        )

        if existing:
            archived_url = existing
        else:
            # Create new record
            archived_url = ArchivedUrl(
                item_id=data.item_id,
                url=article.get("url", ""),
                name=article.get("name", ""),
            )
            db.add(archived_url)
            db.flush()

            # Create metadata from Firestore pocket_data
            pocket_data = article.get("pocket_data", {})
            if pocket_data:
                metadata = UrlMetadata(
                    archived_url_id=archived_url.id,
                    title=pocket_data.get("title"),
                    byline=pocket_data.get("author"),
                    excerpt=pocket_data.get("excerpt"),
                )
                db.add(metadata)

        # Sync artifacts from Firestore archives map
        archives = article.get("archives", {})
        for archiver, archive_data in archives.items():
            # Check if artifact exists
            artifact = (
                db.query(ArchiveArtifact)
                .filter(
                    ArchiveArtifact.archived_url_id == archived_url.id,
                    ArchiveArtifact.archiver == archiver,
                )
                .first()
            )

            if artifact:
                # Update existing
                artifact.status = archive_data.get("status", "pending")
                artifact.success = archive_data.get("success", False)
                if archive_data.get("gcs_path"):
                    artifact.gcs_path = archive_data.get("gcs_path")
            else:
                # Create new
                artifact = ArchiveArtifact(
                    archived_url_id=archived_url.id,
                    archiver=archiver,
                    status=archive_data.get("status", "pending"),
                    success=archive_data.get("success", False),
                    gcs_path=archive_data.get("gcs_path"),
                )
                db.add(artifact)

        db.commit()

        logger.info(
            "Synced article from Firestore to PostgreSQL",
            extra={"item_id": data.item_id, "postgres_id": archived_url.id},
        )

        return FirestoreToPostgresSyncResponse(
            synced=True,
            postgres_id=archived_url.id,
            message=f"Successfully synced article {data.item_id} to PostgreSQL",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Sync failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Sync failed: {str(e)}",
        )
