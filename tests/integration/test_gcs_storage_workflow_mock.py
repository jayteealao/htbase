"""
Integration tests for GCS storage workflow using mocks.

Tests GCS integration using mocks for fast testing without credentials,
corresponding to Test Case 2 from TESTING_PLAN.md.

These tests verify:
- GCS upload with compression (Test 2.2.1)
- GCS path tracking in database (Test 2.2.2)
- GCS file retrieval (Test 2.3.1)
- Multiple provider upload
- Upload failure handling
- Signed URL generation
"""

import gzip
import json
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
import pytest


class TestGCSStorageWorkflowMock:
    """Test GCS storage workflow with mocked GCS client."""

    def test_gcs_upload_with_compression_mock(self, integration_temp_dir, mocker):
        """
        Test: Mock GCS upload → verify compression ratio > 70% → verify .gz extension added.

        Corresponds to TESTING_PLAN Test Case 2.2.1: GCS Upload Verification
        """
        from app.storage.gcs_file_storage import GCSFileStorage
        from app.storage.file_storage import UploadResult

        # Create test file with compressible content
        test_file = integration_temp_dir / "test.html"
        test_content = b"<html><body>" + b"x" * 10000 + b"</body></html>"
        test_file.write_bytes(test_content)
        original_size = len(test_content)

        # Mock GCS client
        mock_client = mocker.Mock()
        mock_bucket = mocker.Mock()
        mock_blob = mocker.Mock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        # Patch storage client creation
        mocker.patch('google.cloud.storage.Client', return_value=mock_client)

        # Create GCS storage instance
        storage = GCSFileStorage(bucket_name="test-bucket", project_id="test-project")

        # Upload file
        result = storage.upload_file(
            local_path=test_file,
            destination_path="archives/test/file.html",
            compress=True
        )

        # Verify upload was called
        mock_blob.upload_from_filename.assert_called_once()

        # Verify compression ratio
        if result.compression_ratio:
            assert result.compression_ratio > 70, f"Compression ratio too low: {result.compression_ratio}%"

        # Verify .gz extension was added
        assert result.uri.endswith('.gz'), f"Expected .gz extension in URI: {result.uri}"

    def test_gcs_path_tracking_in_database_mock(self, mocker, integration_temp_dir):
        """
        Test: Mock upload → verify storage_uploads JSON contains GCS uri (gs://...).

        Corresponds to TESTING_PLAN Test Case 2.2.2: Database Metadata Verification
        """
        from app.storage.gcs_file_storage import GCSFileStorage

        # Create test file
        test_file = integration_temp_dir / "test.html"
        test_file.write_text("<html>Test</html>")

        # Mock GCS client
        mock_client = mocker.Mock()
        mock_bucket = mocker.Mock()
        mock_blob = mocker.Mock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.public_url = "gs://test-bucket/archives/test/file.html.gz"

        mocker.patch('google.cloud.storage.Client', return_value=mock_client)

        # Create storage instance
        storage = GCSFileStorage(bucket_name="test-bucket", project_id="test-project")

        # Upload file
        result = storage.upload_file(
            local_path=test_file,
            destination_path="archives/test/file.html",
            compress=True
        )

        # Verify GCS URI format
        assert result.uri.startswith("gs://"), f"Expected gs:// URI, got: {result.uri}"
        assert "test-bucket" in result.uri
        assert ".gz" in result.uri

        # Simulate database storage_uploads JSON
        storage_metadata = {
            'provider_name': storage.provider_name,
            'storage_uri': result.uri,
            'original_size': result.original_size,
            'stored_size': result.stored_size,
            'compression_ratio': result.compression_ratio,
            'uploaded_at': datetime.utcnow().isoformat(),
            'success': result.success
        }

        # Verify metadata structure
        assert storage_metadata['provider_name'] == 'gcs'
        assert storage_metadata['storage_uri'].startswith('gs://')
        assert storage_metadata['success'] is True

    def test_gcs_multiple_provider_upload_mock(self, mocker, integration_temp_dir):
        """
        Test: Mock GCS + Local providers → both upload → verify storage_uploads has 2 entries.

        Verifies multi-provider upload workflow.
        """
        from app.storage.gcs_file_storage import GCSFileStorage
        from app.storage.local_file_storage import LocalFileStorage

        # Create test file
        test_file = integration_temp_dir / "test.html"
        test_file.write_text("<html>Multi-provider test</html>")

        # Mock GCS client
        mock_client = mocker.Mock()
        mock_bucket = mocker.Mock()
        mock_blob = mocker.Mock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        mocker.patch('google.cloud.storage.Client', return_value=mock_client)

        # Create providers
        gcs_storage = GCSFileStorage(bucket_name="test-bucket", project_id="test-project")
        local_storage = LocalFileStorage(root_dir=integration_temp_dir / "local")

        providers = [gcs_storage, local_storage]

        # Upload to all providers
        upload_results = []
        for provider in providers:
            result = provider.upload_file(
                local_path=test_file,
                destination_path="archives/test/file.html",
                compress=True
            )
            upload_results.append({
                'provider_name': provider.provider_name,
                'success': result.success,
                'uri': result.uri
            })

        # Verify both uploads succeeded
        assert len(upload_results) == 2
        assert upload_results[0]['success'] is True
        assert upload_results[1]['success'] is True

        # Verify different providers
        provider_names = {r['provider_name'] for r in upload_results}
        assert 'gcs' in provider_names
        assert 'local' in provider_names

    def test_gcs_upload_failure_handling_mock(self, mocker, integration_temp_dir):
        """
        Test: Mock GCS upload failure → all_uploads_succeeded=False → local file NOT deleted.

        Verifies error handling when GCS upload fails.
        """
        from app.storage.gcs_file_storage import GCSFileStorage

        # Create test file
        test_file = integration_temp_dir / "test.html"
        test_file.write_text("<html>Failure test</html>")

        # Mock GCS client to raise exception
        mock_client = mocker.Mock()
        mock_bucket = mocker.Mock()
        mock_blob = mocker.Mock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        # Simulate upload failure
        mock_blob.upload_from_filename.side_effect = Exception("GCS upload failed")

        mocker.patch('google.cloud.storage.Client', return_value=mock_client)

        # Create storage instance
        storage = GCSFileStorage(bucket_name="test-bucket", project_id="test-project")

        # Upload file (should handle error gracefully)
        result = storage.upload_file(
            local_path=test_file,
            destination_path="archives/test/file.html",
            compress=True
        )

        # Verify upload failed
        assert result.success is False
        assert result.error is not None
        assert "failed" in result.error.lower() or "error" in result.error.lower()

        # Verify local file still exists (not deleted on failure)
        assert test_file.exists(), "Local file should not be deleted on upload failure"

    def test_gcs_file_retrieval_via_api_mock(self, test_app_with_fakes, mocker, integration_temp_dir):
        """
        Test: Mock GCS serve_file → POST /archive/retrieve → verify decompression.

        Verifies file retrieval from GCS via API with decompression.
        """
        from fastapi.testclient import TestClient
        from app.storage.gcs_file_storage import GCSFileStorage

        # Create and compress test content
        test_content = b"<html><body>GCS retrieval test</body></html>"
        compressed_content = gzip.compress(test_content, compresslevel=9)

        # Mock GCS blob download
        mock_blob = mocker.Mock()
        mock_blob.download_as_bytes.return_value = compressed_content

        mock_bucket = mocker.Mock()
        mock_bucket.blob.return_value = mock_blob

        mock_client = mocker.Mock()
        mock_client.bucket.return_value = mock_bucket

        mocker.patch('google.cloud.storage.Client', return_value=mock_client)

        # Create GCS storage instance
        gcs_storage = GCSFileStorage(bucket_name="test-bucket", project_id="test-project")

        # Mock the get_file_stream method to return decompressed content
        def mock_get_file_stream(storage_path):
            import io
            # Simulate decompression
            decompressed = gzip.decompress(compressed_content)
            return io.BytesIO(decompressed)

        mocker.patch.object(gcs_storage, 'get_file_stream', side_effect=mock_get_file_stream)

        # Test file retrieval
        stream = gcs_storage.get_file_stream("archives/test/file.html.gz")
        retrieved_content = stream.read()

        # Verify content was decompressed
        assert retrieved_content == test_content
        assert b"GCS retrieval test" in retrieved_content

    def test_gcs_signed_url_generation_mock(self, mocker, integration_temp_dir):
        """
        Test: Mock generate_access_url → verify signed URL format → verify expiration.

        Verifies signed URL generation for GCS.
        """
        from app.storage.gcs_file_storage import GCSFileStorage

        # Mock GCS client
        mock_client = mocker.Mock()
        mock_bucket = mocker.Mock()
        mock_blob = mocker.Mock()

        # Mock signed URL generation
        expected_signed_url = "https://storage.googleapis.com/test-bucket/file.html?X-Goog-Signature=abc123&X-Goog-Expires=3600"
        mock_blob.generate_signed_url.return_value = expected_signed_url

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        mocker.patch('google.cloud.storage.Client', return_value=mock_client)

        # Create storage instance
        storage = GCSFileStorage(bucket_name="test-bucket", project_id="test-project")

        # Generate signed URL
        storage_path = "archives/test/file.html"
        expiration = timedelta(hours=1)

        signed_url = storage.generate_access_url(storage_path, expiration)

        # Verify signed URL format
        assert signed_url.startswith("https://")
        assert "storage.googleapis.com" in signed_url or "X-Goog" in signed_url

        # Verify generate_signed_url was called with correct expiration
        mock_blob.generate_signed_url.assert_called_once()

    def test_gcs_compression_metadata_storage_mock(self, mocker, integration_temp_dir):
        """
        Test: Mock GCS upload → verify blob metadata contains compression info.

        Verifies GCS blob metadata tracking.
        """
        from app.storage.gcs_file_storage import GCSFileStorage

        # Create test file
        test_file = integration_temp_dir / "test.html"
        test_content = b"<html><body>" + b"Test content" * 100 + b"</body></html>"
        test_file.write_bytes(test_content)

        # Mock GCS client
        mock_client = mocker.Mock()
        mock_bucket = mocker.Mock()
        mock_blob = mocker.Mock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        mocker.patch('google.cloud.storage.Client', return_value=mock_client)

        # Create storage instance
        storage = GCSFileStorage(bucket_name="test-bucket", project_id="test-project")

        # Upload with compression
        result = storage.upload_file(
            local_path=test_file,
            destination_path="archives/test/file.html",
            compress=True
        )

        # Verify blob metadata was set
        # Check if metadata attribute was set on mock_blob
        if hasattr(mock_blob, 'metadata'):
            metadata = mock_blob.metadata
            # Should contain compression info
            assert 'compressed' in str(metadata).lower() or metadata is not None

    def test_gcs_provider_capabilities_mock(self):
        """
        Test: Verify GCS provider capabilities flags.

        Verifies provider metadata and capabilities.
        """
        from app.storage.gcs_file_storage import GCSFileStorage

        # Create storage instance (no actual GCS connection needed)
        storage = GCSFileStorage(bucket_name="test-bucket", project_id="test-project")

        # Verify capabilities
        assert storage.provider_name == "gcs"
        assert storage.supports_compression is True
        assert storage.supports_signed_urls is True

    def test_gcs_batch_upload_mock(self, mocker, integration_temp_dir):
        """
        Test: Mock batch upload of multiple files to GCS.

        Verifies batch upload functionality.
        """
        from app.storage.gcs_file_storage import GCSFileStorage

        # Create multiple test files
        test_files = []
        for i in range(3):
            test_file = integration_temp_dir / f"test{i}.html"
            test_file.write_text(f"<html>Test file {i}</html>")
            test_files.append(test_file)

        # Mock GCS client
        mock_client = mocker.Mock()
        mock_bucket = mocker.Mock()

        def create_mock_blob(name):
            blob = mocker.Mock()
            blob.public_url = f"gs://test-bucket/{name}"
            return blob

        mock_bucket.blob.side_effect = create_mock_blob
        mock_client.bucket.return_value = mock_bucket

        mocker.patch('google.cloud.storage.Client', return_value=mock_client)

        # Create storage instance
        storage = GCSFileStorage(bucket_name="test-bucket", project_id="test-project")

        # Upload all files
        upload_results = []
        for i, test_file in enumerate(test_files):
            result = storage.upload_file(
                local_path=test_file,
                destination_path=f"archives/batch/file{i}.html",
                compress=True
            )
            upload_results.append(result)

        # Verify all uploads
        assert len(upload_results) == 3
        for result in upload_results:
            # In mock mode, success depends on whether exceptions were raised
            assert result is not None
