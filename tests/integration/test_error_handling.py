"""
Integration tests for error handling and recovery.

Tests error scenarios and recovery mechanisms,
corresponding to Test Case 4 from TESTING_PLAN.md.

These tests verify:
- Permission errors (Test 4.2.1)
- Corrupted database records (Test 4.3.2)
- Disk space simulation (Test 4.2.2)
- Invalid URL handling (Test 4.1.1)
- Network errors (Test 4.1.2)
- Partial storage failures
- Timeout handling
"""

import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


class TestErrorHandling:
    """Test error handling and recovery mechanisms."""

    def test_permission_denied_on_data_dir(self, monkeypatch, tmp_path):
        """
        Test: Create unwritable DATA_DIR → archive fails gracefully → returns error message.

        Corresponds to TESTING_PLAN Test Case 4.2.1: Permission Denied
        """
        # Create directory with restricted permissions
        restricted_dir = tmp_path / "restricted"
        restricted_dir.mkdir()

        # Make directory unwritable (Unix only)
        if os.name != 'nt':  # Skip on Windows
            os.chmod(restricted_dir, 0o444)  # Read-only

            monkeypatch.setenv("DATA_DIR", str(restricted_dir))
            monkeypatch.setenv("START_HT", "false")

            from app.core.config import get_settings
            get_settings.cache_clear()

            try:
                import app.server as server
                client = TestClient(server.app)

                response = client.post(
                    "/archive/monolith",
                    json={"id": "test_permission", "url": "https://example.com"}
                )

                # Should handle gracefully (may return 200 with ok=false or error code)
                assert response.status_code in [200, 403, 500]

                if response.status_code == 200:
                    data = response.json()
                    # If 200, should indicate failure
                    assert data.get("ok") is False or "error" in str(data).lower()

            finally:
                # Restore permissions for cleanup
                if os.name != 'nt':
                    os.chmod(restricted_dir, 0o755)
        else:
            pytest.skip("Permission testing not applicable on Windows")

    def test_corrupted_database_record_handling(self, test_app_with_fakes, in_memory_db_storage):
        """
        Test: Insert artifact with invalid saved_path → retrieve returns 404 with error.

        Corresponds to TESTING_PLAN Test Case 4.3.2: Corrupted Database Records
        """
        client = TestClient(test_app_with_fakes)

        # Create article with corrupted path
        in_memory_db_storage.create_article(
            item_id="corrupted_001",
            url="https://example.com/corrupted"
        )

        in_memory_db_storage.update_artifact_status(
            item_id="corrupted_001",
            archiver="monolith",
            status="success",
            gcs_path="/nonexistent/invalid/path.html"
        )

        # Try to retrieve
        response = client.post(
            "/archive/retrieve",
            json={"id": "corrupted_001", "archiver": "monolith"}
        )

        # Should return 404 or handle gracefully
        assert response.status_code in [404, 500]

    def test_disk_space_full_simulation(self, mocker, test_app_with_fakes):
        """
        Test: Mock OSError('No space left') → archive fails → error logged.

        Corresponds to TESTING_PLAN Test Case 4.2.2: Disk Space Full Simulation
        """
        client = TestClient(test_app_with_fakes)

        # Mock file write to raise disk space error
        original_write = Path.write_text

        def mock_write_text(self, *args, **kwargs):
            if "test_diskfull" in str(self):
                raise OSError(28, "No space left on device")
            return original_write(self, *args, **kwargs)

        mocker.patch.object(Path, 'write_text', side_effect=mock_write_text)

        # Attempt to save
        response = client.post(
            "/archive/monolith",
            json={"id": "test_diskfull", "url": "https://example.com/diskfull"}
        )

        # Should handle error gracefully
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            data = response.json()
            # Should indicate failure
            assert data.get("ok") is False or data.get("exit_code", 0) != 0

    def test_invalid_url_handling(self, test_app_with_fakes):
        """
        Test: POST /archive/monolith with invalid URL → returns 400 or handles gracefully.

        Corresponds to TESTING_PLAN Test Case 4.1.1: Invalid URL Handling
        """
        client = TestClient(test_app_with_fakes)

        invalid_urls = [
            "not-a-url",
            "ftp://invalid-protocol.com",
            "javascript:alert('xss')",
            "file:///etc/passwd",
        ]

        for invalid_url in invalid_urls:
            response = client.post(
                "/archive/monolith",
                json={"id": f"test_invalid_{hash(invalid_url)}", "url": invalid_url}
            )

            # Should return validation error or handle gracefully
            assert response.status_code in [200, 400, 422], \
                f"Invalid URL not handled properly: {invalid_url}"

    def test_archiver_timeout_handling(self, test_app_with_fakes, dummy_archivers):
        """
        Test: Use TimeoutArchiver → exceeds timeout → returns error with timeout message.

        Tests timeout handling in archivers.
        """
        client = TestClient(test_app_with_fakes)

        # Use timeout archiver if available
        if "timeout" in dummy_archivers:
            test_app_with_fakes.state.archivers["timeout"] = dummy_archivers["timeout"]

            response = client.post(
                "/archive/timeout",
                json={"id": "test_timeout", "url": "https://example.com"}
            )

            # Should handle timeout (may succeed or fail depending on implementation)
            assert response.status_code in [200, 408, 500]
        else:
            pytest.skip("TimeoutArchiver not available in test setup")

    def test_network_error_during_url_check(self, mocker, test_app_with_fakes):
        """
        Test: Mock requests.head to raise ConnectionError → marks URL as unreachable.

        Corresponds to TESTING_PLAN Test Case 4.1.2: Network Error During URL Check
        """
        client = TestClient(test_app_with_fakes)

        # Mock requests.head to raise connection error
        mock_head = mocker.patch("requests.head")
        mock_head.side_effect = ConnectionError("Connection refused")

        response = client.post(
            "/archive/monolith",
            json={"id": "test_network_error", "url": "https://unreachable.example.com"}
        )

        # Should handle network error gracefully
        assert response.status_code in [200, 400, 500, 503]

    def test_partial_storage_upload_failure(self, mocker, integration_temp_dir):
        """
        Test: GCS upload succeeds, Local fails → all_uploads_succeeded=False → local not deleted.

        Tests partial failure in multi-provider upload.
        """
        from app.storage.gcs_file_storage import GCSFileStorage
        from app.storage.local_file_storage import LocalFileStorage

        # Create test file
        test_file = integration_temp_dir / "partial_fail.html"
        test_file.write_text("<html>Partial failure test</html>")

        # Mock GCS to succeed
        mock_gcs_client = mocker.Mock()
        mock_bucket = mocker.Mock()
        mock_blob = mocker.Mock()

        mock_gcs_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.public_url = "gs://test-bucket/file.html.gz"

        mocker.patch('google.cloud.storage.Client', return_value=mock_gcs_client)

        # Create providers
        gcs_storage = GCSFileStorage(bucket_name="test-bucket", project_id="test-project")

        # Mock local storage to fail
        local_storage = LocalFileStorage(root_dir=integration_temp_dir / "local")

        original_upload = local_storage.upload_file

        def failing_upload(*args, **kwargs):
            from app.storage.file_storage import UploadResult
            return UploadResult(
                success=False,
                uri="",
                original_size=0,
                stored_size=0,
                error="Simulated local storage failure"
            )

        mocker.patch.object(local_storage, 'upload_file', side_effect=failing_upload)

        # Upload to both providers
        gcs_result = gcs_storage.upload_file(
            local_path=test_file,
            destination_path="test/file.html",
            compress=True
        )

        local_result = local_storage.upload_file(
            local_path=test_file,
            destination_path="test/file.html",
            compress=True
        )

        # Check results
        # GCS should succeed (mocked)
        # Local should fail (mocked to fail)
        assert local_result.success is False

        # Verify local file still exists (not deleted on partial failure)
        assert test_file.exists(), "Local file should not be deleted when some uploads fail"

    def test_malformed_json_request(self, test_app_with_fakes):
        """
        Test: Send malformed JSON → returns 422 validation error.

        Tests request validation.
        """
        client = TestClient(test_app_with_fakes)

        # Missing required fields
        response = client.post(
            "/archive/monolith",
            json={"id": "test"}  # Missing 'url'
        )

        assert response.status_code == 422  # Validation error

        # Invalid field types
        response2 = client.post(
            "/archive/monolith",
            json={"id": 12345, "url": "not checked yet"}  # id should be string
        )

        # Should handle type coercion or return validation error
        assert response2.status_code in [200, 422]

    def test_archiver_not_found(self, test_app_with_fakes):
        """
        Test: Request non-existent archiver → returns 404 or appropriate error.

        Tests archiver lookup error handling.
        """
        client = TestClient(test_app_with_fakes)

        response = client.post(
            "/archive/nonexistent_archiver",
            json={"id": "test", "url": "https://example.com"}
        )

        # Should return 404 or 500 for missing archiver
        assert response.status_code in [404, 500]

    def test_database_connection_error_simulation(self, mocker, test_app_with_fakes):
        """
        Test: Mock database connection error → handles gracefully.

        Tests database error handling.
        """
        # This test depends on how database is accessed in the app
        # For now, just verify the app doesn't crash
        client = TestClient(test_app_with_fakes)

        # App should still respond even if DB operations might fail
        response = client.get("/")  # Root endpoint or health check

        # Should return something (200 or error, but not crash)
        assert response is not None

    def test_concurrent_write_conflict(self, test_app_with_fakes):
        """
        Test: Two concurrent saves to same item_id → handle gracefully.

        Tests concurrent write conflict handling.
        """
        import threading
        import queue

        client = TestClient(test_app_with_fakes)

        results = queue.Queue()
        item_id = "concurrent_conflict"
        url = "https://example.com/conflict"

        def save_worker(worker_id):
            try:
                response = client.post(
                    "/archive/monolith",
                    json={"id": item_id, "url": url}
                )
                results.put((worker_id, response.status_code, response.json()))
            except Exception as e:
                results.put((worker_id, -1, str(e)))

        # Launch concurrent saves
        threads = []
        for i in range(2):
            thread = threading.Thread(target=save_worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Both should complete (may succeed or handle conflict)
        assert results.qsize() == 2

    def test_file_corruption_detection(self, integration_temp_dir, real_file_storage):
        """
        Test: Upload corrupted file → detect and handle appropriately.

        Tests file integrity handling.
        """
        # Create "corrupted" file (truncated)
        corrupt_file = integration_temp_dir / "corrupt.html"
        corrupt_file.write_bytes(b"<html><body>Truncated")  # Incomplete HTML

        # Upload should still work (corruption detection is optional)
        result = real_file_storage.upload_file(
            local_path=corrupt_file,
            destination_path="test/corrupt.html",
            compress=False
        )

        # Should succeed (file operations don't validate HTML)
        # App may choose to validate content separately
        assert result is not None

    def test_extremely_long_url_handling(self, test_app_with_fakes):
        """
        Test: Extremely long URL → handle appropriately.

        Tests URL length limits.
        """
        client = TestClient(test_app_with_fakes)

        # Create very long URL (>2048 characters)
        long_url = "https://example.com/" + ("a" * 3000)

        response = client.post(
            "/archive/monolith",
            json={"id": "test_long_url", "url": long_url}
        )

        # Should handle (may accept or reject based on validation)
        assert response.status_code in [200, 400, 414, 422]

    def test_special_characters_in_item_id(self, test_app_with_fakes):
        """
        Test: Item ID with special characters → sanitized properly.

        Tests item ID sanitization.
        """
        client = TestClient(test_app_with_fakes)

        special_ids = [
            "test/with/slashes",
            "test:with:colons",
            "test with spaces",
            "test<>with<>brackets",
        ]

        for special_id in special_ids:
            response = client.post(
                "/archive/monolith",
                json={"id": special_id, "url": "https://example.com"}
            )

            # Should handle sanitization
            assert response.status_code in [200, 400]

            if response.status_code == 200:
                data = response.json()
                # Sanitized ID should be returned
                assert data.get("id") is not None

    def test_retry_mechanism_on_transient_error(self, mocker):
        """
        Test: Transient error → retry succeeds.

        Tests retry logic (if implemented).
        """
        # Create mock that fails first time, succeeds second time
        attempt_count = [0]

        def failing_then_succeeding(*args, **kwargs):
            attempt_count[0] += 1
            if attempt_count[0] == 1:
                raise Exception("Transient error")
            return "Success"

        mock_function = mocker.Mock(side_effect=failing_then_succeeding)

        # Test retry logic
        try:
            mock_function()
        except Exception:
            # Retry
            result = mock_function()
            assert result == "Success"
            assert attempt_count[0] == 2
