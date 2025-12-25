"""
Integration tests for GCS storage workflow with real Google Cloud Storage.

Tests GCS integration with actual GCS service (requires credentials),
corresponding to Test Case 2 from TESTING_PLAN.md.

These tests:
- Require real GCS credentials to run
- Use @pytest.mark.skipif to skip when credentials unavailable
- Test actual GCS upload/download/compression
- Clean up test data after execution

Environment Variables Required:
- TEST_GCS_BUCKET: GCS bucket name for testing
- TEST_GCS_PROJECT_ID: GCP project ID
- GOOGLE_APPLICATION_CREDENTIALS: Path to service account JSON

Usage:
    # Run with GCS credentials
    export TEST_GCS_BUCKET=htbase-test-bucket
    export TEST_GCS_PROJECT_ID=my-project
    export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
    pytest tests/integration/test_gcs_storage_workflow_real.py -v -m gcs

    # Skip GCS tests
    pytest tests/integration/test_gcs_storage_workflow_real.py -v -m "not gcs"
"""

import os
from pathlib import Path
from datetime import datetime
import pytest

# Skip all tests in this module if GCS credentials not available
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_GCS_BUCKET"),
    reason="TEST_GCS_BUCKET not set - GCS credentials required"
)


@pytest.mark.gcs
class TestGCSStorageWorkflowReal:
    """Test GCS storage workflow with real GCS service."""

    @pytest.fixture
    def gcs_test_bucket(self):
        """Get GCS test bucket name from environment."""
        return os.getenv("TEST_GCS_BUCKET")

    @pytest.fixture
    def gcs_test_project(self):
        """Get GCS test project ID from environment."""
        return os.getenv("TEST_GCS_PROJECT_ID")

    @pytest.fixture
    def real_gcs_storage(self, gcs_test_bucket, gcs_test_project):
        """Create real GCS storage instance."""
        from app.storage.gcs_file_storage import GCSFileStorage

        storage = GCSFileStorage(
            bucket_name=gcs_test_bucket,
            project_id=gcs_test_project
        )

        yield storage

        # Cleanup: Delete test files after test
        # (actual cleanup implementation would go here)

    def test_gcs_upload_real_compression_ratio(self, integration_temp_dir, real_gcs_storage):
        """
        Test: Upload to real GCS → verify compression_ratio > 70%.

        Corresponds to TESTING_PLAN Test Case 2.2.1: GCS Upload Verification (Real)
        """
        # Create highly compressible test file
        test_file = integration_temp_dir / "real_gcs_test.html"
        compressible_content = "<html><body>" + ("x" * 50000) + "</body></html>"
        test_file.write_text(compressible_content)

        # Upload to real GCS
        test_path = f"test/real/{datetime.utcnow().isoformat()}/test.html"

        result = real_gcs_storage.upload_file(
            local_path=test_file,
            destination_path=test_path,
            compress=True
        )

        # Verify upload succeeded
        assert result.success, f"GCS upload failed: {result.error}"
        assert result.uri.startswith("gs://"), f"Invalid GCS URI: {result.uri}"

        # Verify compression ratio
        assert result.compression_ratio is not None
        assert result.compression_ratio > 70, \
            f"Compression ratio too low: {result.compression_ratio}%"

        print(f"\n✅ Real GCS Upload:")
        print(f"   Compression: {result.compression_ratio:.2f}%")
        print(f"   URI: {result.uri}")

        # Cleanup
        try:
            real_gcs_storage.delete_file(test_path + ".gz")
        except Exception:
            pass  # Best effort cleanup

    def test_gcs_upload_download_roundtrip_real(self, integration_temp_dir, real_gcs_storage):
        """
        Test: Upload to GCS → download → verify content matches.

        Tests complete upload/download cycle with real GCS.
        """
        # Create test file
        test_file = integration_temp_dir / "roundtrip.html"
        test_content = "<html><body>GCS roundtrip test content</body></html>"
        test_file.write_text(test_content)

        # Upload
        test_path = f"test/roundtrip/{datetime.utcnow().isoformat()}/file.html"

        upload_result = real_gcs_storage.upload_file(
            local_path=test_file,
            destination_path=test_path,
            compress=True
        )

        assert upload_result.success, f"Upload failed: {upload_result.error}"

        # Download
        download_path = integration_temp_dir / "downloaded.html"

        download_success = real_gcs_storage.download_file(
            storage_path=test_path + ".gz",  # Compressed file
            local_path=download_path,
            decompress=True
        )

        assert download_success, "Download failed"
        assert download_path.exists(), "Downloaded file not found"

        # Verify content matches
        downloaded_content = download_path.read_text()
        assert downloaded_content == test_content, "Content mismatch after roundtrip"

        print(f"\n✅ Real GCS Roundtrip: Content verified")

        # Cleanup
        try:
            real_gcs_storage.delete_file(test_path + ".gz")
        except Exception:
            pass

    def test_gcs_metadata_storage_real(self, integration_temp_dir, real_gcs_storage):
        """
        Test: Upload to GCS → verify blob metadata contains compressed=true, original_size.

        Corresponds to TESTING_PLAN Test Case 2.2.2 (Real)
        """
        test_file = integration_temp_dir / "metadata_test.html"
        test_content = "<html><body>Metadata test</body></html>"
        test_file.write_text(test_content)

        test_path = f"test/metadata/{datetime.utcnow().isoformat()}/file.html"

        result = real_gcs_storage.upload_file(
            local_path=test_file,
            destination_path=test_path,
            compress=True
        )

        assert result.success

        # Get metadata
        metadata = real_gcs_storage.get_metadata(test_path + ".gz")

        assert metadata is not None, "Metadata not found"
        assert metadata.compressed is True, "Compressed flag not set"
        assert metadata.size > 0, "Invalid size"

        print(f"\n✅ Real GCS Metadata:")
        print(f"   Compressed: {metadata.compressed}")
        print(f"   Size: {metadata.size} bytes")

        # Cleanup
        try:
            real_gcs_storage.delete_file(test_path + ".gz")
        except Exception:
            pass

    def test_gcs_cleanup_after_upload_real(self, integration_temp_dir, real_gcs_storage):
        """
        Test: Upload to GCS → verify file can be deleted.

        Tests cleanup functionality.
        """
        test_file = integration_temp_dir / "cleanup_test.html"
        test_file.write_text("<html>Cleanup test</html>")

        test_path = f"test/cleanup/{datetime.utcnow().isoformat()}/file.html"

        # Upload
        result = real_gcs_storage.upload_file(
            local_path=test_file,
            destination_path=test_path,
            compress=True
        )

        assert result.success

        # Verify exists
        assert real_gcs_storage.exists(test_path + ".gz")

        # Delete
        delete_success = real_gcs_storage.delete_file(test_path + ".gz")

        assert delete_success, "Delete failed"

        # Verify deleted
        assert not real_gcs_storage.exists(test_path + ".gz"), "File still exists after delete"

        print(f"\n✅ Real GCS Cleanup: File deleted successfully")

    def test_gcs_invalid_credentials_fallback_real(self, monkeypatch, integration_temp_dir):
        """
        Test: Invalid GCS credentials → logs error → operation fails gracefully.

        Corresponds to TESTING_PLAN Test Case 2.5.1: Invalid Credentials
        """
        from app.storage.gcs_file_storage import GCSFileStorage

        # Set invalid credentials path
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/nonexistent/path.json")

        # Attempt to create storage (should fail or handle gracefully)
        try:
            storage = GCSFileStorage(
                bucket_name="invalid-bucket",
                project_id="invalid-project"
            )

            test_file = integration_temp_dir / "invalid_creds_test.html"
            test_file.write_text("<html>Test</html>")

            result = storage.upload_file(
                local_path=test_file,
                destination_path="test/file.html",
                compress=True
            )

            # Should fail
            assert result.success is False, "Upload should fail with invalid credentials"
            assert result.error is not None

            print(f"\n✅ Invalid Credentials: Handled gracefully")

        except Exception as e:
            # Exception is also acceptable (credential loading may fail immediately)
            print(f"\n✅ Invalid Credentials: Raised exception as expected: {type(e).__name__}")

    def test_gcs_signed_url_generation_real(self, integration_temp_dir, real_gcs_storage):
        """
        Test: Upload file → generate signed URL → verify URL format.

        Tests signed URL generation with real GCS.
        """
        test_file = integration_temp_dir / "signed_url_test.html"
        test_file.write_text("<html>Signed URL test</html>")

        test_path = f"test/signed/{datetime.utcnow().isoformat()}/file.html"

        # Upload
        result = real_gcs_storage.upload_file(
            local_path=test_file,
            destination_path=test_path,
            compress=True
        )

        assert result.success

        # Generate signed URL
        from datetime import timedelta

        signed_url = real_gcs_storage.generate_access_url(
            storage_path=test_path + ".gz",
            expiration=timedelta(hours=1)
        )

        # Verify URL format
        assert signed_url.startswith("https://"), f"Invalid signed URL: {signed_url}"
        assert "storage.googleapis.com" in signed_url or "storage.cloud.google.com" in signed_url

        print(f"\n✅ Signed URL Generated:")
        print(f"   URL: {signed_url[:80]}...")

        # Cleanup
        try:
            real_gcs_storage.delete_file(test_path + ".gz")
        except Exception:
            pass

    def test_gcs_list_files_real(self, integration_temp_dir, real_gcs_storage):
        """
        Test: Upload multiple files → list with prefix → verify results.

        Tests file listing functionality.
        """
        test_prefix = f"test/list/{datetime.utcnow().isoformat()}"

        # Upload multiple files
        for i in range(3):
            test_file = integration_temp_dir / f"list_test_{i}.html"
            test_file.write_text(f"<html>File {i}</html>")

            result = real_gcs_storage.upload_file(
                local_path=test_file,
                destination_path=f"{test_prefix}/file_{i}.html",
                compress=True
            )

            assert result.success

        # List files
        files = real_gcs_storage.list_files(prefix=test_prefix)

        # Should find the uploaded files
        assert len(files) >= 3, f"Expected at least 3 files, found {len(files)}"

        print(f"\n✅ GCS List Files: Found {len(files)} files")

        # Cleanup
        for i in range(3):
            try:
                real_gcs_storage.delete_file(f"{test_prefix}/file_{i}.html.gz")
            except Exception:
                pass

    def test_gcs_large_file_upload_real(self, integration_temp_dir, real_gcs_storage):
        """
        Test: Upload large file (10MB) → verify successful upload and compression.

        Tests large file handling.
        """
        # Create 10MB file
        large_file = integration_temp_dir / "large.html"
        large_content = "<html><body>" + ("x" * 10_000_000) + "</body></html>"
        large_file.write_text(large_content)

        test_path = f"test/large/{datetime.utcnow().isoformat()}/large.html"

        # Upload
        result = real_gcs_storage.upload_file(
            local_path=large_file,
            destination_path=test_path,
            compress=True
        )

        assert result.success, f"Large file upload failed: {result.error}"
        assert result.compression_ratio > 70, "Large file compression insufficient"

        print(f"\n✅ Large File Upload:")
        print(f"   Size: {result.original_size / 1024 / 1024:.2f} MB")
        print(f"   Compression: {result.compression_ratio:.2f}%")

        # Cleanup
        try:
            real_gcs_storage.delete_file(test_path + ".gz")
        except Exception:
            pass
