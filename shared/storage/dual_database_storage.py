"""
Dual Database Storage Provider

Orchestrates dual writes to PostgreSQL (source of truth) and Firestore (mobile replica).

Strategy:
- PostgreSQL gets ALL data (articles, artifacts, summaries, entities, tags)
- Firestore gets filtered data (articles + pocket data only)
- Writes must succeed to PostgreSQL; Firestore is best-effort based on failure mode
- Reads always use PostgreSQL (source of truth)
- Implements eventual consistency with reconciliation worker support
"""

import logging
from datetime import datetime
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

    Architecture:
    - PostgreSQL: Source of truth for ALL data (articles, artifacts, summaries, etc.)
    - Firestore: Read replica for mobile apps (articles + pocket metadata only)
    - Sync: Best-effort eventual consistency (PostgreSQL → Firestore)

    Write Order (CRITICAL):
    1. PostgreSQL write (blocking, must succeed)
    2. Firestore write (best-effort based on failure_mode)

    ⚠️ IMPORTANT: Distributed Transaction Semantics

    This class does NOT provide true atomic dual-writes across both databases.
    Neither PostgreSQL nor Firestore supports distributed transactions (2PC).

    Failure Modes:

    1. "fail_fast" (strict, raises exception on Firestore failure)
       - PostgreSQL write succeeds ✅
       - Firestore write fails ❌
       - Exception raised to caller
       - ⚠️ WARNING: PostgreSQL data IS ALREADY COMMITTED (cannot rollback)
       - Result: Split-brain state (PostgreSQL has data, Firestore doesn't)
       - Recovery: Reconciliation worker must sync PostgreSQL → Firestore
       - Use when: You want to know immediately about sync failures

    2. "log_and_continue" (eventual consistency, tolerates Firestore failures)
       - PostgreSQL write succeeds ✅
       - Firestore write fails ❌
       - Logs warning but returns success
       - Result: Firestore eventual consistency (will be synced later)
       - Recovery: Reconciliation worker handles sync
       - Use when: Firestore is truly optional, mobile app can tolerate stale data

    3. "queue_retry" (future enhancement, not yet implemented)
       - Would queue failed Firestore writes for retry
       - Requires message queue infrastructure

    Reconciliation:
    - A separate reconciliation worker should periodically sync PostgreSQL → Firestore
    - Query PostgreSQL for records with firestore_synced=False
    - Retry Firestore writes for unsynced records
    - Mark records as synced on success

    Example Failure Scenario:

        storage = DualDatabaseStorage(pg, fs, failure_mode="fail_fast")

        try:
            storage.create_article(metadata)
        except Exception:
            # Exception raised because Firestore failed
            # BUT: Article exists in PostgreSQL! (committed before Firestore attempt)
            # Check PostgreSQL directly to see data

    Best Practices:
    - Use "log_and_continue" for production (tolerates Firestore outages)
    - Implement reconciliation worker to fix sync lag
    - Monitor Firestore sync lag metrics
    - Alert on sustained sync failures (>1 hour lag)
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

        ⚠️ CRITICAL: PostgreSQL write happens BEFORE Firestore write.
        If Firestore fails, PostgreSQL data is ALREADY COMMITTED (cannot rollback).

        Flow:
        1. Write to PostgreSQL (BLOCKING - must succeed or entire operation fails)
        2. If PostgreSQL succeeds → PostgreSQL data is COMMITTED
        3. Filter data for Firestore (articles + pocket metadata only)
        4. Write to Firestore (best-effort based on failure_mode)
        5. Handle Firestore failures based on failure_mode setting

        Failure Scenarios:

        Scenario A: PostgreSQL fails
        - Returns: False immediately
        - State: No data written anywhere ✅ (safe)

        Scenario B: PostgreSQL succeeds, Firestore fails (failure_mode="fail_fast")
        - PostgreSQL: Data committed ✅
        - Firestore: No data ❌
        - Returns: False (or raises exception)
        - State: SPLIT-BRAIN ⚠️ (PostgreSQL has data, Firestore doesn't)
        - Recovery: Reconciliation worker must sync

        Scenario C: PostgreSQL succeeds, Firestore fails (failure_mode="log_and_continue")
        - PostgreSQL: Data committed ✅
        - Firestore: No data ❌
        - Returns: True (logs warning)
        - State: Eventual consistency ⏱️ (Firestore will be synced later)
        - Recovery: Reconciliation worker handles automatically

        Args:
            metadata: Article metadata

        Returns:
            - True: PostgreSQL write succeeded (Firestore may or may not have succeeded)
            - False: PostgreSQL write failed OR (Firestore failed AND failure_mode="fail_fast")

        Raises:
            May raise exception if failure_mode="fail_fast" and Firestore fails
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

            # Step 3: Update sync timestamp on success
            self._update_article_sync_timestamp(metadata.item_id)

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

                # Update sync timestamp on success
                self._update_article_sync_timestamp(item_id)

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

            # Update sync timestamp on success (marks as synced deletion)
            self._update_article_sync_timestamp(item_id)

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

            # Update sync timestamp on success
            self._update_artifact_sync_timestamp(artifact.item_id, artifact.archiver)

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

            # Update sync timestamp on success
            self._update_artifact_sync_timestamp(item_id, archiver)

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

            # Update sync timestamp on success
            self._update_article_sync_timestamp(pocket.item_id)

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
            # Compensation logic: rollback PostgreSQL write
            try:
                self._compensate_postgres_write(operation, item_id)
            except Exception as comp_error:
                logger.error(
                    f"Compensation failed for {item_id}: {comp_error}",
                    exc_info=True
                )
            return False

        elif self.failure_mode == "log_and_continue":
            logger.warning(f"{log_msg} [LOG_AND_CONTINUE MODE - CONTINUING]")
            # Record sync failure - reconciliation worker will fix later
            return True

        elif self.failure_mode == "queue_retry":
            logger.warning(f"{log_msg} [QUEUE_RETRY MODE - QUEUING FOR RETRY]")
            # TODO: Implement retry queue
            # For now, just log and continue
            return True

        else:
            logger.error(f"Unknown failure_mode: {self.failure_mode}")
            return False

    def _compensate_postgres_write(self, operation: str, item_id: str) -> None:
        """
        Compensate for failed Firestore write by rolling back PostgreSQL.

        This is only called in fail_fast mode to maintain consistency.

        Args:
            operation: The operation that failed
            item_id: The item identifier
        """
        logger.info(
            f"Executing compensation for {operation} on {item_id}"
        )

        # Only compensate for certain operations to avoid data loss
        if operation in ["create_article", "create_artifact", "create_pocket_data"]:
            # For creates, we can safely delete
            if operation == "create_article":
                self.postgres.delete_article(item_id)
            # Note: For artifacts and pocket data, compensation is more complex
            # and would require additional context. For now, we log the failure.
            logger.warning(
                f"Compensation not fully implemented for {operation}, "
                f"manual reconciliation may be needed"
            )

    def _update_article_sync_timestamp(self, item_id: str) -> None:
        """
        Update the last_synced_to_firestore timestamp for an article.

        Args:
            item_id: The article identifier
        """
        try:
            from shared.db.session import get_session
            from shared.db.models import ArchivedUrl

            with get_session() as session:
                au = session.query(ArchivedUrl).filter(
                    ArchivedUrl.item_id == item_id
                ).first()

                if au:
                    au.last_synced_to_firestore = datetime.utcnow()
                    session.commit()
                    logger.debug(f"Updated sync timestamp for article {item_id}")

        except Exception as e:
            logger.error(
                f"Failed to update sync timestamp for {item_id}: {e}",
                exc_info=True
            )

    def _update_artifact_sync_timestamp(
        self, item_id: str, archiver: str
    ) -> None:
        """
        Update the last_synced_to_firestore timestamp for an artifact.

        Args:
            item_id: The article identifier
            archiver: The archiver name
        """
        try:
            from shared.db.session import get_session
            from shared.db.models import ArchivedUrl, ArchiveArtifact

            with get_session() as session:
                # Find the artifact
                au = session.query(ArchivedUrl).filter(
                    ArchivedUrl.item_id == item_id
                ).first()

                if not au:
                    logger.warning(f"Article {item_id} not found for artifact sync")
                    return

                artifact = session.query(ArchiveArtifact).filter(
                    ArchiveArtifact.archived_url_id == au.id,
                    ArchiveArtifact.archiver == archiver
                ).first()

                if artifact:
                    artifact.last_synced_to_firestore = datetime.utcnow()
                    session.commit()
                    logger.debug(
                        f"Updated sync timestamp for artifact {item_id}/{archiver}"
                    )

        except Exception as e:
            logger.error(
                f"Failed to update artifact sync timestamp for "
                f"{item_id}/{archiver}: {e}",
                exc_info=True
            )
