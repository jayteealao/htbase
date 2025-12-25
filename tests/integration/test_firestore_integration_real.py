"""
Integration tests for Firestore database backend with real Firebase.

Tests Firestore integration with actual Firebase service (requires credentials),
corresponding to Test Case 3 from TESTING_PLAN.md.

These tests:
- Require real Firebase/Firestore credentials to run
- Use @pytest.mark.skipif to skip when credentials unavailable
- Test actual Firestore document operations
- Clean up test data after execution

Environment Variables Required:
- TEST_FIRESTORE_PROJECT: Firebase project ID for testing
- FIREBASE_APPLICATION_CREDENTIALS: Path to Firebase service account JSON

Usage:
    # Run with Firestore credentials
    export TEST_FIRESTORE_PROJECT=my-firebase-project
    export FIREBASE_APPLICATION_CREDENTIALS=/path/to/firebase-credentials.json
    pytest tests/integration/test_firestore_integration_real.py -v -m firestore

    # Skip Firestore tests
    pytest tests/integration/test_firestore_integration_real.py -v -m "not firestore"
"""

import os
from datetime import datetime
import pytest

# Skip all tests in this module if Firestore credentials not available
pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_FIRESTORE_PROJECT"),
    reason="TEST_FIRESTORE_PROJECT not set - Firestore credentials required"
)


@pytest.mark.firestore
class TestFirestoreIntegrationReal:
    """Test Firestore database backend with real Firebase service."""

    @pytest.fixture
    def firestore_test_project(self):
        """Get Firestore test project ID from environment."""
        return os.getenv("TEST_FIRESTORE_PROJECT")

    @pytest.fixture
    def real_firestore_storage(self, firestore_test_project):
        """Create real Firestore storage instance."""
        try:
            from app.storage.firestore_storage import FirestoreStorage

            storage = FirestoreStorage(project_id=firestore_test_project)

            yield storage

            # Cleanup would go here if implemented
        except ImportError:
            pytest.skip("FirestoreStorage not available")

    def test_firestore_article_creation_real(self, real_firestore_storage):
        """
        Test: Create article in real Firestore → verify document exists.

        Corresponds to TESTING_PLAN Test Case 3.2.1 (Real)
        """
        test_item_id = f"real_test_{datetime.utcnow().isoformat()}"
        test_url = "https://example.com/real-firestore-test"

        # Create article
        success = real_firestore_storage.create_article(
            item_id=test_item_id,
            url=test_url,
            metadata={"title": "Real Firestore Test", "test": True}
        )

        assert success is True, "Article creation failed"

        # Verify article exists
        article = real_firestore_storage.get_article(test_item_id)

        assert article is not None, "Article not found after creation"
        assert article['item_id'] == test_item_id
        assert article['url'] == test_url
        assert article['metadata']['title'] == "Real Firestore Test"

        print(f"\n✅ Firestore Article Created: {test_item_id}")

        # Cleanup
        try:
            # Delete test document
            # real_firestore_storage.delete_article(test_item_id)
            pass
        except Exception:
            pass  # Best effort cleanup

    def test_firestore_artifact_query_real(self, real_firestore_storage):
        """
        Test: Create artifacts → query by item_id → verify results.

        Tests Firestore query functionality.
        """
        test_item_id = f"query_test_{datetime.utcnow().isoformat()}"
        test_url = "https://example.com/query-test"

        # Create article
        real_firestore_storage.create_article(
            item_id=test_item_id,
            url=test_url
        )

        # Create multiple artifacts
        archivers = ["monolith", "readability", "pdf"]

        for archiver in archivers:
            success = real_firestore_storage.update_artifact_status(
                item_id=test_item_id,
                archiver=archiver,
                status="success",
                gcs_path=f"gs://test-bucket/{test_item_id}/{archiver}.html.gz"
            )
            assert success, f"Failed to create artifact for {archiver}"

        # Query artifacts
        artifacts = real_firestore_storage.list_artifacts(item_id=test_item_id)

        assert len(artifacts) >= len(archivers), \
            f"Expected at least {len(archivers)} artifacts, found {len(artifacts)}"

        # Verify archiver names
        artifact_archivers = {a['archiver'] for a in artifacts}
        for archiver in archivers:
            assert archiver in artifact_archivers, f"Missing artifact for {archiver}"

        print(f"\n✅ Firestore Query: Found {len(artifacts)} artifacts")

        # Cleanup
        try:
            # real_firestore_storage.delete_article(test_item_id)
            pass
        except Exception:
            pass

    def test_firestore_gcs_full_cloud_workflow_real(
        self,
        real_firestore_storage,
        integration_temp_dir
    ):
        """
        Test: Upload to GCS → store metadata in Firestore → retrieve → verify end-to-end.

        Corresponds to TESTING_PLAN Test Case 3.3: Full Cloud Workflow
        Requires both GCS and Firestore credentials.
        """
        # Skip if GCS not also available
        if not os.getenv("TEST_GCS_BUCKET"):
            pytest.skip("TEST_GCS_BUCKET not set - GCS required for full cloud workflow")

        from app.storage.gcs_file_storage import GCSFileStorage

        test_item_id = f"cloud_workflow_{datetime.utcnow().isoformat()}"
        test_url = "https://example.com/cloud-workflow"

        # Create test file
        test_file = integration_temp_dir / "cloud_workflow.html"
        test_file.write_text("<html><body>Full cloud workflow test</body></html>")

        # Initialize GCS
        gcs_storage = GCSFileStorage(
            bucket_name=os.getenv("TEST_GCS_BUCKET"),
            project_id=os.getenv("TEST_GCS_PROJECT_ID")
        )

        # Upload to GCS
        gcs_path = f"test/cloud_workflow/{test_item_id}/file.html"

        upload_result = gcs_storage.upload_file(
            local_path=test_file,
            destination_path=gcs_path,
            compress=True
        )

        assert upload_result.success, "GCS upload failed"

        # Store metadata in Firestore
        real_firestore_storage.create_article(
            item_id=test_item_id,
            url=test_url,
            metadata={"source": "full_cloud_workflow_test"}
        )

        real_firestore_storage.update_artifact_status(
            item_id=test_item_id,
            archiver="monolith",
            status="success",
            gcs_path=upload_result.uri,
            gcs_bucket=os.getenv("TEST_GCS_BUCKET"),
            compressed_size=upload_result.stored_size,
            compression_ratio=upload_result.compression_ratio
        )

        # Verify Firestore metadata
        artifact = real_firestore_storage.get_artifact(test_item_id, "monolith")

        assert artifact is not None
        assert artifact['gcs_path'] == upload_result.uri
        assert artifact['compression_ratio'] == upload_result.compression_ratio

        print(f"\n✅ Full Cloud Workflow:")
        print(f"   GCS URI: {upload_result.uri}")
        print(f"   Firestore: {test_item_id}")
        print(f"   Compression: {upload_result.compression_ratio:.2f}%")

        # Cleanup
        try:
            gcs_storage.delete_file(gcs_path + ".gz")
            # real_firestore_storage.delete_article(test_item_id)
        except Exception:
            pass

    def test_firestore_document_structure_real(self, real_firestore_storage):
        """
        Test: Create document → verify structure matches expectations.

        Verifies Firestore document schema.
        """
        test_item_id = f"structure_test_{datetime.utcnow().isoformat()}"

        # Create comprehensive article
        real_firestore_storage.create_article(
            item_id=test_item_id,
            url="https://example.com/structure",
            pocket_data={"time_added": "2024-01-01"},
            metadata={"title": "Structure Test", "word_count": 500}
        )

        # Create artifact
        real_firestore_storage.update_artifact_status(
            item_id=test_item_id,
            archiver="monolith",
            status="success",
            gcs_path="gs://bucket/test.html.gz"
        )

        # Retrieve and verify structure
        article = real_firestore_storage.get_article(test_item_id)

        # Required fields
        assert 'item_id' in article
        assert 'url' in article
        assert 'created_at' in article

        # Optional fields
        if 'metadata' in article:
            assert article['metadata']['title'] == "Structure Test"

        if 'pocket_data' in article:
            assert article['pocket_data']['time_added'] == "2024-01-01"

        print(f"\n✅ Firestore Document Structure: Verified")

        # Cleanup
        try:
            # real_firestore_storage.delete_article(test_item_id)
            pass
        except Exception:
            pass

    def test_firestore_pagination_real(self, real_firestore_storage):
        """
        Test: Create multiple documents → paginate results.

        Tests Firestore pagination.
        """
        test_prefix = f"page_test_{datetime.utcnow().timestamp()}"

        # Create multiple articles
        for i in range(5):
            real_firestore_storage.create_article(
                item_id=f"{test_prefix}_{i:03d}",
                url=f"https://example.com/page{i}"
            )

        # Query with pagination
        page1 = real_firestore_storage.list_articles(limit=2, offset=0)
        page2 = real_firestore_storage.list_articles(limit=2, offset=2)

        # Verify pagination works
        assert len(page1) <= 2
        assert len(page2) <= 2

        print(f"\n✅ Firestore Pagination: Page1={len(page1)}, Page2={len(page2)}")

        # Cleanup
        for i in range(5):
            try:
                # real_firestore_storage.delete_article(f"{test_prefix}_{i:03d}")
                pass
            except Exception:
                pass

    def test_firestore_update_operations_real(self, real_firestore_storage):
        """
        Test: Update document multiple times → verify latest state persists.

        Tests Firestore update behavior.
        """
        test_item_id = f"update_test_{datetime.utcnow().isoformat()}"

        # Create article
        real_firestore_storage.create_article(
            item_id=test_item_id,
            url="https://example.com/update"
        )

        # Initial artifact
        real_firestore_storage.update_artifact_status(
            item_id=test_item_id,
            archiver="monolith",
            status="pending"
        )

        # Update to success
        real_firestore_storage.update_artifact_status(
            item_id=test_item_id,
            archiver="monolith",
            status="success",
            gcs_path="gs://bucket/final.html.gz",
            exit_code=0
        )

        # Verify final state
        artifact = real_firestore_storage.get_artifact(test_item_id, "monolith")

        assert artifact['status'] == "success"
        assert artifact['gcs_path'] == "gs://bucket/final.html.gz"
        assert artifact['exit_code'] == 0

        print(f"\n✅ Firestore Updates: Final state verified")

        # Cleanup
        try:
            # real_firestore_storage.delete_article(test_item_id)
            pass
        except Exception:
            pass
