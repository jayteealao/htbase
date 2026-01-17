"""
Unit tests for repository implementations.
"""

import pytest
from shared.database.repositories import ArticleRepository, ArtifactRepository


class TestArticleRepository:
    """Test ArticleRepository in isolation."""

    def test_create_article(self, article_repository, sample_article_data):
        """Test article creation."""
        article = article_repository.create(**sample_article_data)

        assert article["item_id"] == sample_article_data["item_id"]
        assert article["url"] == sample_article_data["url"]
        assert "created_at" in article
        assert "updated_at" in article
        assert article["archives"] == {}

    def test_get_nonexistent_article(self, article_repository):
        """Test getting article that doesn't exist."""
        article = article_repository.get("nonexistent")
        assert article is None

    def test_exists_check(self, article_repository, sample_article_data):
        """Test article existence check."""
        assert not article_repository.exists(sample_article_data["item_id"])

        article_repository.create(**sample_article_data)

        assert article_repository.exists(sample_article_data["item_id"])

    def test_update_with_partial_data(self, article_repository, sample_article_data):
        """Test updating only some fields."""
        article_repository.create(**sample_article_data)

        # Update only title
        article_repository.update(
            item_id=sample_article_data["item_id"],
            title="New Title"
        )

        article = article_repository.get(sample_article_data["item_id"])
        assert article["title"] == "New Title"
        assert article["byline"] == sample_article_data["byline"]  # Unchanged

    def test_query_by_url(self, article_repository, sample_article_data):
        """Test querying article by URL."""
        article_repository.create(**sample_article_data)

        result = article_repository.query_by_url(sample_article_data["url"])
        assert result is not None
        assert result["url"] == sample_article_data["url"]

        # Query non-existent URL
        result = article_repository.query_by_url("https://nonexistent.com")
        assert result is None


class TestArtifactRepository:
    """Test ArtifactRepository in isolation."""

    def test_update_artifact_status(
        self,
        article_repository,
        artifact_repository,
        sample_article_data
    ):
        """Test updating artifact status."""
        # Create article first
        article_repository.create(**sample_article_data)

        # Update artifact
        artifact_repository.update(
            item_id=sample_article_data["item_id"],
            archiver="singlefile",
            status="success",
            gcs_path="gs://bucket/file.html",
            file_size=1234
        )

        # Retrieve artifact
        artifact = artifact_repository.get(
            item_id=sample_article_data["item_id"],
            archiver="singlefile"
        )

        assert artifact["status"] == "success"
        assert artifact["gcs_path"] == "gs://bucket/file.html"
        assert artifact["file_size"] == 1234

    def test_get_nonexistent_artifact(self, artifact_repository):
        """Test getting artifact that doesn't exist."""
        artifact = artifact_repository.get("nonexistent", "singlefile")
        assert artifact is None

    def test_multiple_artifacts_per_article(
        self,
        article_repository,
        artifact_repository,
        sample_article_data
    ):
        """Test multiple artifacts for same article."""
        # Create article
        article_repository.create(**sample_article_data)

        # Add multiple artifacts
        for archiver in ["singlefile", "monolith", "readability"]:
            artifact_repository.update(
                item_id=sample_article_data["item_id"],
                archiver=archiver,
                status="success",
                gcs_path=f"gs://bucket/{archiver}.html"
            )

        # Verify each artifact
        for archiver in ["singlefile", "monolith", "readability"]:
            artifact = artifact_repository.get(
                item_id=sample_article_data["item_id"],
                archiver=archiver
            )
            assert artifact is not None
            assert artifact["status"] == "success"
            assert archiver in artifact["gcs_path"]
