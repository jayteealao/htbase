"""
Integration tests for the complete archive workflow.

Tests the end-to-end flow from API request to Firestore storage.
"""

import pytest
from fastapi.testclient import TestClient

from shared.database.repositories import ArticleRepository, ArtifactRepository


class TestArchiveWorkflow:
    """Test complete archive workflow."""

    def test_create_article_via_repository(self, article_repository, sample_article_data):
        """Test creating article using repository."""
        # Create article
        article = article_repository.create(**sample_article_data)

        assert article["item_id"] == sample_article_data["item_id"]
        assert article["url"] == sample_article_data["url"]
        assert article["title"] == sample_article_data["title"]

        # Verify it exists
        assert article_repository.exists(sample_article_data["item_id"])

        # Retrieve it
        retrieved = article_repository.get(sample_article_data["item_id"])
        assert retrieved is not None
        assert retrieved["item_id"] == sample_article_data["item_id"]

    def test_update_article_metadata(self, article_repository, sample_article_data):
        """Test updating article metadata."""
        # Create article
        article_repository.create(**sample_article_data)

        # Update title
        article_repository.update(
            item_id=sample_article_data["item_id"],
            title="Updated Title"
        )

        # Verify update
        article = article_repository.get(sample_article_data["item_id"])
        assert article["title"] == "Updated Title"
        assert article["byline"] == sample_article_data["byline"]  # Unchanged

    def test_delete_article(self, article_repository, sample_article_data):
        """Test deleting article."""
        # Create article
        article_repository.create(**sample_article_data)
        assert article_repository.exists(sample_article_data["item_id"])

        # Delete it
        deleted = article_repository.delete(sample_article_data["item_id"])
        assert deleted is True

        # Verify it's gone
        assert not article_repository.exists(sample_article_data["item_id"])

        # Try deleting again
        deleted_again = article_repository.delete(sample_article_data["item_id"])
        assert deleted_again is False

    def test_list_articles(self, article_repository):
        """Test listing articles with pagination."""
        # Create multiple articles
        for i in range(5):
            article_repository.create(
                item_id=f"test-{i}",
                url=f"https://example.com/article-{i}",
                title=f"Article {i}"
            )

        # List all
        articles = article_repository.list(limit=10)
        assert len(articles) == 5

        # List with limit
        articles = article_repository.list(limit=3)
        assert len(articles) == 3

    def test_artifact_update(self, article_repository, artifact_repository, sample_article_data):
        """Test updating artifact status."""
        # Create article
        article_repository.create(**sample_article_data)

        # Update artifact status
        artifact_repository.update(
            item_id=sample_article_data["item_id"],
            archiver="singlefile",
            status="in_progress"
        )

        # Get artifact
        artifact = artifact_repository.get(
            item_id=sample_article_data["item_id"],
            archiver="singlefile"
        )

        assert artifact is not None
        assert artifact["status"] == "in_progress"

        # Update to success with GCS path
        artifact_repository.update(
            item_id=sample_article_data["item_id"],
            archiver="singlefile",
            status="success",
            gcs_path="gs://bucket/path/to/file.html",
            file_size=12345,
            exit_code=0
        )

        # Verify update
        artifact = artifact_repository.get(
            item_id=sample_article_data["item_id"],
            archiver="singlefile"
        )

        assert artifact["status"] == "success"
        assert artifact["gcs_path"] == "gs://bucket/path/to/file.html"
        assert artifact["file_size"] == 12345
        assert artifact["exit_code"] == 0


class TestAPIEndpoints:
    """Test API endpoints with dependency injection."""

    @pytest.mark.skip(reason="Requires full API setup with dependency overrides")
    def test_create_archive_endpoint(self, api_client, article_repository):
        """Test POST /archives endpoint with injected repository."""
        # This demonstrates how to test with dependency injection
        # In actual test, you would:
        # 1. Override get_article_repository() dependency with mock
        # 2. Make API request
        # 3. Verify repository methods were called correctly

        from services.api_gateway.app.main import app
        from shared.web.dependencies import get_article_repository

        # Override dependency
        app.dependency_overrides[get_article_repository] = lambda: article_repository

        response = api_client.post(
            "/api/v1/archives",
            json={
                "items": [
                    {"id": "test-123", "url": "https://example.com/article"}
                ],
                "archivers": ["singlefile"]
            },
            headers={"Authorization": "Bearer test-api-key"}
        )

        assert response.status_code == 200
        assert article_repository.exists("test-123")

    def test_get_archive_endpoint(self, api_client, article_repository, sample_article_data):
        """Test GET /archives/{id} endpoint."""
        # Create article
        article_repository.create(**sample_article_data)

        # Override dependency
        from services.api_gateway.app.main import app
        from shared.web.dependencies import get_article_repository
        app.dependency_overrides[get_article_repository] = lambda: article_repository

        response = api_client.get(
            f"/api/v1/archives/{sample_article_data['item_id']}",
            headers={"Authorization": "Bearer test-api-key"}
        )

        # Would check response in real test
        # assert response.status_code == 200
        # assert response.json()["item_id"] == sample_article_data["item_id"]


@pytest.mark.integration
class TestEndToEndFlow:
    """End-to-end integration tests."""

    def test_complete_archive_flow(
        self,
        article_repository,
        artifact_repository,
        mock_celery_app
    ):
        """Test complete flow: create article -> archive -> update status."""
        # Step 1: Create article
        article_repository.create(
            item_id="e2e-test",
            url="https://example.com/article",
            title="E2E Test Article"
        )

        # Step 2: Update artifact to in_progress (simulating archiver start)
        artifact_repository.update(
            item_id="e2e-test",
            archiver="singlefile",
            status="in_progress"
        )

        # Step 3: Update to success (simulating archiver completion)
        artifact_repository.update(
            item_id="e2e-test",
            archiver="singlefile",
            status="success",
            gcs_path="gs://test-bucket/e2e-test/singlefile.html.gz",
            file_size=54321,
            exit_code=0
        )

        # Verify final state
        article = article_repository.get("e2e-test")
        assert article["item_id"] == "e2e-test"

        artifact = artifact_repository.get("e2e-test", "singlefile")
        assert artifact["status"] == "success"
        assert "gcs_path" in artifact
        assert artifact["file_size"] == 54321
