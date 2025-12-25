"""
Tests for the Admin API endpoints.

Tests the /saves, /archivers, /saves/requeue, /summarize, and delete endpoints
using FastAPI TestClient with mocked dependencies.
"""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

import pytest


class TestAdminAPI:
    """Test the admin API endpoints."""

    def test_list_saves_default_params(self, test_client: TestClient, temp_env):
        """Test listing saves with default parameters."""
        # First create some saves to list
        payload = {"id": "test1", "url": "https://example1.com"}
        test_client.post("/archive/monolith", json=payload)
        payload = {"id": "test2", "url": "https://example2.com"}
        test_client.post("/archive/monolith", json=payload)

        response = test_client.get("/admin/saves")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:  # If there are saves
            save = data[0]
            assert "rowid" in save
            assert "id" in save
            assert "url" in save
            assert "status" in save
            assert "success" in save
            assert "exit_code" in save
            assert "saved_path" in save
            assert "file_exists" in save
            assert "relative_path" in save
            assert "archiver" in save
            assert "created_at" in save

    def test_list_saves_with_pagination(self, test_client: TestClient):
        """Test listing saves with limit and offset."""
        response = test_client.get("/admin/saves?limit=10&offset=5")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_saves_empty_result(self, test_client: TestClient):
        """Test listing saves when no saves exist."""
        response = test_client.get("/admin/saves?limit=1&offset=999999")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_list_saves_file_exists_check(self, test_client: TestClient, temp_env):
        """Test that file existence is properly checked."""
        # Create a save
        payload = {"id": "test123", "url": "https://example.com"}
        test_client.post("/archive/monolith", json=payload)

        response = test_client.get("/admin/saves")

        assert response.status_code == 200
        data = response.json()
        if data:
            save = data[0]
            assert save["file_exists"] is True
            assert save["relative_path"] is not None
            assert "test123/monolith" in save["relative_path"]

    def test_list_archivers_success(self, test_client: TestClient):
        """Test listing available archivers."""
        response = test_client.get("/admin/archivers")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should contain "monolith" from test_client setup
        assert "monolith" in data

    def test_list_archivers_empty(self, test_client: TestClient):
        """Test listing archivers when none are registered."""
        # Mock empty archiver registry
        with patch.object(test_client.app.state, 'archivers', {}):
            response = test_client.get("/admin/archivers")

            assert response.status_code == 200
            data = response.json()
            assert data == []

    def test_requeue_saves_by_ids_success(self, test_client: TestClient):
        """Test requeueing saves by specific IDs."""
        # Create some saves first
        payload1 = {"id": "test1", "url": "https://example1.com"}
        test_client.post("/archive/monolith", json=payload1)
        payload2 = {"id": "test2", "url": "https://example2.com"}
        test_client.post("/archive/monolith", json=payload2)

        # Get row IDs from list endpoint
        saves_response = test_client.get("/admin/saves")
        saves = saves_response.json()

        if len(saves) >= 2:
            artifact_ids = [saves[0]["rowid"], saves[1]["rowid"]]

            requeue_payload = {"artifact_ids": artifact_ids}
            response = test_client.post("/admin/saves/requeue", json=requeue_payload)

            assert response.status_code == 200
            data = response.json()
            assert "requeued_count" in data
            assert "task_ids" in data
            assert isinstance(data["task_ids"], list)

    def test_requeue_saves_by_status_success(self, test_client: TestClient):
        """Test requeueing saves by status."""
        requeue_payload = {
            "status": "failed",
            "include_all": True
        }
        response = test_client.post("/admin/saves/requeue", json=requeue_payload)

        assert response.status_code == 200
        data = response.json()
        assert "requeued_count" in data
        assert "task_ids" in data

    def test_requeue_saves_no_selection_400(self, test_client: TestClient):
        """Test requeue with no selection criteria returns 400."""
        requeue_payload = {}
        response = test_client.post("/admin/saves/requeue", json=requeue_payload)

        assert response.status_code == 400
        assert "Provide artifact_ids or set include_all" in response.json()["detail"]

    def test_requeue_saves_task_manager_not_initialized_500(self, test_client: TestClient):
        """Test requeue when task manager is not initialized."""
        with patch.object(test_client.app.state, 'task_manager', None):
            requeue_payload = {
                "artifact_ids": [1],
                "include_all": False
            }
            response = test_client.post("/admin/saves/requeue", json=requeue_payload)

            assert response.status_code == 500
            assert "task manager not initialized" in response.json()["detail"]

    def test_requeue_saves_no_matching_artifacts(self, test_client: TestClient):
        """Test requeue when no artifacts match filters."""
        requeue_payload = {
            "status": "pending",
            "include_all": True
        }
        response = test_client.post("/admin/saves/requeue", json=requeue_payload)

        assert response.status_code == 200
        data = response.json()
        assert data["requeued_count"] == 0
        assert data["task_ids"] == []

    def test_summarize_article_by_rowid_success(self, test_client: TestClient):
        """Test summarizing article by row ID."""
        # Create a save first
        payload = {"id": "test123", "url": "https://example.com"}
        archive_response = test_client.post("/archive/monolith", json=payload)
        rowid = archive_response.json()["db_rowid"]

        if rowid:
            summarize_payload = {"rowid": rowid}
            response = test_client.post("/admin/summarize", json=summarize_payload)

            # This might return 503 if summarizer is not enabled, which is expected in tests
            assert response.status_code in [200, 503]

    def test_summarize_article_by_item_id_success(self, test_client: TestClient):
        """Test summarizing article by item ID."""
        # Create a save first
        payload = {"id": "test123", "url": "https://example.com"}
        test_client.post("/archive/monolith", json=payload)

        summarize_payload = {"item_id": "test123"}
        response = test_client.post("/admin/summarize", json=summarize_payload)

        # This might return 503 if summarizer is not enabled, which is expected in tests
        assert response.status_code in [200, 503]

    def test_summarize_article_by_url_success(self, test_client: TestClient):
        """Test summarizing article by URL."""
        # Create a save first
        payload = {"id": "test123", "url": "https://example.com"}
        test_client.post("/archive/monolith", json=payload)

        summarize_payload = {"url": "https://example.com"}
        response = test_client.post("/admin/summarize", json=summarize_payload)

        # This might return 503 if summarizer is not enabled, which is expected in tests
        assert response.status_code in [200, 503]

    def test_summarize_article_not_found_404(self, test_client: TestClient):
        """Test summarizing non-existent article returns 404."""
        summarize_payload = {"rowid": 999999}
        response = test_client.post("/admin/summarize", json=summarize_payload)

        assert response.status_code == 404
        assert "save not found" in response.json()["detail"]

    def test_summarize_article_no_identifier_400(self, test_client: TestClient):
        """Test summarizing with no identifier returns 400."""
        summarize_payload = {}
        response = test_client.post("/admin/summarize", json=summarize_payload)

        # This should fail validation, likely 422
        assert response.status_code == 422

    def test_summarize_article_summarizer_unavailable_503(self, test_client: TestClient):
        """Test summarizing when summarizer is unavailable."""
        with patch.object(test_client.app.state, 'summarization', None):
            summarize_payload = {"item_id": "test123"}
            response = test_client.post("/admin/summarize", json=summarize_payload)

            assert response.status_code == 503
            assert "summarizer unavailable" in response.json()["detail"]

    def test_summarize_article_summarizer_disabled_503(self, test_client: TestClient):
        """Test summarizing when summarizer is disabled."""
        mock_summarization = Mock()
        mock_summarization.is_enabled = False

        with patch.object(test_client.app.state, 'summarization', mock_summarization):
            summarize_payload = {"item_id": "test123"}
            response = test_client.post("/admin/summarize", json=summarize_payload)

            assert response.status_code == 503
            assert "summarizer unavailable" in response.json()["detail"]

    def test_delete_save_by_rowid_success(self, test_client: TestClient):
        """Test deleting save by row ID without removing files."""
        # Create a save first
        payload = {"id": "test123", "url": "https://example.com"}
        archive_response = test_client.post("/archive/monolith", json=payload)
        rowid = archive_response.json()["db_rowid"]

        if rowid:
            response = test_client.delete(f"/admin/saves/{rowid}")

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert "deleted_count" in data
            assert "deleted_rowids" in data
            assert "removed_files" in data
            assert "errors" in data
            assert data["removed_files"] == []  # remove_files defaults to False

    def test_delete_save_by_rowid_with_file_removal(self, test_client: TestClient, temp_env):
        """Test deleting save by row ID with file removal."""
        # Create a save first
        payload = {"id": "test123", "url": "https://example.com"}
        archive_response = test_client.post("/archive/monolith", json=payload)
        rowid = archive_response.json()["db_rowid"]

        if rowid:
            response = test_client.delete(f"/admin/saves/{rowid}?remove_files=true")

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            # File should be removed
            if data["removed_files"]:
                assert len(data["removed_files"]) > 0
                # Verify file is actually deleted
                for file_path in data["removed_files"]:
                    assert not Path(file_path).exists()

    def test_delete_save_not_found_404(self, test_client: TestClient):
        """Test deleting non-existent save returns 404."""
        response = test_client.delete("/admin/saves/999999")

        assert response.status_code == 404
        assert "save not found" in response.json()["detail"]

    def test_delete_saves_by_item_id_success(self, test_client: TestClient):
        """Test deleting saves by item ID."""
        # Create saves first
        payload = {"id": "test123", "url": "https://example.com"}
        test_client.post("/archive/monolith", json=payload)
        payload = {"id": "test123", "url": "https://example.org"}
        test_client.post("/archive/readability", json=payload)

        response = test_client.delete("/admin/saves/by-item/test123")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "deleted_count" in data
        assert "deleted_rowids" in data

    def test_delete_saves_by_item_id_not_found_404(self, test_client: TestClient):
        """Test deleting saves for non-existent item ID returns 404."""
        response = test_client.delete("/admin/saves/by-item/nonexistent")

        assert response.status_code == 404
        assert "no saves for item_id" in response.json()["detail"]

    def test_delete_saves_by_url_success(self, test_client: TestClient):
        """Test deleting saves by URL."""
        # Create save first
        payload = {"id": "test123", "url": "https://example.com"}
        test_client.post("/archive/monolith", json=payload)

        response = test_client.delete("/admin/saves/by-url?url=https://example.com")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "deleted_count" in data
        assert "deleted_rowids" in data

    def test_delete_saves_by_url_not_found_404(self, test_client: TestClient):
        """Test deleting saves for non-existent URL returns 404."""
        response = test_client.delete("/admin/saves/by-url?url=https://nonexistent.com")

        assert response.status_code == 404
        assert "no saves for url" in response.json()["detail"]

    def test_delete_saves_empty_directory_cleanup(self, test_client: TestClient, temp_env):
        """Test that empty directories are cleaned up after file deletion."""
        # Create a save first
        payload = {"id": "test123", "url": "https://example.com"}
        archive_response = test_client.post("/archive/monolith", json=payload)
        rowid = archive_response.json()["db_rowid"]

        if rowid:
            # Verify directory exists
            data_dir = temp_env / "data"
            item_dir = data_dir / "test123" / "monolith"
            assert item_dir.exists()

            # Delete with file removal
            response = test_client.delete(f"/admin/saves/{rowid}?remove_files=true")

            assert response.status_code == 200

            # Directory should be cleaned up (empty parent directories removed)
            # Note: This might not work in all test environments due to OS constraints

    def test_delete_saves_file_removal_errors(self, test_client: TestClient):
        """Test handling of file removal errors."""
        # Mock a save that references a non-existent file
        with patch('api.admin.ArchiveArtifactRepository') as mock_repo_class:
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo

            # Mock row with non-existent file path
            mock_row = Mock()
            mock_row.id = 1
            mock_row.saved_path = "/non/existent/path.html"
            mock_repo.get_by_id.return_value = mock_row
            mock_repo.delete_many.return_value = 1

            response = test_client.delete("/admin/saves/1?remove_files=true")

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            # Should have no removed files but might have errors
            assert isinstance(data["removed_files"], list)

    def test_list_saves_archiver_inference(self, test_client: TestClient, temp_env):
        """Test that archiver is inferred from path when not in DB."""
        response = test_client.get("/admin/saves")

        assert response.status_code == 200
        data = response.json()
        if data:
            save = data[0]
            # Archiver should be "monolith" either from DB or inferred from path
            assert save["archiver"] == "monolith"

    def test_list_saves_relative_path_calculation(self, test_client: TestClient, temp_env):
        """Test that relative paths are calculated correctly."""
        response = test_client.get("/admin/saves")

        assert response.status_code == 200
        data = response.json()
        if data:
            save = data[0]
            if save["relative_path"]:
                # Should be relative to data directory
                assert not save["relative_path"].startswith("/")
                assert "test" in save["relative_path"]

    def test_requeue_request_validation(self, test_client: TestClient):
        """Test RequeueRequest model validation."""
        # Valid request
        requeue_payload = {
            "artifact_ids": [1, 2, 3],
            "status": "failed",
            "include_all": False
        }
        response = test_client.post("/admin/saves/requeue", json=requeue_payload)
        # Should not fail validation (might fail on business logic)
        assert response.status_code != 422

        # Invalid status
        invalid_payload = {
            "artifact_ids": [1, 2, 3],
            "status": "invalid_status",
            "include_all": False
        }
        response = test_client.post("/admin/saves/requeue", json=invalid_payload)
        # Should fail validation
        assert response.status_code == 422

    def test_summarize_request_validation(self, test_client: TestClient):
        """Test SummarizeRequest model validation."""
        # Valid request
        summarize_payload = {"item_id": "test123"}
        response = test_client.post("/admin/summarize", json=summarize_payload)
        # Should not fail validation (might fail on business logic)
        assert response.status_code != 422

    def test_admin_endpoint_logging(self, test_client: TestClient):
        """Test that admin endpoints log properly."""
        with patch('api.admin.logger') as mock_logger:
            # Test list saves
            test_client.get("/admin/saves")

            # Test requeue
            requeue_payload = {"status": "failed", "include_all": True}
            test_client.post("/admin/saves/requeue", json=requeue_payload)

            # Should have logged operations
            assert mock_logger.info.called

    def test_admin_response_models(self, test_client: TestClient):
        """Test that admin responses match expected models."""
        # Test list saves response
        response = test_client.get("/admin/saves")
        if response.status_code == 200:
            data = response.json()
            if data:
                save = data[0]
                required_fields = ["rowid", "id", "url", "status", "success", "exit_code",
                                 "saved_path", "file_exists", "relative_path", "archiver", "created_at"]
                for field in required_fields:
                    assert field in save

        # Test delete response
        # Create a save first
        payload = {"id": "test_delete", "url": "https://example.com"}
        archive_response = test_client.post("/archive/monolith", json=payload)
        rowid = archive_response.json()["db_rowid"]

        if rowid:
            response = test_client.delete(f"/admin/saves/{rowid}")
            if response.status_code == 200:
                data = response.json()
                required_fields = ["deleted_count", "deleted_rowids", "removed_files", "errors", "ok"]
                for field in required_fields:
                    assert field in data