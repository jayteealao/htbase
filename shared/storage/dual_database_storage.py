"""
Dual Database Storage Provider

Orchestrates dual writes to PostgreSQL (source of truth) and Firestore (mobile replica).

Strategy:
- PostgreSQL gets ALL data (articles, artifacts, summaries, entities, tags)
- Firestore gets filtered data (articles + pocket data only)
- Writes must succeed to PostgreSQL; Firestore is best-effort based on failure mode
- Reads always use PostgreSQL (source of truth)
"""

import logging
from typing import Optional, List, Dict, Any

from .database_storage import (
    DatabaseStorageProvider,
    ArticleMetadata,
    ArticleRecord,
    ArchiveArtifact,
    PocketData,
    ArticleSummary,
    ArticleEntity,
    ArticleTag,
    ArchiveStatus,
)
from .postgres_storage import PostgresStorage
from .firestore_storage import FirestoreStorage
from .sync_filter import SyncFilter

logger = logging.getLogger(__name__)


class DualDatabaseStorage(DatabaseStorageProvider):
    """
    Dual-database storage provider that writes to both PostgreSQL and Firestore.

    PostgreSQL is the source of truth for all data.
    Firestore is a read replica for mobile apps (articles + pocket data only).

    Failure Modes (configurable):
    - fail_fast: If Firestore fails, fail entire operation
    - log_and_continue: Log Firestore failures, continue with PostgreSQL
    - queue_retry: Queue failed Firestore writes for retry (future enhancement)
    """

    def __init__(
        self,
        postgres: PostgresStorage,
        firestore: FirestoreStorage,
        failure_mode: str = "fail_fast"
    ):
        """
        Initialize dual database storage.

        Args:
            postgres: PostgreSQL storage provider (primary)
            firestore: Firestore storage provider (replica)
            failure_mode: How to handle Firestore failures
                          ("fail_fast", "log_and_continue", "queue_retry")
        """
        self.postgres = postgres
        self.firestore = firestore
        self.sync_filter = SyncFilter()
        self.failure_mode = failure_mode

        logger.info(
            f"Initialized DualDatabaseStorage "
            f"(PostgreSQL + Firestore, failure_mode={failure_mode})"
        )

    # ==================== Article Operations ====================

    def create_article(self, metadata: ArticleMetadata) -> bool:
        """
        Create article in both databases.

        Flow:
        1. Write to PostgreSQL (source of truth)
        2. Filter data for Firestore
        3. Write to Firestore (articles + pocket only)
        4. Handle failures based on failure_mode

        Args:
            metadata: Article metadata

        Returns:
            True if successful (based on failure mode)
        """
        # Step 1: Write to PostgreSQL first
        pg_success = self.postgres.create_article(metadata)
        if not pg_success:
            logger.error(f"PostgreSQL create_article failed for {metadata.item_id}")
            return False  # PostgreSQL is source of truth - fail immediately

        # Step 2: Write to Firestore (filtered data)
        try:
            fs_success = self.firestore.create_article(metadata)

            if not fs_success:
                return self._handle_firestore_failure(
                    operation="create_article",
                    item_id=metadata.item_id,
                    error="Firestore write returned False"
                )
        except Exception as e:
            return self._handle_firestore_failure(
                operation="create_article",
                item_id=metadata.item_id,
                error=str(e)
            )

        logger.debug(f"Dual write successful for article {metadata.item_id}")
        return True

    def get_article(self, item_id: str) -> Optional[ArticleRecord]:
        """
        Get article from PostgreSQL (source of truth).

        Args:
            item_id: Article identifier

        Returns:
            ArticleRecord or None
        """
        return self.postgres.get_article(item_id)

    def get_article_by_url(self, url: str) -> Optional[ArticleRecord]:
        """
        Get article by URL from PostgreSQL.

        Args:
            url: Article URL

        Returns:
            ArticleRecord or None
        """
        return self.postgres.get_article_by_url(url)

    def update_article_metadata(self, item_id: str, metadata: Dict[str, Any]) -> bool:
        """
        Update article metadata in both databases.

        Args:
            item_id: Article identifier
            metadata: Fields to update

        Returns:
            True if successful
        """
        # Update PostgreSQL first
        pg_success = self.postgres.update_article_metadata(item_id, metadata)
        if not pg_success:
            logger.error(f"PostgreSQL update_article_metadata failed for {item_id}")
            return False

        # Update Firestore (only allowed fields)
        try:
            # Filter metadata to Firestore-allowed fields
            filtered_metadata = {
                k: v for k, v in metadata.items()
                if k in self.sync_filter.ALLOWED_METADATA_FIELDS
            }

            if filtered_metadata:
                fs_success = self.firestore.update_article_metadata(item_id, filtered_metadata)
                if not fs_success:
                    return self._handle_firestore_failure(
                        operation="update_article_metadata",
                        item_id=item_id,
                        error="Firestore update returned False"
                    )
        except Exception as e:
            return self._handle_firestore_failure(
                operation="update_article_metadata",
                item_id=item_id,
                error=str(e)
            )

        return True

    def delete_article(self, item_id: str) -> bool:
        """
        Delete article from both databases.

        Args:
            item_id: Article identifier

        Returns:
            True if successful
        """
        # Delete from PostgreSQL first
        pg_success = self.postgres.delete_article(item_id)
        if not pg_success:
            logger.error(f"PostgreSQL delete_article failed for {item_id}")
            return False

        # Delete from Firestore
        try:
            fs_success = self.firestore.delete_article(item_id)
            if not fs_success:
                return self._handle_firestore_failure(
                    operation="delete_article",
                    item_id=item_id,
                    error="Firestore delete returned False"
                )
        except Exception as e:
            return self._handle_firestore_failure(
                operation="delete_article",
                item_id=item_id,
                error=str(e)
            )

        return True

    def list_articles(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ArticleRecord]:
        """
        List articles from PostgreSQL (source of truth).

        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            filters: Filter criteria

        Returns:
            List of ArticleRecord
        """
        return self.postgres.list_articles(limit, offset, filters)

    # ==================== Archive Artifact Operations ====================

    def create_artifact(self, artifact: ArchiveArtifact) -> bool:
        """
        Create artifact in both databases.

        Flow:
        1. Write full artifact to PostgreSQL
        2. Write basic status to Firestore (status, gcs_path only)

        Args:
            artifact: Archive artifact data

        Returns:
            True if successful
        """
        # Write to PostgreSQL first
        pg_success = self.postgres.create_artifact(artifact)
        if not pg_success:
            logger.error(f"PostgreSQL create_artifact failed for {artifact.item_id}/{artifact.archiver}")
            return False

        # Write to Firestore (filtered)
        try:
            fs_success = self.firestore.create_artifact(artifact)
            if not fs_success:
                return self._handle_firestore_failure(
                    operation="create_artifact",
                    item_id=artifact.item_id,
                    error=f"Firestore artifact write failed for {artifact.archiver}"
                )
        except Exception as e:
            return self._handle_firestore_failure(
                operation="create_artifact",
                item_id=artifact.item_id,
                error=str(e)
            )

        return True

    def get_artifacts(self, item_id: str) -> List[ArchiveArtifact]:
        """
        Get all artifacts from PostgreSQL.

        Args:
            item_id: Article identifier

        Returns:
            List of ArchiveArtifact
        """
        return self.postgres.get_artifacts(item_id)

    def get_artifact(self, item_id: str, archiver: str) -> Optional[ArchiveArtifact]:
        """
        Get specific artifact from PostgreSQL.

        Args:
            item_id: Article identifier
            archiver: Archiver name

        Returns:
            ArchiveArtifact or None
        """
        return self.postgres.get_artifact(item_id, archiver)

    def update_artifact_status(
        self,
        item_id: str,
        archiver: str,
        status: ArchiveStatus,
        **kwargs
    ) -> bool:
        """
        Update artifact status in both databases.

        Flow:
        1. Update PostgreSQL artifact table (full history)
        2. Update Firestore archives map (basic status only)

        Args:
            item_id: Article identifier
            archiver: Archiver name
            status: New status
            **kwargs: Additional fields (gcs_path, error_message, etc.)

        Returns:
            True if successful
        """
        # Update PostgreSQL first
        pg_success = self.postgres.update_artifact_status(
            item_id, archiver, status, **kwargs
        )
        if not pg_success:
            logger.error(f"PostgreSQL update_artifact_status failed for {item_id}/{archiver}")
            return False

        # Update Firestore (filtered fields only)
        try:
            # Filter kwargs to Firestore-allowed fields
            filtered_kwargs = self.sync_filter.filter_artifact_for_firestore(
                archiver=archiver,
                status=status,
                gcs_path=kwargs.get('gcs_path'),
                gcs_bucket=kwargs.get('gcs_bucket'),
                file_size=kwargs.get('file_size'),
            )

            fs_success = self.firestore.update_artifact_status(
                item_id, archiver, status, **filtered_kwargs
            )

            if not fs_success:
                return self._handle_firestore_failure(
                    operation="update_artifact_status",
                    item_id=item_id,
                    error=f"Firestore artifact update failed for {archiver}"
                )
        except Exception as e:
            return self._handle_firestore_failure(
                operation="update_artifact_status",
                item_id=item_id,
                error=str(e)
            )

        return True

    # ==================== Pocket Data Operations ====================

    def create_pocket_data(self, pocket: PocketData) -> bool:
        """
        Create Pocket data in both databases.

        Args:
            pocket: Pocket data

        Returns:
            True if successful
        """
        # Write to PostgreSQL first
        pg_success = self.postgres.create_pocket_data(pocket)
        if not pg_success:
            logger.error(f"PostgreSQL create_pocket_data failed for {pocket.item_id}")
            return False

        # Write to Firestore
        try:
            fs_success = self.firestore.create_pocket_data(pocket)
            if not fs_success:
                return self._handle_firestore_failure(
                    operation="create_pocket_data",
                    item_id=pocket.item_id,
                    error="Firestore pocket write failed"
                )
        except Exception as e:
            return self._handle_firestore_failure(
                operation="create_pocket_data",
                item_id=pocket.item_id,
                error=str(e)
            )

        return True

    def get_pocket_data(self, item_id: str) -> Optional[PocketData]:
        """
        Get Pocket data from PostgreSQL.

        Args:
            item_id: Article identifier

        Returns:
            PocketData or None
        """
        return self.postgres.get_pocket_data(item_id)

    # ==================== AI Content Operations (PostgreSQL Only) ====================

    def create_summary(self, summary: ArticleSummary) -> bool:
        """
        Create summary in PostgreSQL only (not synced to Firestore).

        Args:
            summary: Article summary

        Returns:
            True if successful
        """
        # Summaries stay in PostgreSQL only (too large for Firestore)
        return self.postgres.create_summary(summary)

    def get_summary(self, item_id: str) -> Optional[ArticleSummary]:
        """
        Get summary from PostgreSQL.

        Args:
            item_id: Article identifier

        Returns:
            ArticleSummary or None
        """
        return self.postgres.get_summary(item_id)

    def create_entities(self, entities: List[ArticleEntity]) -> bool:
        """
        Create entities in PostgreSQL only (not synced to Firestore).

        Args:
            entities: List of entities

        Returns:
            True if successful
        """
        # Entities stay in PostgreSQL only
        return self.postgres.create_entities(entities)

    def get_entities(self, item_id: str) -> List[ArticleEntity]:
        """
        Get entities from PostgreSQL.

        Args:
            item_id: Article identifier

        Returns:
            List of ArticleEntity
        """
        return self.postgres.get_entities(item_id)

    def create_tags(self, tags: List[ArticleTag]) -> bool:
        """
        Create tags in PostgreSQL only (not synced to Firestore).

        Args:
            tags: List of tags

        Returns:
            True if successful
        """
        # Tags stay in PostgreSQL only
        return self.postgres.create_tags(tags)

    def get_tags(self, item_id: str) -> List[ArticleTag]:
        """
        Get tags from PostgreSQL.

        Args:
            item_id: Article identifier

        Returns:
            List of ArticleTag
        """
        return self.postgres.get_tags(item_id)

    # ==================== Batch Operations ====================

    def batch_create_articles(self, articles: List[ArticleMetadata]) -> int:
        """
        Create multiple articles in batch (both databases).

        Args:
            articles: List of article metadata

        Returns:
            Number of articles created
        """
        # Batch write to PostgreSQL first
        pg_count = self.postgres.batch_create_articles(articles)

        # Batch write to Firestore (best effort)
        try:
            fs_count = self.firestore.batch_create_articles(articles)
            if fs_count != pg_count:
                logger.warning(
                    f"Firestore batch write mismatch: "
                    f"PostgreSQL={pg_count}, Firestore={fs_count}"
                )
        except Exception as e:
            logger.error(f"Firestore batch_create_articles failed: {e}")
            if self.failure_mode == "fail_fast":
                # Note: Can't rollback PostgreSQL batch easily
                logger.error("Firestore batch failed in fail_fast mode (PostgreSQL committed)")

        return pg_count

    def batch_update_artifacts(self, artifacts: List[ArchiveArtifact]) -> int:
        """
        Update multiple artifacts in batch (both databases).

        Args:
            artifacts: List of artifacts

        Returns:
            Number of artifacts updated
        """
        # Batch update PostgreSQL first
        pg_count = self.postgres.batch_update_artifacts(artifacts)

        # Batch update Firestore (best effort)
        try:
            fs_count = self.firestore.batch_update_artifacts(artifacts)
            if fs_count != pg_count:
                logger.warning(
                    f"Firestore batch artifact mismatch: "
                    f"PostgreSQL={pg_count}, Firestore={fs_count}"
                )
        except Exception as e:
            logger.error(f"Firestore batch_update_artifacts failed: {e}")

        return pg_count

    # ==================== Query Operations ====================

    def count_articles(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count articles from PostgreSQL.

        Args:
            filters: Filter criteria

        Returns:
            Count of matching articles
        """
        return self.postgres.count_articles(filters)

    def search_articles(
        self,
        query: str,
        limit: Optional[int] = None
    ) -> List[ArticleRecord]:
        """
        Full-text search articles from PostgreSQL.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching ArticleRecord
        """
        return self.postgres.search_articles(query, limit)

    # ==================== Provider Info ====================

    @property
    def provider_name(self) -> str:
        """Name of the database provider."""
        return "dual"

    @property
    def supports_transactions(self) -> bool:
        """Whether this provider supports ACID transactions."""
        # Both backends support transactions
        return True

    @property
    def supports_full_text_search(self) -> bool:
        """Whether this provider supports full-text search."""
        # PostgreSQL does, Firestore doesn't, but we use PostgreSQL for searches
        return True

    # ==================== Private Helpers ====================

    def _handle_firestore_failure(
        self,
        operation: str,
        item_id: str,
        error: str
    ) -> bool:
        """
        Handle Firestore write failure based on configured failure mode.

        Args:
            operation: Name of operation that failed
            item_id: Article/item identifier
            error: Error message

        Returns:
            True if should continue (log_and_continue mode)
            False if should fail (fail_fast mode)
        """
        log_msg = f"Firestore {operation} failed for {item_id}: {error}"

        if self.failure_mode == "fail_fast":
            logger.error(f"{log_msg} [FAIL_FAST MODE - FAILING OPERATION]")
            return False

        elif self.failure_mode == "log_and_continue":
            logger.warning(f"{log_msg} [LOG_AND_CONTINUE MODE - CONTINUING]")
            return True

        elif self.failure_mode == "queue_retry":
            logger.warning(f"{log_msg} [QUEUE_RETRY MODE - QUEUING FOR RETRY]")
            # TODO: Implement retry queue
            # For now, just log and continue
            return True

        else:
            logger.error(f"Unknown failure_mode: {self.failure_mode}")
            return False
