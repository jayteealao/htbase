"""
PostgreSQL Database Storage Implementation

Wraps existing SQLAlchemy repository operations to provide
a unified interface compatible with other database providers.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, func

from .database_storage import (
    DatabaseStorageProvider,
    ArticleMetadata,
    ArchiveArtifact,
    PocketData,
    ArticleSummary,
    ArticleEntity,
    ArticleTag,
    ArticleRecord,
    ArchiveStatus
)
from db.repositories import (
    ArchivedUrlRepository,
    ArchiveArtifactRepository,
    UrlMetadataRepository,
    ArticleSummaryRepository,
    ArticleEntityRepository,
    ArticleTagRepository
)
from db.models import ArchivedUrl, UrlMetadata
from db.models import ArchiveArtifact as DBArchiveArtifact
from db.models import ArticleSummary as DBArticleSummary
from db.models import ArticleEntity as DBArticleEntity
from db.models import ArticleTag as DBArticleTag
from db.session import get_session


class PostgresStorage(DatabaseStorageProvider):
    """
    PostgreSQL storage implementation.

    Wraps existing repository classes:
    - ArchivedUrlRepository
    - ArchiveArtifactRepository
    - UrlMetadataRepository
    - ArticleSummaryRepository
    - ArticleEntityRepository
    - ArticleTagRepository
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize PostgreSQL storage.

        Args:
            db_path: Optional database path (for sqlite legacy support)
                    If None, uses connection from config
        """
        self.db_path = db_path
        self.url_repo = ArchivedUrlRepository(db_path)
        self.artifact_repo = ArchiveArtifactRepository(db_path)
        self.metadata_repo = UrlMetadataRepository(db_path)
        self.summary_repo = ArticleSummaryRepository(db_path)
        self.entity_repo = ArticleEntityRepository(db_path)
        self.tag_repo = ArticleTagRepository(db_path)

    # ==================== Article Operations ====================

    def create_article(self, metadata: ArticleMetadata) -> bool:
        """Create a new article record."""
        try:
            with get_session(self.db_path) as session:
                # Create archived URL
                au = ArchivedUrl(
                    url=metadata.url,
                    item_id=metadata.item_id,
                    name=None
                )
                session.add(au)
                session.flush()

                # Create metadata if provided
                if any([
                    metadata.title,
                    metadata.byline,
                    metadata.text_content,
                    metadata.word_count
                ]):
                    um = UrlMetadata(
                        archived_url_id=au.id,
                        title=metadata.title,
                        byline=metadata.byline,
                        text=metadata.text_content,
                        word_count=metadata.word_count
                    )
                    session.add(um)

                session.commit()
                return True

        except Exception:
            return False

    def get_article(self, item_id: str) -> Optional[ArticleRecord]:
        """Get complete article record by item_id."""
        try:
            with get_session(self.db_path) as session:
                # Find archived URL by item_id
                au = session.execute(
                    select(ArchivedUrl).where(ArchivedUrl.item_id == item_id)
                ).scalars().first()

                if not au:
                    return None

                return self._build_article_record(session, au)

        except Exception:
            return None

    def get_article_by_url(self, url: str) -> Optional[ArticleRecord]:
        """Get article record by URL."""
        try:
            au = self.url_repo.get_by_url(url)
            if not au:
                return None

            with get_session(self.db_path) as session:
                au = session.merge(au)  # Reattach to session
                return self._build_article_record(session, au)

        except Exception:
            return None

    def update_article_metadata(self, item_id: str, metadata: Dict[str, Any]) -> bool:
        """Update article metadata fields."""
        try:
            with get_session(self.db_path) as session:
                # Find archived URL
                au = session.execute(
                    select(ArchivedUrl).where(ArchivedUrl.item_id == item_id)
                ).scalars().first()

                if not au:
                    return False

                # Update ArchivedUrl fields
                if "url" in metadata:
                    au.url = metadata["url"]
                if "name" in metadata:
                    au.name = metadata["name"]

                # Update UrlMetadata fields
                um = session.execute(
                    select(UrlMetadata).where(
                        UrlMetadata.archived_url_id == au.id
                    )
                ).scalars().first()

                if um:
                    if "title" in metadata:
                        um.title = metadata["title"]
                    if "byline" in metadata:
                        um.byline = metadata["byline"]
                    if "text_content" in metadata:
                        um.text = metadata["text_content"]
                    if "word_count" in metadata:
                        um.word_count = metadata["word_count"]
                    if "excerpt" in metadata:
                        um.description = metadata["excerpt"]
                elif any(k in metadata for k in ["title", "byline", "text_content", "word_count", "excerpt"]):
                    # Create metadata if it doesn't exist
                    um = UrlMetadata(
                        archived_url_id=au.id,
                        title=metadata.get("title"),
                        byline=metadata.get("byline"),
                        text=metadata.get("text_content"),
                        word_count=metadata.get("word_count"),
                        description=metadata.get("excerpt")
                    )
                    session.add(um)

                session.commit()
                return True

        except Exception:
            return False

    def delete_article(self, item_id: str) -> bool:
        """Delete article and all related data."""
        try:
            with get_session(self.db_path) as session:
                au = session.execute(
                    select(ArchivedUrl).where(ArchivedUrl.item_id == item_id)
                ).scalars().first()

                if not au:
                    return False

                # SQLAlchemy cascade will delete related records
                session.delete(au)
                session.commit()
                return True

        except Exception:
            return False

    def list_articles(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ArticleRecord]:
        """List articles with optional filtering."""
        try:
            with get_session(self.db_path) as session:
                query = select(ArchivedUrl)

                # Apply filters (basic implementation)
                # Note: filters may need to be applied on joined tables
                # depending on what fields are requested

                # Order by created_at desc
                query = query.order_by(ArchivedUrl.created_at.desc())

                # Apply offset
                if offset:
                    query = query.offset(offset)

                # Apply limit
                if limit:
                    query = query.limit(limit)

                results = session.execute(query).scalars().all()

                articles = []
                for au in results:
                    article = self._build_article_record(session, au)
                    if article:
                        articles.append(article)

                return articles

        except Exception:
            return []

    # ==================== Archive Artifact Operations ====================

    def create_artifact(self, artifact: ArchiveArtifact) -> bool:
        """Create or update archive artifact."""
        try:
            with get_session(self.db_path) as session:
                # Find archived URL by item_id
                au = session.execute(
                    select(ArchivedUrl).where(
                        ArchivedUrl.item_id == artifact.item_id
                    )
                ).scalars().first()

                if not au:
                    # Create archived URL if it doesn't exist
                    au = ArchivedUrl(
                        item_id=artifact.item_id,
                        url=""  # URL will be updated later
                    )
                    session.add(au)
                    session.flush()

                # Get or create artifact
                art = session.execute(
                    select(DBArchiveArtifact).where(
                        DBArchiveArtifact.archived_url_id == au.id,
                        DBArchiveArtifact.archiver == artifact.archiver
                    )
                ).scalars().first()

                if art is None:
                    art = DBArchiveArtifact(
                        archived_url_id=au.id,
                        archiver=artifact.archiver
                    )
                    session.add(art)

                # Update fields
                art.success = (artifact.status == ArchiveStatus.SUCCESS)
                art.status = artifact.status.value
                art.exit_code = artifact.exit_code
                art.saved_path = artifact.gcs_path or artifact.local_path
                art.size_bytes = artifact.file_size
                art.updated_at = datetime.utcnow()

                # Store GCS info in saved_path for now
                # TODO: Add gcs_path/gcs_bucket columns to schema
                if artifact.gcs_path:
                    art.saved_path = f"gs://{artifact.gcs_bucket}/{artifact.gcs_path}"

                session.commit()
                return True

        except Exception:
            return False

    def get_artifacts(self, item_id: str) -> List[ArchiveArtifact]:
        """Get all artifacts for an article."""
        try:
            with get_session(self.db_path) as session:
                au = session.execute(
                    select(ArchivedUrl).where(ArchivedUrl.item_id == item_id)
                ).scalars().first()

                if not au:
                    return []

                arts = session.execute(
                    select(DBArchiveArtifact).where(
                        DBArchiveArtifact.archived_url_id == au.id
                    )
                ).scalars().all()

                return [self._db_artifact_to_artifact(art, item_id) for art in arts]

        except Exception:
            return []

    def get_artifact(self, item_id: str, archiver: str) -> Optional[ArchiveArtifact]:
        """Get specific artifact by archiver name."""
        try:
            with get_session(self.db_path) as session:
                au = session.execute(
                    select(ArchivedUrl).where(ArchivedUrl.item_id == item_id)
                ).scalars().first()

                if not au:
                    return None

                art = session.execute(
                    select(DBArchiveArtifact).where(
                        DBArchiveArtifact.archived_url_id == au.id,
                        DBArchiveArtifact.archiver == archiver
                    )
                ).scalars().first()

                if not art:
                    return None

                return self._db_artifact_to_artifact(art, item_id)

        except Exception:
            return None

    def update_artifact_status(
        self,
        item_id: str,
        archiver: str,
        status: ArchiveStatus,
        **kwargs
    ) -> bool:
        """Update artifact status and related fields."""
        try:
            with get_session(self.db_path) as session:
                au = session.execute(
                    select(ArchivedUrl).where(ArchivedUrl.item_id == item_id)
                ).scalars().first()

                if not au:
                    return False

                art = session.execute(
                    select(DBArchiveArtifact).where(
                        DBArchiveArtifact.archived_url_id == au.id,
                        DBArchiveArtifact.archiver == archiver
                    )
                ).scalars().first()

                if not art:
                    return False

                # Update status
                art.status = status.value
                art.success = (status == ArchiveStatus.SUCCESS)
                art.updated_at = datetime.utcnow()

                # Update additional fields
                for key, value in kwargs.items():
                    if key == "gcs_path":
                        art.saved_path = value
                    elif key == "gcs_bucket":
                        # Store as gs:// URL
                        if value and kwargs.get("gcs_path"):
                            art.saved_path = f"gs://{value}/{kwargs['gcs_path']}"
                    elif key == "error_message":
                        # No error_message column in current schema
                        pass
                    elif key == "file_size":
                        art.size_bytes = value
                    elif key == "exit_code":
                        art.exit_code = value

                session.commit()
                return True

        except Exception:
            return False

    # ==================== Pocket Data Operations ====================

    def create_pocket_data(self, pocket: PocketData) -> bool:
        """
        Create or update Pocket metadata.

        Note: Current PostgreSQL schema doesn't have a separate
        Pocket table. This is a no-op for compatibility.
        """
        # TODO: Add Pocket tables to schema or store in JSONB
        return True

    def get_pocket_data(self, item_id: str) -> Optional[PocketData]:
        """
        Get Pocket metadata for an article.

        Note: Current PostgreSQL schema doesn't have Pocket tables.
        Returns None for compatibility.
        """
        # TODO: Implement when Pocket tables are added
        return None

    # ==================== AI Content Operations ====================

    def create_summary(self, summary: ArticleSummary) -> bool:
        """Store article summary."""
        try:
            with get_session(self.db_path) as session:
                au = session.execute(
                    select(ArchivedUrl).where(ArchivedUrl.item_id == summary.item_id)
                ).scalars().first()

                if not au:
                    return False

                # Check if summary exists
                summ = session.execute(
                    select(DBArticleSummary).where(
                        DBArticleSummary.archived_url_id == au.id,
                        DBArticleSummary.summary_type == "default"
                    )
                ).scalars().first()

                if summ is None:
                    summ = DBArticleSummary(
                        archived_url_id=au.id,
                        summary_type="default",
                        summary_text=summary.summary
                    )
                    session.add(summ)
                else:
                    summ.summary_text = summary.summary
                    summ.updated_at = datetime.utcnow()

                session.commit()
                return True

        except Exception:
            return False

    def get_summary(self, item_id: str) -> Optional[ArticleSummary]:
        """Get article summary."""
        try:
            with get_session(self.db_path) as session:
                au = session.execute(
                    select(ArchivedUrl).where(ArchivedUrl.item_id == item_id)
                ).scalars().first()

                if not au:
                    return None

                summ = session.execute(
                    select(DBArticleSummary).where(
                        DBArticleSummary.archived_url_id == au.id,
                        DBArticleSummary.summary_type == "default"
                    )
                ).scalars().first()

                if not summ:
                    return None

                return ArticleSummary(
                    item_id=item_id,
                    summary=summ.summary_text,
                    created_at=summ.created_at
                )

        except Exception:
            return None

    def create_entities(self, entities: List[ArticleEntity]) -> bool:
        """Store extracted entities (batch)."""
        if not entities:
            return True

        try:
            with get_session(self.db_path) as session:
                item_id = entities[0].item_id
                au = session.execute(
                    select(ArchivedUrl).where(ArchivedUrl.item_id == item_id)
                ).scalars().first()

                if not au:
                    return False

                for entity in entities:
                    # Check if exists
                    ent = session.execute(
                        select(DBArticleEntity).where(
                            DBArticleEntity.archived_url_id == au.id,
                            DBArticleEntity.entity == entity.entity_value,
                            DBArticleEntity.entity_type == entity.entity_type
                        )
                    ).scalars().first()

                    if ent is None:
                        ent = DBArticleEntity(
                            archived_url_id=au.id,
                            entity=entity.entity_value,
                            entity_type=entity.entity_type,
                            confidence=entity.confidence
                        )
                        session.add(ent)

                session.commit()
                return True

        except Exception:
            return False

    def get_entities(self, item_id: str) -> List[ArticleEntity]:
        """Get all entities for an article."""
        try:
            with get_session(self.db_path) as session:
                au = session.execute(
                    select(ArchivedUrl).where(ArchivedUrl.item_id == item_id)
                ).scalars().first()

                if not au:
                    return []

                ents = session.execute(
                    select(DBArticleEntity).where(
                        DBArticleEntity.archived_url_id == au.id
                    )
                ).scalars().all()

                return [
                    ArticleEntity(
                        item_id=item_id,
                        entity_type=ent.entity_type or "",
                        entity_value=ent.entity,
                        confidence=ent.confidence
                    )
                    for ent in ents
                ]

        except Exception:
            return []

    def create_tags(self, tags: List[ArticleTag]) -> bool:
        """Store article tags (batch)."""
        if not tags:
            return True

        try:
            with get_session(self.db_path) as session:
                item_id = tags[0].item_id
                au = session.execute(
                    select(ArchivedUrl).where(ArchivedUrl.item_id == item_id)
                ).scalars().first()

                if not au:
                    return False

                for tag in tags:
                    # Check if exists
                    t = session.execute(
                        select(DBArticleTag).where(
                            DBArticleTag.archived_url_id == au.id,
                            DBArticleTag.tag == tag.tag,
                            DBArticleTag.source == "auto"
                        )
                    ).scalars().first()

                    if t is None:
                        t = DBArticleTag(
                            archived_url_id=au.id,
                            tag=tag.tag,
                            source="auto",
                            confidence=tag.confidence
                        )
                        session.add(t)

                session.commit()
                return True

        except Exception:
            return False

    def get_tags(self, item_id: str) -> List[ArticleTag]:
        """Get all tags for an article."""
        try:
            with get_session(self.db_path) as session:
                au = session.execute(
                    select(ArchivedUrl).where(ArchivedUrl.item_id == item_id)
                ).scalars().first()

                if not au:
                    return []

                tags = session.execute(
                    select(DBArticleTag).where(
                        DBArticleTag.archived_url_id == au.id
                    )
                ).scalars().all()

                return [
                    ArticleTag(
                        item_id=item_id,
                        tag=t.tag,
                        confidence=t.confidence
                    )
                    for t in tags
                ]

        except Exception:
            return []

    # ==================== Batch Operations ====================

    def batch_create_articles(self, articles: List[ArticleMetadata]) -> int:
        """Create multiple articles in batch."""
        count = 0
        for article in articles:
            if self.create_article(article):
                count += 1
        return count

    def batch_update_artifacts(self, artifacts: List[ArchiveArtifact]) -> int:
        """Update multiple artifacts in batch."""
        count = 0
        for artifact in artifacts:
            if self.create_artifact(artifact):
                count += 1
        return count

    # ==================== Query Operations ====================

    def count_articles(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count articles matching filters."""
        try:
            with get_session(self.db_path) as session:
                query = select(func.count(ArchivedUrl.id))
                # TODO: Apply filters
                return session.execute(query).scalar() or 0

        except Exception:
            return 0

    def search_articles(
        self,
        query: str,
        limit: Optional[int] = None
    ) -> List[ArticleRecord]:
        """
        Full-text search articles.

        Uses PostgreSQL text search capabilities.
        """
        try:
            with get_session(self.db_path) as session:
                # Join with url_metadata for text search
                stmt = (
                    select(ArchivedUrl)
                    .join(UrlMetadata, UrlMetadata.archived_url_id == ArchivedUrl.id)
                    .where(
                        UrlMetadata.title.ilike(f"%{query}%") |
                        UrlMetadata.text.ilike(f"%{query}%")
                    )
                )

                if limit:
                    stmt = stmt.limit(limit)

                results = session.execute(stmt).scalars().all()

                articles = []
                for au in results:
                    article = self._build_article_record(session, au)
                    if article:
                        articles.append(article)

                return articles

        except Exception:
            return []

    # ==================== Provider Info ====================

    @property
    def provider_name(self) -> str:
        """Provider name."""
        return "postgres"

    @property
    def supports_transactions(self) -> bool:
        """Supports ACID transactions."""
        return True

    @property
    def supports_full_text_search(self) -> bool:
        """Supports full-text search."""
        return True

    # ==================== Helper Methods ====================

    def _build_article_record(
        self,
        session,
        au: ArchivedUrl
    ) -> Optional[ArticleRecord]:
        """Build complete ArticleRecord from database."""
        try:
            # Get metadata
            um = session.execute(
                select(UrlMetadata).where(
                    UrlMetadata.archived_url_id == au.id
                )
            ).scalars().first()

            metadata = ArticleMetadata(
                item_id=au.item_id or "",
                url=au.url,
                title=um.title if um else None,
                byline=um.byline if um else None,
                excerpt=um.description if um else None,
                text_content=um.text if um else None,
                word_count=um.word_count if um else None,
                created_at=au.created_at
            )

            # Get artifacts
            arts = session.execute(
                select(DBArchiveArtifact).where(
                    DBArchiveArtifact.archived_url_id == au.id
                )
            ).scalars().all()

            artifacts = [
                self._db_artifact_to_artifact(art, au.item_id or "")
                for art in arts
            ]

            # Get summary
            summ = session.execute(
                select(DBArticleSummary).where(
                    DBArticleSummary.archived_url_id == au.id,
                    DBArticleSummary.summary_type == "default"
                )
            ).scalars().first()

            summary = None
            if summ:
                summary = ArticleSummary(
                    item_id=au.item_id or "",
                    summary=summ.summary_text,
                    created_at=summ.created_at
                )

            # Get entities
            ents = session.execute(
                select(DBArticleEntity).where(
                    DBArticleEntity.archived_url_id == au.id
                )
            ).scalars().all()

            entities = [
                ArticleEntity(
                    item_id=au.item_id or "",
                    entity_type=ent.entity_type or "",
                    entity_value=ent.entity,
                    confidence=ent.confidence
                )
                for ent in ents
            ] if ents else None

            # Get tags
            tags_db = session.execute(
                select(DBArticleTag).where(
                    DBArticleTag.archived_url_id == au.id
                )
            ).scalars().all()

            tags = [
                ArticleTag(
                    item_id=au.item_id or "",
                    tag=t.tag,
                    confidence=t.confidence
                )
                for t in tags_db
            ] if tags_db else None

            return ArticleRecord(
                metadata=metadata,
                archives=artifacts,
                pocket=None,  # TODO: Implement when Pocket tables exist
                summary=summary,
                entities=entities,
                tags=tags
            )

        except Exception:
            return None

    def _db_artifact_to_artifact(
        self,
        art: DBArchiveArtifact,
        item_id: str
    ) -> ArchiveArtifact:
        """Convert DB artifact to abstraction artifact."""
        # Parse status
        status = ArchiveStatus.PENDING
        if art.status:
            try:
                status = ArchiveStatus(art.status)
            except ValueError:
                # Fallback based on success field
                status = ArchiveStatus.SUCCESS if art.success else ArchiveStatus.FAILED

        # Parse GCS path if stored as gs:// URL
        gcs_path = None
        gcs_bucket = None
        local_path = art.saved_path

        if art.saved_path and art.saved_path.startswith("gs://"):
            parts = art.saved_path[5:].split("/", 1)
            if len(parts) == 2:
                gcs_bucket = parts[0]
                gcs_path = parts[1]
                local_path = None

        return ArchiveArtifact(
            item_id=item_id,
            archiver=art.archiver,
            status=status,
            gcs_path=gcs_path,
            gcs_bucket=gcs_bucket,
            local_path=local_path,
            file_size=art.size_bytes,
            exit_code=art.exit_code,
            error_message=None,  # Not stored in current schema
            created_at=art.created_at,
            updated_at=art.updated_at
        )
