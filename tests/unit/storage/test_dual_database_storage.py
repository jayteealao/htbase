"""
Unit tests for DualDatabaseStorage

Tests dual-write behavior and failure handling.
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime

from storage.dual_database_storage import DualDatabaseStorage
from storage.database_storage import (
    ArticleMetadata,
    ArchiveArtifact,
    PocketData,
    ArchiveStatus,
)


@pytest.fixture
def mock_postgres():
    """Mock PostgreSQL storage."""
    postgres = Mock()
    postgres.provider_name = "postgres"
    postgres.supports_transactions = True
    postgres.supports_full_text_search = True
    return postgres


@pytest.fixture
def mock_firestore():
    """Mock Firestore storage."""
    firestore = Mock()
    firestore.provider_name = "firestore"
    firestore.supports_transactions = True
    firestore.supports_full_text_search = False
    return firestore


@pytest.fixture
def dual_storage_fail_fast(mock_postgres, mock_firestore):
    """DualDatabaseStorage in fail_fast mode."""
    return DualDatabaseStorage(
        postgres=mock_postgres,
        firestore=mock_firestore,
        failure_mode="fail_fast"
    )


@pytest.fixture
def dual_storage_log_continue(mock_postgres, mock_firestore):
    """DualDatabaseStorage in log_and_continue mode."""
    return DualDatabaseStorage(
        postgres=mock_postgres,
        firestore=mock_firestore,
        failure_mode="log_and_continue"
    )


class TestDualDatabaseStorageCreation:
    """Test dual database storage creation and initialization."""

    def test_initialization(self, mock_postgres, mock_firestore):
        """Test DualDatabaseStorage initializes correctly."""
        dual = DualDatabaseStorage(
            postgres=mock_postgres,
            firestore=mock_firestore,
            failure_mode="fail_fast"
        )

        assert dual.postgres == mock_postgres
        assert dual.firestore == mock_firestore
        assert dual.failure_mode == "fail_fast"
        assert dual.provider_name == "dual"
        assert dual.supports_transactions == True
        assert dual.supports_full_text_search == True


class TestArticleOperations:
    """Test article creation and retrieval."""

    def test_create_article_both_succeed(self, dual_storage_fail_fast, mock_postgres, mock_firestore):
        """Test happy path - both databases succeed."""
        # Setup
        metadata = ArticleMetadata(
            item_id="test123",
            url="https://example.com",
            title="Test Article"
        )
        mock_postgres.create_article.return_value = True
        mock_firestore.create_article.return_value = True

        # Execute
        result = dual_storage_fail_fast.create_article(metadata)

        # Assert
        assert result == True
        assert mock_postgres.create_article.called
        assert mock_firestore.create_article.called

    def test_create_article_postgres_fails(self, dual_storage_fail_fast, mock_postgres, mock_firestore):
        """Test PostgreSQL failure - entire operation fails."""
        # Setup
        metadata = ArticleMetadata(item_id="test123", url="https://example.com")
        mock_postgres.create_article.return_value = False

        # Execute
        result = dual_storage_fail_fast.create_article(metadata)

        # Assert
        assert result == False
        assert mock_postgres.create_article.called
        assert not mock_firestore.create_article.called  # Never tried

    def test_create_article_firestore_fails_fail_fast(self, dual_storage_fail_fast, mock_postgres, mock_firestore):
        """Test Firestore failure with fail_fast mode - entire operation fails."""
        # Setup
        metadata = ArticleMetadata(item_id="test123", url="https://example.com")
        mock_postgres.create_article.return_value = True
        mock_firestore.create_article.return_value = False

        # Execute
        result = dual_storage_fail_fast.create_article(metadata)

        # Assert
        assert result == False  # fail_fast mode
        assert mock_postgres.create_article.called
        assert mock_firestore.create_article.called

    def test_create_article_firestore_fails_log_continue(self, dual_storage_log_continue, mock_postgres, mock_firestore):
        """Test Firestore failure with log_and_continue mode - operation succeeds."""
        # Setup
        metadata = ArticleMetadata(item_id="test123", url="https://example.com")
        mock_postgres.create_article.return_value = True
        mock_firestore.create_article.side_effect = Exception("Firestore down")

        # Execute
        result = dual_storage_log_continue.create_article(metadata)

        # Assert
        assert result == True  # PostgreSQL succeeded, continue
        assert mock_postgres.create_article.called
        assert mock_firestore.create_article.called

    def test_get_article_from_postgres(self, dual_storage_fail_fast, mock_postgres):
        """Test article retrieval uses PostgreSQL (source of truth)."""
        # Setup
        expected_article = Mock()
        mock_postgres.get_article.return_value = expected_article

        # Execute
        result = dual_storage_fail_fast.get_article("test123")

        # Assert
        assert result == expected_article
        assert mock_postgres.get_article.called_with("test123")


class TestArtifactOperations:
    """Test archive artifact operations."""

    def test_create_artifact_both_succeed(self, dual_storage_fail_fast, mock_postgres, mock_firestore):
        """Test artifact creation in both databases."""
        # Setup
        artifact = ArchiveArtifact(
            item_id="test123",
            archiver="monolith",
            status=ArchiveStatus.SUCCESS,
            gcs_path="gs://bucket/path"
        )
        mock_postgres.create_artifact.return_value = True
        mock_firestore.create_artifact.return_value = True

        # Execute
        result = dual_storage_fail_fast.create_artifact(artifact)

        # Assert
        assert result == True
        assert mock_postgres.create_artifact.called
        assert mock_firestore.create_artifact.called

    def test_update_artifact_status_both_succeed(self, dual_storage_fail_fast, mock_postgres, mock_firestore):
        """Test artifact status update in both databases."""
        # Setup
        mock_postgres.update_artifact_status.return_value = True
        mock_firestore.update_artifact_status.return_value = True

        # Execute
        result = dual_storage_fail_fast.update_artifact_status(
            item_id="test123",
            archiver="pdf",
            status=ArchiveStatus.SUCCESS,
            gcs_path="gs://bucket/test123/pdf/output.pdf.gz",
            file_size=12345
        )

        # Assert
        assert result == True
        assert mock_postgres.update_artifact_status.called
        assert mock_firestore.update_artifact_status.called

    def test_get_artifacts_from_postgres(self, dual_storage_fail_fast, mock_postgres):
        """Test artifact retrieval uses PostgreSQL."""
        # Setup
        expected_artifacts = [Mock(), Mock()]
        mock_postgres.get_artifacts.return_value = expected_artifacts

        # Execute
        result = dual_storage_fail_fast.get_artifacts("test123")

        # Assert
        assert result == expected_artifacts
        assert mock_postgres.get_artifacts.called_with("test123")


class TestPocketDataOperations:
    """Test Pocket data sync."""

    def test_create_pocket_data_both_succeed(self, dual_storage_fail_fast, mock_postgres, mock_firestore):
        """Test Pocket data creation in both databases."""
        # Setup
        pocket = PocketData(
            item_id="test123",
            resolved_id="456",
            favorite=True
        )
        mock_postgres.create_pocket_data.return_value = True
        mock_firestore.create_pocket_data.return_value = True

        # Execute
        result = dual_storage_fail_fast.create_pocket_data(pocket)

        # Assert
        assert result == True
        assert mock_postgres.create_pocket_data.called
        assert mock_firestore.create_pocket_data.called


class TestAIContentOperationsPostgresOnly:
    """Test that AI-generated content stays PostgreSQL-only."""

    def test_create_summary_postgres_only(self, dual_storage_fail_fast, mock_postgres, mock_firestore):
        """Test summaries are NOT synced to Firestore."""
        # Setup
        from storage.database_storage import ArticleSummary
        summary = ArticleSummary(
            item_id="test123",
            summary="This is a summary"
        )
        mock_postgres.create_summary.return_value = True

        # Execute
        result = dual_storage_fail_fast.create_summary(summary)

        # Assert
        assert result == True
        assert mock_postgres.create_summary.called
        assert not mock_firestore.create_summary.called  # NOT synced to Firestore

    def test_create_entities_postgres_only(self, dual_storage_fail_fast, mock_postgres, mock_firestore):
        """Test entities are NOT synced to Firestore."""
        # Setup
        from storage.database_storage import ArticleEntity
        entities = [
            ArticleEntity(item_id="test123", entity_type="PERSON", entity_value="John Doe")
        ]
        mock_postgres.create_entities.return_value = True

        # Execute
        result = dual_storage_fail_fast.create_entities(entities)

        # Assert
        assert result == True
        assert mock_postgres.create_entities.called
        assert not mock_firestore.create_entities.called  # NOT synced to Firestore

    def test_create_tags_postgres_only(self, dual_storage_fail_fast, mock_postgres, mock_firestore):
        """Test tags are NOT synced to Firestore."""
        # Setup
        from storage.database_storage import ArticleTag
        tags = [ArticleTag(item_id="test123", tag="technology")]
        mock_postgres.create_tags.return_value = True

        # Execute
        result = dual_storage_fail_fast.create_tags(tags)

        # Assert
        assert result == True
        assert mock_postgres.create_tags.called
        assert not mock_firestore.create_tags.called  # NOT synced to Firestore


class TestBatchOperations:
    """Test batch operations."""

    def test_batch_create_articles(self, dual_storage_fail_fast, mock_postgres, mock_firestore):
        """Test batch article creation."""
        # Setup
        articles = [
            ArticleMetadata(item_id="test1", url="https://example.com/1"),
            ArticleMetadata(item_id="test2", url="https://example.com/2"),
        ]
        mock_postgres.batch_create_articles.return_value = 2
        mock_firestore.batch_create_articles.return_value = 2

        # Execute
        result = dual_storage_fail_fast.batch_create_articles(articles)

        # Assert
        assert result == 2
        assert mock_postgres.batch_create_articles.called
        assert mock_firestore.batch_create_articles.called


class TestQueryOperations:
    """Test query operations use PostgreSQL."""

    def test_count_articles_from_postgres(self, dual_storage_fail_fast, mock_postgres):
        """Test article counting uses PostgreSQL."""
        # Setup
        mock_postgres.count_articles.return_value = 42

        # Execute
        result = dual_storage_fail_fast.count_articles()

        # Assert
        assert result == 42
        assert mock_postgres.count_articles.called

    def test_search_articles_from_postgres(self, dual_storage_fail_fast, mock_postgres):
        """Test full-text search uses PostgreSQL."""
        # Setup
        expected_results = [Mock(), Mock()]
        mock_postgres.search_articles.return_value = expected_results

        # Execute
        result = dual_storage_fail_fast.search_articles("test query")

        # Assert
        assert result == expected_results
        assert mock_postgres.search_articles.called_with("test query")


class TestFailureModes:
    """Test different failure handling modes."""

    def test_fail_fast_mode_on_firestore_exception(self, dual_storage_fail_fast, mock_postgres, mock_firestore):
        """Test fail_fast mode fails on Firestore exception."""
        # Setup
        metadata = ArticleMetadata(item_id="test123", url="https://example.com")
        mock_postgres.create_article.return_value = True
        mock_firestore.create_article.side_effect = Exception("Connection timeout")

        # Execute
        result = dual_storage_fail_fast.create_article(metadata)

        # Assert
        assert result == False  # Operation failed in fail_fast mode

    def test_log_and_continue_mode_on_firestore_exception(self, dual_storage_log_continue, mock_postgres, mock_firestore):
        """Test log_and_continue mode continues on Firestore exception."""
        # Setup
        metadata = ArticleMetadata(item_id="test123", url="https://example.com")
        mock_postgres.create_article.return_value = True
        mock_firestore.create_article.side_effect = Exception("Connection timeout")

        # Execute
        result = dual_storage_log_continue.create_article(metadata)

        # Assert
        assert result == True  # Operation succeeded (PostgreSQL committed)
