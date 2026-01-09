"""
Tests for dual database storage failure scenarios.

Tests the compensation logic, sync timestamp tracking, and eventual consistency
behavior when Firestore writes fail.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from shared.storage.dual_database_storage import DualDatabaseStorage
from shared.storage.database_storage import (
    ArticleMetadata,
    ArchiveArtifact,
    PocketData,
    ArchiveStatus,
)


class TestDualDatabaseFailureScenarios:
    """Test failure scenarios and compensation logic."""

    @pytest.fixture
    def mock_postgres(self):
        """Mock PostgreSQL storage."""
        mock = Mock()
        mock.create_article = Mock(return_value=True)
        mock.update_article_metadata = Mock(return_value=True)
        mock.delete_article = Mock(return_value=True)
        mock.create_artifact = Mock(return_value=True)
        mock.create_pocket_data = Mock(return_value=True)
        return mock

    @pytest.fixture
    def mock_firestore(self):
        """Mock Firestore storage."""
        mock = Mock()
        mock.create_article = Mock(return_value=True)
        mock.update_article_metadata = Mock(return_value=True)
        mock.delete_article = Mock(return_value=True)
        mock.create_artifact = Mock(return_value=True)
        mock.create_pocket_data = Mock(return_value=True)
        return mock

    @pytest.fixture
    def sample_metadata(self):
        """Sample article metadata."""
        return ArticleMetadata(
            url="https://example.com/article",
            item_id="test-123",
            title="Test Article",
            byline="Test Author",
            text_content="Test content",
            word_count=100,
            excerpt="Test excerpt"
        )

    @pytest.fixture
    def sample_artifact(self):
        """Sample archive artifact."""
        return ArchiveArtifact(
            item_id="test-123",
            archiver="singlefile",
            status=ArchiveStatus.COMPLETED,
            gcs_path="archives/test-123/singlefile/output.html.gz",
            gcs_bucket="test-bucket",
            file_size=1024,
            created_at=datetime.utcnow()
        )

    def test_fail_fast_mode_firestore_down_on_create(
        self, mock_postgres, mock_firestore, sample_metadata
    ):
        """Test fail_fast mode when Firestore is down during create."""
        # Firestore fails
        mock_firestore.create_article = Mock(side_effect=Exception("Firestore unavailable"))

        dual_storage = DualDatabaseStorage(
            postgres=mock_postgres,
            firestore=mock_firestore,
            failure_mode="fail_fast"
        )

        # Should return False due to Firestore failure
        with patch.object(dual_storage, '_update_article_sync_timestamp'):
            result = dual_storage.create_article(sample_metadata)

        assert result is False
        # PostgreSQL should have been called
        mock_postgres.create_article.assert_called_once()
        # Compensation should attempt to delete from PostgreSQL
        mock_postgres.delete_article.assert_called_once_with(sample_metadata.item_id)

    def test_fail_fast_mode_firestore_returns_false(
        self, mock_postgres, mock_firestore, sample_metadata
    ):
        """Test fail_fast mode when Firestore returns False."""
        # Firestore returns False
        mock_firestore.create_article = Mock(return_value=False)

        dual_storage = DualDatabaseStorage(
            postgres=mock_postgres,
            firestore=mock_firestore,
            failure_mode="fail_fast"
        )

        with patch.object(dual_storage, '_update_article_sync_timestamp'):
            result = dual_storage.create_article(sample_metadata)

        assert result is False
        mock_postgres.create_article.assert_called_once()
        # Compensation should attempt rollback
        mock_postgres.delete_article.assert_called_once_with(sample_metadata.item_id)

    def test_log_and_continue_mode_firestore_down(
        self, mock_postgres, mock_firestore, sample_metadata
    ):
        """Test log_and_continue mode when Firestore is down."""
        # Firestore fails
        mock_firestore.create_article = Mock(side_effect=Exception("Firestore unavailable"))

        dual_storage = DualDatabaseStorage(
            postgres=mock_postgres,
            firestore=mock_firestore,
            failure_mode="log_and_continue"
        )

        with patch.object(dual_storage, '_update_article_sync_timestamp'):
            result = dual_storage.create_article(sample_metadata)

        # Should continue despite Firestore failure
        assert result is True
        mock_postgres.create_article.assert_called_once()
        # No compensation in log_and_continue mode
        mock_postgres.delete_article.assert_not_called()

    def test_sync_timestamp_updated_on_success(
        self, mock_postgres, mock_firestore, sample_metadata
    ):
        """Test that sync timestamp is updated after successful Firestore write."""
        dual_storage = DualDatabaseStorage(
            postgres=mock_postgres,
            firestore=mock_firestore,
            failure_mode="fail_fast"
        )

        with patch.object(dual_storage, '_update_article_sync_timestamp') as mock_update:
            result = dual_storage.create_article(sample_metadata)

        assert result is True
        # Timestamp should be updated on success
        mock_update.assert_called_once_with(sample_metadata.item_id)

    def test_sync_timestamp_not_updated_on_failure(
        self, mock_postgres, mock_firestore, sample_metadata
    ):
        """Test that sync timestamp is NOT updated when Firestore fails."""
        # Firestore fails
        mock_firestore.create_article = Mock(side_effect=Exception("Firestore unavailable"))

        dual_storage = DualDatabaseStorage(
            postgres=mock_postgres,
            firestore=mock_firestore,
            failure_mode="log_and_continue"
        )

        with patch.object(dual_storage, '_update_article_sync_timestamp') as mock_update:
            result = dual_storage.create_article(sample_metadata)

        # Timestamp should NOT be updated on failure
        mock_update.assert_not_called()

    def test_artifact_sync_timestamp_updated(
        self, mock_postgres, mock_firestore, sample_artifact
    ):
        """Test that artifact sync timestamp is updated after successful write."""
        dual_storage = DualDatabaseStorage(
            postgres=mock_postgres,
            firestore=mock_firestore,
            failure_mode="fail_fast"
        )

        with patch.object(dual_storage, '_update_artifact_sync_timestamp') as mock_update:
            result = dual_storage.create_artifact(sample_artifact)

        assert result is True
        mock_update.assert_called_once_with(
            sample_artifact.item_id,
            sample_artifact.archiver
        )

    def test_partial_firestore_outage(
        self, mock_postgres, mock_firestore, sample_metadata
    ):
        """Test behavior during partial Firestore outage (intermittent failures)."""
        # Simulate intermittent failures
        call_count = 0

        def intermittent_failure(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise Exception("Timeout")
            return True

        mock_firestore.create_article = Mock(side_effect=intermittent_failure)

        dual_storage = DualDatabaseStorage(
            postgres=mock_postgres,
            firestore=mock_firestore,
            failure_mode="log_and_continue"
        )

        with patch.object(dual_storage, '_update_article_sync_timestamp'):
            # First call should succeed
            result1 = dual_storage.create_article(sample_metadata)
            assert result1 is True

            # Second call should fail but continue
            result2 = dual_storage.create_article(sample_metadata)
            assert result2 is True

    def test_update_article_metadata_failure(
        self, mock_postgres, mock_firestore
    ):
        """Test update_article_metadata failure handling."""
        mock_firestore.update_article_metadata = Mock(
            side_effect=Exception("Firestore write failed")
        )

        dual_storage = DualDatabaseStorage(
            postgres=mock_postgres,
            firestore=mock_firestore,
            failure_mode="log_and_continue"
        )

        with patch.object(dual_storage, '_update_article_sync_timestamp'):
            result = dual_storage.update_article_metadata(
                "test-123",
                {"title": "Updated Title"}
            )

        # Should continue in log_and_continue mode
        assert result is True
        mock_postgres.update_article_metadata.assert_called_once()

    def test_delete_article_firestore_failure(
        self, mock_postgres, mock_firestore
    ):
        """Test delete_article when Firestore fails."""
        mock_firestore.delete_article = Mock(return_value=False)

        dual_storage = DualDatabaseStorage(
            postgres=mock_postgres,
            firestore=mock_firestore,
            failure_mode="log_and_continue"
        )

        with patch.object(dual_storage, '_update_article_sync_timestamp'):
            result = dual_storage.delete_article("test-123")

        assert result is True
        mock_postgres.delete_article.assert_called_once()

    def test_postgres_failure_stops_operation(
        self, mock_postgres, mock_firestore, sample_metadata
    ):
        """Test that PostgreSQL failure stops the operation (source of truth)."""
        # PostgreSQL fails
        mock_postgres.create_article = Mock(return_value=False)

        dual_storage = DualDatabaseStorage(
            postgres=mock_postgres,
            firestore=mock_firestore,
            failure_mode="fail_fast"
        )

        result = dual_storage.create_article(sample_metadata)

        # Operation should fail
        assert result is False
        # Firestore should not be called
        mock_firestore.create_article.assert_not_called()

    def test_compensation_failure_logged(
        self, mock_postgres, mock_firestore, sample_metadata
    ):
        """Test that compensation failures are logged but don't crash."""
        # Firestore fails
        mock_firestore.create_article = Mock(side_effect=Exception("Firestore down"))
        # Compensation also fails
        mock_postgres.delete_article = Mock(side_effect=Exception("Delete failed"))

        dual_storage = DualDatabaseStorage(
            postgres=mock_postgres,
            firestore=mock_firestore,
            failure_mode="fail_fast"
        )

        with patch.object(dual_storage, '_update_article_sync_timestamp'):
            # Should not raise exception despite compensation failure
            result = dual_storage.create_article(sample_metadata)

        assert result is False

    def test_pocket_data_sync_timestamp(
        self, mock_postgres, mock_firestore
    ):
        """Test that pocket data updates article sync timestamp."""
        pocket_data = PocketData(
            item_id="test-123",
            pocket_id="12345",
            given_url="https://example.com",
            resolved_url="https://example.com/article",
            favorite=False,
            status=1,
            time_added=datetime.utcnow(),
            time_updated=datetime.utcnow()
        )

        dual_storage = DualDatabaseStorage(
            postgres=mock_postgres,
            firestore=mock_firestore,
            failure_mode="fail_fast"
        )

        with patch.object(dual_storage, '_update_article_sync_timestamp') as mock_update:
            result = dual_storage.create_pocket_data(pocket_data)

        assert result is True
        # Should update article sync timestamp (not pocket-specific)
        mock_update.assert_called_once_with(pocket_data.item_id)


class TestSyncTimestampMethods:
    """Test sync timestamp update methods."""

    @patch('shared.storage.dual_database_storage.get_session')
    def test_update_article_sync_timestamp_success(self, mock_get_session):
        """Test successful article sync timestamp update."""
        # Mock session and query
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        mock_article = Mock()
        mock_article.last_synced_to_firestore = None
        mock_session.query.return_value.filter.return_value.first.return_value = mock_article

        dual_storage = DualDatabaseStorage(
            postgres=Mock(),
            firestore=Mock(),
            failure_mode="fail_fast"
        )

        # Should not raise exception
        dual_storage._update_article_sync_timestamp("test-123")

        # Timestamp should be set
        assert mock_article.last_synced_to_firestore is not None
        mock_session.commit.assert_called_once()

    @patch('shared.storage.dual_database_storage.get_session')
    def test_update_artifact_sync_timestamp_success(self, mock_get_session):
        """Test successful artifact sync timestamp update."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        mock_article = Mock()
        mock_article.id = 1
        mock_artifact = Mock()
        mock_artifact.last_synced_to_firestore = None

        # Setup query chain
        query_mock = Mock()
        query_mock.filter.return_value.first.side_effect = [mock_article, mock_artifact]
        mock_session.query.return_value = query_mock

        dual_storage = DualDatabaseStorage(
            postgres=Mock(),
            firestore=Mock(),
            failure_mode="fail_fast"
        )

        dual_storage._update_artifact_sync_timestamp("test-123", "singlefile")

        # Timestamp should be set
        assert mock_artifact.last_synced_to_firestore is not None
        mock_session.commit.assert_called_once()

    @patch('shared.storage.dual_database_storage.get_session')
    def test_update_sync_timestamp_article_not_found(self, mock_get_session):
        """Test sync timestamp update when article not found."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = Mock(return_value=False)

        # Article not found
        mock_session.query.return_value.filter.return_value.first.return_value = None

        dual_storage = DualDatabaseStorage(
            postgres=Mock(),
            firestore=Mock(),
            failure_mode="fail_fast"
        )

        # Should not raise exception
        dual_storage._update_article_sync_timestamp("test-123")

        # Commit should not be called
        mock_session.commit.assert_not_called()
