"""
Tests for dual database reconciliation worker.

Tests the reconciliation Celery task that fixes drift between PostgreSQL
and Firestore.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch

from services.storage_worker.app.tasks import (
    reconcile_dual_database,
    detect_sync_drift,
)


class TestReconciliationWorker:
    """Test reconciliation worker functionality."""

    @patch('services.storage_worker.app.tasks.get_session')
    @patch('services.storage_worker.app.tasks.PostgresStorage')
    @patch('services.storage_worker.app.tasks.FirestoreStorage')
    def test_reconcile_unsynced_articles(
        self, mock_firestore_cls, mock_postgres_cls, mock_get_session
    ):
        """Test reconciliation of articles that have never been synced."""
        # Setup mocks
        mock_postgres = Mock()
        mock_firestore = Mock()
        mock_postgres_cls.return_value = mock_postgres
        mock_firestore_cls.return_value = mock_firestore

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        # Create unsynced article
        mock_article = Mock()
        mock_article.item_id = "test-123"
        mock_article.last_synced_to_firestore = None

        mock_session.query.return_value.filter.return_value.limit.return_value.all.return_value = [
            mock_article
        ]

        # Mock article record from PostgreSQL
        mock_record = Mock()
        mock_record.url = "https://example.com"
        mock_record.item_id = "test-123"
        mock_record.title = "Test Article"
        mock_record.byline = "Test Author"
        mock_record.text_content = "Test content"
        mock_record.word_count = 100
        mock_record.excerpt = "Test excerpt"
        mock_postgres.get_article.return_value = mock_record

        # Firestore write succeeds
        mock_firestore.create_article.return_value = True

        # Run reconciliation
        result = reconcile_dual_database(Mock())

        # Verify results
        assert result["articles_synced"] == 1
        assert result["articles_failed"] == 0
        mock_firestore.create_article.assert_called_once()
        mock_session.commit.assert_called()

    @patch('services.storage_worker.app.tasks.get_session')
    @patch('services.storage_worker.app.tasks.PostgresStorage')
    @patch('services.storage_worker.app.tasks.FirestoreStorage')
    def test_reconcile_handles_firestore_failure(
        self, mock_firestore_cls, mock_postgres_cls, mock_get_session
    ):
        """Test reconciliation handles Firestore failures gracefully."""
        mock_postgres = Mock()
        mock_firestore = Mock()
        mock_postgres_cls.return_value = mock_postgres
        mock_firestore_cls.return_value = mock_firestore

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        mock_article = Mock()
        mock_article.item_id = "test-123"
        mock_article.last_synced_to_firestore = None

        mock_session.query.return_value.filter.return_value.limit.return_value.all.return_value = [
            mock_article
        ]

        mock_record = Mock()
        mock_record.url = "https://example.com"
        mock_record.item_id = "test-123"
        mock_record.title = "Test Article"
        mock_record.byline = "Test Author"
        mock_record.text_content = "Test content"
        mock_record.word_count = 100
        mock_record.excerpt = "Test excerpt"
        mock_postgres.get_article.return_value = mock_record

        # Firestore write fails
        mock_firestore.create_article.return_value = False

        result = reconcile_dual_database(Mock())

        # Should handle failure gracefully
        assert result["articles_synced"] == 0
        assert result["articles_failed"] == 1
        # Timestamp should NOT be updated on failure
        mock_session.commit.assert_not_called()

    @patch('services.storage_worker.app.tasks.get_session')
    @patch('services.storage_worker.app.tasks.PostgresStorage')
    @patch('services.storage_worker.app.tasks.FirestoreStorage')
    def test_reconcile_artifacts(
        self, mock_firestore_cls, mock_postgres_cls, mock_get_session
    ):
        """Test reconciliation of unsynced artifacts."""
        mock_postgres = Mock()
        mock_firestore = Mock()
        mock_postgres_cls.return_value = mock_postgres
        mock_firestore_cls.return_value = mock_firestore

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        # Mock article
        mock_article = Mock()
        mock_article.item_id = "test-123"

        # Mock artifact
        mock_artifact = Mock()
        mock_artifact.archiver = "singlefile"
        mock_artifact.status = "completed"
        mock_artifact.gcs_path = "archives/test-123/singlefile/output.html.gz"
        mock_artifact.gcs_bucket = "test-bucket"
        mock_artifact.size_bytes = 1024
        mock_artifact.created_at = datetime.utcnow()
        mock_artifact.last_synced_to_firestore = None
        mock_artifact.success = True

        # First query returns empty list (no unsynced articles)
        # Second query returns artifacts to sync
        def side_effect(*args, **kwargs):
            if len(side_effect.calls) == 0:
                side_effect.calls.append(1)
                result = Mock()
                result.limit.return_value.all.return_value = []
                return result
            else:
                result = Mock()
                result.limit.return_value.all.return_value = [(mock_artifact, mock_article)]
                return result

        side_effect.calls = []
        mock_session.query.return_value.filter.side_effect = side_effect

        mock_firestore.create_artifact.return_value = True

        result = reconcile_dual_database(Mock())

        assert result["artifacts_synced"] == 1
        assert result["artifacts_failed"] == 0
        mock_firestore.create_artifact.assert_called_once()

    @patch('services.storage_worker.app.tasks.get_session')
    @patch('services.storage_worker.app.tasks.PostgresStorage')
    @patch('services.storage_worker.app.tasks.FirestoreStorage')
    def test_reconcile_batches_records(
        self, mock_firestore_cls, mock_postgres_cls, mock_get_session
    ):
        """Test that reconciliation processes records in batches."""
        mock_postgres = Mock()
        mock_firestore = Mock()
        mock_postgres_cls.return_value = mock_postgres
        mock_firestore_cls.return_value = mock_firestore

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        # Create 50 unsynced articles (max batch size)
        mock_articles = []
        for i in range(50):
            mock_article = Mock()
            mock_article.item_id = f"test-{i}"
            mock_article.last_synced_to_firestore = None
            mock_articles.append(mock_article)

        mock_session.query.return_value.filter.return_value.limit.return_value.all.return_value = (
            mock_articles
        )

        # Mock successful article retrieval and sync
        mock_record = Mock()
        mock_record.url = "https://example.com"
        mock_record.item_id = "test-123"
        mock_record.title = "Test Article"
        mock_record.byline = "Test Author"
        mock_record.text_content = "Test content"
        mock_record.word_count = 100
        mock_record.excerpt = "Test excerpt"
        mock_postgres.get_article.return_value = mock_record
        mock_firestore.create_article.return_value = True

        result = reconcile_dual_database(Mock())

        # Should process all 50 articles
        assert result["articles_synced"] == 50
        assert result["articles_failed"] == 0
        assert mock_firestore.create_article.call_count == 50


class TestSyncDriftDetection:
    """Test sync drift detection monitoring."""

    @patch('services.storage_worker.app.tasks.get_session')
    def test_detect_no_drift(self, mock_get_session):
        """Test drift detection when everything is in sync."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        # All queries return 0 (no drift)
        mock_session.query.return_value.filter.return_value.count.return_value = 0

        result = detect_sync_drift(Mock())

        assert result["total_drift"] == 0
        assert result["drift_detected"] is False
        assert result["never_synced_articles"] == 0
        assert result["stale_articles"] == 0
        assert result["never_synced_artifacts"] == 0
        assert result["stale_artifacts"] == 0

    @patch('services.storage_worker.app.tasks.get_session')
    def test_detect_drift_never_synced(self, mock_get_session):
        """Test drift detection for never-synced records."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        # Simulate drift: 5 never-synced articles, 3 never-synced artifacts
        counts = [5, 0, 3, 0]  # never_synced_articles, stale_articles, never_synced_artifacts, stale_artifacts
        mock_session.query.return_value.filter.return_value.count.side_effect = counts

        result = detect_sync_drift(Mock())

        assert result["total_drift"] == 8
        assert result["drift_detected"] is True
        assert result["never_synced_articles"] == 5
        assert result["never_synced_artifacts"] == 3

    @patch('services.storage_worker.app.tasks.get_session')
    def test_detect_drift_stale_records(self, mock_get_session):
        """Test drift detection for stale records (sync lag > 10 min)."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        # Simulate stale records
        counts = [0, 10, 0, 5]
        mock_session.query.return_value.filter.return_value.count.side_effect = counts

        result = detect_sync_drift(Mock())

        assert result["total_drift"] == 15
        assert result["drift_detected"] is True
        assert result["stale_articles"] == 10
        assert result["stale_artifacts"] == 5

    @patch('services.storage_worker.app.tasks.get_session')
    def test_detect_significant_drift_logged(self, mock_get_session):
        """Test that significant drift triggers warning log."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        # Simulate significant drift (>10 records)
        counts = [20, 5, 10, 3]
        mock_session.query.return_value.filter.return_value.count.side_effect = counts

        with patch('services.storage_worker.app.tasks.logger') as mock_logger:
            result = detect_sync_drift(Mock())

            # Should log warning for significant drift
            assert mock_logger.warning.called
            assert result["total_drift"] == 38

    @patch('services.storage_worker.app.tasks.get_session')
    def test_drift_detection_includes_timestamp(self, mock_get_session):
        """Test that drift detection includes timestamp."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        mock_session.query.return_value.filter.return_value.count.return_value = 0

        result = detect_sync_drift(Mock())

        assert "checked_at" in result
        # Should be a valid ISO format timestamp
        datetime.fromisoformat(result["checked_at"])


class TestReconciliationEdgeCases:
    """Test edge cases in reconciliation logic."""

    @patch('services.storage_worker.app.tasks.get_session')
    @patch('services.storage_worker.app.tasks.PostgresStorage')
    @patch('services.storage_worker.app.tasks.FirestoreStorage')
    def test_reconcile_article_not_in_postgres(
        self, mock_firestore_cls, mock_postgres_cls, mock_get_session
    ):
        """Test reconciliation when article exists in DB but get_article returns None."""
        mock_postgres = Mock()
        mock_firestore = Mock()
        mock_postgres_cls.return_value = mock_postgres
        mock_firestore_cls.return_value = mock_firestore

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        mock_article = Mock()
        mock_article.item_id = "test-123"
        mock_article.last_synced_to_firestore = None

        mock_session.query.return_value.filter.return_value.limit.return_value.all.return_value = [
            mock_article
        ]

        # Article not found in PostgreSQL (data inconsistency)
        mock_postgres.get_article.return_value = None

        result = reconcile_dual_database(Mock())

        # Should skip the article
        assert result["articles_synced"] == 0
        assert result["articles_failed"] == 0
        mock_firestore.create_article.assert_not_called()

    @patch('services.storage_worker.app.tasks.get_session')
    @patch('services.storage_worker.app.tasks.PostgresStorage')
    @patch('services.storage_worker.app.tasks.FirestoreStorage')
    def test_reconcile_handles_exceptions(
        self, mock_firestore_cls, mock_postgres_cls, mock_get_session
    ):
        """Test that reconciliation handles exceptions and continues."""
        mock_postgres = Mock()
        mock_firestore = Mock()
        mock_postgres_cls.return_value = mock_postgres
        mock_firestore_cls.return_value = mock_firestore

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        # Two articles to sync
        mock_article1 = Mock()
        mock_article1.item_id = "test-1"
        mock_article2 = Mock()
        mock_article2.item_id = "test-2"

        mock_session.query.return_value.filter.return_value.limit.return_value.all.return_value = [
            mock_article1, mock_article2
        ]

        mock_record = Mock()
        mock_record.url = "https://example.com"
        mock_record.item_id = "test-1"
        mock_record.title = "Test Article"
        mock_record.byline = "Test Author"
        mock_record.text_content = "Test content"
        mock_record.word_count = 100
        mock_record.excerpt = "Test excerpt"

        # First article throws exception, second succeeds
        mock_postgres.get_article.side_effect = [
            Exception("Database error"),
            mock_record
        ]
        mock_firestore.create_article.return_value = True

        result = reconcile_dual_database(Mock())

        # Should continue after exception
        assert result["articles_synced"] == 1
        assert result["articles_failed"] == 1
