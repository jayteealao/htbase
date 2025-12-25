"""
Tests for BaseArchiver base class.

Tests all BaseArchiver methods using fakes for storage and database.
"""

from pathlib import Path

import pytest

from app.archivers.base import BaseArchiver
from app.models import ArchiveResult
from tests.utils import create_test_article, create_dummy_html_file


class ConcreteArchiver(BaseArchiver):
    """Concrete implementation of BaseArchiver for testing."""

    name = "test_archiver"
    output_extension = "html"

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        """Simple test implementation that creates a file."""
        out_dir, out_path = self.get_output_path(item_id)
        out_path.write_text(f"<html><body>Archived: {url}</body></html>", encoding="utf-8")
        return ArchiveResult(success=True, exit_code=0, saved_path=str(out_path))


# ==================== Output Path Tests ====================

class TestGetOutputPath:
    """Test get_output_path method."""

    def test_creates_output_directory(self, temp_env):
        """Test that output directory is created."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings())
        out_dir, out_path = archiver.get_output_path("test_item")

        assert out_dir.exists()
        assert out_dir.is_dir()

    def test_returns_correct_paths(self, temp_env):
        """Test that correct paths are returned."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings())
        out_dir, out_path = archiver.get_output_path("test_item")

        assert out_dir.name == "test_archiver"
        assert out_path.name == "output.html"
        assert out_path.parent == out_dir

    def test_sanitizes_item_id(self, temp_env):
        """Test that item_id is sanitized."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings())
        out_dir, out_path = archiver.get_output_path("../../../etc/passwd")

        # Should be sanitized (no path traversal)
        assert "../" not in str(out_dir)

    def test_handles_spaces_in_item_id(self, temp_env):
        """Test handling of spaces in item_id."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings())
        out_dir, out_path = archiver.get_output_path("item with spaces")

        # Path should exist and be accessible
        assert out_dir.exists()


# ==================== Existing Output Tests ====================

class TestHasExistingOutput:
    """Test has_existing_output method."""

    def test_returns_none_when_no_output(self, temp_env):
        """Test returns None when no output exists."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings())
        existing = archiver.has_existing_output("nonexistent")

        assert existing is None

    def test_finds_standard_output_file(self, temp_env):
        """Test finds standard output file."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings())

        # Create output file
        out_dir, out_path = archiver.get_output_path("test_item")
        out_path.write_text("<html>test</html>", encoding="utf-8")

        existing = archiver.has_existing_output("test_item")

        assert existing is not None
        assert existing == out_path

    def test_finds_numbered_variant(self, temp_env):
        """Test finds numbered variant files."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings())

        # Create numbered variant
        out_dir, out_path = archiver.get_output_path("test_item")
        numbered_path = out_dir / "output (2).html"
        numbered_path.write_text("<html>test</html>", encoding="utf-8")

        existing = archiver.has_existing_output("test_item")

        assert existing is not None
        assert "(2)" in existing.name

    def test_ignores_empty_files(self, temp_env):
        """Test ignores empty output files."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings())

        # Create empty file
        out_dir, out_path = archiver.get_output_path("test_item")
        out_path.write_text("", encoding="utf-8")

        existing = archiver.has_existing_output("test_item")

        assert existing is None  # Should ignore empty files


# ==================== Validation Tests ====================

class TestValidateOutput:
    """Test validate_output method."""

    def test_success_with_valid_output(self, temp_env, tmp_path):
        """Test validation succeeds with valid output."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings())

        # Create valid output file
        output_file = tmp_path / "output.html"
        output_file.write_text("<html>test</html>", encoding="utf-8")

        valid = archiver.validate_output(output_file, exit_code=0, min_size=1)

        assert valid is True

    def test_fails_with_nonzero_exit_code(self, temp_env, tmp_path):
        """Test validation fails with non-zero exit code."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings())

        output_file = tmp_path / "output.html"
        output_file.write_text("<html>test</html>", encoding="utf-8")

        valid = archiver.validate_output(output_file, exit_code=1, min_size=1)

        assert valid is False

    def test_fails_when_file_missing(self, temp_env, tmp_path):
        """Test validation fails when file doesn't exist."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings())

        nonexistent_file = tmp_path / "missing.html"

        valid = archiver.validate_output(nonexistent_file, exit_code=0, min_size=1)

        assert valid is False

    def test_fails_when_file_too_small(self, temp_env, tmp_path):
        """Test validation fails when file is too small."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings())

        # Create file that's too small
        output_file = tmp_path / "output.html"
        output_file.write_text("x", encoding="utf-8")

        valid = archiver.validate_output(output_file, exit_code=0, min_size=100)

        assert valid is False


# ==================== Result Creation Tests ====================

class TestCreateResult:
    """Test create_result method."""

    def test_creates_success_result(self, temp_env, tmp_path):
        """Test creates success result for valid output."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings())

        output_file = tmp_path / "output.html"
        output_file.write_text("<html>test</html>", encoding="utf-8")

        result = archiver.create_result(output_file, exit_code=0)

        assert result.success is True
        assert result.exit_code == 0
        assert result.saved_path == str(output_file)

    def test_creates_failure_result(self, temp_env, tmp_path):
        """Test creates failure result for invalid output."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings())

        output_file = tmp_path / "output.html"
        # File doesn't exist

        result = archiver.create_result(output_file, exit_code=1)

        assert result.success is False
        assert result.exit_code == 1
        assert result.saved_path is None

    def test_includes_metadata(self, temp_env, tmp_path):
        """Test includes custom metadata."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings())

        output_file = tmp_path / "output.html"
        output_file.write_text("<html>test</html>", encoding="utf-8")

        metadata = {"custom_key": "custom_value"}
        result = archiver.create_result(output_file, exit_code=0, metadata=metadata)

        assert result.metadata == metadata


# ==================== Storage Upload Tests ====================

class TestUploadToAllProviders:
    """Test upload_to_all_providers method."""

    def test_uploads_to_single_provider(self, temp_env, tmp_path, in_memory_file_storage):
        """Test uploading to single storage provider."""
        from core.config import get_settings

        archiver = ConcreteArchiver(
            get_settings(),
            file_storage_providers=[in_memory_file_storage]
        )

        # Create file to upload
        upload_file = tmp_path / "output.html"
        upload_file.write_text("<html>test</html>", encoding="utf-8")

        results = archiver.upload_to_all_providers(upload_file, "test_item")

        assert len(results) == 1
        assert results[0]['success'] is True
        assert results[0]['provider_name'] == "memory"

    def test_uploads_to_multiple_providers(self, temp_env, tmp_path):
        """Test uploading to multiple storage providers."""
        from core.config import get_settings
        from fakes.storage import InMemoryFileStorage

        provider1 = InMemoryFileStorage()
        provider2 = InMemoryFileStorage()

        archiver = ConcreteArchiver(
            get_settings(),
            file_storage_providers=[provider1, provider2]
        )

        upload_file = tmp_path / "output.html"
        upload_file.write_text("<html>test</html>", encoding="utf-8")

        results = archiver.upload_to_all_providers(upload_file, "test_item")

        assert len(results) == 2
        assert all(r['success'] for r in results)

    def test_returns_empty_when_no_providers(self, temp_env, tmp_path):
        """Test returns empty list when no providers configured."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings(), file_storage_providers=[])

        upload_file = tmp_path / "output.html"
        upload_file.write_text("<html>test</html>", encoding="utf-8")

        results = archiver.upload_to_all_providers(upload_file, "test_item")

        assert results == []

    def test_returns_empty_when_file_missing(self, temp_env, tmp_path, in_memory_file_storage):
        """Test returns empty list when file doesn't exist."""
        from core.config import get_settings

        archiver = ConcreteArchiver(
            get_settings(),
            file_storage_providers=[in_memory_file_storage]
        )

        nonexistent_file = tmp_path / "missing.html"

        results = archiver.upload_to_all_providers(nonexistent_file, "test_item")

        assert results == []

    def test_handles_upload_failure(self, temp_env, tmp_path):
        """Test handles upload failure gracefully."""
        from core.config import get_settings
        from fakes.storage import InMemoryFileStorage

        # Configure provider to fail on specific path
        provider = InMemoryFileStorage(fail_on_paths=["archives/test_item/test_archiver/output.html"])

        archiver = ConcreteArchiver(
            get_settings(),
            file_storage_providers=[provider]
        )

        upload_file = tmp_path / "output.html"
        upload_file.write_text("<html>test</html>", encoding="utf-8")

        results = archiver.upload_to_all_providers(upload_file, "test_item")

        assert len(results) == 1
        assert results[0]['success'] is False
        assert 'error' in results[0]


# ==================== Database Update Tests ====================

class TestUpdateDatabaseStorage:
    """Test update_database_storage method."""

    def test_updates_database_with_storage_metadata(self, temp_env, in_memory_db_storage):
        """Test updates database with storage metadata."""
        from core.config import get_settings

        archiver = ConcreteArchiver(
            get_settings(),
            db_storage=in_memory_db_storage
        )

        archive_result = {
            'gcs_path': 'gs://bucket/path/file.html',
            'gcs_bucket': 'bucket',
            'compressed_size': 12345,
            'compression_ratio': 85.5
        }

        archiver.update_database_storage("test_item", archive_result)

        # Verify database was updated
        artifact = in_memory_db_storage.get_artifact("test_item", "test_archiver")
        assert artifact is not None

    def test_noop_when_no_db_storage(self, temp_env):
        """Test is no-op when db_storage not configured."""
        from core.config import get_settings

        archiver = ConcreteArchiver(get_settings(), db_storage=None)

        # Should not raise
        archiver.update_database_storage("test_item", {"gcs_path": "gs://bucket/path"})


# ==================== Integration Tests ====================

class TestArchiveWithStorage:
    """Test archive_with_storage method (integration)."""

    def test_archives_and_uploads(self, temp_env, in_memory_file_storage, in_memory_db_storage):
        """Test complete archiving with storage upload."""
        from core.config import get_settings

        archiver = ConcreteArchiver(
            get_settings(),
            file_storage_providers=[in_memory_file_storage],
            db_storage=in_memory_db_storage
        )

        result = archiver.archive_with_storage(url="https://example.com", item_id="test_item")

        assert result.success
        assert result.saved_path is not None
        assert 'storage_uploads' in result.metadata
        assert len(result.metadata['storage_uploads']) == 1
        assert result.metadata['all_uploads_succeeded'] is True

    def test_includes_upload_metadata(self, temp_env, in_memory_file_storage):
        """Test includes upload metadata in result."""
        from core.config import get_settings

        archiver = ConcreteArchiver(
            get_settings(),
            file_storage_providers=[in_memory_file_storage]
        )

        result = archiver.archive_with_storage(url="https://example.com", item_id="test_item")

        upload = result.metadata['storage_uploads'][0]
        assert upload['success'] is True
        assert upload['provider_name'] == "memory"
        assert 'storage_uri' in upload

    def test_handles_partial_upload_failure(self, temp_env):
        """Test handles partial upload failure."""
        from core.config import get_settings
        from fakes.storage import InMemoryFileStorage

        good_provider = InMemoryFileStorage()
        bad_provider = InMemoryFileStorage(
            fail_on_paths=["archives/test_item/test_archiver/output.html"]
        )

        archiver = ConcreteArchiver(
            get_settings(),
            file_storage_providers=[good_provider, bad_provider]
        )

        result = archiver.archive_with_storage(url="https://example.com", item_id="test_item")

        assert result.success  # Archive itself succeeded
        assert len(result.metadata['storage_uploads']) == 2
        assert result.metadata['all_uploads_succeeded'] is False  # But not all uploads did

    def test_skips_upload_on_archive_failure(self, temp_env, in_memory_file_storage):
        """Test skips upload when archiving fails."""
        from core.config import get_settings
        from fakes.archivers import FailingArchiver

        archiver = FailingArchiver(
            get_settings(),
            exit_code=1
        )
        archiver.file_storage_providers = [in_memory_file_storage]

        result = archiver.archive_with_storage(url="https://example.com", item_id="test_item")

        assert not result.success
        # Should not have storage_uploads since archive failed
        assert 'storage_uploads' not in (result.metadata or {})
