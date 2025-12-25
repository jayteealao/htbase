"""
Tests for PostgresStorage.

Tests PostgreSQL storage implementation using mocks to avoid actual database calls.
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import pytest

from app.storage.postgres_storage import PostgresStorage
from app.storage.database_storage import (
    ArticleMetadata,
    ArchiveArtifact,
    ArticleSummary,
    ArticleEntity,
    ArticleTag,
    ArchiveStatus
)


class TestPostgresStorage:
    """Test PostgresStorage implementation."""

    def test_provider_name(self):
        """Test provider name is correct."""
        with patch('storage.postgres_storage.get_session'):
            storage = PostgresStorage()
            assert storage.provider_name == "postgres"

    def test_supports_transactions(self):
        """Test transaction support flag."""
        with patch('storage.postgres_storage.get_session'):
            storage = PostgresStorage()
            assert storage.supports_transactions is True

    def test_supports_full_text_search(self):
        """Test full-text search support flag."""
        with patch('storage.postgres_storage.get_session'):
            storage = PostgresStorage()
            assert storage.supports_full_text_search is True

    # ==================== Initialization Tests ====================

    def test_initialization_with_db_path(self):
        """Test initialization with database path."""
        with patch('storage.postgres_storage.get_session'):
            db_path = Path("/tmp/test.db")
            storage = PostgresStorage(db_path)

            assert storage.db_path == db_path
            assert storage.url_repo is not None
            assert storage.artifact_repo is not None

    def test_initialization_without_db_path(self):
        """Test initialization without database path."""
        with patch('storage.postgres_storage.get_session'):
            storage = PostgresStorage()

            assert storage.db_path is None
            assert storage.url_repo is not None

    # ==================== Article Operations Tests ====================

    def test_create_article_success(self):
        """Test successful article creation."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            # Mock database session
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock database objects
            mock_au = Mock()
            mock_au.id = 1
            session.execute.return_value.scalars.return_value.first.return_value = None

            storage = PostgresStorage()

            metadata = ArticleMetadata(
                item_id="test123",
                url="https://example.com",
                title="Test Article",
                byline="Test Author",
                text_content="Test content",
                word_count=100
            )

            result = storage.create_article(metadata)

            assert result is True
            session.add.assert_called()
            session.commit.assert_called()

    def test_create_article_minimal_metadata(self):
        """Test article creation with minimal metadata."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            mock_au = Mock()
            mock_au.id = 1
            session.execute.return_value.scalars.return_value.first.return_value = None

            storage = PostgresStorage()

            metadata = ArticleMetadata(
                item_id="test123",
                url="https://example.com"
            )

            result = storage.create_article(metadata)

            assert result is True
            # Should not create UrlMetadata if no metadata fields
            assert session.add.call_count == 1  # Only ArchivedUrl

    def test_create_article_failure(self):
        """Test article creation with database error."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            session.commit.side_effect = Exception("Database error")
            mock_session.return_value.__enter__.return_value = session

            storage = PostgresStorage()

            metadata = ArticleMetadata(
                item_id="test123",
                url="https://example.com"
            )

            result = storage.create_article(metadata)

            assert result is False

    def test_get_article_success(self):
        """Test successful article retrieval."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock ArchivedUrl
            mock_au = Mock()
            mock_au.id = 1
            mock_au.item_id = "test123"
            mock_au.url = "https://example.com"
            mock_au.created_at = datetime.utcnow()

            # Mock UrlMetadata
            mock_um = Mock()
            mock_um.title = "Test Article"
            mock_um.byline = "Test Author"
            mock_um.text = "Test content"
            mock_um.word_count = 100

            # Mock ArchiveArtifact
            mock_art = Mock()
            mock_art.archiver = "monolith"
            mock_art.success = True
            mock_art.status = "success"
            mock_art.saved_path = "/path/to/file"
            mock_art.size_bytes = 1024
            mock_art.exit_code = 0
            mock_art.created_at = datetime.utcnow()
            mock_art.updated_at = datetime.utcnow()

            # Configure query results
            session.execute.side_effect = [
                # First call: get ArchivedUrl
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_au)))),
                # Second call: get UrlMetadata
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_um)))),
                # Third call: get ArchiveArtifacts
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_art])))),
                # Fourth call: get summary
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),
                # Fifth call: get entities
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
                # Sixth call: get tags
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
            ]

            storage = PostgresStorage()

            article = storage.get_article("test123")

            assert article is not None
            assert article.metadata.item_id == "test123"
            assert article.metadata.url == "https://example.com"
            assert article.metadata.title == "Test Article"
            assert len(article.archives) == 1
            assert article.archives[0].archiver == "monolith"

    def test_get_article_not_found(self):
        """Test article retrieval for non-existent article."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock no ArchivedUrl found
            session.execute.return_value.scalars.return_value.first.return_value = None

            storage = PostgresStorage()

            article = storage.get_article("nonexistent")

            assert article is None

    def test_get_article_by_url_success(self):
        """Test successful article retrieval by URL."""
        with patch('storage.postgres_storage.get_session') as mock_session, \
             patch('storage.postgres_storage.ArchivedUrlRepository') as mock_repo:

            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock repository returning ArchivedUrl
            mock_au = Mock()
            mock_au.id = 1
            mock_au.item_id = "test123"
            mock_au.url = "https://example.com"
            mock_au.created_at = datetime.utcnow()

            mock_repo.return_value.get_by_url.return_value = mock_au

            # Mock merge to return the same object
            session.merge.return_value = mock_au

            # Mock other queries to return minimal data
            session.execute.side_effect = [
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),  # UrlMetadata
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),    # Artifacts
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),  # Summary
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),    # Entities
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))     # Tags
            ]

            storage = PostgresStorage()

            article = storage.get_article_by_url("https://example.com")

            assert article is not None
            assert article.metadata.url == "https://example.com"
            mock_repo.return_value.get_by_url.assert_called_once_with("https://example.com")

    def test_update_article_metadata_success(self):
        """Test successful article metadata update."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock existing ArchivedUrl and UrlMetadata
            mock_au = Mock()
            mock_au.id = 1
            mock_um = Mock()

            session.execute.side_effect = [
                # First call: get ArchivedUrl
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_au)))),
                # Second call: get UrlMetadata
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_um))))
            ]

            storage = PostgresStorage()

            metadata = {
                "title": "Updated Title",
                "word_count": 200
            }

            result = storage.update_article_metadata("test123", metadata)

            assert result is True
            assert mock_um.title == "Updated Title"
            assert mock_um.word_count == 200
            session.commit.assert_called()

    def test_update_article_metadata_creates_metadata(self):
        """Test updating article metadata creates UrlMetadata if missing."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock existing ArchivedUrl but no UrlMetadata
            mock_au = Mock()
            mock_au.id = 1

            session.execute.side_effect = [
                # First call: get ArchivedUrl
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_au)))),
                # Second call: get UrlMetadata (not found)
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
            ]

            storage = PostgresStorage()

            metadata = {
                "title": "New Title"
            }

            result = storage.update_article_metadata("test123", metadata)

            assert result is True
            # Should have created new UrlMetadata
            assert session.add.call_count >= 1

    def test_delete_article_success(self):
        """Test successful article deletion."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock existing ArchivedUrl
            mock_au = Mock()
            session.execute.return_value.scalars.return_value.first.return_value = mock_au

            storage = PostgresStorage()

            result = storage.delete_article("test123")

            assert result is True
            session.delete.assert_called_once_with(mock_au)
            session.commit.assert_called_once()

    def test_delete_article_not_found(self):
        """Test deleting non-existent article."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock no ArchivedUrl found
            session.execute.return_value.scalars.return_value.first.return_value = None

            storage = PostgresStorage()

            result = storage.delete_article("nonexistent")

            assert result is False

    # ==================== Archive Artifact Tests ====================

    def test_create_artifact_success(self):
        """Test successful artifact creation."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock ArchivedUrl exists
            mock_au = Mock()
            mock_au.id = 1

            # Mock no existing artifact
            session.execute.side_effect = [
                # First call: get ArchivedUrl
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_au)))),
                # Second call: get existing artifact (none)
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
            ]

            storage = PostgresStorage()

            artifact = ArchiveArtifact(
                item_id="test123",
                archiver="monolith",
                status=ArchiveStatus.SUCCESS,
                local_path="/path/to/file.html",
                file_size=1024,
                exit_code=0
            )

            result = storage.create_artifact(artifact)

            assert result is True
            # Should have created new artifact
            assert session.add.call_count >= 1

    def test_create_artifact_creates_archived_url(self):
        """Test artifact creation creates ArchivedUrl if missing."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock no ArchivedUrl exists
            session.execute.return_value.scalars.return_value.first.return_value = None

            storage = PostgresStorage()

            artifact = ArchiveArtifact(
                item_id="test123",
                archiver="monolith",
                status=ArchiveStatus.SUCCESS
            )

            result = storage.create_artifact(artifact)

            assert result is True
            # Should have created ArchivedUrl
            assert session.add.call_count >= 2  # ArchivedUrl + ArchiveArtifact

    def test_get_artifact_success(self):
        """Test successful artifact retrieval."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock ArchivedUrl
            mock_au = Mock()
            mock_au.id = 1

            # Mock existing artifact
            mock_art = Mock()
            mock_art.archiver = "monolith"
            mock_art.success = True
            mock_art.status = "success"
            mock_art.saved_path = "/path/to/file"
            mock_art.size_bytes = 1024
            mock_art.exit_code = 0
            mock_art.created_at = datetime.utcnow()
            mock_art.updated_at = datetime.utcnow()

            session.execute.side_effect = [
                # First call: get ArchivedUrl
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_au)))),
                # Second call: get artifact
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_art))))
            ]

            storage = PostgresStorage()

            artifact = storage.get_artifact("test123", "monolith")

            assert artifact is not None
            assert artifact.item_id == "test123"
            assert artifact.archiver == "monolith"
            assert artifact.status == ArchiveStatus.SUCCESS
            assert artifact.local_path == "/path/to/file"

    def test_get_artifact_not_found(self):
        """Test artifact retrieval for non-existent artifact."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock ArchivedUrl exists but no artifact
            mock_au = Mock()
            mock_au.id = 1

            session.execute.side_effect = [
                # First call: get ArchivedUrl
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_au)))),
                # Second call: get artifact (none)
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
            ]

            storage = PostgresStorage()

            artifact = storage.get_artifact("test123", "monolith")

            assert artifact is None

    def test_update_artifact_status_success(self):
        """Test successful artifact status update."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock ArchivedUrl and existing artifact
            mock_au = Mock()
            mock_au.id = 1
            mock_art = Mock()

            session.execute.side_effect = [
                # First call: get ArchivedUrl
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_au)))),
                # Second call: get artifact
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_art))))
            ]

            storage = PostgresStorage()

            result = storage.update_artifact_status(
                "test123",
                "monolith",
                ArchiveStatus.SUCCESS,
                file_size=2048,
                exit_code=0
            )

            assert result is True
            assert mock_art.status == "success"
            assert mock_art.success is True
            assert mock_art.size_bytes == 2048
            assert mock_art.exit_code == 0
            session.commit.assert_called()

    # ==================== Summary Tests ====================

    def test_create_summary_success(self):
        """Test successful summary creation."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock ArchivedUrl exists, no existing summary
            mock_au = Mock()
            mock_au.id = 1

            session.execute.side_effect = [
                # First call: get ArchivedUrl
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_au)))),
                # Second call: get existing summary (none)
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
            ]

            storage = PostgresStorage()

            summary = ArticleSummary(
                item_id="test123",
                summary="This is a test summary"
            )

            result = storage.create_summary(summary)

            assert result is True
            # Should have created new summary
            assert session.add.call_count >= 1

    def test_create_summary_updates_existing(self):
        """Test summary creation updates existing summary."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock ArchivedUrl and existing summary
            mock_au = Mock()
            mock_au.id = 1
            mock_summ = Mock()

            session.execute.side_effect = [
                # First call: get ArchivedUrl
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_au)))),
                # Second call: get existing summary
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_summ))))
            ]

            storage = PostgresStorage()

            summary = ArticleSummary(
                item_id="test123",
                summary="Updated summary"
            )

            result = storage.create_summary(summary)

            assert result is True
            assert mock_summ.summary_text == "Updated summary"
            assert mock_summ.updated_at is not None

    def test_get_summary_success(self):
        """Test successful summary retrieval."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock ArchivedUrl and summary
            mock_au = Mock()
            mock_au.id = 1
            mock_summ = Mock()
            mock_summ.summary_text = "Test summary"
            mock_summ.created_at = datetime.utcnow()

            session.execute.side_effect = [
                # First call: get ArchivedUrl
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_au)))),
                # Second call: get summary
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_summ))))
            ]

            storage = PostgresStorage()

            summary = storage.get_summary("test123")

            assert summary is not None
            assert summary.item_id == "test123"
            assert summary.summary == "Test summary"

    def test_get_summary_not_found(self):
        """Test summary retrieval for non-existent summary."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock ArchivedUrl exists but no summary
            mock_au = Mock()
            mock_au.id = 1

            session.execute.side_effect = [
                # First call: get ArchivedUrl
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_au)))),
                # Second call: get summary (none)
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
            ]

            storage = PostgresStorage()

            summary = storage.get_summary("test123")

            assert summary is None

    # ==================== Entity Tests ====================

    def test_create_entities_success(self):
        """Test successful entity creation."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock ArchivedUrl exists, no existing entities
            mock_au = Mock()
            mock_au.id = 1

            session.execute.side_effect = [
                # First call: get ArchivedUrl
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_au)))),
                # Second call: check existing entity (none)
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
            ]

            storage = PostgresStorage()

            entities = [
                ArticleEntity(
                    item_id="test123",
                    entity_type="PERSON",
                    entity_value="John Doe",
                    confidence=0.9
                )
            ]

            result = storage.create_entities(entities)

            assert result is True
            # Should have created new entity
            assert session.add.call_count >= 1

    def test_get_entities_success(self):
        """Test successful entity retrieval."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock ArchivedUrl and entities
            mock_au = Mock()
            mock_au.id = 1
            mock_ent = Mock()
            mock_ent.entity_type = "PERSON"
            mock_ent.entity = "John Doe"
            mock_ent.confidence = 0.9

            session.execute.side_effect = [
                # First call: get ArchivedUrl
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_au)))),
                # Second call: get entities
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_ent]))))
            ]

            storage = PostgresStorage()

            entities = storage.get_entities("test123")

            assert len(entities) == 1
            assert entities[0].item_id == "test123"
            assert entities[0].entity_type == "PERSON"
            assert entities[0].entity_value == "John Doe"
            assert entities[0].confidence == 0.9

    # ==================== Tag Tests ====================

    def test_create_tags_success(self):
        """Test successful tag creation."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock ArchivedUrl exists, no existing tags
            mock_au = Mock()
            mock_au.id = 1

            session.execute.side_effect = [
                # First call: get ArchivedUrl
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_au)))),
                # Second call: check existing tag (none)
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))
            ]

            storage = PostgresStorage()

            tags = [
                ArticleTag(
                    item_id="test123",
                    tag="technology",
                    confidence=0.8
                )
            ]

            result = storage.create_tags(tags)

            assert result is True
            # Should have created new tag
            assert session.add.call_count >= 1

    def test_get_tags_success(self):
        """Test successful tag retrieval."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock ArchivedUrl and tags
            mock_au = Mock()
            mock_au.id = 1
            mock_tag = Mock()
            mock_tag.tag = "technology"
            mock_tag.confidence = 0.8

            session.execute.side_effect = [
                # First call: get ArchivedUrl
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_au)))),
                # Second call: get tags
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_tag]))))
            ]

            storage = PostgresStorage()

            tags = storage.get_tags("test123")

            assert len(tags) == 1
            assert tags[0].item_id == "test123"
            assert tags[0].tag == "technology"
            assert tags[0].confidence == 0.8

    # ==================== Pocket Data Tests ====================

    def test_create_pocket_data_noop(self):
        """Test Pocket data creation is a no-op (not implemented)."""
        with patch('storage.postgres_storage.get_session'):
            storage = PostgresStorage()

            pocket_data = Mock()  # PocketData doesn't exist yet, use Mock
            result = storage.create_pocket_data(pocket_data)

            assert result is True

    def test_get_pocket_data_none(self):
        """Test Pocket data retrieval returns None (not implemented)."""
        with patch('storage.postgres_storage.get_session'):
            storage = PostgresStorage()

            result = storage.get_pocket_data("test123")

            assert result is None

    # ==================== Query Operations Tests ====================

    def test_count_articles_success(self):
        """Test successful article count."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock count query
            session.execute.return_value.scalar.return_value = 42

            storage = PostgresStorage()

            count = storage.count_articles()

            assert count == 42

    def test_count_articles_error(self):
        """Test article count with database error."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            session.execute.side_effect = Exception("Database error")
            mock_session.return_value.__enter__.return_value = session

            storage = PostgresStorage()

            count = storage.count_articles()

            assert count == 0

    def test_search_articles_success(self):
        """Test successful article search."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock search results
            mock_au = Mock()
            mock_au.id = 1
            mock_au.item_id = "test123"
            mock_au.url = "https://example.com"
            mock_au.created_at = datetime.utcnow()

            session.execute.return_value.scalars.return_value.all.return_value = [mock_au]

            # Mock minimal metadata for article building
            session.execute.side_effect = [
                # First call: search query
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_au])))),
                # Second call: get metadata (none)
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),
                # Third call: get artifacts (none)
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
                # Fourth call: get summary (none)
                MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))),
                # Fifth call: get entities (none)
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
                # Sixth call: get tags (none)
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
            ]

            storage = PostgresStorage()

            articles = storage.search_articles("test query")

            assert len(articles) == 1
            assert articles[0].metadata.item_id == "test123"

    # ==================== Batch Operations Tests ====================

    def test_batch_create_articles_success(self):
        """Test successful batch article creation."""
        with patch('storage.postgres_storage.get_session') as mock_session:
            session = MagicMock()
            mock_session.return_value.__enter__.return_value = session

            # Mock database objects
            mock_au = Mock()
            mock_au.id = 1
            session.execute.return_value.scalars.return_value.first.return_value = None

            storage = PostgresStorage()

            articles = [
                ArticleMetadata(
                    item_id="test1",
                    url="https://example1.com"
                ),
                ArticleMetadata(
                    item_id="test2",
                    url="https://example2.com"
                )
            ]

            count = storage.batch_create_articles(articles)

            assert count == 2

    # ==================== Helper Method Tests ====================

    def test_db_artifact_to_artifact_with_gcs_path(self):
        """Test conversion of DB artifact with GCS path."""
        with patch('storage.postgres_storage.get_session'):
            storage = PostgresStorage()

            # Mock DB artifact with GCS path stored as gs:// URL
            mock_art = Mock()
            mock_art.archiver = "monolith"
            mock_art.success = True
            mock_art.status = "success"
            mock_art.saved_path = "gs://test-bucket/archives/test.html"
            mock_art.size_bytes = 1024
            mock_art.exit_code = 0
            mock_art.created_at = datetime.utcnow()
            mock_art.updated_at = datetime.utcnow()

            artifact = storage._db_artifact_to_artifact(mock_art, "test123")

            assert artifact.item_id == "test123"
            assert artifact.archiver == "monolith"
            assert artifact.gcs_bucket == "test-bucket"
            assert artifact.gcs_path == "archives/test.html"
            assert artifact.local_path is None

    def test_db_artifact_to_artifact_with_local_path(self):
        """Test conversion of DB artifact with local path."""
        with patch('storage.postgres_storage.get_session'):
            storage = PostgresStorage()

            # Mock DB artifact with local path
            mock_art = Mock()
            mock_art.archiver = "monolith"
            mock_art.success = True
            mock_art.status = "success"
            mock_art.saved_path = "/path/to/file.html"
            mock_art.size_bytes = 1024
            mock_art.exit_code = 0
            mock_art.created_at = datetime.utcnow()
            mock_art.updated_at = datetime.utcnow()

            artifact = storage._db_artifact_to_artifact(mock_art, "test123")

            assert artifact.item_id == "test123"
            assert artifact.archiver == "monolith"
            assert artifact.local_path == "/path/to/file.html"
            assert artifact.gcs_bucket is None
            assert artifact.gcs_path is None