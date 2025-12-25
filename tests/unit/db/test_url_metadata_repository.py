"""
Tests for the UrlMetadataRepository.

Tests the URL metadata database operations including CRUD operations for readability
metadata, article content, and author information.
"""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from app.db.models import UrlMetadata
from app.db.repositories import UrlMetadataRepository


class TestUrlMetadataRepository:
    """Test the UrlMetadataRepository class."""

    @pytest.fixture
    def mock_db_path(self):
        """Mock database path."""
        return Path("/tmp/test.db")

    @pytest.fixture
    def repository(self, mock_db_path):
        """Create UrlMetadataRepository instance for testing."""
        return UrlMetadataRepository(mock_db_path)

    def test_model_class_property(self, repository):
        """Test model_class property."""
        assert repository.model_class == UrlMetadata

    def test_get_by_archived_url_found(self, repository):
        """Test get_by_archived_url returns metadata when found."""
        mock_metadata = Mock(spec=UrlMetadata)
        mock_metadata.id = 1
        mock_metadata.archived_url_id = 123
        mock_metadata.title = "Test Article"

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = mock_metadata
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.get_by_archived_url(123)

            assert result == mock_metadata
            mock_session.execute.assert_called_once()

    def test_get_by_archived_url_not_found(self, repository):
        """Test get_by_archived_url returns None when not found."""
        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = None
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.get_by_archived_url(123)

            assert result is None

    def test_upsert_new_metadata(self, repository):
        """Test upsert creates new metadata when none exists."""
        data = {
            "title": "Test Article",
            "author": "John Doe",
            "byline": "By John Doe",
            "excerpt": "Test excerpt",
            "text": "Full article text content",
            "site_name": "Example Site",
            "word_count": 500,
            "length": 2000,
            "published_date": "2023-01-01",
            "url": "https://example.com/article"
        }

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = None
            mock_save = Mock(spec=UrlMetadata)
            mock_save.id = 1
            mock_session.merge.return_value = mock_save
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.upsert(save_rowid=123, data=data)

            assert result == mock_save
            mock_session.merge.assert_called_once()
            mock_session.flush.assert_called_once()

            # Check that merge was called with UrlMetadata instance
            merge_call_args = mock_session.merge.call_args[0][0]
            assert isinstance(merge_call_args, UrlMetadata)
            assert merge_call_args.save_rowid == 123
            assert merge_call_args.title == "Test Article"
            assert merge_call_args.author == "John Doe"

    def test_upsert_existing_metadata(self, repository):
        """Test upsert updates existing metadata."""
        existing_metadata = Mock(spec=UrlMetadata)
        existing_metadata.id = 1
        existing_metadata.save_rowid = 123

        data = {
            "title": "Updated Article Title",
            "author": "Jane Smith",
            "word_count": 600
        }

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = existing_metadata
            mock_session.merge.return_value = existing_metadata
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.upsert(save_rowid=123, data=data)

            assert result == existing_metadata
            mock_session.merge.assert_called_once_with(existing_metadata)
            mock_session.flush.assert_called_once()

            # Check that existing metadata was updated
            assert existing_metadata.title == "Updated Article Title"
            assert existing_metadata.author == "Jane Smith"
            assert existing_metadata.word_count == 600

    def test_upsert_partial_data(self, repository):
        """Test upsert with partial metadata data."""
        existing_metadata = Mock(spec=UrlMetadata)
        existing_metadata.id = 1
        existing_metadata.save_rowid = 123
        existing_metadata.title = "Original Title"
        existing_metadata.author = "Original Author"

        data = {
            "title": "New Title Only"
            # Only updating title, other fields should remain unchanged
        }

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = existing_metadata
            mock_session.merge.return_value = existing_metadata
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.upsert(save_rowid=123, data=data)

            assert result == existing_metadata

            # Check only title was updated
            assert existing_metadata.title == "New Title Only"
            assert existing_metadata.author == "Original Author"  # Unchanged

    def test_upsert_with_empty_data(self, repository):
        """Test upsert with empty data dictionary."""
        existing_metadata = Mock(spec=UrlMetadata)
        existing_metadata.id = 1
        existing_metadata.save_rowid = 123
        existing_metadata.title = "Original Title"

        data = {}  # Empty data

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = existing_metadata
            mock_session.merge.return_value = existing_metadata
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.upsert(save_rowid=123, data=data)

            assert result == existing_metadata
            mock_session.merge.assert_called_once()
            # No fields should be updated since data is empty

    def test_upsert_with_none_values(self, repository):
        """Test upsert with None values in data."""
        existing_metadata = Mock(spec=UrlMetadata)
        existing_metadata.id = 1
        existing_metadata.save_rowid = 123
        existing_metadata.title = "Original Title"
        existing_metadata.author = "Original Author"

        data = {
            "title": "Updated Title",
            "author": None  # Should be set to None
        }

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = existing_metadata
            mock_session.merge.return_value = existing_metadata
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.upsert(save_rowid=123, data=data)

            assert result == existing_metadata
            assert existing_metadata.title == "Updated Title"
            assert existing_metadata.author is None

    def test_upsert_with_nested_data(self, repository):
        """Test upsert with complex nested data."""
        existing_metadata = Mock(spec=UrlMetadata)
        existing_metadata.id = 1
        existing_metadata.save_rowid = 123

        data = {
            "title": "Complex Article",
            "custom_fields": {
                "category": "technology",
                "tags": ["ai", "ml", "nlp"],
                "metadata": {
                    "word_count": 1000,
                    "reading_time": 5
                }
            },
            "simple_list": ["item1", "item2"],
            "number": 42
        }

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = existing_metadata
            mock_session.merge.return_value = existing_metadata
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.upsert(save_rowid=123, data=data)

            assert result == existing_metadata
            # Complex data should be stored as-is
            assert existing_metadata.custom_fields == data["custom_fields"]
            assert existing_metadata.simple_list == data["simple_list"]
            assert existing_metadata.number == 42

    def test_upsert_save_rowid_zero(self, repository):
        """Test upsert with save_rowid of 0."""
        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = None
            mock_save = Mock(spec=UrlMetadata)
            mock_save.id = 1
            mock_session.merge.return_value = mock_save
            mock_get_session.return_value.__enter__.return_value = mock_session

            data = {"title": "Test Article"}
            result = repository.upsert(save_rowid=0, data=data)

            assert result == mock_save
            merge_call_args = mock_session.merge.call_args[0][0]
            assert merge_call_args.save_rowid == 0

    def test_upsert_negative_save_rowid(self, repository):
        """Test upsert with negative save_rowid."""
        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = None
            mock_save = Mock(spec=UrlMetadata)
            mock_save.id = 1
            mock_session.merge.return_value = mock_save
            mock_get_session.return_value.__enter__.return_value = mock_session

            data = {"title": "Test Article"}
            result = repository.upsert(save_rowid=-1, data=data)

            assert result == mock_save
            merge_call_args = mock_session.merge.call_args[0][0]
            assert merge_call_args.save_rowid == -1

    def test_get_by_archived_url_multiple_results(self, repository):
        """Test get_by_archived_url when multiple results exist (should return first)."""
        mock_metadata1 = Mock(spec=UrlMetadata)
        mock_metadata1.id = 1
        mock_metadata2 = Mock(spec=UrlMetadata)
        mock_metadata2.id = 2

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = mock_metadata1
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.get_by_archived_url(123)

            assert result == mock_metadata1
            # Should return the first result
            assert result.id == 1

    def test_get_by_archived_url_with_large_id(self, repository):
        """Test get_by_archived_url with large ID values."""
        mock_metadata = Mock(spec=UrlMetadata)
        mock_metadata.id = 999999999
        mock_metadata.archived_url_id = 2147483647  # Max int32

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = mock_metadata
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.get_by_archived_url(2147483647)

            assert result == mock_metadata
            assert result.archived_url_id == 2147483647

    def test_upsert_with_unicode_text(self, repository):
        """Test upsert with Unicode characters in text."""
        existing_metadata = Mock(spec=UrlMetadata)
        existing_metadata.id = 1

        data = {
            "title": "测试文章",  # Chinese characters
            "author": "Жан Дюпон",  # Cyrillic characters
            "text": "العربية text 🚀 emoji"  # Arabic + emoji
        }

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = existing_metadata
            mock_session.merge.return_value = existing_metadata
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.upsert(save_rowid=123, data=data)

            assert result == existing_metadata
            # Unicode text should be preserved
            assert existing_metadata.title == "测试文章"
            assert existing_metadata.author == "Жан Дюпон"
            assert existing_metadata.text == "العربية text 🚀 emoji"

    def test_base_repository_methods_available(self, repository):
        """Test that BaseRepository methods are available."""
        # These are inherited from BaseRepository, just test they exist
        assert hasattr(repository, 'create')
        assert hasattr(repository, 'get')
        assert hasattr(repository, 'update')
        assert hasattr(repository, 'delete')
        assert hasattr(repository, 'list')
        assert hasattr(repository, 'count')
        assert hasattr(repository, 'exists')

    def test_upsert_very_long_text(self, repository):
        """Test upsert with very long text content."""
        existing_metadata = Mock(spec=UrlMetadata)
        existing_metadata.id = 1

        long_text = "A" * 100000  # 100KB of text

        data = {
            "title": "Long Article",
            "text": long_text
        }

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = existing_metadata
            mock_session.merge.return_value = existing_metadata
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.upsert(save_rowid=123, data=data)

            assert result == existing_metadata
            assert existing_metadata.text == long_text

    def test_upsert_with_special_characters(self, repository):
        """Test upsert with special characters and HTML entities."""
        existing_metadata = Mock(spec=UrlMetadata)
        existing_metadata.id = 1

        data = {
            "title": "Article with <script>alert('xss')</script> & \"quotes\"",
            "excerpt": "Text with newlines\n\tand tabs",
            "url": "https://example.com/path?param=value&other=test#fragment"
        }

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = existing_metadata
            mock_session.merge.return_value = existing_metadata
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.upsert(save_rowid=123, data=data)

            assert result == existing_metadata
            # Special characters should be preserved
            assert "<script>" in existing_metadata.title
            assert "&quot;" not in existing_metadata.title  # Should not be HTML-escaped
            assert "\n" in existing_metadata.excerpt