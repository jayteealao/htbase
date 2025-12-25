"""
Tests for the ArchivedUrlRepository.

Tests the archived URL database operations including CRUD operations, URL uniqueness,
item_id/name management, and total size tracking.
"""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from app.db.models import ArchivedUrl, ArchiveArtifact
from app.db.repositories import ArchivedUrlRepository


class TestArchivedUrlRepository:
    """Test the ArchivedUrlRepository class."""

    @pytest.fixture
    def mock_db_path(self):
        """Mock database path."""
        return Path("/tmp/test.db")

    @pytest.fixture
    def repository(self, mock_db_path):
        """Create ArchivedUrlRepository instance for testing."""
        return ArchivedUrlRepository(mock_db_path)

    def test_model_class_property(self, repository):
        """Test model_class property."""
        assert repository.model_class == ArchivedUrl

    def test_get_by_url_found(self, repository):
        """Test get_by_url returns archived URL when found."""
        mock_archived_url = Mock(spec=ArchivedUrl)
        mock_archived_url.id = 1
        mock_archived_url.url = "https://example.com"

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = mock_archived_url
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.get_by_url("https://example.com")

            assert result == mock_archived_url
            mock_session.execute.assert_called_once()

    def test_get_by_url_not_found(self, repository):
        """Test get_by_url returns None when URL not found."""
        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = None
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.get_by_url("https://example.com")

            assert result is None

    def test_get_by_url_session_found(self, repository):
        """Test get_by_url_session returns archived URL within session."""
        mock_archived_url = Mock(spec=ArchivedUrl)
        mock_archived_url.id = 1
        mock_session = Mock()
        mock_session.execute.return_value.scalars.return_value.first.return_value = mock_archived_url

        result = repository.get_by_url_session(mock_session, "https://example.com")

        assert result == mock_archived_url
        mock_session.execute.assert_called_once()

    def test_get_by_url_session_not_found(self, repository):
        """Test get_by_url_session returns None within session when not found."""
        mock_session = Mock()
        mock_session.execute.return_value.scalars.return_value.first.return_value = None

        result = repository.get_by_url_session(mock_session, "https://example.com")

        assert result is None

    def test_get_or_create_new_url(self, repository):
        """Test get_or_create creates new archived URL when none exists."""
        with patch.object(repository, '_get_or_create_session') as mock_get_create:
            mock_archived_url = Mock(spec=ArchivedUrl)
            mock_archived_url.id = 1
            mock_get_create.return_value = mock_archived_url

            result = repository.get_or_create(
                url="https://example.com",
                item_id="test123",
                name="Test Article"
            )

            assert result == mock_archived_url
            mock_get_create.assert_called_once_with(
                mock_get_create.call_args[0][0],  # session
                url="https://example.com",
                item_id="test123",
                name="Test Article"
            )

    def test_get_or_create_existing_url(self, repository):
        """Test get_or_create returns existing archived URL."""
        with patch.object(repository, '_get_or_create_session') as mock_get_create:
            mock_archived_url = Mock(spec=ArchivedUrl)
            mock_archived_url.id = 1
            mock_get_create.return_value = mock_archived_url

            result = repository.get_or_create(url="https://example.com")

            assert result == mock_archived_url

    def test_get_or_create_session_new_url(self, repository):
        """Test _get_or_create_session creates new archived URL in session."""
        mock_session = Mock()
        mock_session.execute.return_value.scalars.return_value.first.return_value = None

        with patch('db.repositories.ArchivedUrl') as mock_archived_url_class:
            mock_archived_url = Mock(spec=ArchivedUrl)
            mock_archived_url.id = 1
            mock_archived_url_class.return_value = mock_archived_url

            result = repository._get_or_create_session(
                mock_session,
                url="https://example.com",
                item_id="test123",
                name="Test Article"
            )

            mock_session.execute.assert_called_once()
            mock_session.add.assert_called_once_with(mock_archived_url)
            mock_session.flush.assert_called_once()
            assert result == mock_archived_url
            mock_archived_url_class.assert_called_once_with(
                url="https://example.com",
                item_id="test123",
                name="Test Article"
            )

    def test_get_or_create_session_existing_url_no_updates(self, repository):
        """Test _get_or_create_session returns existing URL without updates."""
        mock_session = Mock()
        mock_existing_url = Mock(spec=ArchivedUrl)
        mock_existing_url.item_id = "existing123"
        mock_existing_url.name = "Existing Name"
        mock_session.execute.return_value.scalars.return_value.first.return_value = mock_existing_url

        result = repository._get_or_create_session(
            mock_session,
            url="https://example.com",
            item_id="test123",  # Different from existing
            name="Test Article"  # Different from existing
        )

        # Should not create new URL
        mock_session.add.assert_not_called()
        mock_session.flush.assert_not_called()
        assert result == mock_existing_url
        # Existing values should not be changed
        assert mock_existing_url.item_id == "existing123"
        assert mock_existing_url.name == "Existing Name"

    def test_get_or_create_session_backfills_item_id(self, repository):
        """Test _get_or_create_session backfills missing item_id."""
        mock_session = Mock()
        mock_existing_url = Mock(spec=ArchivedUrl)
        mock_existing_url.item_id = None  # Missing
        mock_existing_url.name = "Existing Name"
        mock_session.execute.return_value.scalars.return_value.first.return_value = mock_existing_url

        result = repository._get_or_create_session(
            mock_session,
            url="https://example.com",
            item_id="new123",  # Should be backfilled
            name="Existing Name"  # Same as existing
        )

        # Should update item_id
        assert mock_existing_url.item_id == "new123"
        assert mock_existing_url.name == "Existing Name"
        mock_session.flush.assert_called_once()
        assert result == mock_existing_url

    def test_get_or_create_session_backfills_name(self, repository):
        """Test _get_or_create_session backfills missing name."""
        mock_session = Mock()
        mock_existing_url = Mock(spec=ArchivedUrl)
        mock_existing_url.item_id = "existing123"
        mock_existing_url.name = None  # Missing
        mock_session.execute.return_value.scalars.return_value.first.return_value = mock_existing_url

        result = repository._get_or_create_session(
            mock_session,
            url="https://example.com",
            item_id="existing123",  # Same as existing
            name="New Name"  # Should be backfilled
        )

        # Should update name
        assert mock_existing_url.item_id == "existing123"
        assert mock_existing_url.name == "New Name"
        mock_session.flush.assert_called_once()
        assert result == mock_existing_url

    def test_get_or_create_session_backfills_both(self, repository):
        """Test _get_or_create_session backfills both missing item_id and name."""
        mock_session = Mock()
        mock_existing_url = Mock(spec=ArchivedUrl)
        mock_existing_url.item_id = None  # Missing
        mock_existing_url.name = None  # Missing
        mock_session.execute.return_value.scalars.return_value.first.return_value = mock_existing_url

        result = repository._get_or_create_session(
            mock_session,
            url="https://example.com",
            item_id="new123",
            name="New Name"
        )

        # Should update both
        assert mock_existing_url.item_id == "new123"
        assert mock_existing_url.name == "New Name"
        mock_session.flush.assert_called_once()
        assert result == mock_existing_url

    def test_get_or_create_session_no_backfills_when_none_provided(self, repository):
        """Test _get_or_create_session doesn't backfill when None provided."""
        mock_session = Mock()
        mock_existing_url = Mock(spec=ArchivedUrl)
        mock_existing_url.item_id = None  # Missing
        mock_existing_url.name = "Existing Name"
        mock_session.execute.return_value.scalars.return_value.first.return_value = mock_existing_url

        result = repository._get_or_create_session(
            mock_session,
            url="https://example.com",
            item_id=None,  # None provided
            name="Existing Name"  # Same as existing
        )

        # Should only update item_id if provided, but None is provided
        # So only name should remain unchanged
        assert mock_existing_url.item_id is None
        assert mock_existing_url.name == "Existing Name"
        mock_session.flush.assert_not_called()  # No changes
        assert result == mock_existing_url

    def test_update_total_size_calculates_from_artifacts(self, repository):
        """Test update_total_size calculates total size from all artifacts."""
        mock_artifact1 = Mock(spec=ArchiveArtifact)
        mock_artifact1.size_bytes = 1024
        mock_artifact2 = Mock(spec=ArchiveArtifact)
        mock_artifact2.size_bytes = 2048
        mock_artifact3 = Mock(spec=ArchiveArtifact)
        mock_artifact3.size_bytes = None  # Should be ignored

        mock_archived_url = Mock(spec=ArchivedUrl)

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = [
                mock_artifact1, mock_artifact2, mock_artifact3
            ]
            mock_session.get.return_value = mock_archived_url
            mock_get_session.return_value.__enter__.return_value = mock_session

            repository.update_total_size(123)

            # Check query was called
            mock_session.execute.assert_called_once()
            mock_session.get.assert_called_once_with(ArchivedUrl, 123)

            # Check total size was calculated (1024 + 2048, None ignored)
            assert mock_archived_url.total_size_bytes == 3072

    def test_update_total_size_no_artifacts(self, repository):
        """Test update_total_size handles no artifacts gracefully."""
        mock_archived_url = Mock(spec=ArchivedUrl)

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = []
            mock_session.get.return_value = mock_archived_url
            mock_get_session.return_value.__enter__.return_value = mock_session

            repository.update_total_size(123)

            # Should set total_size_bytes to None (no artifacts)
            assert mock_archived_url.total_size_bytes is None

    def test_update_total_size_all_none_sizes(self, repository):
        """Test update_total_size handles all None sizes."""
        mock_artifact1 = Mock(spec=ArchiveArtifact)
        mock_artifact1.size_bytes = None
        mock_artifact2 = Mock(spec=ArchiveArtifact)
        mock_artifact2.size_bytes = None

        mock_archived_url = Mock(spec=ArchivedUrl)

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = [
                mock_artifact1, mock_artifact2
            ]
            mock_session.get.return_value = mock_archived_url
            mock_get_session.return_value.__enter__.return_value = mock_session

            repository.update_total_size(123)

            # Should set to None since all artifacts have None sizes
            assert mock_archived_url.total_size_bytes is None

    def test_update_total_size_archived_url_not_found(self, repository):
        """Test update_total_size handles missing archived URL gracefully."""
        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = []
            mock_session.get.return_value = None  # No ArchivedUrl found
            mock_get_session.return_value.__enter__.return_value = mock_session

            # Should not raise exception
            repository.update_total_size(123)

    def test_get_by_url_with_special_characters(self, repository):
        """Test get_by_url with special characters in URL."""
        mock_archived_url = Mock(spec=ArchivedUrl)
        mock_archived_url.url = "https://example.com/path?query=value&param=test#fragment"

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = mock_archived_url
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.get_by_url("https://example.com/path?query=value&param=test#fragment")

            assert result == mock_archived_url

    def test_get_or_create_with_empty_item_id(self, repository):
        """Test get_or_create with empty string item_id."""
        with patch.object(repository, '_get_or_create_session') as mock_get_create:
            mock_archived_url = Mock(spec=ArchivedUrl)
            mock_get_create.return_value = mock_archived_url

            result = repository.get_or_create(
                url="https://example.com",
                item_id="",  # Empty string
                name="Test"
            )

            assert result == mock_archived_url
            # Empty string should still be passed through
            mock_get_create.assert_called_once_with(
                mock_get_create.call_args[0][0],
                url="https://example.com",
                item_id="",
                name="Test"
            )

    def test_get_or_create_with_empty_name(self, repository):
        """Test get_or_create with empty string name."""
        with patch.object(repository, '_get_or_create_session') as mock_get_create:
            mock_archived_url = Mock(spec=ArchivedUrl)
            mock_get_create.return_value = mock_archived_url

            result = repository.get_or_create(
                url="https://example.com",
                item_id="test123",
                name=""  # Empty string
            )

            assert result == mock_archived_url
            # Empty string should still be passed through
            mock_get_create.assert_called_once_with(
                mock_get_create.call_args[0][0],
                url="https://example.com",
                item_id="test123",
                name=""
            )

    def test_get_or_create_minimal_parameters(self, repository):
        """Test get_or_create with only URL parameter."""
        with patch.object(repository, '_get_or_create_session') as mock_get_create:
            mock_archived_url = Mock(spec=ArchivedUrl)
            mock_get_create.return_value = mock_archived_url

            result = repository.get_or_create(url="https://example.com")

            assert result == mock_archived_url
            mock_get_create.assert_called_once_with(
                mock_get_create.call_args[0][0],
                url="https://example.com",
                item_id=None,
                name=None
            )

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

    def test_update_total_size_zero_total(self, repository):
        """Test update_total_size when total size is 0."""
        mock_artifact1 = Mock(spec=ArchiveArtifact)
        mock_artifact1.size_bytes = 0
        mock_artifact2 = Mock(spec=ArchiveArtifact)
        mock_artifact2.size_bytes = 0

        mock_archived_url = Mock(spec=ArchivedUrl)

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = [
                mock_artifact1, mock_artifact2
            ]
            mock_session.get.return_value = mock_archived_url
            mock_get_session.return_value.__enter__.return_value = mock_session

            repository.update_total_size(123)

            # Should set to None when total is 0 (empty/invalid)
            assert mock_archived_url.total_size_bytes is None

    def test_update_total_size_negative_sizes(self, repository):
        """Test update_total_size with negative sizes."""
        mock_artifact1 = Mock(spec=ArchiveArtifact)
        mock_artifact1.size_bytes = 1024
        mock_artifact2 = Mock(spec=ArchiveArtifact)
        mock_artifact2.size_bytes = -512  # Negative size

        mock_archived_url = Mock(spec=ArchivedUrl)

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = [
                mock_artifact1, mock_artifact2
            ]
            mock_session.get.return_value = mock_archived_url
            mock_get_session.return_value.__enter__.return_value = mock_session

            repository.update_total_size(123)

            # Should include negative sizes in total
            assert mock_archived_url.total_size_bytes == 512  # 1024 + (-512)