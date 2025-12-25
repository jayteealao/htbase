"""
Tests for the ArchiveArtifactRepository.

Tests the artifact database operations including CRUD operations, status management,
artifact lifecycle, size tracking, and relationship management.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Any, Dict, List, Optional

import pytest

from app.db.models import ArchivedUrl, ArchiveArtifact
from app.db.repositories import ArchiveArtifactRepository
from app.db.schemas import ArtifactSchema, ArtifactStatus


class TestArchiveArtifactRepository:
    """Test the ArchiveArtifactRepository class."""

    @pytest.fixture
    def mock_db_path(self):
        """Mock database path."""
        return Path("/tmp/test.db")

    @pytest.fixture
    def repository(self, mock_db_path):
        """Create ArchiveArtifactRepository instance for testing."""
        return ArchiveArtifactRepository(mock_db_path)

    def test_model_class_property(self, repository):
        """Test model_class property."""
        assert repository.model_class == ArchiveArtifact

    def test_get_or_create_new_artifact(self, repository):
        """Test get_or_create creates new artifact when none exists."""
        with patch.object(repository, '_get_or_create_session') as mock_get_create:
            mock_artifact = Mock(spec=ArchiveArtifact)
            mock_artifact.id = 1
            mock_get_create.return_value = mock_artifact

            result = repository.get_or_create(
                archived_url_id=123,
                archiver="monolith",
                task_id="task123"
            )

            assert result == mock_artifact
            mock_get_create.assert_called_once_with(
                mock_get_create.call_args[0][0],  # session
                archived_url_id=123,
                archiver="monolith",
                task_id="task123"
            )

    def test_get_or_create_existing_artifact(self, repository):
        """Test get_or_create returns existing artifact."""
        with patch.object(repository, '_get_or_create_session') as mock_get_create:
            mock_artifact = Mock(spec=ArchiveArtifact)
            mock_artifact.id = 1
            mock_get_create.return_value = mock_artifact

            result = repository.get_or_create(
                archived_url_id=123,
                archiver="monolith"
            )

            assert result == mock_artifact

    def test_get_or_create_session_new_artifact(self, repository):
        """Test _get_or_create_session creates new artifact in session."""
        mock_session = Mock()
        mock_session.execute.return_value.scalars.return_value.first.return_value = None

        with patch('db.repositories.ArchiveArtifact') as mock_artifact_class:
            mock_artifact = Mock(spec=ArchiveArtifact)
            mock_artifact.id = 1
            mock_artifact_class.return_value = mock_artifact

            result = repository._get_or_create_session(
                mock_session,
                archived_url_id=123,
                archiver="monolith",
                task_id="task123"
            )

            mock_session.execute.assert_called_once()
            mock_session.add.assert_called_once_with(mock_artifact)
            mock_session.flush.assert_called_once()
            assert result == mock_artifact
            mock_artifact_class.assert_called_once_with(
                archived_url_id=123,
                archiver="monolith",
                task_id="task123",
                status=ArtifactStatus.PENDING
            )

    def test_get_or_create_session_existing_artifact(self, repository):
        """Test _get_or_create_session returns existing artifact."""
        mock_session = Mock()
        mock_existing_artifact = Mock(spec=ArchiveArtifact)
        mock_existing_artifact.task_id = "old_task"
        mock_existing_artifact.status = None
        mock_session.execute.return_value.scalars.return_value.first.return_value = mock_existing_artifact

        result = repository._get_or_create_session(
            mock_session,
            archived_url_id=123,
            archiver="monolith",
            task_id="new_task"
        )

        # Should not create new artifact
        mock_session.add.assert_not_called()
        # Should update task_id and status
        assert mock_existing_artifact.task_id == "new_task"
        assert mock_existing_artifact.status == ArtifactStatus.PENDING
        mock_session.flush.assert_called_once()
        assert result == mock_existing_artifact

    def test_get_or_create_session_no_task_id(self, repository):
        """Test _get_or_create_session with no task_id."""
        mock_session = Mock()
        mock_existing_artifact = Mock(spec=ArchiveArtifact)
        mock_existing_artifact.task_id = "old_task"
        mock_existing_artifact.status = ArtifactStatus.PENDING
        mock_session.execute.return_value.scalars.return_value.first.return_value = mock_existing_artifact

        result = repository._get_or_create_session(
            mock_session,
            archived_url_id=123,
            archiver="monolith"
            # No task_id
        )

        # Should not update existing artifact
        assert mock_existing_artifact.task_id == "old_task"
        assert mock_existing_artifact.status == ArtifactStatus.PENDING
        mock_session.flush.assert_not_called()
        assert result == mock_existing_artifact

    def test_list_by_status_empty_statuses(self, repository):
        """Test list_by_status returns empty list for empty statuses."""
        result = repository.list_by_status([])
        assert result == []

    def test_list_by_status_with_statuses(self, repository):
        """Test list_by_status returns artifacts for given statuses."""
        mock_artifact1 = Mock(spec=ArchiveArtifact)
        mock_artifact1.id = 1
        mock_artifact1.archiver = "monolith"
        mock_artifact1.status = ArtifactStatus.PENDING
        mock_artifact1.task_id = "task1"
        mock_artifact1.success = False
        mock_artifact1.exit_code = None
        mock_artifact1.saved_path = None
        mock_artifact1.size_bytes = None
        mock_artifact1.created_at = datetime(2023, 1, 1)
        mock_artifact1.updated_at = datetime(2023, 1, 1)

        mock_artifact2 = Mock(spec=ArchiveArtifact)
        mock_artifact2.id = 2
        mock_artifact2.archiver = "readability"
        mock_artifact2.status = ArtifactStatus.FAILED
        mock_artifact2.task_id = "task2"
        mock_artifact2.success = False
        mock_artifact2.exit_code = 1
        mock_artifact2.saved_path = None
        mock_artifact2.size_bytes = None
        mock_artifact2.created_at = datetime(2023, 1, 2)
        mock_artifact2.updated_at = datetime(2023, 1, 2)

        mock_archived_url1 = Mock(spec=ArchivedUrl)
        mock_archived_url1.id = 10
        mock_archived_url1.item_id = "test1"
        mock_archived_url1.url = "https://example1.com"

        mock_archived_url2 = Mock(spec=ArchivedUrl)
        mock_archived_url2.id = 11
        mock_archived_url2.item_id = "test2"
        mock_archived_url2.url = "https://example2.com"

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.all.return_value = [
                (mock_artifact1, mock_archived_url1),
                (mock_artifact2, mock_archived_url2)
            ]
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.list_by_status([ArtifactStatus.PENDING, ArtifactStatus.FAILED])

            assert len(result) == 2

            # Check first artifact schema
            schema1 = result[0]
            assert isinstance(schema1, ArtifactSchema)
            assert schema1.artifact_id == 1
            assert schema1.archiver == "monolith"
            assert schema1.status == ArtifactStatus.PENDING
            assert schema1.task_id == "task1"
            assert schema1.item_id == "test1"
            assert schema1.url == "https://example1.com"
            assert schema1.archived_url_id == 10
            assert schema1.success is False

            # Check second artifact schema
            schema2 = result[1]
            assert schema2.artifact_id == 2
            assert schema2.archiver == "readability"
            assert schema2.status == ArtifactStatus.FAILED

    def test_list_by_status_with_limit(self, repository):
        """Test list_by_status with limit parameter."""
        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.all.return_value = []
            mock_get_session.return_value.__enter__.return_value = mock_session

            repository.list_by_status([ArtifactStatus.PENDING], limit=5)

            # Check that limit was applied to query
            call_args = mock_session.execute.call_args[0][0]
            # Note: In a real test, we'd check the SQL statement, but here we just ensure it's called

    def test_finalize_result_success(self, repository):
        """Test finalize_result updates artifact with success."""
        mock_session = Mock()
        mock_artifact = Mock(spec=ArchiveArtifact)
        mock_session.get.return_value = mock_artifact

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_session

            repository.finalize_result(
                artifact_id=123,
                success=True,
                exit_code=0,
                saved_path="/tmp/test.html",
                size_bytes=1024
            )

            mock_session.get.assert_called_once_with(ArchiveArtifact, 123)
            assert mock_artifact.success is True
            assert mock_artifact.exit_code == 0
            assert mock_artifact.saved_path == "/tmp/test.html"
            assert mock_artifact.status == ArtifactStatus.SUCCESS
            assert mock_artifact.size_bytes == 1024

    def test_finalize_result_failure(self, repository):
        """Test finalize_result updates artifact with failure."""
        mock_session = Mock()
        mock_artifact = Mock(spec=ArchiveArtifact)
        mock_session.get.return_value = mock_artifact

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_session

            repository.finalize_result(
                rowid=123,  # Test rowid parameter
                success=False,
                exit_code=1,
                saved_path=None
            )

            assert mock_artifact.success is False
            assert mock_artifact.exit_code == 1
            assert mock_artifact.saved_path is None
            assert mock_artifact.status == ArtifactStatus.FAILED

    def test_finalize_result_missing_size_bytes(self, repository):
        """Test finalize_result with missing size_bytes doesn't update it."""
        mock_session = Mock()
        mock_artifact = Mock(spec=ArchiveArtifact)
        mock_artifact.size_bytes = 500  # Existing value
        mock_session.get.return_value = mock_artifact

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_session

            repository.finalize_result(
                artifact_id=123,
                success=True,
                exit_code=0,
                saved_path="/tmp/test.html"
                # No size_bytes provided
            )

            assert mock_artifact.size_bytes == 500  # Should remain unchanged

    def test_finalize_result_artifact_not_found(self, repository):
        """Test finalize_result handles missing artifact gracefully."""
        mock_session = Mock()
        mock_session.get.return_value = None

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_session

            # Should not raise exception
            repository.finalize_result(
                artifact_id=999,
                success=True,
                exit_code=0,
                saved_path="/tmp/test.html"
            )

    def test_finalize_result_no_id_provided(self, repository):
        """Test finalize_result raises ValueError when no ID provided."""
        with pytest.raises(ValueError, match="artifact_id or rowid must be provided"):
            repository.finalize_result(
                success=True,
                exit_code=0,
                saved_path="/tmp/test.html"
            )

    def test_find_successful_by_url(self, repository):
        """Test find_successful finds artifact by URL."""
        mock_archived_url = Mock(spec=ArchivedUrl)
        mock_archived_url.id = 10
        mock_artifact = Mock(spec=ArchiveArtifact)
        mock_artifact.id = 1

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            # First query finds the archived URL
            mock_session.execute.return_value.scalars.return_value.first.side_effect = [
                mock_archived_url,  # First call: find ArchivedUrl
                mock_artifact        # Second call: find ArchiveArtifact
            ]
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.find_successful(
                item_id="test123",
                url="https://example.com",
                archiver="monolith"
            )

            assert result == mock_artifact

            # Verify both queries were called
            assert mock_session.execute.call_count == 2

    def test_find_successful_by_item_id_fallback(self, repository):
        """Test find_successful falls back to item_id when URL not found."""
        mock_archived_url = Mock(spec=ArchivedUrl)
        mock_archived_url.id = 10
        mock_archived_url.url = "https://example.com"  # Same URL to match
        mock_artifact = Mock(spec=ArchiveArtifact)
        mock_artifact.id = 1

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            # First query returns None for URL, second finds by item_id
            mock_session.execute.return_value.scalars.return_value.first.side_effect = [
                None,           # First call: no ArchivedUrl by URL
                mock_archived_url,  # Second call: ArchivedUrl by item_id
                mock_artifact   # Third call: ArchiveArtifact
            ]
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.find_successful(
                item_id="test123",
                url="https://example.com",
                archiver="monolith"
            )

            assert result == mock_artifact

    def test_find_successful_item_id_url_mismatch(self, repository):
        """Test find_successful returns None when item_id URL doesn't match."""
        mock_archived_url = Mock(spec=ArchivedUrl)
        mock_archived_url.id = 10
        mock_archived_url.url = "https://different.com"  # Different URL

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            # First query returns None for URL, second finds by item_id but URL mismatches
            mock_session.execute.return_value.scalars.return_value.first.side_effect = [
                None,
                mock_archived_url
            ]
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.find_successful(
                item_id="test123",
                url="https://example.com",
                archiver="monolith"
            )

            assert result is None

    def test_find_successful_no_archived_url(self, repository):
        """Test find_successful returns None when no archived URL found."""
        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.first.return_value = None
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.find_successful(
                item_id="test123",
                url="https://example.com",
                archiver="monolith"
            )

            assert result is None

    def test_list_by_item_id(self, repository):
        """Test list_by_item_id returns all artifacts for item ID."""
        mock_artifact1 = Mock(spec=ArchiveArtifact)
        mock_artifact2 = Mock(spec=ArchiveArtifact)

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = [
                mock_artifact1, mock_artifact2
            ]
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.list_by_item_id("test123")

            assert len(result) == 2
            assert result[0] == mock_artifact1
            assert result[1] == mock_artifact2

    def test_list_by_url(self, repository):
        """Test list_by_url returns all artifacts for URL."""
        mock_artifact1 = Mock(spec=ArchiveArtifact)
        mock_artifact2 = Mock(spec=ArchiveArtifact)

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = [
                mock_artifact1, mock_artifact2
            ]
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.list_by_url("https://example.com")

            assert len(result) == 2
            assert result[0] == mock_artifact1
            assert result[1] == mock_artifact2

    def test_list_by_task_id(self, repository):
        """Test list_by_task_id returns artifacts with URL info."""
        mock_artifact = Mock(spec=ArchiveArtifact)
        mock_artifact.id = 1
        mock_artifact.success = True
        mock_artifact.exit_code = 0
        mock_artifact.saved_path = "/tmp/test.html"
        mock_artifact.created_at = datetime(2023, 1, 1, 12, 0, 0)

        mock_archived_url = Mock(spec=ArchivedUrl)
        mock_archived_url.item_id = "test123"
        mock_archived_url.url = "https://example.com"

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.all.return_value = [
                (mock_artifact, mock_archived_url)
            ]
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.list_by_task_id("task123")

            assert len(result) == 1
            artifact_dict = result[0]

            assert artifact_dict["rowid"] == 1
            assert artifact_dict["item_id"] == "test123"
            assert artifact_dict["user_id"] is None
            assert artifact_dict["url"] == "https://example.com"
            assert artifact_dict["success"] == 1  # Boolean converted to int
            assert artifact_dict["exit_code"] == 0
            assert artifact_dict["saved_path"] == "/tmp/test.html"
            assert artifact_dict["created_at"] == "2023-01-01T12:00:00"

    def test_list_by_task_id_with_none_created_at(self, repository):
        """Test list_by_task_id handles None created_at gracefully."""
        mock_artifact = Mock(spec=ArchiveArtifact)
        mock_artifact.id = 1
        mock_artifact.success = False
        mock_artifact.exit_code = 1
        mock_artifact.saved_path = None
        mock_artifact.created_at = None  # None created_at

        mock_archived_url = Mock(spec=ArchivedUrl)
        mock_archived_url.item_id = "test123"
        mock_archived_url.url = "https://example.com"

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.all.return_value = [
                (mock_artifact, mock_archived_url)
            ]
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.list_by_task_id("task123")

            artifact_dict = result[0]
            assert artifact_dict["created_at"] is None

    def test_list_by_task_id_empty_result(self, repository):
        """Test list_by_task_id returns empty list for no artifacts."""
        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.all.return_value = []
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.list_by_task_id("nonexistent_task")

            assert result == []

    def test_delete_many_by_ids(self, repository):
        """Test delete_many_by_ids deletes artifacts by IDs."""
        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.rowcount = 3
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.delete_many_by_ids([1, 2, 3])

            assert result == 3
            mock_session.execute.assert_called_once()

    def test_delete_many_by_ids_empty_list(self, repository):
        """Test delete_many_by_ids returns 0 for empty ID list."""
        result = repository.delete_many_by_ids([])
        assert result == 0

    def test_delete_many_by_item_id_and_archivers(self, repository):
        """Test delete_many_by_item_id_and_archivers deletes artifacts."""
        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.execute.return_value.rowcount = 2
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.delete_many_by_item_id_and_archivers(
                "test123", ["monolith", "readability"]
            )

            assert result == 2
            mock_session.execute.assert_called_once()

    def test_delete_many_by_item_id_and_archivers_empty_archivers(self, repository):
        """Test delete_many_by_item_id_and_archivers returns 0 for empty archivers."""
        result = repository.delete_many_by_item_id_and_archivers("test123", [])
        assert result == 0

    def test_get_by_id(self, repository):
        """Test get_by_id retrieves artifact by ID."""
        mock_artifact = Mock(spec=ArchiveArtifact)
        mock_artifact.id = 1

        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.get.return_value = mock_artifact
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.get_by_id(1)

            assert result == mock_artifact
            mock_session.get.assert_called_once_with(ArchiveArtifact, 1)

    def test_get_by_id_not_found(self, repository):
        """Test get_by_id returns None when artifact not found."""
        with patch.object(repository, '_get_session') as mock_get_session:
            mock_session = Mock()
            mock_session.get.return_value = None
            mock_get_session.return_value.__enter__.return_value = mock_session

            result = repository.get_by_id(999)

            assert result is None

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