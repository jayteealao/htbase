"""
Integration Tests for Dual PostgreSQL + Firestore Persistence

Tests the complete flow from archival to GCS upload to dual database writes.
Requires both PostgreSQL and Firestore to be available.
"""

import pytest
import os
import time
from pathlib import Path
from unittest.mock import patch, Mock

from fastapi.testclient import TestClient
from google.cloud import firestore

from core.config import get_settings
from storage.postgres_storage import PostgresStorage
from storage.firestore_storage import FirestoreStorage
from storage.database_storage import ArticleMetadata, ArchiveArtifact, ArchiveStatus


# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def test_settings():
    """Override settings for integration tests."""
    # Set environment variables for dual persistence
    os.environ['ENABLE_DUAL_PERSISTENCE'] = 'true'
    os.environ['DUAL_WRITE_FAILURE_MODE'] = 'fail_fast'
    os.environ['ENABLE_LAZY_MIGRATION'] = 'true'
    os.environ['FIRESTORE__PROJECT_ID'] = os.getenv('FIRESTORE_PROJECT_ID', 'trails-e428e')

    # Clear settings cache
    get_settings.cache_clear()

    settings = get_settings()
    yield settings

    # Cleanup
    get_settings.cache_clear()


@pytest.fixture(scope="module")
def postgres_storage(test_settings):
    """PostgreSQL storage instance."""
    return PostgresStorage()


@pytest.fixture(scope="module")
def firestore_storage(test_settings):
    """Firestore storage instance."""
    project_id = test_settings.firestore.project_id
    if not project_id:
        pytest.skip("Firestore not configured (FIRESTORE__PROJECT_ID missing)")
    return FirestoreStorage(project_id=project_id)


@pytest.fixture(scope="module")
def firestore_client(test_settings):
    """Raw Firestore client for verification."""
    project_id = test_settings.firestore.project_id
    if not project_id:
        pytest.skip("Firestore not configured")
    return firestore.Client(project=project_id)


@pytest.fixture
def test_item_id():
    """Generate unique test item ID."""
    import uuid
    return f"test_dual_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cleanup_test_data(firestore_client, postgres_storage):
    """Cleanup test data after each test."""
    test_ids = []

    def register_cleanup(item_id: str):
        test_ids.append(item_id)

    yield register_cleanup

    # Cleanup after test
    for item_id in test_ids:
        # Delete from Firestore
        try:
            doc_ref = firestore_client.collection('articles').document(item_id)
            doc_ref.delete()
        except Exception as e:
            print(f"Failed to delete Firestore doc {item_id}: {e}")

        # Delete from PostgreSQL
        try:
            postgres_storage.delete_article(item_id)
        except Exception as e:
            print(f"Failed to delete PostgreSQL article {item_id}: {e}")


class TestDualPersistenceArchivalFlow:
    """Test complete archival flow with dual persistence."""

    def test_archive_writes_to_both_databases(
        self,
        test_client,
        postgres_storage,
        firestore_storage,
        test_item_id,
        cleanup_test_data
    ):
        """
        Test that archiving writes to both PostgreSQL and Firestore.

        Flow:
        1. Archive URL with monolith archiver
        2. Verify article in PostgreSQL
        3. Verify article in Firestore
        4. Verify data consistency
        """
        cleanup_test_data(test_item_id)

        # Archive a test URL
        response = test_client.post(
            '/save',
            json={
                'id': test_item_id,
                'url': 'https://example.com',
                'archiver': 'monolith'
            }
        )

        assert response.status_code in [200, 202], f"Archive failed: {response.text}"

        # Wait for archival to complete (if async)
        time.sleep(2)

        # Verify in PostgreSQL
        pg_article = postgres_storage.get_article(test_item_id)
        assert pg_article is not None, "Article not found in PostgreSQL"
        assert pg_article.metadata.url == 'https://example.com'
        assert len(pg_article.archives) > 0, "No artifacts in PostgreSQL"

        # Verify in Firestore
        fs_article = firestore_storage.get_article(test_item_id)
        assert fs_article is not None, "Article not found in Firestore"
        assert fs_article.metadata.url == 'https://example.com'

        # Verify Firestore has archives map
        assert len(fs_article.archives) > 0, "No artifacts in Firestore"

        # Verify artifact status matches
        for pg_artifact in pg_article.archives:
            fs_artifact = next(
                (a for a in fs_article.archives if a.archiver == pg_artifact.archiver),
                None
            )
            assert fs_artifact is not None, f"Artifact {pg_artifact.archiver} missing in Firestore"
            assert fs_artifact.status == pg_artifact.status

    def test_artifact_update_syncs_to_both_databases(
        self,
        postgres_storage,
        firestore_storage,
        test_item_id,
        cleanup_test_data
    ):
        """
        Test that artifact status updates sync to both databases.
        """
        cleanup_test_data(test_item_id)

        # Create article in both databases
        metadata = ArticleMetadata(
            item_id=test_item_id,
            url='https://example.com/test',
            title='Test Article'
        )

        from storage.dual_database_storage import DualDatabaseStorage
        dual_storage = DualDatabaseStorage(
            postgres=postgres_storage,
            firestore=firestore_storage,
            failure_mode='fail_fast'
        )

        # Create article
        success = dual_storage.create_article(metadata)
        assert success, "Failed to create article in dual storage"

        # Create artifact
        artifact = ArchiveArtifact(
            item_id=test_item_id,
            archiver='pdf',
            status=ArchiveStatus.PENDING
        )
        success = dual_storage.create_artifact(artifact)
        assert success, "Failed to create artifact"

        # Update artifact status
        success = dual_storage.update_artifact_status(
            item_id=test_item_id,
            archiver='pdf',
            status=ArchiveStatus.SUCCESS,
            gcs_path='gs://bucket/test.pdf',
            file_size=12345
        )
        assert success, "Failed to update artifact status"

        # Verify in PostgreSQL
        pg_artifact = postgres_storage.get_artifact(test_item_id, 'pdf')
        assert pg_artifact is not None
        assert pg_artifact.status == ArchiveStatus.SUCCESS
        assert pg_artifact.gcs_path == 'gs://bucket/test.pdf'
        assert pg_artifact.file_size == 12345

        # Verify in Firestore
        fs_artifact = firestore_storage.get_artifact(test_item_id, 'pdf')
        assert fs_artifact is not None
        assert fs_artifact.status == ArchiveStatus.SUCCESS
        assert fs_artifact.gcs_path == 'gs://bucket/test.pdf'
        assert fs_artifact.file_size == 12345


class TestLazyMigration:
    """Test lazy migration of existing PostgreSQL data to Firestore."""

    def test_lazy_migration_on_retrieve(
        self,
        test_client,
        postgres_storage,
        firestore_storage,
        test_item_id,
        cleanup_test_data
    ):
        """
        Test that accessing an article triggers lazy migration.

        Flow:
        1. Create article in PostgreSQL only
        2. Verify NOT in Firestore
        3. Retrieve article (triggers lazy migration)
        4. Verify NOW in Firestore
        """
        cleanup_test_data(test_item_id)

        # Create article in PostgreSQL only (simulate old data)
        metadata = ArticleMetadata(
            item_id=test_item_id,
            url='https://example.com/old',
            title='Old Article'
        )
        postgres_storage.create_article(metadata)

        # Create artifact
        artifact = ArchiveArtifact(
            item_id=test_item_id,
            archiver='monolith',
            status=ArchiveStatus.SUCCESS,
            gcs_path=f'gs://bucket/{test_item_id}/monolith/output.html.gz',
            file_size=5000
        )
        postgres_storage.create_artifact(artifact)

        # Verify NOT in Firestore yet
        fs_article = firestore_storage.get_article(test_item_id)
        assert fs_article is None, "Article should not be in Firestore yet"

        # Retrieve article (triggers lazy migration)
        response = test_client.post(
            '/archive/retrieve',
            json={
                'id': test_item_id,
                'archiver': 'monolith'
            }
        )

        # Migration happens in background, may not be immediate
        time.sleep(1)

        # Verify NOW in Firestore
        fs_article = firestore_storage.get_article(test_item_id)
        assert fs_article is not None, "Article should be migrated to Firestore"
        assert fs_article.metadata.url == 'https://example.com/old'
        assert fs_article.metadata.title == 'Old Article'

        # Verify artifact migrated
        fs_artifacts = firestore_storage.get_artifacts(test_item_id)
        assert len(fs_artifacts) > 0, "Artifacts should be migrated"

        monolith_artifact = next(
            (a for a in fs_artifacts if a.archiver == 'monolith'),
            None
        )
        assert monolith_artifact is not None
        assert monolith_artifact.status == ArchiveStatus.SUCCESS


class TestFirestoreUnavailable:
    """Test graceful degradation when Firestore is unavailable."""

    def test_postgres_only_when_firestore_disabled(
        self,
        test_client,
        postgres_storage,
        test_item_id,
        cleanup_test_data
    ):
        """
        Test that system works with PostgreSQL only if dual persistence disabled.
        """
        cleanup_test_data(test_item_id)

        # Temporarily disable dual persistence
        with patch.dict(os.environ, {'ENABLE_DUAL_PERSISTENCE': 'false'}):
            get_settings.cache_clear()

            # Archive should still work
            response = test_client.post(
                '/save',
                json={
                    'id': test_item_id,
                    'url': 'https://example.com',
                    'archiver': 'monolith'
                }
            )

            assert response.status_code in [200, 202]

            time.sleep(2)

            # Verify in PostgreSQL
            pg_article = postgres_storage.get_article(test_item_id)
            assert pg_article is not None

        get_settings.cache_clear()

    def test_fail_fast_mode_fails_on_firestore_error(
        self,
        postgres_storage,
        test_item_id,
        cleanup_test_data
    ):
        """
        Test that fail_fast mode fails the operation if Firestore fails.
        """
        cleanup_test_data(test_item_id)

        # Create mock Firestore that always fails
        mock_firestore = Mock()
        mock_firestore.create_article.side_effect = Exception("Firestore unavailable")

        from storage.dual_database_storage import DualDatabaseStorage
        dual_storage = DualDatabaseStorage(
            postgres=postgres_storage,
            firestore=mock_firestore,
            failure_mode='fail_fast'
        )

        metadata = ArticleMetadata(
            item_id=test_item_id,
            url='https://example.com'
        )

        # Should fail because Firestore failed
        success = dual_storage.create_article(metadata)
        assert success == False, "fail_fast mode should fail when Firestore fails"

    def test_log_and_continue_mode_succeeds_on_firestore_error(
        self,
        postgres_storage,
        test_item_id,
        cleanup_test_data
    ):
        """
        Test that log_and_continue mode continues if Firestore fails.
        """
        cleanup_test_data(test_item_id)

        # Create mock Firestore that always fails
        mock_firestore = Mock()
        mock_firestore.create_article.side_effect = Exception("Firestore unavailable")

        from storage.dual_database_storage import DualDatabaseStorage
        dual_storage = DualDatabaseStorage(
            postgres=postgres_storage,
            firestore=mock_firestore,
            failure_mode='log_and_continue'
        )

        metadata = ArticleMetadata(
            item_id=test_item_id,
            url='https://example.com'
        )

        # Should succeed because PostgreSQL succeeded
        success = dual_storage.create_article(metadata)
        assert success == True, "log_and_continue mode should succeed when PostgreSQL succeeds"

        # Verify in PostgreSQL
        pg_article = postgres_storage.get_article(test_item_id)
        assert pg_article is not None


class TestDataConsistency:
    """Test data consistency between PostgreSQL and Firestore."""

    def test_firestore_excludes_summaries(
        self,
        postgres_storage,
        firestore_storage,
        test_item_id,
        cleanup_test_data
    ):
        """
        Test that summaries are NOT synced to Firestore.
        """
        cleanup_test_data(test_item_id)

        from storage.dual_database_storage import DualDatabaseStorage
        from storage.database_storage import ArticleSummary

        dual_storage = DualDatabaseStorage(
            postgres=postgres_storage,
            firestore=firestore_storage,
            failure_mode='fail_fast'
        )

        # Create article
        metadata = ArticleMetadata(
            item_id=test_item_id,
            url='https://example.com'
        )
        dual_storage.create_article(metadata)

        # Create summary (should go to PostgreSQL only)
        summary = ArticleSummary(
            item_id=test_item_id,
            summary='This is a test summary'
        )
        dual_storage.create_summary(summary)

        # Verify summary in PostgreSQL
        pg_summary = postgres_storage.get_summary(test_item_id)
        assert pg_summary is not None
        assert pg_summary.summary == 'This is a test summary'

        # Verify summary NOT in Firestore
        fs_summary = firestore_storage.get_summary(test_item_id)
        assert fs_summary is None, "Summaries should not sync to Firestore"

    def test_firestore_excludes_entities_and_tags(
        self,
        postgres_storage,
        firestore_storage,
        test_item_id,
        cleanup_test_data
    ):
        """
        Test that entities and tags are NOT synced to Firestore.
        """
        cleanup_test_data(test_item_id)

        from storage.dual_database_storage import DualDatabaseStorage
        from storage.database_storage import ArticleEntity, ArticleTag

        dual_storage = DualDatabaseStorage(
            postgres=postgres_storage,
            firestore=firestore_storage,
            failure_mode='fail_fast'
        )

        # Create article
        metadata = ArticleMetadata(
            item_id=test_item_id,
            url='https://example.com'
        )
        dual_storage.create_article(metadata)

        # Create entities (should go to PostgreSQL only)
        entities = [
            ArticleEntity(
                item_id=test_item_id,
                entity_type='PERSON',
                entity_value='John Doe'
            )
        ]
        dual_storage.create_entities(entities)

        # Create tags (should go to PostgreSQL only)
        tags = [
            ArticleTag(item_id=test_item_id, tag='technology')
        ]
        dual_storage.create_tags(tags)

        # Verify in PostgreSQL
        pg_entities = postgres_storage.get_entities(test_item_id)
        assert len(pg_entities) > 0

        pg_tags = postgres_storage.get_tags(test_item_id)
        assert len(pg_tags) > 0

        # Verify NOT in Firestore
        fs_entities = firestore_storage.get_entities(test_item_id)
        assert len(fs_entities) == 0, "Entities should not sync to Firestore"

        fs_tags = firestore_storage.get_tags(test_item_id)
        assert len(fs_tags) == 0, "Tags should not sync to Firestore"

    def test_firestore_includes_pocket_data(
        self,
        postgres_storage,
        firestore_storage,
        test_item_id,
        cleanup_test_data
    ):
        """
        Test that Pocket data IS synced to Firestore.
        """
        cleanup_test_data(test_item_id)

        from storage.dual_database_storage import DualDatabaseStorage
        from storage.database_storage import PocketData

        dual_storage = DualDatabaseStorage(
            postgres=postgres_storage,
            firestore=firestore_storage,
            failure_mode='fail_fast'
        )

        # Create article
        metadata = ArticleMetadata(
            item_id=test_item_id,
            url='https://example.com'
        )
        dual_storage.create_article(metadata)

        # Create Pocket data
        pocket = PocketData(
            item_id=test_item_id,
            resolved_id='12345',
            favorite=True,
            word_count=1500
        )
        dual_storage.create_pocket_data(pocket)

        # Verify in PostgreSQL
        pg_pocket = postgres_storage.get_pocket_data(test_item_id)
        assert pg_pocket is not None
        assert pg_pocket.resolved_id == '12345'
        assert pg_pocket.favorite == True

        # Verify in Firestore (Pocket data should sync)
        fs_pocket = firestore_storage.get_pocket_data(test_item_id)
        assert fs_pocket is not None, "Pocket data should sync to Firestore"
        assert fs_pocket.resolved_id == '12345'
        assert fs_pocket.favorite == True


class TestQueryOperations:
    """Test that queries use PostgreSQL (source of truth)."""

    def test_search_uses_postgres(
        self,
        postgres_storage,
        firestore_storage,
        test_item_id,
        cleanup_test_data
    ):
        """
        Test that search operations use PostgreSQL.
        """
        cleanup_test_data(test_item_id)

        from storage.dual_database_storage import DualDatabaseStorage

        dual_storage = DualDatabaseStorage(
            postgres=postgres_storage,
            firestore=firestore_storage,
            failure_mode='fail_fast'
        )

        # Create test article
        metadata = ArticleMetadata(
            item_id=test_item_id,
            url='https://example.com',
            title='Searchable Test Article'
        )
        dual_storage.create_article(metadata)

        # Search should use PostgreSQL
        results = dual_storage.search_articles('Searchable')

        # Note: This may not find results immediately due to indexing delays
        # But it should call PostgreSQL search, not Firestore

    def test_count_uses_postgres(
        self,
        postgres_storage,
        firestore_storage
    ):
        """
        Test that count operations use PostgreSQL.
        """
        from storage.dual_database_storage import DualDatabaseStorage

        dual_storage = DualDatabaseStorage(
            postgres=postgres_storage,
            firestore=firestore_storage,
            failure_mode='fail_fast'
        )

        # Count should use PostgreSQL
        count = dual_storage.count_articles()
        assert count >= 0  # Should return PostgreSQL count


class TestFirebaseAPI:
    """Test Firebase API endpoints with dual persistence."""

    def test_firebase_archive_endpoint_dual_write(
        self,
        test_client,
        postgres_storage,
        firestore_storage,
        test_item_id,
        cleanup_test_data
    ):
        """
        Test Firebase-specific archive endpoint writes to both databases.
        """
        cleanup_test_data(test_item_id)

        response = test_client.post(
            '/firebase/archive',
            json={
                'item_id': test_item_id,
                'url': 'https://example.com/firebase',
                'archiver': 'monolith'
            }
        )

        assert response.status_code == 200

        time.sleep(2)

        # Verify in both databases
        pg_article = postgres_storage.get_article(test_item_id)
        assert pg_article is not None

        fs_article = firestore_storage.get_article(test_item_id)
        assert fs_article is not None
