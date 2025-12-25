"""
Tests for the Sync API endpoints.

Tests the bidirectional sync endpoints between PostgreSQL and Firestore
using FastAPI TestClient with mocked storage backends.
"""

from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

import pytest


class TestSyncAPI:
    """Test the Sync API endpoints."""

    def test_sync_postgres_to_firestore_specific_article_success(self, test_client: TestClient):
        """Test successful PostgreSQL to Firestore sync for specific article."""
        # Mock required storage backends
        mock_postgres_storage = Mock()
        mock_firestore_storage = Mock()

        mock_article = {
            'item_id': 'test123',
            'url': 'https://example.com/article',
            'pocket_data': {'title': 'Test Article'},
            'created_at': '2023-01-01T00:00:00Z',
            'updated_at': '2023-01-01T00:00:00Z'
        }

        mock_artifacts = [
            {
                'archiver': 'monolith',
                'status': 'success',
                'gcs_path': 'archives/test123/monolith/output.html',
                'success': True,
                'created_at': '2023-01-01T00:00:00Z',
                'size_bytes': 1024
            }
        ]

        mock_postgres_storage.get_article.return_value = mock_article
        mock_postgres_storage.list_artifacts.return_value = mock_artifacts

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage):
                payload = {
                    "article_id": "test123",
                    "limit": 100
                }

                response = test_client.post("/sync/postgres-to-firestore", json=payload)

                assert response.status_code == 200
                data = response.json()
                assert data["synced"] == 1
                assert data["total"] == 1
                assert data["errors"] == []

                # Verify Firestore operations were called
                mock_firestore_storage.create_article.assert_called_once()
                assert mock_firestore_storage.update_artifact_status.call_count == 1

    def test_sync_postgres_to_firestore_multiple_articles_success(self, test_client: TestClient):
        """Test successful PostgreSQL to Firestore sync for multiple articles."""
        mock_postgres_storage = Mock()
        mock_firestore_storage = Mock()

        mock_articles = [
            {
                'item_id': 'test1',
                'url': 'https://example1.com',
                'pocket_data': {},
                'created_at': '2023-01-01T00:00:00Z'
            },
            {
                'item_id': 'test2',
                'url': 'https://example2.com',
                'pocket_data': {},
                'created_at': '2023-01-01T00:00:00Z'
            }
        ]

        mock_postgres_storage.list_articles.return_value = mock_articles
        mock_postgres_storage.list_artifacts.return_value = []

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage):
                payload = {
                    "limit": 2
                }

                response = test_client.post("/sync/postgres-to-firestore", json=payload)

                assert response.status_code == 200
                data = response.json()
                assert data["synced"] == 2
                assert data["total"] == 2
                assert data["errors"] == []

                # Verify Firestore operations were called for each article
                assert mock_firestore_storage.create_article.call_count == 2

    def test_sync_postgres_to_firestore_no_db_storage_503(self, test_client: TestClient):
        """Test PostgreSQL to Firestore sync when DB storage not available."""
        with patch.object(test_client.app.state, 'db_storage', None):
            payload = {
                "article_id": "test123",
                "limit": 100
            }

            response = test_client.post("/sync/postgres-to-firestore", json=payload)

            assert response.status_code == 503
            assert "Database storage not initialized" in response.json()["detail"]

    def test_sync_postgres_to_firestore_specific_article_not_found_404(self, test_client: TestClient):
        """Test sync when specific article not found in PostgreSQL."""
        mock_postgres_storage = Mock()
        mock_postgres_storage.get_article.return_value = None

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            payload = {
                "article_id": "nonexistent",
                "limit": 100
            }

            response = test_client.post("/sync/postgres-to-firestore", json=payload)

            assert response.status_code == 404
            assert "Article not found in PostgreSQL" in response.json()["detail"]

    def test_sync_postgres_to_firestore_firestore_init_failure(self, test_client: TestClient):
        """Test sync when Firestore initialization fails."""
        mock_postgres_storage = Mock()
        mock_postgres_storage.get_article.return_value = {'item_id': 'test123'}

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', side_effect=Exception("Firestore init failed")):
                payload = {
                    "article_id": "test123",
                    "limit": 100
                }

                response = test_client.post("/sync/postgres-to-firestore", json=payload)

                assert response.status_code == 503
                assert "Failed to initialize Firestore" in response.json()["detail"]

    def test_sync_postgres_to_firestore_postgres_init_failure(self, test_client: TestClient):
        """Test sync when PostgreSQL initialization fails."""
        mock_db_storage = Mock()  # Not PostgresStorage
        mock_db_storage.provider_name = "firestore"

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage):
            with patch('storage.postgres_storage.PostgresStorage', side_effect=Exception("PostgreSQL init failed")):
                payload = {
                    "article_id": "test123",
                    "limit": 100
                }

                response = test_client.post("/sync/postgres-to-firestore", json=payload)

                assert response.status_code == 503
                assert "Failed to initialize PostgreSQL" in response.json()["detail"]

    def test_sync_postgres_to_firestore_with_firestore_project_id(self, test_client: TestClient):
        """Test sync using Firestore project_id from settings."""
        mock_postgres_storage = Mock()
        mock_postgres_storage.get_article.return_value = {'item_id': 'test123'}

        mock_firestore_storage = Mock()

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage) as mock_firestore_init:
                with patch('api.sync.get_settings') as mock_settings:
                    mock_settings.return_value.firestore.project_id = "test-project"

                    payload = {
                        "article_id": "test123",
                        "limit": 100
                    }

                    response = test_client.post("/sync/postgres-to-firestore", json=payload)

                    assert response.status_code == 200
                    mock_firestore_init.assert_called_once_with(project_id="test-project")

    def test_sync_postgres_to_firestore_no_firestore_project_id_400(self, test_client: TestClient):
        """Test sync when Firestore project_id not configured."""
        mock_postgres_storage = Mock()
        mock_postgres_storage.get_article.return_value = {'item_id': 'test123'}

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage') as mock_firestore_init:
                with patch('api.sync.get_settings') as mock_settings:
                    mock_settings.return_value.firestore.project_id = None

                    payload = {
                        "article_id": "test123",
                        "limit": 100
                    }

                    response = test_client.post("/sync/postgres-to-firestore", json=payload)

                    assert response.status_code == 400
                    assert "Firestore not configured" in response.json()["detail"]

    def test_sync_postgres_to_firestore_with_postgres_storage(self, test_client: TestClient):
        """Test sync using existing PostgreSQL storage."""
        mock_postgres_storage = Mock()
        mock_postgres_storage.provider_name = "postgres"
        mock_postgres_storage.get_article.return_value = {'item_id': 'test123'}

        mock_firestore_storage = Mock()

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage):
                payload = {
                    "article_id": "test123",
                    "limit": 100
                }

                response = test_client.post("/sync/postgres-to-firestore", json=payload)

                assert response.status_code == 200
                # Should not reinitialize PostgresStorage since it's already the right type
                with patch('storage.postgres_storage.PostgresStorage') as mock_postgres_init:
                    mock_postgres_init.assert_not_called()

    def test_sync_postgres_to_firestore_sync_errors_handling(self, test_client: TestClient):
        """Test sync error handling when some articles fail."""
        mock_postgres_storage = Mock()
        mock_firestore_storage = Mock()

        # First article succeeds, second fails
        mock_postgres_storage.get_article.return_value = {'item_id': 'test1'}
        mock_postgres_storage.list_artifacts.return_value = []

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage):
                mock_firestore_storage.create_article.side_effect = [None, Exception("Firestore error")]

                payload = {
                    "limit": 2
                }

                response = test_client.post("/sync/postgres-to-firestore", json=payload)

                assert response.status_code == 200
                data = response.json()
                assert data["synced"] == 1  # One succeeded
                assert data["total"] == 2
                assert len(data["errors"]) == 1
                assert "Firestore error" in data["errors"][0]

    def test_sync_firestore_to_postgres_success(self, test_client: TestClient):
        """Test successful Firestore to PostgreSQL sync."""
        mock_postgres_storage = Mock()
        mock_firestore_storage = Mock()

        mock_article = {
            'item_id': 'test123',
            'url': 'https://example.com/article',
            'pocket_data': {'title': 'Test Article'},
            'archives': {
                'monolith': {
                    'status': 'success',
                    'gcs_path': 'archives/test123/monolith/output.html'
                },
                'readability': {
                    'status': 'pending',
                    'gcs_path': 'archives/test123/readability/output.html'
                }
            }
        }

        mock_firestore_storage.get_article.return_value = mock_article
        mock_postgres_storage.create_article.return_value = {'id': 123}
        mock_postgres_storage.update_artifact_status.return_value = True

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage):
                payload = {
                    "item_id": "test123"
                }

                response = test_client.post("/sync/firestore-to-postgres", json=payload)

                assert response.status_code == 200
                data = response.json()
                assert data["synced"] is True
                assert data["postgres_id"] == 123
                assert "Successfully synced" in data["message"]

                # Verify operations were called
                mock_postgres_storage.create_article.assert_called_once_with(
                    item_id="test123",
                    url="https://example.com/article",
                    pocket_data={'title': 'Test Article'}
                )
                assert mock_postgres_storage.update_artifact_status.call_count == 2  # monolith and readability

    def test_sync_firestore_to_postgres_no_db_storage_503(self, test_client: TestClient):
        """Test Firestore to PostgreSQL sync when DB storage not available."""
        with patch.object(test_client.app.state, 'db_storage', None):
            payload = {"item_id": "test123"}

            response = test_client.post("/sync/firestore-to-postgres", json=payload)

            assert response.status_code == 503
            assert "Database storage not initialized" in response.json()["detail"]

    def test_sync_firestore_to_postgres_article_not_found_404(self, test_client: TestClient):
        """Test sync when article not found in Firestore."""
        mock_postgres_storage = Mock()
        mock_firestore_storage = Mock()
        mock_firestore_storage.get_article.return_value = None

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage):
                payload = {"item_id": "nonexistent"}

                response = testifact_postgresStorage = Mock()
        mock_firestore_storage = Mock()
        mock_firestore_storage.get_article.return_value = None

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage):
                payload = {"item_id": "nonexistent"}

                response = test_client.post("/sync/firestore-to-postgres", json=payload)

                assert response.status_code == 404
                assert "Article not found in Firestore" in response.json()["detail"]

    def test_sync_firestore_to_postgres_firestore_init_failure(self, test_client: TestClient):
        """Test Firestore to PostgreSQL sync when Firestore initialization fails."""
        mock_postgres_storage = Mock()

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', side_effect=Exception("Firestore init failed")):
                payload = {"item_id": "test123"}

                response = test_client.post("/sync/firestore-to-postgres", json=payload)

                assert response.status_code == 503
                assert "Failed to initialize Firestore" in response.json()["detail"]

    def test_sync_firestore_to_postgres_postgres_init_failure(self, test_client: TestClient):
        """Test Firestore to PostgreSQL sync when PostgreSQL initialization fails."""
        mock_db_storage = Mock()  # Not PostgresStorage
        mock_db_storage.provider_name = "firestore"

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage):
            with patch('storage.postgres_storage.PostgresStorage', side_effect=Exception("PostgreSQL init failed")):
                payload = {"item_id": "test123"}

                response = test_client.post("/sync/firestore-to-postgres", json=payload)

                assert response.status_code == 503
                assert "Failed to initialize PostgreSQL" in response.json()["detail"]

    def test_sync_firestore_to_postgres_with_project_id(self, test_client: TestClient):
        """Test sync using Firestore project_id from settings."""
        mock_postgres_storage = Mock()
        mock_firestore_storage = Mock()
        mock_postgres_storage.create_article.return_value = {'id': 123}

        mock_firestore_storage.get_article.return_value = {
            'item_id': 'test123',
            'url': 'https://example.com/article',
            'archives': {}
        }

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage) as mock_firestore_init:
                with patch('api.sync.get_settings') as mock_settings:
                    mock_settings.return_value.firestore.project_id = "test-project"

                    payload = {"item_id": "test123"}

                    response = test_client.post("/sync/firestore-to-postgres", json=payload)

                    assert response.status_code == 200
                    mock_firestore_init.assert_called_once_with(project_id="test-project")

    def test_sync_firestore_to_postgres_no_project_id_400(self, test_client: TestClient):
        """Test sync when Firestore project_id not configured."""
        mock_postgres_storage = Mock()

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage') as mock_firestore_init:
                with patch('api.sync.get_settings') as mock_settings:
                    mock_settings.return_value.firestore.project_id = None

                    payload = {"item_id": "test123"}

                    response = test_client.post("/sync/firestore-to-postgres", json=payload)

                    assert response.status_code == 400
                    assert "Firestore not configured" in response.json()["detail"]

    def test_sync_firestore_to_postgres_with_postgres_storage(self, test_client: TestClient):
        """Test sync using existing PostgreSQL storage."""
        mock_postgres_storage = Mock()
        mock_postgres_storage.provider_name = "postgres"
        mock_postgres_storage.create_article.return_value = {'id': 123}
        mock_postgres_storage.update_artifact_status.return_value = True

        mock_firestore_storage = Mock()
        mock_firestore_storage.get_article.return_value = {
            'item_id': 'test123',
            'url': 'https://example.com/article',
            'archives': {}
        }

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage):
                payload = {"item_id": "test123"}

                response = test_client.post("/sync/firestore-to-postgres", json=payload)

                assert response.status_code == 200
                # Should not reinitialize storages since they're already the right types
                with patch('storage.postgres_storage.PostgresStorage') as mock_postgres_init:
                    mock_postgres_init.assert_not_called()

    def test_sync_firestore_to_postgres_artifact_sync_failure(self, test_client: TestClient):
        """Test Firestore to PostgreSQL sync with artifact sync failures."""
        mock_postgres_storage = Mock()
        mock_postgres_storage.create_article.return_value = {'id': 123}
        mock_postgres_storage.update_artifact_status.side_effect = Exception("Artifact sync error")

        mock_firestore_storage = Mock()
        mock_firestore_storage.get_article.return_value = {
            'item_id': 'test123',
            'url': 'https://example.com/article',
            'archives': {
                'monolith': {
                    'status': 'success',
                    'gcs_path': 'archives/test123/monolith/output.html'
                }
            }
        }

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage):
                payload = {"item_id": "test123"}

                response = test_client.post("/sync/firestore-to-postgres", json=payload)

                assert response.status_code == 200
                data = response.json()
                assert data["synced"] is True  # Article sync succeeded
                assert data["postgres_id"] == 123
                assert "Successfully synced" in data["message"]

                # Artifact sync should have failed but not failed the overall operation
                mock_postgres_storage.update_artifact_status.assert_called_once()

    def test_sync_firestore_to_postgres_no_archives(self, test_client: TestClient):
        """Test Firestore to PostgreSQL sync when article has no archives."""
        mock_postgres_storage = Mock()
        mock_postgres_storage.create_article.return_value = {'id': 123}
        mock_postgres_storage.update_artifact_status.return_value = True

        mock_firestore_storage = Mock()
        mock_firestore_storage.get_article.return_value = {
            'item_id': 'test123',
            'url': 'https://example.com/article',
            'archives': {}  # No archives
        }

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage):
                payload = {"item_id": "test123"}

                response = test_client.post("/sync/firestore-to-postgres", json=payload)

                assert response.status_code == 200
                data = response.json()
                assert data["synced"] is True
                assert data["postgres_id"] == 123

                # No update_artifact_status calls since no archives
                mock_postgres_storage.update_artifact_status.assert_not_called()

    def test_sync_postgres_to_firestore_request_validation(self, test_client: TestClient):
        """Test PostgresToFirestoreSyncRequest model validation."""
        # Valid request
        valid_payload = {
            "article_id": "test123",
            "limit": 100
        }
        response = test_client.post("/sync/postgres-to-firestore", json=valid_payload)
        # Might fail on business logic but not validation
        assert response.status_code != 422

        # Invalid limit
        invalid_payload = {
            "article_id": "test123",
            "limit": 1500  # Over maximum
        }
        response = test_client.post("/sync/postgres-to-firestore", json=invalid_payload)
        # Should fail validation
        assert response.status_code == 422

        # Negative limit
        invalid_payload = {
            "article_id": "test123",
            "limit": -1
        }
        response = test_client.post("/sync/postgres-to-firestore", json=invalid_payload)
        assert response.status_code == 422

    def test_sync_firestore_to_postgres_request_validation(self, test_client: TestClient):
        """Test FirestoreToPostgresSyncRequest model validation."""
        # Valid request
        valid_payload = {
            "item_id": "test123"
        }
        response = test_client.post("/sync/firestore-to-postgres", json=valid_payload)
        # Might fail on business logic but not validation
        assert response.status_code != 422

        # Missing required field
        invalid_payload = {}
        response = test_client.post("/sync/firestore-to-postgres", json=invalid_payload)
        assert response.status_code == 422

    def test_build_firestore_document_helper(self):
        """Test the _build_firestore_document helper function."""
        from api.sync import _build_firestore_document

        article = {
            'item_id': 'test123',
            'url': 'https://example.com/article',
            'pocket_data': {'title': 'Test Article', 'tags': ['technology']},
            'created_at': '2023-01-01T00:00:00Z',
            'updated_at': '2023-01-01T00:00:00Z'
        }

        artifacts = [
            {
                'archiver': 'monolith',
                'status': 'success',
                'gcs_path': 'archives/test123/monolith/output.html',
                'success': True,
                'created_at': '2023-01-01T00:00:00Z',
                'size_bytes': 1024
            },
            {
                'archiver': 'readability',
                'status': 'pending',
                'gcs_path': None,
                'success': False,
                'created_at': '2023-01-01T00:00:00Z',
                'size_bytes': None
            }
        ]

        result = _build_firestore_document(article, artifacts)

        assert 'url' in result
        assert result['url'] == 'https://example.com/article'
        assert 'pocket_data' in result
        assert result['pocket_data'] == {'title': 'Test Article', 'tags': ['technology']}
        assert 'archives' in result
        assert 'monolith' in result['archives']
        assert 'readability' in result['archives']
        assert result['archives']['monolith']['status'] == 'success'
        assert result['archives']['monolith']['gcs_path'] == 'archives/test123/monolith/output.html'
        assert result['archives']['readability']['status'] == 'pending'

    def test_build_firestore_document_empty_artifacts(self):
        """Test _build_firestore_document with no artifacts."""
        from api.sync import _build_firestore_document

        article = {
            'item_id': 'test123',
            'url': 'https://example.com/article',
            'created_at': '2023-01-01T00:00:00Z',
            'updated_at': '2023-01-01T00:00:00Z'
        }

        result = _build_firestore_document(article, [])

        assert 'archives' in result
        assert result['archives'] == {}

    def test_sync_api_error_handling(self, test_client: TestClient):
        """Test error handling in sync API."""
        # Test with invalid JSON
        response = test_client.post(
            "/sync/postgres-to-firestore",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422  # Validation error

    def test_sync_api_response_models(self, test_client: TestClient):
        """Test that sync responses match expected models."""
        mock_postgres_storage = Mock()
        mock_firestore_storage = Mock()
        mock_postgres_storage.get_article.return_value = {'item_id': 'test123'}
        mock_postgres_storage.list_artifacts.return_value = []
        mock_firestore_storage.create_article.return_value = True

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage):
                # Test PostgresToFirestoreSyncResponse
                payload = {"article_id": "test123"}
                response = test_client.post("/sync/postgres-to-firestore", json=payload)

                if response.status_code == 200:
                    data = response.json()
                    required_fields = ["synced", "total", "errors"]
                    for field in required_fields:
                        assert field in data

                # Test FirestoreToPostgresSyncResponse
                mock_firestore_storage.get_article.return_value = {
                    'item_id': 'test123',
                    'url': 'https://example.com/article',
                    'archives': {}
                }
                mock_postgres_storage.create_article.return_value = {'id': 123}

                response = test_client.post("/sync/firestore-to-postgres", json={"item_id": "test123"})

                if response.status_code == 200:
                    data = response.json()
                    required_fields = ["synced", "postgres_id", "message"]
                    for field in required_fields:
                        assert field in data

    def test_sync_api_logging(self, test_client: TestClient):
        """Test that sync endpoints log properly."""
        mock_postgres_storage = Mock()
        mock_firestore_storage = Mock()
        mock_postgres_storage.get_article.return_value = {'item_id': 'test123'}

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage), \
                 patch('api.sync.logger') as mock_logger:

                payload = {"article_id": "test123"}
                test_client.post("/sync/postgres-to-firestore", json=payload)

                # Should have logged the operation
                assert mock_logger.info.called

    def test_sync_api_edge_cases(self, test_client: TestClient):
        """Test edge cases in sync API."""
        # Test with very long article ID
        long_id = "test_" + "a" * 100

        mock_postgres_storage = Mock()
        mock_firestore_storage = Mock()
        mock_postgres_storage.get_article.return_value = None  # Not found

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage):

                response = test_client.post("/sync/postgres-to-firestore", json={"article_id": long_id})

                assert response.status_code == 404

        # Test with maximum limit
        mock_postgres_storage.get_article.return_value = {'item_id': 'test123'}
        mock_postgres_storage.list_artifacts.return_value = []

        with patch.object(test_client.app.state, 'db_storage', mock_postgres_storage):
            with patch('storage.firestore_storage.FirestoreStorage', return_value=mock_firestore_storage):

                response = test_client.post("/sync/postgres-to-firestore", json={"limit": 1000})

                assert response.status_code == 200