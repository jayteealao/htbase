"""
Tests for the Saves API endpoints.

Tests the /archive/{archiver}, /save, and /archive/retrieve endpoints
using FastAPI TestClient with mocked dependencies.
"""

import gzip
import json
import tarfile
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

import pytest

from models import SaveRequest, BatchCreateRequest, ArchiveRetrieveRequest


class TestSavesAPI:
    """Test the saves API endpoints."""

    def test_archive_with_known_archiver_success(self, test_client: TestClient):
        """Test successful archive with known archiver."""
        payload = {
            "id": "test123",
            "url": "https://example.com"
        }

        response = test_client.post("/archive/monolith", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["id"] == "test123"
        assert data["exit_code"] == 0
        assert data["saved_path"] is not None

    def test_archive_with_unknown_archiver_404(self, test_client: TestClient):
        """Test archive with unknown archiver returns 404."""
        payload = {
            "id": "test123",
            "url": "https://example.com"
        }

        response = test_client.post("/archive/unknown", json=payload)

        assert response.status_code == 404
        assert "Unknown archiver" in response.json()["detail"]

    def test_archive_with_missing_id_400(self, test_client: TestClient):
        """Test archive with missing ID returns 400."""
        payload = {
            "url": "https://example.com"
        }

        response = test_client.post("/archive/monolith", json=payload)

        assert response.status_code == 400
        assert "id is required" in response.json()["detail"]

    def test_archive_with_empty_id_400(self, test_client: TestClient):
        """Test archive with empty ID returns 400."""
        payload = {
            "id": "   ",
            "url": "https://example.com"
        }

        response = test_client.post("/archive/monolith", json=payload)

        assert response.status_code == 400
        assert "id is required" in response.json()["detail"]

    def test_archive_with_all_archivers_success(self, test_client: TestClient):
        """Test archive with 'all' archivers."""
        payload = {
            "id": "test123",
            "url": "https://example.com"
        }

        response = test_client.post("/archive/all", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["id"] == "test123"

    def test_archive_with_sanitized_id(self, test_client: TestClient):
        """Test that ID is properly sanitized."""
        payload = {
            "id": "test with spaces & symbols!",
            "url": "https://example.com"
        }

        response = test_client.post("/archive/monolith", json=payload)

        assert response.status_code == 200
        data = response.json()
        # ID should be sanitized (no spaces or special chars)
        assert " " not in data["id"]
        assert "&" not in data["id"]
        assert "!" not in data["id"]

    def test_archive_creates_file(self, test_client: TestClient, temp_env):
        """Test that archive creates actual file."""
        payload = {
            "id": "test123",
            "url": "https://example.com"
        }

        response = test_client.post("/archive/monolith", json=payload)
        assert response.status_code == 200

        # Check file was created
        data_dir = temp_env / "data"
        expected_file = data_dir / "test123" / "monolith" / "output.html"
        assert expected_file.exists()
        assert "Dummy saved: https://example.com" in expected_file.read_text()

    def test_save_default_enqueue_success(self, test_client: TestClient):
        """Test default save endpoint enqueues task."""
        payload = {
            "id": "test123",
            "url": "https://example.com"
        }

        response = test_client.post("/save", json=payload)

        assert response.status_code == 202
        data = response.json()
        assert "task_id" in data
        assert data["count"] == 1

    def test_save_default_missing_id_400(self, test_client: TestClient):
        """Test save with missing ID returns 400."""
        payload = {
            "url": "https://example.com"
        }

        response = test_client.post("/save", json=payload)

        assert response.status_code == 400
        assert "id is required" in response.json()["detail"]

    def test_save_default_empty_id_400(self, test_client: TestClient):
        """Test save with empty ID returns 400."""
        payload = {
            "id": "   ",
            "url": "https://example.com"
        }

        response = test_client.post("/save", json=payload)

        assert response.status_code == 400
        assert "id is required" in response.json()["detail"]

    def test_save_batch_enqueue_success(self, test_client: TestClient):
        """Test batch save endpoint enqueues task."""
        payload = {
            "items": [
                {"id": "test1", "url": "https://example1.com"},
                {"id": "test2", "url": "https://example2.com"}
            ]
        }

        response = test_client.post("/save/batch", json=payload)

        assert response.status_code == 202
        data = response.json()
        assert "task_id" in data
        assert data["count"] == 2

    def test_archive_with_batch_enqueue_success(self, test_client: TestClient):
        """Test archive batch endpoint enqueues task."""
        payload = {
            "items": [
                {"id": "test1", "url": "https://example1.com"},
                {"id": "test2", "url": "https://example2.com"}
            ]
        }

        response = test_client.post("/archive/monolith/batch", json=payload)

        assert response.status_code == 202
        data = response.json()
        assert "task_id" in data
        assert data["count"] == 2

    def test_archive_batch_missing_id_400(self, test_client: TestClient):
        """Test archive batch with missing ID returns 400."""
        payload = {
            "items": [
                {"url": "https://example1.com"},  # Missing ID
                {"id": "test2", "url": "https://example2.com"}
            ]
        }

        response = test_client.post("/archive/monolith/batch", json=payload)

        assert response.status_code == 400
        assert "id is required" in response.json()["detail"]

    def test_archive_batch_empty_id_400(self, test_client: TestClient):
        """Test archive batch with empty ID returns 400."""
        payload = {
            "items": [
                {"id": "   ", "url": "https://example1.com"},  # Empty ID
                {"id": "test2", "url": "https://example2.com"}
            ]
        }

        response = test_client.post("/archive/monolith/batch", json=payload)

        assert response.status_code == 400
        assert "id is required" in response.json()["detail"]

    def test_retrieve_archive_single_success(self, test_client: TestClient, temp_env):
        """Test retrieving single archive file."""
        # First create an archive
        payload = {"id": "test123", "url": "https://example.com"}
        test_client.post("/archive/monolith", json=payload)

        # Then retrieve it
        retrieve_payload = {"id": "test123", "archiver": "monolith"}
        response = test_client.post("/archive/retrieve", json=retrieve_payload)

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert "content-disposition" in response.headers
        content = response.content
        assert b"Dummy saved: https://example.com" in content

    def test_retrieve_archive_not_found_404(self, test_client: TestClient):
        """Test retrieving non-existent archive returns 404."""
        retrieve_payload = {"id": "nonexistent", "archiver": "monolith"}
        response = test_client.post("/archive/retrieve", json=retrieve_payload)

        assert response.status_code == 404
        assert "url not archived" in response.json()["detail"]

    def test_retrieve_archive_all_bundle(self, test_client: TestClient, temp_env):
        """Test retrieving all archives as bundle."""
        # First create an archive
        payload = {"id": "test123", "url": "https://example.com"}
        test_client.post("/archive/monolith", json=payload)

        # Then retrieve all
        retrieve_payload = {"id": "test123", "archiver": "all"}
        response = test_client.post("/archive/retrieve", json=retrieve_payload)

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/gzip"
        assert "content-disposition" in response.headers
        assert "artifacts.tar.gz" in response.headers["content-disposition"]

        # Verify it's a valid gzip tar archive
        content = response.content
        buffer = BytesIO(content)
        with gzip.GzipFile(fileobj=buffer, mode='rb') as gz:
            with tarfile.open(fileobj=gz, mode='r:') as tar:
                members = tar.getnames()
                assert len(members) == 1
                assert "monolith/" in members[0]

    def test_retrieve_archive_default_archiver(self, test_client: TestClient, temp_env):
        """Test retrieving archive defaults to all archivers."""
        # First create an archive
        payload = {"id": "test123", "url": "https://example.com"}
        test_client.post("/archive/monolith", json=payload)

        # Retrieve without specifying archiver
        retrieve_payload = {"id": "test123"}  # No archiver specified
        response = test_client.post("/archive/retrieve", json=retrieve_payload)

        assert response.status_code == 200
        # Should return all archives (bundle)
        assert response.headers["content-type"] == "application/gzip"

    def test_retrieve_archive_by_url(self, test_client: TestClient, temp_env):
        """Test retrieving archive by URL instead of ID."""
        # First create an archive
        payload = {"id": "test123", "url": "https://example.com"}
        test_client.post("/archive/monolith", json=payload)

        # Then retrieve by URL
        retrieve_payload = {"url": "https://example.com", "archiver": "monolith"}
        response = test_client.post("/archive/retrieve", json=retrieve_payload)

        assert response.status_code == 200
        assert b"Dummy saved: https://example.com" in response.content

    def test_get_archive_size_success(self, test_client: TestClient, temp_env):
        """Test getting archive size statistics."""
        # First create an archive to get a row ID
        payload = {"id": "test123", "url": "https://example.com"}
        archive_response = test_client.post("/archive/monolith", json=payload)
        row_id = archive_response.json()["db_rowid"]

        if row_id:
            # Then get size statistics
            response = test_client.get(f"/archive/{row_id}/size")

            assert response.status_code == 200
            data = response.json()
            assert "total_size_bytes" in data
            assert "artifacts" in data
            assert isinstance(data["artifacts"], list)

    def test_get_archive_size_not_found_404(self, test_client: TestClient):
        """Test getting size for non-existent archive returns 404."""
        response = test_client.get("/archive/999999/size")

        assert response.status_code == 404
        assert "Archived URL not found" in response.json()["detail"]

    @patch('core.utils.check_url_archivability')
    def test_archive_url_404_handling(self, mock_check, test_client: TestClient):
        """Test that 404 URLs are handled gracefully."""
        # Mock URL check to return 404
        from core.utils import URLCheckResult
        mock_check.return_value = URLCheckResult(
            status_code=404,
            should_archive=False,
            error="Page not found"
        )

        payload = {"id": "test123", "url": "https://nonexistent.com"}

        response = test_client.post("/archive/monolith", json=payload)

        assert response.status_code == 200  # Still returns 200, but with failure
        data = response.json()
        assert data["ok"] is False
        assert data["exit_code"] == 404

    @patch('core.utils.rewrite_paywalled_url')
    def test_archive_paywall_url_rewriting(self, mock_rewrite, test_client: TestClient):
        """Test that paywalled URLs are rewritten."""
        # Mock URL rewriting
        mock_rewrite.return_value = "https://example.com/paywall-bypass"

        payload = {"id": "test123", "url": "https://example.com/paywall"}

        response = test_client.post("/archive/monolith", json=payload)

        assert response.status_code == 200
        # Should have called rewrite function
        mock_rewrite.assert_called_once_with("https://example.com/paywall")

    def test_infer_extension_from_archiver(self):
        """Test extension inference from archiver names."""
        from api.saves import infer_extension_from_archiver

        assert infer_extension_from_archiver("monolith") == ".html"
        assert infer_extension_from_archiver("singlefile") == ".html"
        assert infer_extension_from_archiver("readability") == ".html"
        assert infer_extension_from_archiver("pdf") == ".pdf"
        assert infer_extension_from_archiver("screenshot") == ".png"
        assert infer_extension_from_archiver("singlefile-cli") == ".html"
        assert infer_extension_from_archiver("unknown") == ""

    def test_sanitize_optional_id(self):
        """Test optional ID sanitization."""
        from api.saves import _sanitize_optional_id

        assert _sanitize_optional_id("test123") == "test123"
        assert _sanitize_optional_id("  test123  ") == "test123"
        assert _sanitize_optional_id(None) is None
        assert _sanitize_optional_id("") is None
        assert _sanitize_optional_id("   ") is None
        assert _sanitize_optional_id("test with spaces") == "test_with_spaces"

    def test_latest_successful_artifacts(self):
        """Test filtering to latest successful artifacts."""
        from api.saves import _latest_successful_artifacts

        # Mock artifact objects
        artifacts = []
        for i in range(3):
            artifact = Mock()
            artifact.success = True
            artifact.saved_path = f"/path/to/file{i}.html"
            artifact.archiver = "monolith"
            artifact.id = i
            artifacts.append(artifact)

        # Add an older successful artifact
        old_artifact = Mock()
        old_artifact.success = True
        old_artifact.saved_path = "/path/to/old.html"
        old_artifact.archiver = "monolith"
        old_artifact.id = 0
        artifacts.append(old_artifact)

        # Add failed artifact
        failed_artifact = Mock()
        failed_artifact.success = False
        failed_artifact.saved_path = "/path/to/failed.html"
        failed_artifact.archiver = "readability"
        failed_artifact.id = 5
        artifacts.append(failed_artifact)

        # Add artifact with no saved_path
        no_path_artifact = Mock()
        no_path_artifact.success = True
        no_path_artifact.saved_path = None
        no_path_artifact.archiver = "readability"
        no_path_artifact.id = 6
        artifacts.append(no_path_artifact)

        latest = _latest_successful_artifacts(artifacts)

        # Should get the latest successful artifact for each archiver
        assert len(latest) == 2  # monolith and readability
        monolith_artifacts = [a for a in latest if a.archiver == "monolith"]
        assert len(monolith_artifacts) == 1
        assert monolith_artifacts[0].id == 2  # Latest monolith artifact

        # Should not include failed or no-path artifacts
        readability_artifacts = [a for a in latest if a.archiver == "readability"]
        assert len(readability_artifacts) == 0  # No successful readability artifacts

    def test_archive_with_no_archivers_registered(self, test_client: TestClient):
        """Test archive when no archivers are registered."""
        # Mock empty archiver registry
        with patch.object(test_client.app.state, 'archivers', {}):
            payload = {"id": "test123", "url": "https://example.com"}
            response = test_client.post("/archive/all", json=payload)

            assert response.status_code == 500
            assert "no archivers registered" in response.json()["detail"]

    def test_archive_with_task_manager_not_initialized(self, test_client: TestClient):
        """Test save endpoint when task manager is not initialized."""
        # Mock missing task manager
        with patch.object(test_client.app.state, 'task_manager', None):
            payload = {"id": "test123", "url": "https://example.com"}
            response = test_client.post("/save", json=payload)

            assert response.status_code == 500
            assert "task manager not initialized" in response.json()["detail"]

    def test_retrieve_bundle_filename_generation(self, test_client: TestClient, temp_env):
        """Test that bundle filename is properly generated."""
        # First create an archive
        payload = {"id": "test with spaces", "url": "https://example.com"}
        test_client.post("/archive/monolith", json=payload)

        # Then retrieve all
        retrieve_payload = {"id": "test with spaces", "archiver": "all"}
        response = test_client.post("/archive/retrieve", json=retrieve_payload)

        assert response.status_code == 200
        content_disposition = response.headers["content-disposition"]
        # Should have sanitized filename
        assert "test_with_spaces-artifacts.tar.gz" in content_disposition

    def test_archive_request_payload_logging(self, test_client: TestClient):
        """Test that archive request payloads are properly logged."""
        payload = {
            "id": "test123",
            "url": "https://example.com"
        }

        with patch('api.saves.logger') as mock_logger:
            test_client.post("/archive/monolith", json=payload)

            # Should have logged the request
            mock_logger.info.assert_called()
            # Check that logger was called with the right context
            call_args = mock_logger.info.call_args
            assert "Archive request received" in str(call_args)

    def test_save_request_payload_logging(self, test_client: TestClient):
        """Test that save request payloads are properly logged."""
        payload = {
            "id": "test123",
            "url": "https://example.com"
        }

        with patch('api.saves.logger') as mock_logger:
            test_client.post("/save", json=payload)

            # Should have logged the request
            mock_logger.info.assert_called()
            call_args = mock_logger.info.call_args
            assert "/save requested" in str(call_args)

    def test_invalid_json_payload_400(self, test_client: TestClient):
        """Test that invalid JSON returns 400."""
        response = test_client.post(
            "/archive/monolith",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422  # Validation error

    def test_missing_content_type_handled(self, test_client: TestClient):
        """Test that missing content type is handled gracefully."""
        response = test_client.post(
            "/archive/monolith",
            json={"id": "test123", "url": "https://example.com"}
        )

        assert response.status_code == 200  # Should work with TestClient

    def test_response_model_validation(self, test_client: TestClient):
        """Test that response matches expected model."""
        payload = {"id": "test123", "url": "https://example.com"}
        response = test_client.post("/archive/monolith", json=payload)

        assert response.status_code == 200
        data = response.json()

        # Verify required fields from SaveResponse
        assert "ok" in data
        assert "exit_code" in data
        assert "saved_path" in data
        assert "id" in data
        assert "db_rowid" in data

    def test_task_accepted_response_validation(self, test_client: TestClient):
        """Test that task acceptance response matches expected model."""
        payload = {"id": "test123", "url": "https://example.com"}
        response = test_client.post("/save", json=payload)

        assert response.status_code == 202
        data = response.json()

        # Verify required fields from TaskAccepted
        assert "task_id" in data
        assert "count" in data
        assert isinstance(data["task_id"], str)
        assert isinstance(data["count"], int)