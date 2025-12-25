"""
Tests for GCSFileStorage.

Tests Google Cloud Storage implementation using mocks to avoid actual GCS calls.
"""

import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest

from storage.gcs_file_storage import GCSFileStorage


class TestGCSFileStorage:
    """Test GCSFileStorage implementation."""

    def test_provider_name(self):
        """Test provider name is correct."""
        with patch('storage.gcs_file_storage.storage.Client'):
            storage = GCSFileStorage("test-bucket")
            assert storage.provider_name == "gcs"

    def test_supports_compression(self):
        """Test compression support flag."""
        with patch('storage.gcs_file_storage.storage.Client'):
            storage = GCSFileStorage("test-bucket")
            assert storage.supports_compression is True

    def test_supports_signed_urls(self):
        """Test signed URLs support flag."""
        with patch('storage.gcs_file_storage.storage.Client'):
            storage = GCSFileStorage("test-bucket")
            assert storage.supports_signed_urls is True

    # ==================== Initialization Tests ====================

    def test_initialization_with_bucket_and_project(self):
        """Test initialization with bucket name and project ID."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            storage = GCSFileStorage("test-bucket", project_id="test-project")

            mock_client.assert_called_once_with(project="test-project")
            mock_client.return_value.bucket.assert_called_once_with("test-bucket")
            assert storage.bucket_name == "test-bucket"

    def test_initialization_with_bucket_only(self):
        """Test initialization with bucket name only."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            storage = GCSFileStorage("test-bucket")

            mock_client.assert_called_once_with(project=None)
            mock_client.return_value.bucket.assert_called_once_with("test-bucket")
            assert storage.bucket_name == "test-bucket"

    # ==================== Upload Tests ====================

    def test_upload_file_success_uncompressed(self, temp_env):
        """Test successful file upload without compression."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            # Mock GCS components
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            # Create test file
            test_file = temp_env / "test.html"
            test_content = b"<html><body>Test content</body></html>"
            test_file.write_bytes(test_content)

            result = storage.upload_file(test_file, "archives/test.html", compress=False)

            assert result.success
            assert result.original_size == len(test_content)
            assert result.stored_size == len(test_content)
            assert result.compression_ratio is None
            assert result.uri == "gs://test-bucket/archives/test.html"
            assert result.error is None

            # Verify GCS calls
            mock_bucket.blob.assert_called_once_with("archives/test.html")
            mock_blob.upload_from_filename.assert_called_once()
            assert mock_blob.content_type == "text/html"

    def test_upload_file_success_compressed(self, temp_env):
        """Test successful file upload with compression."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            # Create test file with compressible content
            test_file = temp_env / "test.html"
            test_content = b"<html><body>" + b"x" * 1000 + b"</body></html>"
            test_file.write_bytes(test_content)

            result = storage.upload_file(test_file, "archives/test.html", compress=True)

            assert result.success
            assert result.original_size == len(test_content)
            assert result.stored_size < result.original_size  # Should be compressed
            assert result.compression_ratio is not None
            assert result.compression_ratio > 0
            assert result.uri == "gs://test-bucket/archives/test.html.gz"

            # Verify compressed metadata
            assert mock_blob.metadata == {'compressed': 'true', 'original_size': str(len(test_content))}

    def test_upload_file_with_storage_class(self, temp_env):
        """Test upload with storage class specification."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            test_file = temp_env / "test.html"
            test_content = b"<html>Test</html>"
            test_file.write_bytes(test_content)

            result = storage.upload_file(
                test_file,
                "archives/test.html",
                compress=True,
                storage_class="STANDARD"
            )

            assert result.success
            mock_blob.update_storage_class.assert_called_once_with("STANDARD")

    def test_upload_file_source_not_found(self, temp_env):
        """Test upload with non-existent source file."""
        with patch('storage.gcs_file_storage.storage.Client'):
            storage = GCSFileStorage("test-bucket")

            non_existent = temp_env / "nonexistent.html"
            result = storage.upload_file(non_existent, "archives/test.html")

            assert not result.success
            assert result.original_size == 0
            assert result.stored_size == 0
            assert "Source file not found" in result.error

    def test_upload_file_gcs_error(self, temp_env):
        """Test upload when GCS raises an error."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.upload_from_filename.side_effect = Exception("GCS error")
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            test_file = temp_env / "test.html"
            test_content = b"<html>Test</html>"
            test_file.write_bytes(test_content)

            result = storage.upload_file(test_file, "archives/test.html")

            assert not result.success
            assert "GCS error" in result.error

    def test_upload_file_cleanup_temp_compressed_file(self, temp_env):
        """Test that temporary compressed file is cleaned up."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            test_file = temp_env / "test.html"
            test_content = b"<html>Test</html>"
            test_file.write_bytes(test_content)

            storage.upload_file(test_file, "archives/test.html", compress=True)

            # Temp compressed file should be cleaned up
            temp_compressed = test_file.with_suffix('.html.gz')
            assert not temp_compressed.exists()

    # ==================== Download Tests ====================

    def test_download_file_success_uncompressed(self, temp_env):
        """Test successful file download without decompression."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            # Download file
            download_file = temp_env / "downloaded.html"
            success = storage.download_file("archives/test.html", download_file, decompress=False)

            assert success
            assert download_file.exists()
            mock_blob.download_to_filename.assert_called_once_with(str(download_file))

    def test_download_file_success_decompressed(self, temp_env):
        """Test successful file download with decompression."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            # Create a temporary compressed file to simulate download
            temp_compressed = temp_env / "temp.gz"
            with gzip.open(temp_compressed, 'wb') as f:
                f.write(b"<html>Test content</html>")

            # Mock the download to filename to create our test file
            def mock_download(filename):
                shutil.copy2(temp_compressed, filename)

            mock_blob.download_to_filename.side_effect = mock_download

            # Download file
            download_file = temp_env / "downloaded.html"
            success = storage.download_file("archives/test.html.gz", download_file, decompress=True)

            assert success
            assert download_file.exists()
            assert download_file.read_bytes() == b"<html>Test content</html>"

            # Temp file should be cleaned up
            temp_download = download_file.with_suffix('.html.gz')
            assert not temp_download.exists()

    def test_download_file_not_found(self, temp_env):
        """Test downloading non-existent file."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = False
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            download_file = temp_env / "downloaded.html"
            success = storage.download_file("archives/nonexistent.html", download_file)

            assert not success
            assert not download_file.exists()

    def test_download_file_creates_parent_directories(self, temp_env):
        """Test download creates parent directories."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            # Download to nested path
            download_file = temp_env / "nested" / "deep" / "downloaded.html"
            success = storage.download_file("archives/test.html", download_file)

            assert success
            assert download_file.parent.exists()

    # ==================== Stream Tests ====================

    def test_get_file_stream_success(self):
        """Test getting file stream successfully."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            stream = storage.get_file_stream("archives/test.html")

            mock_bucket.blob.assert_called_once_with("archives/test.html")
            mock_blob.open.assert_called_once_with('rb')
            assert stream == mock_blob.open.return_value

    # ==================== Existence Tests ====================

    def test_exists_true(self):
        """Test exists returns True for existing file."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            assert storage.exists("archives/test.html")
            mock_blob.exists.assert_called_once()

    def test_exists_false(self):
        """Test exists returns False for non-existent file."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = False
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            assert not storage.exists("archives/nonexistent.html")

    # ==================== Metadata Tests ====================

    def test_get_metadata_success_uncompressed(self):
        """Test getting metadata for existing uncompressed file."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_blob.size = 1024
            mock_blob.time_created = datetime.utcnow()
            mock_blob.storage_class = "STANDARD"
            mock_blob.content_type = "text/html"
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            metadata = storage.get_metadata("archives/test.html")

            assert metadata is not None
            assert metadata.path == "archives/test.html"
            assert metadata.size == 1024
            assert metadata.storage_class == "STANDARD"
            assert metadata.content_type == "text/html"
            assert metadata.compressed is False
            assert metadata.compression_ratio is None

    def test_get_metadata_success_compressed(self):
        """Test getting metadata for existing compressed file."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_blob.size = 512  # Compressed size
            mock_blob.time_created = datetime.utcnow()
            mock_blob.storage_class = "STANDARD"
            mock_blob.content_type = "text/html"
            mock_blob.metadata = {"compressed": "true", "original_size": "1024"}
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            metadata = storage.get_metadata("archives/test.html.gz")

            assert metadata is not None
            assert metadata.path == "archives/test.html.gz"
            assert metadata.size == 512
            assert metadata.compressed is True
            assert metadata.compression_ratio is not None
            assert abs(metadata.compression_ratio - 50.0) < 0.1  # (1024-512)/1024 * 100

    def test_get_metadata_not_found(self):
        """Test getting metadata for non-existent file."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = False
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            assert storage.get_metadata("archives/nonexistent.html") is None

    # ==================== Delete Tests ====================

    def test_delete_file_success(self):
        """Test successful file deletion."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            success = storage.delete_file("archives/test.html")

            assert success
            mock_blob.delete.assert_called_once()

    def test_delete_file_not_found(self):
        """Test deleting non-existent file."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = False
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            success = storage.delete_file("archives/nonexistent.html")

            assert success  # Returns True even if file doesn't exist
            mock_blob.delete.assert_not_called()

    # ==================== URL Generation Tests ====================

    def test_generate_access_url_default_expiration(self):
        """Test generating signed URL with default expiration."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.generate_signed_url.return_value = "https://signed-url"
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            url = storage.generate_access_url("archives/test.html")

            assert url == "https://signed-url"
            mock_blob.generate_signed_url.assert_called_once_with(
                version="v4",
                expiration=timedelta(days=7),
                method="GET"
            )

    def test_generate_access_url_custom_expiration(self):
        """Test generating signed URL with custom expiration."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.generate_signed_url.return_value = "https://signed-url"
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            expiration = timedelta(hours=24)
            url = storage.generate_access_url("archives/test.html", expiration)

            assert url == "https://signed-url"
            mock_blob.generate_signed_url.assert_called_once_with(
                version="v4",
                expiration=expiration,
                method="GET"
            )

    # ==================== File Listing Tests ====================

    def test_list_files_all(self):
        """Test listing all files."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            # Mock blobs
            mock_blob1 = Mock()
            mock_blob1.name = "archives/test1.html"
            mock_blob1.size = 1024
            mock_blob1.time_created = datetime.utcnow()
            mock_blob1.storage_class = "STANDARD"
            mock_blob1.content_type = "text/html"
            mock_blob1.exists.return_value = True

            mock_blob2 = Mock()
            mock_blob2.name = "archives/test2.html"
            mock_blob2.size = 2048
            mock_blob2.time_created = datetime.utcnow()
            mock_blob2.storage_class = "STANDARD"
            mock_blob2.content_type = "text/html"
            mock_blob2.exists.return_value = True

            mock_client.return_value.list_blobs.return_value = [mock_blob1, mock_blob2]

            storage = GCSFileStorage("test-bucket")

            files = storage.list_files()

            assert len(files) == 2
            assert files[0].path == "archives/test1.html"
            assert files[1].path == "archives/test2.html"

    def test_list_files_with_prefix(self):
        """Test listing files with prefix filter."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_blob = Mock()
            mock_blob.name = "archive1/test.html"
            mock_blob.size = 1024
            mock_blob.time_created = datetime.utcnow()
            mock_blob.storage_class = "STANDARD"
            mock_blob.content_type = "text/html"
            mock_blob.exists.return_value = True

            mock_client.return_value.list_blobs.return_value = [mock_blob]

            storage = GCSFileStorage("test-bucket")

            files = storage.list_files(prefix="archive1/")

            assert len(files) == 1
            assert files[0].path == "archive1/test.html"
            mock_client.return_value.list_blobs.assert_called_once_with(
                "test-bucket",
                prefix="archive1/",
                max_results=None
            )

    def test_list_files_with_limit(self):
        """Test listing files with limit."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_blob = Mock()
            mock_blob.name = "archives/test.html"
            mock_blob.size = 1024
            mock_blob.time_created = datetime.utcnow()
            mock_blob.storage_class = "STANDARD"
            mock_blob.content_type = "text/html"
            mock_blob.exists.return_value = True

            mock_client.return_value.list_blobs.return_value = [mock_blob]

            storage = GCSFileStorage("test-bucket")

            files = storage.list_files(limit=5)

            assert len(files) == 1
            mock_client.return_value.list_blobs.assert_called_once_with(
                "test-bucket",
                prefix="",
                max_results=5
            )

    # ==================== Lifecycle Policy Tests ====================

    def test_set_lifecycle_policy(self):
        """Test setting lifecycle policy."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_client.return_value.get_bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            storage.set_lifecycle_policy()

            # Verify lifecycle rules were added
            assert mock_bucket.add_lifecycle_delete_rule.called
            assert mock_bucket.add_lifecycle_set_storage_class_rule.called
            mock_bucket.patch.assert_called_once()

    # ==================== File Serving Tests ====================

    def test_serve_file_success(self):
        """Test serving file from GCS."""
        from fastapi.responses import StreamingResponse

        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_blob.open.return_value.__enter__.return_value = b"<html>Test</html>"
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            response = storage.serve_file("archives/test.html", "test.html", "text/html")

            assert isinstance(response, StreamingResponse)
            assert response.headers["Content-Disposition"] == 'attachment; filename="test.html"'

    def test_serve_file_not_found(self):
        """Test serving non-existent file from GCS."""
        from fastapi import HTTPException

        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = False
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            with pytest.raises(HTTPException) as exc_info:
                storage.serve_file("archives/nonexistent.html", "test.html")

            assert exc_info.value.status_code == 404
            assert "File not found in GCS" in exc_info.value.detail

    # ==================== Download to Temp Tests ====================

    def test_download_to_temp_success(self, temp_env):
        """Test download to temporary location."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            # Mock the download_file method
            with patch.object(GCSFileStorage, 'download_file') as mock_download:
                mock_download.return_value = True

                storage = GCSFileStorage("test-bucket")
                temp_path = storage.download_to_temp("archives/test.html")

                assert temp_path.suffix == ""  # No .gz for uncompressed
                mock_download.assert_called_once()

    def test_download_to_temp_compressed(self, temp_env):
        """Test download compressed file to temporary location."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = True
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            # Mock the download_file method
            with patch.object(GCSFileStorage, 'download_file') as mock_download:
                mock_download.return_value = True

                storage = GCSFileStorage("test-bucket")
                temp_path = storage.download_to_temp("archives/test.html.gz")

                assert temp_path.suffix == ".gz"  # Keeps .gz suffix
                mock_download.assert_called_once_with("archives/test.html.gz", temp_path, decompress=True)

    def test_download_to_temp_not_found(self):
        """Test download to temp for non-existent file."""
        with patch('storage.gcs_file_storage.storage.Client') as mock_client:
            mock_bucket = Mock()
            mock_blob = Mock()
            mock_blob.exists.return_value = False
            mock_bucket.blob.return_value = mock_blob
            mock_client.return_value.bucket.return_value = mock_bucket

            storage = GCSFileStorage("test-bucket")

            with pytest.raises(FileNotFoundError) as exc_info:
                storage.download_to_temp("archives/nonexistent.html")

            assert "File not found in GCS" in str(exc_info.value)