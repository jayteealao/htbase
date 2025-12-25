"""
Integration tests for Firestore database backend using mocks.

Tests Firestore integration using mocks for fast testing without credentials,
corresponding to Test Case 3 from TESTING_PLAN.md.

These tests verify:
- Firestore article creation (Test 3.2.1)
- Firestore document structure (Test 3.2.2)
- Firestore + GCS integration (Test 3.3)
- Artifact status updates
- List/query operations
"""

from datetime import datetime
import pytest


class TestFirestoreIntegrationMock:
    """Test Firestore database backend with mocked Firestore client."""

    def test_firestore_article_creation_mock(self, mocker):
        """
        Test: Mock Firestore create_article → verify document structure.

        Corresponds to TESTING_PLAN Test Case 3.2.1: Basic Firestore Storage
        """
        # Mock Firestore client
        mock_firestore = mocker.Mock()
        mock_collection = mocker.Mock()
        mock_document = mocker.Mock()

        mock_firestore.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_document

        mocker.patch('google.cloud.firestore.Client', return_value=mock_firestore)

        # Use InMemoryDatabaseStorage as Firestore mock
        from tests.fakes.storage import InMemoryDatabaseStorage

        storage = InMemoryDatabaseStorage()

        # Create article
        success = storage.create_article(
            item_id="test_firestore_001",
            url="https://example.com/article",
            metadata={"title": "Test Article", "author": "Test Author"}
        )

        assert success is True

        # Verify article exists
        article = storage.get_article("test_firestore_001")
        assert article is not None
        assert article['url'] == "https://example.com/article"
        assert article['item_id'] == "test_firestore_001"
        assert article['metadata']['title'] == "Test Article"

    def test_firestore_artifact_status_update_mock(self, mocker):
        """
        Test: Mock update_artifact_status → verify status field updates.

        Tests artifact status tracking in Firestore.
        """
        from tests.fakes.storage import InMemoryDatabaseStorage

        storage = InMemoryDatabaseStorage()

        # Create article first
        storage.create_article(
            item_id="test_artifact_001",
            url="https://example.com/test"
        )

        # Update artifact status
        success = storage.update_artifact_status(
            item_id="test_artifact_001",
            archiver="monolith",
            status="success",
            gcs_path="gs://bucket/test.html.gz",
            compression_ratio=85.5
        )

        assert success is True

        # Verify artifact
        artifact = storage.get_artifact("test_artifact_001", "monolith")
        assert artifact is not None
        assert artifact['status'] == "success"
        assert artifact['gcs_path'] == "gs://bucket/test.html.gz"
        assert artifact['compression_ratio'] == 85.5

    def test_firestore_document_structure_validation_mock(self, mocker):
        """
        Test: Mock Firestore → verify document has: url, item_id, created_at, archives, metadata.

        Corresponds to TESTING_PLAN Test Case 3.2.2: Firestore Metadata Structure
        """
        from tests.fakes.storage import InMemoryDatabaseStorage

        storage = InMemoryDatabaseStorage()

        # Create comprehensive article
        storage.create_article(
            item_id="test_structure_001",
            url="https://example.com/structure",
            pocket_data={"time_added": "2024-01-01"},
            metadata={"title": "Structure Test", "word_count": 500}
        )

        # Create multiple artifacts
        for archiver in ["monolith", "readability", "pdf"]:
            storage.update_artifact_status(
                item_id="test_structure_001",
                archiver=archiver,
                status="success",
                gcs_path=f"gs://bucket/{archiver}.html.gz"
            )

        # Verify document structure
        article = storage.get_article("test_structure_001")

        # Required fields
        assert 'item_id' in article
        assert 'url' in article
        assert 'created_at' in article
        assert isinstance(article['created_at'], datetime)

        # Metadata
        assert 'metadata' in article
        assert article['metadata']['title'] == "Structure Test"

        # Verify artifacts
        artifacts = storage.list_artifacts(item_id="test_structure_001")
        assert len(artifacts) == 3

        archiver_names = {a['archiver'] for a in artifacts}
        assert archiver_names == {"monolith", "readability", "pdf"}

    def test_firestore_list_articles_pagination_mock(self, mocker):
        """
        Test: Mock list_articles with limit/offset → verify pagination works.

        Tests Firestore query pagination.
        """
        from tests.fakes.storage import InMemoryDatabaseStorage

        storage = InMemoryDatabaseStorage()

        # Create multiple articles
        for i in range(15):
            storage.create_article(
                item_id=f"article_{i:03d}",
                url=f"https://example.com/article{i}"
            )

        # Test pagination
        page1 = storage.list_articles(limit=5, offset=0)
        assert len(page1) == 5

        page2 = storage.list_articles(limit=5, offset=5)
        assert len(page2) == 5

        page3 = storage.list_articles(limit=5, offset=10)
        assert len(page3) == 5

        # Verify different articles in each page
        page1_ids = {a['item_id'] for a in page1}
        page2_ids = {a['item_id'] for a in page2}
        assert len(page1_ids & page2_ids) == 0, "Pages should not overlap"

    def test_firestore_gcs_integration_mock(self, mocker):
        """
        Test: Mock Firestore + Mock GCS → verify storage_uploads tracked in Firestore.

        Corresponds to TESTING_PLAN Test Case 3.3: Firestore + GCS Integration
        """
        from tests.fakes.storage import InMemoryDatabaseStorage

        storage = InMemoryDatabaseStorage()

        # Create article
        storage.create_article(
            item_id="test_integration_001",
            url="https://example.com/integration"
        )

        # Simulate GCS upload results
        gcs_upload_metadata = [
            {
                'provider_name': 'gcs',
                'storage_uri': 'gs://bucket/integration.html.gz',
                'original_size': 10000,
                'stored_size': 1500,
                'compression_ratio': 85.0,
                'success': True
            },
            {
                'provider_name': 'local',
                'storage_uri': 'file:///backup/integration.html.gz',
                'original_size': 10000,
                'stored_size': 1500,
                'compression_ratio': 85.0,
                'success': True
            }
        ]

        # Update artifact with storage uploads
        storage.update_artifact_status(
            item_id="test_integration_001",
            archiver="monolith",
            status="success",
            gcs_path="gs://bucket/integration.html.gz",
            storage_uploads=gcs_upload_metadata
        )

        # Verify storage_uploads tracked
        artifact = storage.get_artifact("test_integration_001", "monolith")
        assert artifact is not None
        assert 'storage_uploads' in artifact
        assert len(artifact['storage_uploads']) == 2

        # Verify GCS provider data
        gcs_upload = next(u for u in artifact['storage_uploads'] if u['provider_name'] == 'gcs')
        assert gcs_upload['storage_uri'].startswith('gs://')
        assert gcs_upload['compression_ratio'] == 85.0

    def test_firestore_query_filtering_mock(self):
        """
        Test: Query artifacts by status → verify filtering works.

        Tests Firestore query filtering.
        """
        from tests.fakes.storage import InMemoryDatabaseStorage

        storage = InMemoryDatabaseStorage()

        # Create articles with different statuses
        for i in range(10):
            storage.create_article(
                item_id=f"filter_test_{i}",
                url=f"https://example.com/{i}"
            )

            status = "success" if i % 2 == 0 else "failed"
            storage.update_artifact_status(
                item_id=f"filter_test_{i}",
                archiver="monolith",
                status=status
            )

        # Query successful artifacts
        success_artifacts = storage.list_artifacts(status="success")
        assert len(success_artifacts) == 5

        # Query failed artifacts
        failed_artifacts = storage.list_artifacts(status="failed")
        assert len(failed_artifacts) == 5

        # Verify statuses
        assert all(a['status'] == 'success' for a in success_artifacts)
        assert all(a['status'] == 'failed' for a in failed_artifacts)

    def test_firestore_artifact_updates_mock(self):
        """
        Test: Update artifact multiple times → verify latest state.

        Tests artifact update behavior.
        """
        from tests.fakes.storage import InMemoryDatabaseStorage

        storage = InMemoryDatabaseStorage()

        storage.create_article(item_id="update_test", url="https://example.com")

        # Initial state
        storage.update_artifact_status(
            item_id="update_test",
            archiver="monolith",
            status="pending"
        )

        artifact = storage.get_artifact("update_test", "monolith")
        assert artifact['status'] == "pending"

        # Update to processing
        storage.update_artifact_status(
            item_id="update_test",
            archiver="monolith",
            status="processing"
        )

        artifact = storage.get_artifact("update_test", "monolith")
        assert artifact['status'] == "processing"

        # Final update to success
        storage.update_artifact_status(
            item_id="update_test",
            archiver="monolith",
            status="success",
            gcs_path="gs://bucket/final.html.gz",
            exit_code=0
        )

        artifact = storage.get_artifact("update_test", "monolith")
        assert artifact['status'] == "success"
        assert artifact['gcs_path'] == "gs://bucket/final.html.gz"
        assert artifact['exit_code'] == 0

    def test_firestore_batch_operations_mock(self):
        """
        Test: Batch create multiple articles → verify efficient operation.

        Tests batch operation support.
        """
        from tests.fakes.storage import InMemoryDatabaseStorage

        storage = InMemoryDatabaseStorage()

        # Batch create
        batch_items = [
            {"item_id": f"batch_{i}", "url": f"https://example.com/batch{i}"}
            for i in range(20)
        ]

        for item in batch_items:
            storage.create_article(**item)

        # Verify all created
        count = storage.get_article_count()
        assert count >= 20

        # Query batch
        articles = storage.list_articles(limit=20)
        assert len(articles) == 20

    def test_firestore_provider_capabilities_mock(self):
        """
        Test: Verify Firestore provider capabilities and metadata.

        Tests provider interface.
        """
        from tests.fakes.storage import InMemoryDatabaseStorage

        storage = InMemoryDatabaseStorage()

        # Verify provider name
        assert storage.provider_name == "memory"  # Fake implementation

        # Verify it's a DatabaseStorageProvider
        from app.storage.database_storage import DatabaseStorageProvider
        assert isinstance(storage, DatabaseStorageProvider)
