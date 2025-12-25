"""
Tests for LocalFileStorage.

Tests local filesystem storage implementation using temporary directories
to avoid affecting the actual filesystem.
"""

import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

import pytest

from storage.local_file_storage import LocalFileStorage


class TestLocalFileStorage:
    """Test LocalFileStorage implementation."""

    def test_provider_name(self, temp_env):
        """Test provider name is correct."""
        storage = LocalFileStorage(temp_env / "storage")
        assert storage.provider_name == "local"

    def test_supports_compression(self, temp_env):
        """Test compression support flag."""
        storage = LocalFileStorage(temp_env / "storage")
        assert storage.supports_compression is True

    def test_supports_signed_urls(self, temp_env):
        """Test signed URLs support flag."""
        storage = LocalFileStorage(temp_env / "storage")
        assert storage.supports_signed_urls is False

    # ==================== Initialization Tests ====================

    def test_initialization_creates_root_dir(self, temp_env):
        """Test that initialization creates root directory."""
        storage_dir = temp_env / "test_storage"
        assert not storage_dir.exists()

        storage = LocalFileStorage(storage_dir)

        assert storage_dir.exists()
        assert storage.root_dir == storage_dir.resolve()

    def test_initialization_with_existing_dir(self, temp_env):
        """Test initialization with existing directory."""
        storage_dir = temp_env / "existing_storage"
        storage_dir.mkdir(parents=True)

        storage = LocalFileStorage(storage_dir)

        assert storage.root_dir == storage_dir.resolve()

    def test_initialization_with_base_url(self, temp_env):
        """Test initialization with base URL."""
        storage = LocalFileStorage(temp_env / "storage", base_url="http://localhost:8000/files")
        assert storage.base_url == "http://localhost:8000/files"

    # ==================== Upload Tests ====================

    def test_upload_file_success_uncompressed(self, temp_env):
        """Test successful file upload without compression."""
        storage = LocalFileStorage(temp_env / "storage")

        # Create test file
        test_file = temp_env / "test.html"
        test_content = b"<html><body>Test content</body></html>"
        test_file.write_bytes(test_content)

        result = storage.upload_file(test_file, "archives/test.html", compress=False)

        assert result.success
        assert result.original_size == len(test_content)
        assert result.stored_size == len(test_content)
        assert result.compression_ratio is None
        assert result.error is None

        # Check file was actually created
        stored_file = storage.root_dir / "archives" / "test.html"
        assert stored_file.exists()
        assert stored_file.read_bytes() == test_content

    def test_upload_file_success_compressed(self, temp_env):
        """Test successful file upload with compression."""
        storage = LocalFileStorage(temp_env / "storage")

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

        # Check compressed file was created
        stored_file = storage.root_dir / "archives" / "test.html.gz"
        assert stored_file.exists()
        assert stored_file.suffix == ".gz"

        # Verify content is compressed
        with gzip.open(stored_file, 'rb') as f:
            decompressed = f.read()
        assert decompressed == test_content

    def test_upload_file_with_storage_class(self, temp_env):
        """Test upload with storage class specification."""
        storage = LocalFileStorage(temp_env / "storage")

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
        # Storage class is stored in metadata but not used in local storage

    def test_upload_file_creates_parent_directories(self, temp_env):
        """Test upload creates parent directories."""
        storage = LocalFileStorage(temp_env / "storage")

        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)

        result = storage.upload_file(test_file, "deep/nested/path/test.html")

        assert result.success

        # Check directories were created
        stored_file = storage.root_dir / "deep" / "nested" / "path" / "test.html"
        assert stored_file.exists()
        assert stored_file.parent.exists()

    def test_upload_file_source_not_found(self, temp_env):
        """Test upload with non-existent source file."""
        storage = LocalFileStorage(temp_env / "storage")

        non_existent = temp_env / "nonexistent.html"
        result = storage.upload_file(non_existent, "archives/test.html")

        assert not result.success
        assert result.original_size == 0
        assert result.stored_size == 0
        assert "Source file not found" in result.error

    def test_upload_file_with_base_url_uri(self, temp_env):
        """Test upload generates correct URI with base URL."""
        storage = LocalFileStorage(
            temp_env / "storage",
            base_url="http://localhost:8000/files"
        )

        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)

        result = storage.upload_file(test_file, "archives/test.html", compress=False)

        assert result.success
        assert result.uri == "http://localhost:8000/files/archives/test.html"

    def test_upload_file_without_base_url_uri(self, temp_env):
        """Test upload generates correct URI without base URL."""
        storage = LocalFileStorage(temp_env / "storage")

        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)

        result = storage.upload_file(test_file, "archives/test.html", compress=False)

        assert result.success
        assert result.uri.startswith("file:///")
        assert "storage/archives/test.html" in result.uri

    # ==================== Download Tests ====================

    def test_download_file_success_uncompressed(self, temp_env):
        """Test successful file download without decompression."""
        storage = LocalFileStorage(temp_env / "storage")

        # Upload file first
        test_file = temp_env / "test.html"
        test_content = b"<html><body>Test</body></html>"
        test_file.write_bytes(test_content)
        storage.upload_file(test_file, "archives/test.html", compress=False)

        # Download to different location
        download_file = temp_env / "downloaded.html"
        success = storage.download_file("archives/test.html", download_file, decompress=False)

        assert success
        assert download_file.exists()
        assert download_file.read_bytes() == test_content

    def test_download_file_success_decompressed(self, temp_env):
        """Test successful file download with decompression."""
        storage = LocalFileStorage(temp_env / "storage")

        # Upload compressed file
        test_file = temp_env / "test.html"
        test_content = b"<html><body>" + b"x" * 100 + b"</body></html>"
        test_file.write_bytes(test_content)
        storage.upload_file(test_file, "archives/test.html", compress=True)

        # Download with decompression
        download_file = temp_env / "downloaded.html"
        success = storage.download_file("archives/test.html", download_file, decompress=True)

        assert success
        assert download_file.exists()
        assert download_file.read_bytes() == test_content  # Should be decompressed to original

    def test_download_file_not_found(self, temp_env):
        """Test downloading non-existent file."""
        storage = LocalFileStorage(temp_env / "storage")

        download_file = temp_env / "downloaded.html"
        success = storage.download_file("archives/nonexistent.html", download_file)

        assert not success
        assert not download_file.exists()

    def test_download_compressed_without_decompression(self, temp_env):
        """Test downloading compressed file without decompression."""
        storage = LocalFileStorage(temp_env / "storage")

        # Upload compressed file
        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)
        storage.upload_file(test_file, "archives/test.html", compress=True)

        # Download without decompression
        download_file = temp_env / "downloaded.html.gz"
        success = storage.download_file("archives/test.html.gz", download_file, decompress=False)

        assert success
        assert download_file.exists()
        assert download_file.suffix == ".gz"

    def test_download_creates_parent_directories(self, temp_env):
        """Test download creates parent directories."""
        storage = LocalFileStorage(temp_env / "storage")

        # Upload file first
        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)
        storage.upload_file(test_file, "archives/test.html", compress=False)

        # Download to nested path
        download_file = temp_env / "nested" / "deep" / "downloaded.html"
        success = storage.download_file("archives/test.html", download_file)

        assert success
        assert download_file.exists()
        assert download_file.read_bytes() == test_content

    # ==================== Stream Tests ====================

    def test_get_file_stream_uncompressed(self, temp_env):
        """Test getting file stream for uncompressed file."""
        storage = LocalFileStorage(temp_env / "storage")

        test_file = temp_env / "test.html"
        test_content = b"<html><body>Stream test</body></html>"
        test_file.write_bytes(test_content)
        storage.upload_file(test_file, "archives/test.html", compress=False)

        stream = storage.get_file_stream("archives/test.html")
        content = stream.read()
        assert content == test_content
        stream.close()

    def test_get_file_stream_compressed(self, temp_env):
        """Test getting file stream for compressed file."""
        storage = LocalFileStorage(temp_env / "storage")

        test_file = temp_env / "test.html"
        test_content = b"<html><body>" + b"x" * 100 + b"</body></html>"
        test_file.write_bytes(test_content)
        storage.upload_file(test_file, "archives/test.html", compress=True)

        stream = storage.get_file_stream("archives/test.html.gz")
        content = stream.read()
        # Should be compressed content
        assert content != test_content
        stream.close()

        # Verify it's gzip compressed
        decompressed = gzip.decompress(content)
        assert decompressed == test_content

    def test_get_file_stream_not_found(self, temp_env):
        """Test getting stream for non-existent file."""
        storage = LocalFileStorage(temp_env / "storage")

        with pytest.raises(FileNotFoundError):
            storage.get_file_stream("archives/nonexistent.html")

    # ==================== Existence Tests ====================

    def test_exists_true(self, temp_env):
        """Test exists returns True for existing file."""
        storage = LocalFileStorage(temp_env / "storage")

        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)
        storage.upload_file(test_file, "archives/test.html")

        assert storage.exists("archives/test.html")

    def test_exists_false(self, temp_env):
        """Test exists returns False for non-existent file."""
        storage = LocalFileStorage(temp_env / "storage")

        assert not storage.exists("archives/nonexistent.html")

    # ==================== Metadata Tests ====================

    def test_get_metadata_success_uncompressed(self, temp_env):
        """Test getting metadata for existing uncompressed file."""
        storage = LocalFileStorage(temp_env / "storage")

        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)
        storage.upload_file(test_file, "archives/test.html", compress=False)

        metadata = storage.get_metadata("archives/test.html")

        assert metadata is not None
        assert metadata.path == "archives/test.html"
        assert metadata.size == len(test_content)
        assert metadata.created_at is not None
        assert metadata.storage_class == "LOCAL"
        assert metadata.content_type == "text/html"
        assert metadata.compressed is False
        assert metadata.compression_ratio is None

    def test_get_metadata_success_compressed(self, temp_env):
        """Test getting metadata for existing compressed file."""
        storage = LocalFileStorage(temp_env / "storage")

        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)
        storage.upload_file(test_file, "archives/test.html", compress=True)

        metadata = storage.get_metadata("archives/test.html.gz")

        assert metadata is not None
        assert metadata.path == "archives/test.html.gz"
        assert metadata.size > 0
        assert metadata.compressed is True
        assert metadata.content_type == "text/html"

    def test_get_metadata_not_found(self, temp_env):
        """Test getting metadata for non-existent file."""
        storage = LocalFileStorage(temp_env / "storage")

        assert storage.get_metadata("archives/nonexistent.html") is None

    def test_content_type_detection_various_extensions(self, temp_env):
        """Test content type detection from file extension."""
        storage = LocalFileStorage(temp_env / "storage")

        test_cases = [
            ("test.html", "text/html"),
            ("test.pdf", "application/pdf"),
            ("test.png", "image/png"),
            ("test.jpg", "image/jpeg"),
            ("test.jpeg", "image/jpeg"),
            ("test.json", "application/json"),
            ("test.txt", "text/plain"),
            ("test.unknown", "application/octet-stream"),
        ]

        for filename, expected_type in test_cases:
            test_file = temp_env / filename
            test_content = b"test content"
            test_file.write_bytes(test_content)

            storage.upload_file(test_file, f"archives/{filename}")

            metadata = storage.get_metadata(f"archives/{filename}")
            assert metadata.content_type == expected_type

    def test_content_type_detection_for_compressed_files(self, temp_env):
        """Test content type detection for compressed files."""
        storage = LocalFileStorage(temp_env / "storage")

        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)

        storage.upload_file(test_file, "archives/test.html", compress=True)

        metadata = storage.get_metadata("archives/test.html.gz")
        assert metadata.content_type == "text/html"  # Should detect from inner extension

    # ==================== Delete Tests ====================

    def test_delete_file_success(self, temp_env):
        """Test successful file deletion."""
        storage = LocalFileStorage(temp_env / "storage")

        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)
        storage.upload_file(test_file, "archives/test.html")

        assert storage.exists("archives/test.html")

        success = storage.delete_file("archives/test.html")
        assert success
        assert not storage.exists("archives/test.html")

    def test_delete_file_not_found(self, temp_env):
        """Test deleting non-existent file."""
        storage = LocalFileStorage(temp_env / "storage")

        success = storage.delete_file("archives/nonexistent.html")
        assert success  # Local storage returns True even if file doesn't exist

    # ==================== URL Generation Tests ====================

    def test_generate_access_url_with_base_url(self, temp_env):
        """Test generating access URL with base URL."""
        storage = LocalFileStorage(
            temp_env / "storage",
            base_url="http://localhost:8000/files"
        )

        url = storage.generate_access_url("archives/test.html")

        assert url == "http://localhost:8000/files/archives/test.html"

    def test_generate_access_url_without_base_url(self, temp_env):
        """Test generating access URL without base URL."""
        storage = LocalFileStorage(temp_env / "storage")

        # Upload a file first
        test_file = temp_env / "test.html"
        test_file.write_bytes(b"<html>Test</html>")
        storage.upload_file(test_file, "archives/test.html")

        url = storage.generate_access_url("archives/test.html")

        assert url.startswith("file:///")
        assert "storage/archives/test.html" in url

    # ==================== File Serving Tests ====================

    def test_serve_file_success(self, temp_env):
        """Test serving file as FileResponse."""
        from fastapi.responses import FileResponse

        storage = LocalFileStorage(temp_env / "storage")

        test_file = temp_env / "test.html"
        test_content = b"<html><body>Serve test</body></html>"
        test_file.write_bytes(test_content)
        storage.upload_file(test_file, "archives/test.html")

        response = storage.serve_file("archives/test.html", "test.html", "text/html")

        assert isinstance(response, FileResponse)
        assert response.media_type == "text/html"

    def test_serve_file_not_found(self, temp_env):
        """Test serving non-existent file."""
        from fastapi import HTTPException

        storage = LocalFileStorage(temp_env / "storage")

        with pytest.raises(HTTPException) as exc_info:
            storage.serve_file("archives/nonexistent.html", "test.html")

        assert exc_info.value.status_code == 404
        assert "File not found" in exc_info.value.detail

    # ==================== File Listing Tests ====================

    def test_list_files_all(self, temp_env):
        """Test listing all files."""
        storage = LocalFileStorage(temp_env / "storage")

        # Upload multiple files
        for i in range(3):
            test_file = temp_env / f"test{i}.html"
            test_content = f"<html>Test {i}</html>".encode()
            test_file.write_bytes(test_content)
            storage.upload_file(test_file, f"archives/test{i}.html")

        files = storage.list_files()

        assert len(files) == 3
        # Check that all files are listed
        paths = [f.path for f in files]
        assert "archives/test0.html" in paths
        assert "archives/test1.html" in paths
        assert "archives/test2.html" in paths

    def test_list_files_with_prefix(self, temp_env):
        """Test listing files with prefix filter."""
        storage = LocalFileStorage(temp_env / "storage")

        # Upload files with different prefixes
        test_file1 = temp_env / "test1.html"
        test_file1.write_bytes(b"<html>Test 1</html>")
        storage.upload_file(test_file1, "archive1/test1.html")

        test_file2 = temp_env / "test2.html"
        test_file2.write_bytes(b"<html>Test 2</html>")
        storage.upload_file(test_file2, "archive2/test2.html")

        files = storage.list_files(prefix="archive1/")

        assert len(files) == 1
        assert files[0].path == "archive1/test1.html"

    def test_list_files_with_limit(self, temp_env):
        """Test listing files with limit."""
        storage = LocalFileStorage(temp_env / "storage")

        # Upload multiple files
        for i in range(5):
            test_file = temp_env / f"test{i}.html"
            test_file.write_bytes(f"<html>Test {i}</html>".encode())
            storage.upload_file(test_file, f"archives/test{i}.html")

        files = storage.list_files(limit=3)

        assert len(files) == 3

    def test_list_files_empty(self, temp_env):
        """Test listing files when storage is empty."""
        storage = LocalFileStorage(temp_env / "storage")

        files = storage.list_files()

        assert len(files) == 0

    # ==================== Download to Temp Tests ====================

    def test_download_to_temp_success(self, temp_env):
        """Test download to temporary location."""
        storage = LocalFileStorage(temp_env / "storage")

        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)
        storage.upload_file(test_file, "archives/test.html")

        temp_path = storage.download_to_temp("archives/test.html")

        assert temp_path.exists()
        assert temp_path.read_bytes() == test_content

    def test_download_to_temp_not_found(self, temp_env):
        """Test download to temp for non-existent file."""
        storage = LocalFileStorage(temp_env / "storage")

        with pytest.raises(FileNotFoundError):
            storage.download_to_temp("archives/nonexistent.html")