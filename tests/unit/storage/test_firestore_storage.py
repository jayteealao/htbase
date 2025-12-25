"""
Tests for FirestoreStorage.

Tests Firestore storage implementation using mocks to avoid actual Firestore calls.
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import pytest

from storage.firestore_storage import FirestoreStorage
from storage.database_storage import (
    ArticleMetadata,
    ArchiveArtifact,
    PocketData,
    ArticleSummary,
    ArticleEntity,
    ArticleTag,
    ArchiveStatus
)


class TestFirestoreStorage:
    """Test FirestoreStorage implementation."""

    def test_provider_name(self):
        """Test provider name is correct."""
        with patch('storage.firestore_storage.firestore.Client'):
            storage = FirestoreStorage("test-project")
            assert storage.provider_name == "firestore"

    def test_supports_transactions(self):
        """Test transaction support flag."""
        with patch('storage.firestore_storage.firestore.Client'):
            storage = FirestoreStorage("test-project")
            assert storage.supports_transactions is True

    def test_supports_full_text_search(self):
        """Test full-text search support flag."""
        with patch('storage.firestore_storage.firestore.Client'):
            storage = FirestoreStorage("test-project")
            assert storage.supports_full_text_search is False

    # ==================== Initialization Tests ====================

    def test_initialization(self):
        """Test initialization with project ID."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            storage = FirestoreStorage("test-project")

            mock_client.assert_called_once_with(project="test-project")
            assert storage.articles_ref is not None

    # ==================== Article Operations Tests ====================

    def test_create_article_success(self):
        """Test successful article creation."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            # Mock Firestore components
            mock_collection = Mock()
            mock_doc = Mock()
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            metadata = ArticleMetadata(
                item_id="test123",
                url="https://example.com",
                title="Test Article",
                byline="Test Author",
                excerpt="Test excerpt",
                text_content="Test content",
                word_count=100
            )

            result = storage.create_article(metadata)

            assert result is True
            mock_collection.document.assert_called_once_with("test123")
            mock_doc.set.assert_called_once()

    def test_create_article_minimal_metadata(self):
        """Test article creation with minimal metadata."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            metadata = ArticleMetadata(
                item_id="test123",
                url="https://example.com"
            )

            result = storage.create_article(metadata)

            assert result is True
            call_args = mock_doc.set.call_args[0][0]
            assert call_args["item_id"] == "test123"
            assert call_args["url"] == "https://example.com"
            assert "metadata" in call_args  # Should be included even if empty

    def test_create_article_failure(self):
        """Test article creation with Firestore error."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_doc.set.side_effect = Exception("Firestore error")
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            metadata = ArticleMetadata(
                item_id="test123",
                url="https://example.com"
            )

            result = storage.create_article(metadata)

            assert result is False

    def test_get_article_success(self):
        """Test successful article retrieval."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            # Mock Firestore components
            mock_collection = Mock()
            mock_doc = Mock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = {
                "item_id": "test123",
                "url": "https://example.com",
                "title": "Test Article",
                "byline": "Test Author",
                "excerpt": "Test excerpt",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "metadata": {
                    "textContent": "Test content",
                    "wordCount": 100
                },
                "archives": {},
                "pocket": None,
                "summary": None,
                "entities": [],
                "tags": []
            }
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            article = storage.get_article("test123")

            assert article is not None
            assert article.metadata.item_id == "test123"
            assert article.metadata.url == "https://example.com"
            assert article.metadata.title == "Test Article"
            assert article.metadata.text_content == "Test content"
            assert article.metadata.word_count == 100

    def test_get_article_not_found(self):
        """Test article retrieval for non-existent article."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_doc.exists = False
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            article = storage.get_article("nonexistent")

            assert article is None

    def test_get_article_by_url_success(self):
        """Test successful article retrieval by URL."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            # Mock Firestore components
            mock_collection = Mock()
            mock_query = Mock()
            mock_doc = Mock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = {
                "item_id": "test123",
                "url": "https://example.com",
                "title": "Test Article",
                "created_at": datetime.utcnow(),
                "metadata": {},
                "archives": {},
                "pocket": None,
                "summary": None,
                "entities": [],
                "tags": []
            }
            mock_query.stream.return_value = [mock_doc]
            mock_collection.where.return_value.limit.return_value = mock_query
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            article = storage.get_article_by_url("https://example.com")

            assert article is not None
            assert article.metadata.url == "https://example.com"
            mock_collection.where.assert_called_once_with("url", "==", "https://example.com")

    def test_get_article_by_url_not_found(self):
        """Test article retrieval by URL for non-existent article."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_query = Mock()
            mock_query.stream.return_value = []
            mock_collection.where.return_value.limit.return_value = mock_query
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            article = storage.get_article_by_url("https://nonexistent.com")

            assert article is None

    def test_update_article_metadata_success(self):
        """Test successful article metadata update."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            metadata = {
                "title": "Updated Title",
                "word_count": 200
            }

            result = storage.update_article_metadata("test123", metadata)

            assert result is True
            mock_doc.update.assert_called_once()
            call_args = mock_doc.update.call_args[0][0]
            assert call_args["title"] == "Updated Title"
            assert call_args["word_count"] == 200
            assert "updated_at" in call_args

    def test_delete_article_success(self):
        """Test successful article deletion."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            result = storage.delete_article("test123")

            assert result is True
            mock_doc.delete.assert_called_once()

    def test_list_articles_success(self):
        """Test successful article listing."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_query = Mock()
            mock_doc1 = Mock()
            mock_doc1.to_dict.return_value = {
                "item_id": "test1",
                "url": "https://example1.com",
                "created_at": datetime.utcnow(),
                "metadata": {},
                "archives": {},
                "pocket": None,
                "summary": None,
                "entities": [],
                "tags": []
            }
            mock_doc2 = Mock()
            mock_doc2.to_dict.return_value = {
                "item_id": "test2",
                "url": "https://example2.com",
                "created_at": datetime.utcnow(),
                "metadata": {},
                "archives": {},
                "pocket": None,
                "summary": None,
                "entities": [],
                "tags": []
            }
            mock_query.stream.return_value = [mock_doc1, mock_doc2]
            mock_collection.limit.return_value = mock_query
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            articles = storage.list_articles(limit=2)

            assert len(articles) == 2
            assert articles[0].metadata.item_id == "test1"
            assert articles[1].metadata.item_id == "test2"
            mock_collection.limit.assert_called_once_with(2)

    # ==================== Archive Artifact Tests ====================

    def test_create_artifact_success(self):
        """Test successful artifact creation."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            artifact = ArchiveArtifact(
                item_id="test123",
                archiver="monolith",
                status=ArchiveStatus.SUCCESS,
                gcs_path="archives/test.html",
                gcs_bucket="test-bucket",
                local_path=None,
                file_size=1024,
                exit_code=0
            )

            result = storage.create_artifact(artifact)

            assert result is True
            mock_doc.update.assert_called_once()
            call_args = mock_doc.update.call_args[0][0]
            assert "archives.monolith" in call_args
            assert call_args["archives.monolith"]["status"] == "success"

    def test_create_artifact_creates_document(self):
        """Test artifact creation creates document if not exists."""
        from google.api_core.exceptions import NotFound

        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            # First call raises NotFound (document doesn't exist)
            # Second call succeeds (document creation)
            mock_doc.update.side_effect = [NotFound("Document not found"), None]
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            artifact = ArchiveArtifact(
                item_id="test123",
                archiver="monolith",
                status=ArchiveStatus.SUCCESS
            )

            result = storage.create_artifact(artifact)

            assert result is True
            assert mock_doc.update.call_count == 2  # First fails, second creates
            assert mock_doc.set.call_count == 1  # Document creation

    def test_get_artifacts_success(self):
        """Test successful artifact retrieval."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = {
                "item_id": "test123",
                "archives": {
                    "monolith": {
                        "status": "success",
                        "gcs_path": "archives/test.html",
                        "gcs_bucket": "test-bucket",
                        "file_size": 1024,
                        "exit_code": 0,
                        "created_at": datetime.utcnow()
                    },
                    "readability": {
                        "status": "pending",
                        "created_at": datetime.utcnow()
                    }
                }
            }
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            artifacts = storage.get_artifacts("test123")

            assert len(artifacts) == 2
            assert artifacts[0].item_id == "test123"
            assert artifacts[0].archiver == "monolith"
            assert artifacts[0].status == ArchiveStatus.SUCCESS
            assert artifacts[1].archiver == "readability"
            assert artifacts[1].status == ArchiveStatus.PENDING

    def test_get_artifact_success(self):
        """Test successful specific artifact retrieval."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = {
                "item_id": "test123",
                "archives": {
                    "monolith": {
                        "status": "success",
                        "gcs_path": "archives/test.html",
                        "gcs_bucket": "test-bucket",
                        "file_size": 1024,
                        "exit_code": 0,
                        "created_at": datetime.utcnow()
                    }
                }
            }
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            artifact = storage.get_artifact("test123", "monolith")

            assert artifact is not None
            assert artifact.item_id == "test123"
            assert artifact.archiver == "monolith"
            assert artifact.status == ArchiveStatus.SUCCESS
            assert artifact.gcs_path == "archives/test.html"
            assert artifact.gcs_bucket == "test-bucket"

    def test_update_artifact_status_success(self):
        """Test successful artifact status update."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            result = storage.update_artifact_status(
                "test123",
                "monolith",
                ArchiveStatus.SUCCESS,
                gcs_path="updated/path.html",
                file_size=2048
            )

            assert result is True
            mock_doc.update.assert_called_once()
            call_args = mock_doc.update.call_args[0][0]
            assert call_args["archives.monolith.status"] == "success"
            assert call_args["archives.monolith.gcs_path"] == "updated/path.html"
            assert call_args["archives.monolith.file_size"] == 2048

    # ==================== Pocket Data Tests ====================

    def test_create_pocket_data_success(self):
        """Test successful Pocket data creation."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            pocket_data = PocketData(
                item_id="test123",
                resolved_id="resolved123",
                word_count=500,
                time_added=datetime.utcnow(),
                time_read=datetime.utcnow(),
                favorite=True,
                status="unread",
                images=[{"url": "https://example.com/image.jpg"}],
                authors=[{"name": "Test Author"}]
            )

            result = storage.create_pocket_data(pocket_data)

            assert result is True
            mock_doc.update.assert_called_once()
            call_args = mock_doc.update.call_args[0][0]
            assert "pocket" in call_args
            assert call_args["pocket"]["itemId"] == "test123"
            assert call_args["pocket"]["wordCount"] == 500

    def test_get_pocket_data_success(self):
        """Test successful Pocket data retrieval."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = {
                "item_id": "test123",
                "pocket": {
                    "itemId": "test123",
                    "resolvedId": "resolved123",
                    "wordCount": 500,
                    "timeAdded": datetime.utcnow(),
                    "favorite": True,
                    "status": "unread"
                }
            }
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            pocket = storage.get_pocket_data("test123")

            assert pocket is not None
            assert pocket.item_id == "test123"
            assert pocket.resolved_id == "resolved123"
            assert pocket.word_count == 500
            assert pocket.favorite is True
            assert pocket.status == "unread"

    def test_get_pocket_data_not_found(self):
        """Test Pocket data retrieval for non-existent data."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = {"item_id": "test123"}  # No pocket data
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            pocket = storage.get_pocket_data("test123")

            assert pocket is None

    # ==================== Summary Tests ====================

    def test_create_summary_success(self):
        """Test successful summary creation."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            summary = ArticleSummary(
                item_id="test123",
                summary="This is a test summary",
                created_at=datetime.utcnow()
            )

            result = storage.create_summary(summary)

            assert result is True
            mock_doc.update.assert_called_once()
            call_args = mock_doc.update.call_args[0][0]
            assert "summary" in call_args
            assert call_args["summary"]["text"] == "This is a test summary"

    def test_get_summary_success(self):
        """Test successful summary retrieval."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = {
                "item_id": "test123",
                "summary": {
                    "text": "Test summary",
                    "createdAt": datetime.utcnow()
                }
            }
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            summary = storage.get_summary("test123")

            assert summary is not None
            assert summary.item_id == "test123"
            assert summary.summary == "Test summary"

    # ==================== Entity Tests ====================

    def test_create_entities_success(self):
        """Test successful entity creation."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            entities = [
                ArticleEntity(
                    item_id="test123",
                    entity_type="PERSON",
                    entity_value="John Doe",
                    confidence=0.9
                ),
                ArticleEntity(
                    item_id="test123",
                    entity_type="ORGANIZATION",
                    entity_value="Example Corp",
                    confidence=0.8
                )
            ]

            result = storage.create_entities(entities)

            assert result is True
            mock_doc.update.assert_called_once()
            call_args = mock_doc.update.call_args[0][0]
            assert "entities" in call_args
            assert len(call_args["entities"]) == 2
            assert call_args["entities"][0]["type"] == "PERSON"
            assert call_args["entities"][0]["value"] == "John Doe"

    def test_get_entities_success(self):
        """Test successful entity retrieval."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = {
                "item_id": "test123",
                "entities": [
                    {
                        "type": "PERSON",
                        "value": "John Doe",
                        "confidence": 0.9
                    },
                    {
                        "type": "ORGANIZATION",
                        "value": "Example Corp",
                        "confidence": 0.8
                    }
                ]
            }
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            entities = storage.get_entities("test123")

            assert len(entities) == 2
            assert entities[0].item_id == "test123"
            assert entities[0].entity_type == "PERSON"
            assert entities[0].entity_value == "John Doe"
            assert entities[0].confidence == 0.9

    # ==================== Tag Tests ====================

    def test_create_tags_success(self):
        """Test successful tag creation."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            tags = [
                ArticleTag(
                    item_id="test123",
                    tag="technology",
                    confidence=0.9
                ),
                ArticleTag(
                    item_id="test123",
                    tag="programming",
                    confidence=0.8
                )
            ]

            result = storage.create_tags(tags)

            assert result is True
            mock_doc.update.assert_called_once()
            call_args = mock_doc.update.call_args[0][0]
            assert "tags" in call_args
            assert len(call_args["tags"]) == 2

    def test_get_tags_success(self):
        """Test successful tag retrieval."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_doc = Mock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = {
                "item_id": "test123",
                "tags": [
                    {
                        "tag": "technology",
                        "confidence": 0.9
                    },
                    {
                        "tag": "programming",
                        "confidence": 0.8
                    }
                ]
            }
            mock_collection.document.return_value = mock_doc
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            tags = storage.get_tags("test123")

            assert len(tags) == 2
            assert tags[0].item_id == "test123"
            assert tags[0].tag == "technology"
            assert tags[0].confidence == 0.9

    # ==================== Batch Operations Tests ====================

    def test_batch_create_articles_success(self):
        """Test successful batch article creation."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_batch = Mock()
            mock_client.return_value.collection.return_value = mock_collection
            mock_client.batch.return_value = mock_batch

            storage = FirestoreStorage("test-project")

            articles = [
                ArticleMetadata(
                    item_id="test1",
                    url="https://example1.com"
                ),
                ArticleMetadata(
                    item_id="test2",
                    url="https://example2.com"
                )
            ]

            count = storage.batch_create_articles(articles)

            assert count == 2
            assert mock_batch.set.call_count == 2
            mock_batch.commit.assert_called_once()

    def test_batch_update_artifacts_success(self):
        """Test successful batch artifact updates."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_batch = Mock()
            mock_client.return_value.collection.return_value = mock_collection
            mock_client.batch.return_value = mock_batch

            storage = FirestoreStorage("test-project")

            artifacts = [
                ArchiveArtifact(
                    item_id="test1",
                    archiver="monolith",
                    status=ArchiveStatus.SUCCESS
                ),
                ArchiveArtifact(
                    item_id="test2",
                    archiver="readability",
                    status=ArchiveStatus.SUCCESS
                )
            ]

            count = storage.batch_update_artifacts(artifacts)

            assert count == 2
            assert mock_batch.update.call_count == 2
            mock_batch.commit.assert_called_once()

    # ==================== Query Operations Tests ====================

    def test_count_articles_success(self):
        """Test successful article count."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_query = Mock()
            mock_doc1 = Mock()
            mock_doc2 = Mock()
            mock_query.stream.return_value = [mock_doc1, mock_doc2]
            mock_collection.where.return_value = mock_query
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            count = storage.count_articles()

            assert count == 2
            mock_collection.where.assert_not_called()  # No filters

    def test_search_articles_success(self):
        """Test successful article search."""
        with patch('storage.firestore_storage.firestore.Client') as mock_client:
            mock_collection = Mock()
            mock_query = Mock()
            mock_doc = Mock()
            mock_doc.to_dict.return_value = {
                "item_id": "test123",
                "url": "https://example.com",
                "title": "Test Article",
                "created_at": datetime.utcnow(),
                "metadata": {},
                "archives": {},
                "pocket": None,
                "summary": None,
                "entities": [],
                "tags": []
            }
            mock_query.stream.return_value = [mock_doc]
            mock_collection.where.return_value.where.return_value.limit.return_value = mock_query
            mock_client.return_value.collection.return_value = mock_collection

            storage = FirestoreStorage("test-project")

            articles = storage.search_articles("Test", limit=10)

            assert len(articles) == 1
            assert articles[0].metadata.item_id == "test123"
            mock_collection.where.assert_called()

    # ==================== Helper Method Tests ====================

    def test_dict_to_artifact_success(self):
        """Test conversion of dict to ArchiveArtifact."""
        with patch('storage.firestore_storage.firestore.Client'):
            storage = FirestoreStorage("test-project")

            data = {
                "status": "success",
                "gcs_path": "archives/test.html",
                "gcs_bucket": "test-bucket",
                "file_size": 1024,
                "exit_code": 0,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }

            artifact = storage._dict_to_artifact("test123", "monolith", data)

            assert artifact is not None
            assert artifact.item_id == "test123"
            assert artifact.archiver == "monolith"
            assert artifact.status == ArchiveStatus.SUCCESS
            assert artifact.gcs_path == "archives/test.html"
            assert artifact.gcs_bucket == "test-bucket"
            assert artifact.file_size == 1024

    def test_doc_to_article_record_success(self):
        """Test conversion of Firestore doc to ArticleRecord."""
        with patch('storage.firestore_storage.firestore.Client'):
            storage = FirestoreStorage("test-project")

            data = {
                "item_id": "test123",
                "url": "https://example.com",
                "title": "Test Article",
                "byline": "Test Author",
                "created_at": datetime.utcnow(),
                "metadata": {
                    "textContent": "Test content",
                    "wordCount": 100
                },
                "archives": {
                    "monolith": {
                        "status": "success",
                        "created_at": datetime.utcnow()
                    }
                },
                "pocket": None,
                "summary": None,
                "entities": [],
                "tags": []
            }

            article = storage._doc_to_article_record(data)

            assert article is not None
            assert article.metadata.item_id == "test123"
            assert article.metadata.url == "https://example.com"
            assert article.metadata.title == "Test Article"
            assert len(article.archives) == 1
            assert article.archives[0].archiver == "monolith"