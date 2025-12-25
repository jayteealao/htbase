"""
Tests for InMemoryFileStorage.

Tests the fake storage implementation to ensure it works correctly
and provides the expected interface for unit tests.
"""

import gzip
import io
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

import pytest

from tests.fakes.storage import InMemoryFileStorage


class TestInMemoryFileStorage:
    """Test InMemoryFileStorage fake implementation."""

    def test_provider_name(self):
        """Test provider name is correct."""
        storage = InMemoryFileStorage()
        assert storage.provider_name == "memory"

    def test_supports_compression(self):
        """Test compression support flag."""
        storage = InMemoryFileStorage()
        assert storage.supports_compression is True

    def test_supports_signed_urls(self):
        """Test signed URLs support flag."""
        storage = InMemoryFileStorage()
        assert storage.supports_signed_urls is True

    # ==================== Upload Tests ====================

    def test_upload_file_success_uncompressed(self, temp_env):
        """Test successful file upload without compression."""
        storage = InMemoryFileStorage()

        # Create test file
        test_file = temp_env / "test.html"
        test_content = b"<html><body>Test content</body></html>"
        test_file.write_bytes(test_content)

        result = storage.upload_file(test_file, "archives/test.html", compress=False)

        assert result.success
        assert result.uri == "memory://archives/test.html"
        assert result.original_size == len(test_content)
        assert result.stored_size == len(test_content)
        assert result.compression_ratio is None
        assert result.error is None

    def test_upload_file_success_compressed(self, temp_env):
        """Test successful file upload with compression."""
        storage = InMemoryFileStorage()

        # Create test file
        test_file = temp_env / "test.html"
        test_content = b"<html><body>" + b"x" * 1000 + b"</body></html>"  # Larger content
        test_file.write_bytes(test_content)

        result = storage.upload_file(test_file, "archives/test.html", compress=True)

        assert result.success
        assert result.uri == "memory://archives/test.html"
        assert result.original_size == len(test_content)
        assert result.stored_size < result.original_size  # Should be compressed
        assert result.compression_ratio is not None
        assert result.compression_ratio > 0

    def test_upload_file_with_storage_class(self, temp_env):
        """Test upload with storage class specification."""
        storage = InMemoryFileStorage()

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
        metadata = storage.get_metadata("archives/test.html")
        assert metadata.storage_class == "STANDARD"

    def test_upload_file_local_read_failure(self, temp_env):
        """Test handling of local file read failure."""
        storage = InMemoryFileStorage()

        # Try to upload non-existent file
        non_existent = temp_env / "nonexistent.html"
        result = storage.upload_file(non_existent, "archives/test.html")

        assert not result.success
        assert result.original_size == 0
        assert result.stored_size == 0
        assert "Failed to read local file" in result.error

    def test_upload_file_configured_failure(self, temp_env):
        """Test configured failure for specific path."""
        storage = InMemoryFileStorage(fail_on_paths=["archives/fail.html"])

        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)

        result = storage.upload_file(test_file, "archives/fail.html")

        assert not result.success
        assert "Configured to fail for path" in result.error

    # ==================== Download Tests ====================

    def test_download_file_success_uncompressed(self, temp_env):
        """Test successful file download without decompression."""
        storage = InMemoryFileStorage()

        # Upload file without compression
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
        storage = InMemoryFileStorage()

        # Upload file with compression
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
        storage = InMemoryFileStorage()

        download_file = temp_env / "downloaded.html"
        success = storage.download_file("archives/nonexistent.html", download_file)

        assert not success
        assert not download_file.exists()

    def test_download_creates_parent_directories(self, temp_env):
        """Test download creates parent directories."""
        storage = InMemoryFileStorage()

        # Upload file
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
        storage = InMemoryFileStorage()

        test_file = temp_env / "test.html"
        test_content = b"<html><body>Stream test</body></html>"
        test_file.write_bytes(test_content)

        storage.upload_file(test_file, "archives/test.html", compress=False)

        stream = storage.get_file_stream("archives/test.html")
        content = stream.read()
        assert content == test_content

    def test_get_file_stream_compressed(self, temp_env):
        """Test getting file stream for compressed file."""
        storage = InMemoryFileStorage()

        test_file = temp_env / "test.html"
        test_content = b"<html><body>" + b"x" * 100 + b"</body></html>"
        test_file.write_bytes(test_content)

        storage.upload_file(test_file, "archives/test.html", compress=True)

        stream = storage.get_file_stream("archives/test.html")
        content = stream.read()
        assert content == test_content  # Should be decompressed automatically

    def test_get_file_stream_not_found(self):
        """Test getting stream for non-existent file."""
        storage = InMemoryFileStorage()

        with pytest.raises(FileNotFoundError):
            storage.get_file_stream("archives/nonexistent.html")

    # ==================== Existence Tests ====================

    def test_exists_true(self, temp_env):
        """Test exists returns True for existing file."""
        storage = InMemoryFileStorage()

        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)

        storage.upload_file(test_file, "archives/test.html")

        assert storage.exists("archives/test.html")

    def test_exists_false(self):
        """Test exists returns False for non-existent file."""
        storage = InMemoryFileStorage()

        assert not storage.exists("archives/nonexistent.html")

    # ==================== Metadata Tests ====================

    def test_get_metadata_success(self, temp_env):
        """Test getting metadata for existing file."""
        storage = InMemoryFileStorage()

        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)

        storage.upload_file(test_file, "archives/test.html", compress=True, storage_class="STANDARD")

        metadata = storage.get_metadata("archives/test.html")

        assert metadata is not None
        assert metadata.path == "archives/test.html"
        assert metadata.size > 0
        assert metadata.created_at is not None
        assert metadata.storage_class == "STANDARD"
        assert metadata.content_type == "text/html"
        assert metadata.compressed is True
        assert metadata.compression_ratio is not None
        assert metadata.compression_ratio > 0

    def test_get_metadata_not_found(self):
        """Test getting metadata for non-existent file."""
        storage = InMemoryFileStorage()

        assert storage.get_metadata("archives/nonexistent.html") is None

    def test_content_type_detection(self, temp_env):
        """Test content type detection from file extension."""
        storage = InMemoryFileStorage()

        # Test various file types
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

    # ==================== Delete Tests ====================

    def test_delete_file_success(self, temp_env):
        """Test successful file deletion."""
        storage = InMemoryFileStorage()

        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)

        storage.upload_file(test_file, "archives/test.html")
        assert storage.exists("archives/test.html")

        success = storage.delete_file("archives/test.html")
        assert success
        assert not storage.exists("archives/test.html")
        assert storage.get_metadata("archives/test.html") is None

    def test_delete_file_not_found(self):
        """Test deleting non-existent file."""
        storage = InMemoryFileStorage()

        success = storage.delete_file("archives/nonexistent.html")
        assert not success

    # ==================== URL Generation Tests ====================

    def test_generate_access_url_default_expiration(self):
        """Test generating access URL with default expiration."""
        storage = InMemoryFileStorage()

        url = storage.generate_access_url("archives/test.html")

        assert url == "memory://archives/test.html"
        assert "expires=" in url

    def test_generate_access_url_custom_expiration(self):
        """Test generating access URL with custom expiration."""
        storage = InMemoryFileStorage()

        expiration = timedelta(hours=24)
        url = storage.generate_access_url("archives/test.html", expiration)

        assert "memory://archives/test.html" in url
        assert "expires=" in url

    # ==================== File Serving Tests ====================

    def test_serve_file_success(self, temp_env):
        """Test serving file as streaming response."""
        from fastapi.responses import StreamingResponse

        storage = InMemoryFileStorage()

        test_file = temp_env / "test.html"
        test_content = b"<html><body>Serve test</body></html>"
        test_file.write_bytes(test_content)

        storage.upload_file(test_file, "archives/test.html")

        response = storage.serve_file("archives/test.html", "test.html", "text/html")

        assert isinstance(response, StreamingResponse)
        assert response.headers["Content-Disposition"] == "attachment; filename=test.html"

    def test_serve_file_not_found(self):
        """Test serving non-existent file."""
        storage = InMemoryFileStorage()

        with pytest.raises(FileNotFoundError):
            storage.serve_file("archives/nonexistent.html", "test.html")

    # ==================== File Listing Tests ====================

    def test_list_files_all(self, temp_env):
        """Test listing all files."""
        storage = InMemoryFileStorage()

        # Upload multiple files
        for i in range(3):
            test_file = temp_env / f"test{i}.html"
            test_file.write_bytes(f"<html>Test {i}</html>".encode())
            storage.upload_file(test_file, f"archives/test{i}.html")

        files = storage.list_files()

        assert len(files) == 3
        # Should be sorted by created_at descending
        assert files[0].path == "archives/test2.html"
        assert files[1].path == "archives/test1.html"
        assert files[2].path == "archives/test0.html"

    def test_list_files_with_prefix(self, temp_env):
        """Test listing files with prefix filter."""
        storage = InMemoryFileStorage()

        # Upload files with different prefixes
        test_file = temp_env / "test1.html"
        test_file.write_bytes(b"<html>Test 1</html>")
        storage.upload_file(test_file, "archive1/test1.html")

        test_file2 = temp_env / "test2.html"
        test_file2.write_bytes(b"<html>Test 2</html>")
        storage.upload_file(test_file2, "archive2/test2.html")

        files = storage.list_files(prefix="archive1/")

        assert len(files) == 1
        assert files[0].path == "archive1/test1.html"

    def test_list_files_with_limit(self, temp_env):
        """Test listing files with limit."""
        storage = InMemoryFileStorage()

        # Upload multiple files
        for i in range(5):
            test_file = temp_env / f"test{i}.html"
            test_file.write_bytes(f"<html>Test {i}</html>".encode())
            storage.upload_file(test_file, f"archives/test{i}.html")

        files = storage.list_files(limit=3)

        assert len(files) == 3
        # Should get the 3 most recent files

    def test_list_files_empty(self):
        """Test listing files when storage is empty."""
        storage = InMemoryFileStorage()

        files = storage.list_files()

        assert len(files) == 0

    # ==================== Helper Methods Tests ====================

    def test_get_file_count(self, temp_env):
        """Test getting file count."""
        storage = InMemoryFileStorage()

        assert storage.get_file_count() == 0

        # Upload files
        for i in range(3):
            test_file = temp_env / f"test{i}.html"
            test_file.write_bytes(f"<html>Test {i}</html>".encode())
            storage.upload_file(test_file, f"archives/test{i}.html")

        assert storage.get_file_count() == 3

    def test_clear(self, temp_env):
        """Test clearing all files."""
        storage = InMemoryFileStorage()

        # Upload files
        test_file = temp_env / "test.html"
        test_file.write_bytes(b"<html>Test</html>")
        storage.upload_file(test_file, "archives/test.html")

        assert storage.get_file_count() == 1
        assert storage.exists("archives/test.html")

        storage.clear()

        assert storage.get_file_count() == 0
        assert not storage.exists("archives/test.html")

    def test_get_raw_content(self, temp_env):
        """Test getting raw (possibly compressed) content."""
        storage = InMemoryFileStorage()

        test_file = temp_env / "test.html"
        test_content = b"<html>Test</html>"
        test_file.write_bytes(test_content)

        storage.upload_file(test_file, "archives/test.html", compress=True)

        raw_content = storage.get_raw_content("archives/test.html")

        assert raw_content is not None
        assert raw_content != test_content  # Should be compressed
        # Verify it's gzip compressed
        decompressed = gzip.decompress(raw_content)
        assert decompressed == test_content

    def test_get_raw_content_not_found(self):
        """Test getting raw content for non-existent file."""
        storage = InMemoryFileStorage()

        assert storage.get_raw_content("archives/nonexistent.html") is None

    # ==================== Compression Quality Tests ====================

    def test_compression_quality(self, temp_env):
        """Test that compression actually reduces size for compressible content."""
        storage = InMemoryFileStorage()

        # Create highly compressible content (repeated text)
        test_file = temp_env / "test.html"
        compressible_content = b"<html><body>" + b"Hello World! " * 100 + b"</body></html>"
        test_file.write_bytes(compressible_content)

        result = storage.upload_file(test_file, "archives/test.html", compress=True)

        # Compressed size should be significantly smaller
        assert result.stored_size < result.original_size * 0.3  # At least 70% compression
        assert result.compression_ratio > 70

    def test_compression_for_already_compressed_content(self, temp_env):
        """Test compression behavior for already compressed content."""
        storage = InMemoryFileStorage()

        test_file = temp_env / "test.jpg"
        # Simulate JPEG content (already compressed)
        already_compressed = bytes(range(256)) * 10  # Random-looking bytes
        test_file.write_bytes(already_compressed)

        result = storage.upload_file(test_file, "archives/test.jpg", compress=True)

        # Compression might not help much for already compressed content
        assert result.stored_size >= result.original_size * 0.95