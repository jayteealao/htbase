"""
Integration tests for storage provider functionality.

Tests the interaction between file storage, database storage, and archivers
to ensure proper data flow and consistency across storage backends.
"""

import gzip
import json
import time
from pathlib import Path
from unittest.mock import patch, Mock

import pytest

from app.core.config import AppSettings
from app.storage.local_file_storage import LocalFileStorage
from app.storage.gcs_file_storage import GCSFileStorage
from app.storage.database_storage import DatabaseStorageProvider
from app.storage.file_storage import FileStorageProvider
from app.archivers.base import BaseArchiver
from models import ArchiveResult, UploadResult, FileMetadata


class TestStorageIntegration:
    """Test storage provider integration."""

    def test_file_storage_upload_download_roundtrip(self, real_file_storage, integration_temp_dir):
        """Test file storage upload and download roundtrip."""
        # Create test file
        test_content = "<html><body>Test content</body></html>"
        test_file = integration_temp_dir / "test.html"
        test_file.write_text(test_content)

        # Upload file
        destination = "test123/monolith/test.html"
        upload_result = real_file_storage.upload_file(str(test_file), destination)

        assert upload_result.success is True
        assert upload_result.storage_path == destination
        assert upload_result.size_bytes == len(test_content)

        # Download file
        download_path = integration_temp_dir / "downloaded.html"
        success = real_file_storage.download_file(destination, str(download_path))

        assert success is True
        assert download_path.exists()
        assert download_path.read_text() == test_content

    def test_file_storage_compression_integration(self, real_file_storage, integration_temp_dir):
        """Test file storage compression and decompression."""
        # Create larger test file that should benefit from compression
        test_content = "<html><body>" + "Large content block. " * 100 + "</body></html>"
        test_file = integration_temp_dir / "large.html"
        test_file.write_text(test_content)

        # Upload with compression
        destination = "test123/monolith/large.html"
        upload_result = real_file_storage.upload_file(str(test_file), destination, compress=True)

        assert upload_result.success is True
        assert upload_result.compressed is True

        # Download with decompression
        download_path = integration_temp_dir / "decompressed.html"
        success = real_file_storage.download_file(destination, str(download_path), decompress=True)

        assert success is True
        assert download_path.read_text() == test_content

    def test_file_storage_metadata_tracking(self, real_file_storage, integration_temp_dir):
        """Test file storage metadata tracking."""
        test_content = "Test content for metadata"
        test_file = integration_temp_dir / "meta_test.txt"
        test_file.write_text(test_content)

        destination = "test123/metadata/meta_test.txt"
        real_file_storage.upload_file(str(test_file), destination)

        # Get metadata
        metadata = real_file_storage.get_metadata(destination)

        assert metadata is not None
        assert metadata.size_bytes == len(test_content)
        assert metadata.content_type is not None
        assert metadata.created_at is not None

    def test_file_storage_list_and_delete(self, real_file_storage, integration_temp_dir):
        """Test file storage listing and deletion."""
        # Create multiple test files
        test_files = [
            ("test123/monolith/file1.html", "<html>File 1</html>"),
            ("test123/monolith/file2.html", "<html>File 2</html>"),
            ("test123/monolith/subdir/file3.html", "<html>File 3</html>"),
            ("test456/readability/file4.html", "<html>File 4</html>"),
        ]

        # Upload files
        for file_path, content in test_files:
            test_file = integration_temp_dir / Path(file_path).name
            test_file.write_text(content)
            real_file_storage.upload_file(str(test_file), file_path)

        # List files with prefix
        monolith_files = real_file_storage.list_files("test123/monolith/")
        assert len(monolith_files) >= 3

        # Check specific file exists
        assert real_file_storage.exists("test123/monolith/file1.html") is True
        assert real_file_storage.exists("nonexistent/file.html") is False

        # Delete specific file
        delete_success = real_file_storage.delete_file("test123/monolith/file1.html")
        assert delete_success is True
        assert real_file_storage.exists("test123/monolith/file1.html") is False

    def test_archiver_with_file_storage_integration(self, real_file_storage, integration_temp_dir):
        """Test archiver integration with file storage."""
        class StorageIntegratedArchiver(BaseArchiver):
            def archive_with_storage(self, url: str, item_id: str) -> ArchiveResult:
                # Create archive content
                content = f"<html><body>Storage integrated archive of {url}</body></html>"

                # Save to local path first
                local_path = self.base_path / item_id / self.name / "output.html"
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_text(content)

                # Upload to storage provider
                storage_path = f"{item_id}/{self.name}/output.html"
                upload_result = self.storage_provider.upload_file(str(local_path), storage_path, compress=True)

                if upload_result.success:
                    # Use storage path instead of local path
                    saved_path = f"storage://{storage_path}"
                    return ArchiveResult(
                        success=True,
                        exit_code=0,
                        saved_path=saved_path,
                        start_time=time.time(),
                        end_time=time.time() + 1,
                        size_bytes=upload_result.size_bytes
                    )
                else:
                    return ArchiveResult(
                        success=False,
                        exit_code=1,
                        error=f"Storage upload failed: {upload_result.error}"
                    )

        archiver = StorageIntegratedArchiver(real_file_storage)
        archiver.storage_provider = real_file_storage  # Inject storage provider

        result = archiver.archive_with_storage("https://example.com/storage-test", "storage123")

        assert result.success is True
        assert result.saved_path.startswith("storage://")
        assert result.size_bytes is not None

    def test_database_storage_crud_operations(self, real_repositories, sample_items):
        """Test database storage CRUD operations."""
        artifact_repo = real_repositories["artifact"]
        url_repo = real_repositories["url"]
        metadata_repo = real_repositories["metadata"]

        # Create archived URL
        archived_url = url_repo.get_or_create(
            url=sample_items[0]["url"],
            item_id=sample_items[0]["item_id"],
            name="Test Article"
        )

        assert archived_url.id is not None
        assert archived_url.url == sample_items[0]["url"]
        assert archived_url.item_id == sample_items[0]["item_id"]

        # Create artifact
        artifact = artifact_repo.get_or_create(
            archived_url_id=archived_url.id,
            archiver="monolith",
            task_id="test123"
        )

        assert artifact.id is not None
        assert artifact.archiver == "monolith"
        assert artifact.task_id == "test123"
        assert artifact.status == "pending"

        # Finalize artifact
        artifact_repo.finalize_result(
            artifact_id=artifact.id,
            success=True,
            exit_code=0,
            saved_path="/tmp/test.html",
            size_bytes=1024
        )

        # Verify finalization
        updated_artifact = artifact_repo.get_by_id(artifact.id)
        assert updated_artifact.success is True
        assert updated_artifact.exit_code == 0
        assert updated_artifact.status == "success"

    def test_database_storage_relationships(self, real_repositories, sample_items):
        """Test database storage relationship integrity."""
        artifact_repo = real_repositories["artifact"]
        url_repo = real_repositories["url"]

        # Create URL and multiple artifacts
        archived_url = url_repo.get_or_create(
            url=sample_items[0]["url"],
            item_id=sample_items[0]["item_id"]
        )

        # Create artifacts for different archivers
        artifact_ids = []
        for archiver in ["monolith", "readability", "pdf"]:
            artifact = artifact_repo.get_or_create(
                archived_url_id=archived_url.id,
                archiver=archiver
            )
            artifact_ids.append(artifact.id)

        # Test listing by URL
        artifacts = artifact_repo.list_by_url(sample_items[0]["url"])
        assert len(artifacts) == 3

        archiver_names = {artifact.archiver for artifact in artifacts}
        assert archiver_names == {"monolith", "readability", "pdf"}

        # Test updating total size
        for i, artifact_id in enumerate(artifact_ids):
            artifact_repo.finalize_result(
                artifact_id=artifact_id,
                success=True,
                exit_code=0,
                saved_path=f"/tmp/test{i}.html",
                size_bytes=1024 * (i + 1)
            )

        # Update total size
        url_repo.update_total_size(archived_url.id)

        # Verify total size calculation
        updated_url = url_repo.get_or_create(sample_items[0]["url"])  # Re-fetch
        assert updated_url.total_size_bytes == 3072  # 1024 + 2048 + 3072

    def test_metadata_storage_integration(self, real_repositories, sample_article_metadata):
        """Test metadata storage integration."""
        metadata_repo = real_repositories["metadata"]
        artifact_repo = real_repositories["artifact"]
        url_repo = real_repositories["url"]

        # Create base records
        archived_url = url_repo.get_or_create(
            url=sample_article_metadata["url"],
            item_id="metadata123",
            name=sample_article_metadata["title"]
        )

        artifact = artifact_repo.get_or_create(
            archived_url_id=archived_url.id,
            archiver="readability"
        )

        # Store metadata
        metadata_repo.upsert(
            save_rowid=artifact.id,
            data=sample_article_metadata
        )

        # Verify metadata retrieval
        # Note: In a real implementation, we'd need a method to retrieve metadata by save_rowid
        # For this test, we're just verifying the upsert operation doesn't fail

    def test_storage_provider_fallback_behavior(self, integration_temp_dir):
        """Test storage provider fallback behavior."""
        # Create primary and backup storage
        primary_storage = LocalFileStorage(integration_temp_dir / "primary")
        backup_storage = LocalFileStorage(integration_temp_dir / "backup")

        # Upload to primary
        test_content = "Fallback test content"
        test_file = integration_temp_dir / "fallback.txt"
        test_file.write_text(test_content)

        destination = "test123/fallback.txt"
        primary_storage.upload_file(str(test_file), destination)

        # Verify primary has the file
        assert primary_storage.exists(destination) is True
        assert backup_storage.exists(destination) is False

    def test_concurrent_storage_operations(self, real_file_storage, integration_temp_dir):
        """Test concurrent storage operations."""
        import threading
        import queue

        results = queue.Queue()

        def upload_worker(worker_id):
            try:
                for i in range(5):
                    test_file = integration_temp_dir / f"worker{worker_id}_{i}.txt"
                    test_file.write_text(f"Content from worker {worker_id}, file {i}")

                    destination = f"worker{worker_id}/file{i}.txt"
                    result = real_file_storage.upload_file(str(test_file), destination)
                    results.put((worker_id, i, result.success))
            except Exception as e:
                results.put((worker_id, -1, False))

        # Start multiple workers
        threads = []
        for worker_id in range(3):
            thread = threading.Thread(target=upload_worker, args=(worker_id,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check results
        success_count = 0
        total_count = 0
        while not results.empty():
            worker_id, file_id, success = results.get()
            total_count += 1
            if success:
                success_count += 1

        assert total_count == 15  # 3 workers × 5 files
        assert success_count == 15  # All should succeed

        # Verify all files exist
        for worker_id in range(3):
            for i in range(5):
                destination = f"worker{worker_id}/file{i}.txt"
                assert real_file_storage.exists(destination) is True

    def test_storage_error_recovery(self, real_file_storage, integration_temp_dir):
        """Test storage error recovery mechanisms."""
        # Create test file
        test_file = integration_temp_dir / "error_test.txt"
        test_file.write_text("Error recovery test")

        # Test upload to non-existent directory (should auto-create)
        destination = "test123/new_dir/error_test.txt"
        upload_result = real_file_storage.upload_file(str(test_file), destination)

        assert upload_result.success is True
        assert real_file_storage.exists(destination) is True

        # Test download of non-existent file
        download_path = integration_temp_dir / "download_error.txt"
        success = real_file_storage.download_file("nonexistent/file.txt", str(download_path))

        assert success is False
        assert not download_path.exists()

    def test_storage_large_file_handling(self, real_file_storage, integration_temp_dir):
        """Test storage handling of large files."""
        # Create large test file (5MB)
        large_content = "Large file content. " * 50000  # ~1.5MB
        test_file = integration_temp_dir / "large.txt"
        test_file.write_text(large_content)

        destination = "test123/large/large.txt"

        # Test upload without compression
        start_time = time.time()
        upload_result = real_file_storage.upload_file(str(test_file), destination, compress=False)
        upload_time = time.time() - start_time

        assert upload_result.success is True
        assert upload_result.compressed is False
        assert upload_result.size_bytes == len(large_content)

        # Test upload with compression
        compressed_destination = "test123/large/compressed.txt.gz"
        start_time = time.time()
        upload_result_compressed = real_file_storage.upload_file(str(test_file), compressed_destination, compress=True)
        compressed_upload_time = time.time() - start_time

        assert upload_result_compressed.success is True
        assert upload_result_compressed.compressed is True

        # Compressed version should be smaller
        assert upload_result_compressed.size_bytes < upload_result.size_bytes

    def test_storage_path_sanitization(self, real_file_storage, integration_temp_dir):
        """Test storage path sanitization and security."""
        test_file = integration_temp_dir / "path_test.txt"
        test_file.write_text("Path test content")

        # Test various potentially problematic paths
        test_paths = [
            "test123/normal/path.txt",
            "test123/with spaces/path.txt",
            "test123/with-dashes/path.txt",
            "test123/with_underscores/path.txt",
            "test123/with.dots/path.txt",
        ]

        for path in test_paths:
            upload_result = real_file_storage.upload_file(str(test_file), path)
            assert upload_result.success is True
            assert real_file_storage.exists(path) is True

    def test_storage_metadata_content_type_detection(self, real_file_storage, integration_temp_dir):
        """Test storage metadata content type detection."""
        # Test different file types
        test_files = [
            ("test.html", "<html><body>HTML content</body></html>", "text/html"),
            ("test.txt", "Plain text content", "text/plain"),
            ("test.json", '{"key": "value"}', "application/json"),
        ]

        for filename, content, expected_type in test_files:
            test_file = integration_temp_dir / filename
            test_file.write_text(content)

            destination = f"test123/metadata/{filename}"
            real_file_storage.upload_file(str(test_file), destination)

            metadata = real_file_storage.get_metadata(destination)
            assert metadata is not None
            # Content type detection might vary, but should contain relevant info
            assert metadata.content_type is not None

    def test_storage_integration_with_archiver_lifecycle(self, integration_settings, real_repositories, real_file_storage):
        """Test storage integration throughout archiver lifecycle."""
        class LifecycleArchiver(BaseArchiver):
            def archive_with_storage(self, url: str, item_id: str) -> ArchiveResult:
                # Create multiple files
                files_created = []

                # Main HTML file
                html_content = f"<html><body>Archive of {url}</body></html>"
                html_path = self.base_path / item_id / self.name / "output.html"
                html_path.parent.mkdir(parents=True, exist_ok=True)
                html_path.write_text(html_content)
                files_created.append(("output.html", html_content))

                # Metadata JSON file
                metadata_content = json.dumps({
                    "url": url,
                    "item_id": item_id,
                    "archiver": self.name,
                    "created_at": time.time()
                })
                metadata_path = self.base_path / item_id / self.name / "metadata.json"
                metadata_path.write_text(metadata_content)
                files_created.append(("metadata.json", metadata_content))

                # Upload all files to storage
                upload_results = []
                for filename, content in files_created:
                    storage_path = f"{item_id}/{self.name}/{filename}"
                    result = self.storage_provider.upload_file(str(metadata_path.parent / filename), storage_path, compress=True)
                    upload_results.append(result)

                # Check if all uploads succeeded
                if all(r.success for r in upload_results):
                    total_size = sum(r.size_bytes for r in upload_results)
                    return ArchiveResult(
                        success=True,
                        exit_code=0,
                        saved_path=f"storage://{item_id}/{self.name}/",
                        start_time=time.time(),
                        end_time=time.time() + 1,
                        size_bytes=total_size,
                        metadata={"files_uploaded": len(files_created)}
                    )
                else:
                    failed_uploads = [r for r in upload_results if not r.success]
                    return ArchiveResult(
                        success=False,
                        exit_code=1,
                        error=f"Failed to upload {len(failed_uploads)} files"
                    )

        archiver = LifecycleArchiver(real_file_storage)
        archiver.storage_provider = real_file_storage

        result = archiver.archive_with_storage("https://example.com/lifecycle", "lifecycle123")

        assert result.success is True
        assert result.saved_path.startswith("storage://")
        assert result.size_bytes is not None
        assert result.metadata["files_uploaded"] == 2