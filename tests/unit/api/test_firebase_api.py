"""
Tests for the Firebase API endpoints.

Tests the Firebase/Firestore integration endpoints for Pocket articles,
download URLs, and Cloud Function triggers using FastAPI TestClient.
"""

from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

import pytest


class TestFirebaseAPI:
    """Test the Firebase API endpoints."""

    def test_add_pocket_article_success(self, test_client: TestClient):
        """Test successful Pocket article addition."""
        # Mock required app state components
        mock_db_storage = Mock()
        mock_db_storage.provider_name = "firestore"
        mock_db_storage.create_article.return_value = True

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage):
            payload = {
                "user_id": "user123",
                "url": "https://example.com/article",
                "pocket_data": {
                    "title": "Test Article",
                    "excerpt": "Test excerpt",
                    "tags": ["technology", "test"]
                },
                "archiver": "monolith"
            }

            response = test_client.post("/firebase/add-pocket-article", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert "article_id" in data
            assert data["article_id"].startswith("pocket_")
            assert "status" in data
            assert "message" in data

    def test_add_pocket_article_with_firestore_warning(self, test_client: TestClient):
        """Test Pocket article addition with non-Firestore backend."""
        # Mock non-Firestore backend
        mock_db_storage = Mock()
        mock_db_storage.provider_name = "postgres"  # Not firestore
        mock_db_storage.create_article.return_value = True

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage):
            payload = {
                "user_id": "user123",
                "url": "https://example.com/article",
                "archiver": "monolith"
            }

            response = test_client.post("/firebase/add-pocket-article", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert "article_id" in data
            # Should still work but with warning logged

    def test_add_pocket_article_no_db_storage_503(self, test_client: TestClient):
        """Test Pocket article addition when DB storage not available."""
        with patch.object(test_client.app.state, 'db_storage', None):
            payload = {
                "user_id": "user123",
                "url": "https://example.com/article",
                "archiver": "monolith"
            }

            response = test_client.post("/firebase/add-pocket-article", json=payload)

            assert response.status_code == 503
            assert "Database storage provider not initialized" in response.json()["detail"]

    def test_add_pocket_article_no_task_manager(self, test_client: TestClient):
        """Test Pocket article addition when task manager not available."""
        mock_db_storage = Mock()
        mock_db_storage.provider_name = "firestore"
        mock_db_storage.create_article.return_value = True

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'task_manager', None):

            payload = {
                "user_id": "user123",
                "url": "https://example.com/article",
                "archiver": "monolith"
            }

            response = test_client.post("/firebase/add-pocket-article", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "saved"
            assert "not queued" in data["message"]

    def test_add_pocket_article_database_error_500(self, test_client: TestClient):
        """Test Pocket article addition when database operation fails."""
        mock_db_storage = Mock()
        mock_db_storage.provider_name = "firestore"
        mock_db_storage.create_article.side_effect = Exception("Database error")

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage):
            payload = {
                "user_id": "user123",
                "url": "https://example.com/article",
                "archiver": "monolith"
            }

            response = test_client.post("/firebase/add-pocket-article", json=payload)

            assert response.status_code == 500
            assert "Failed to add Pocket article" in response.json()["detail"]

    def test_add_pocket_article_url_hash_consistency(self, test_client: TestClient):
        """Test that article ID generation is consistent for same URL."""
        mock_db_storage = Mock()
        mock_db_storage.provider_name = "firestore"
        mock_db_storage.create_article.return_value = True

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage):
            payload = {
                "user_id": "user123",
                "url": "https://example.com/article",
                "archiver": "monolith"
            }

            # Make two requests with same URL
            response1 = test_client.post("/firebase/add-pocket-article", json=payload)
            response2 = test_client.post("/firebase/add-pocket-article", json=payload)

            assert response1.status_code == 200
            assert response2.status_code == 200
            # Should generate same article_id
            assert response1.json()["article_id"] == response2.json()["article_id"]

    def test_generate_download_url_success(self, test_client: TestClient):
        """Test successful download URL generation."""
        # Mock required app state components
        mock_db_storage = Mock()
        mock_db_storage.get_article.return_value = {
            'item_id': 'test123',
            'url': 'https://example.com/article'
        }
        mock_db_storage.get_artifact.return_value = {
            'gcs_path': 'archives/test123/monolith/output.html',
            'storage_uploads': [
                {
                    'success': True,
                    'storage_uri': 'gs://test-bucket/archives/test123/monolith/output.html'
                }
            ]
        }

        mock_file_storage = Mock()
        mock_file_storage.supports_signed_urls = True
        mock_file_storage.generate_access_url.return_value = "https://storage.googleapis.com/signed-url"

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'file_storage_providers', [mock_file_storage]):

            response = test_client.get("/firebase/download/test123/monolith")

            assert response.status_code == 200
            data = response.json()
            assert "download_url" in data
            assert data["download_url"] == "https://storage.googleapis.com/signed-url"
            assert "expires_in" in data
            assert data["expires_in"] == 24 * 3600  # Default 24 hours in seconds
            assert data["archiver"] == "monolith"
            assert data["gcs_path"] == "archives/test123/monolith/output.html"

    def test_generate_download_url_custom_expiration(self, test_client: TestClient):
        """Test download URL generation with custom expiration."""
        mock_db_storage = Mock()
        mock_db_storage.get_article.return_value = {'item_id': 'test123'}
        mock_db_storage.get_artifact.return_value = {
            'gcs_path': 'archives/test123/monolith/output.html'
        }

        mock_file_storage = Mock()
        mock_file_storage.supports_signed_urls = True
        mock_file_storage.generate_access_url.return_value = "https://storage.googleapis.com/signed-url"

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'file_storage_providers', [mock_file_storage]):

            response = test_client.get("/firebase/download/test123/monolith?expiration_hours=48")

            assert response.status_code == 200
            data = response.json()
            assert data["expires_in"] == 48 * 3600  # 48 hours in seconds

    def test_generate_download_url_no_storage_providers_503(self, test_client: TestClient):
        """Test download URL generation when storage providers not available."""
        with patch.object(test_client.app.state, 'file_storage_providers', None):
            response = test_client.get("/firebase/download/test123/monolith")

            assert response.status_code == 503
            assert "File storage providers not initialized" in response.json()["detail"]

    def test_generate_download_url_article_not_found_404(self, test_client: TestClient):
        """Test download URL generation when article not found."""
        mock_db_storage = Mock()
        mock_db_storage.get_article.return_value = None
        mock_file_storage = Mock()

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'file_storage_providers', [mock_file_storage]):

            response = test_client.get("/firebase/download/nonexistent/monolith")

            assert response.status_code == 404
            assert "Article not found" in response.json()["detail"]

    def test_generate_download_url_artifact_not_found_404(self, test_client: TestClient):
        """Test download URL generation when artifact not found."""
        mock_db_storage = Mock()
        mock_db_storage.get_article.return_value = {'item_id': 'test123'}
        mock_db_storage.get_artifact.return_value = None
        mock_file_storage = Mock()

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'file_storage_providers', [mock_file_storage]):

            response = test_client.get("/firebase/download/test123/monolith")

            assert response.status_code == 404
            assert "Artifact not found for archiver" in response.json()["detail"]

    def test_generate_download_url_no_gcs_path_404(self, test_client: TestClient):
        """Test download URL generation when no GCS path found."""
        mock_db_storage = Mock()
        mock_db_storage.get_article.return_value = {'item_id': 'test123'}
        mock_db_storage.get_artifact.return_value = {
            'storage_uploads': [],  # No uploads
            'gcs_path': None  # No GCS path
        }
        mock_file_storage = Mock()

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'file_storage_providers', [mock_file_storage]):

            response = test_client.get("/firebase/download/test123/monolith")

            assert response.status_code == 404
            assert "No GCS path found" in response.json()["detail"]

    def test_generate_download_url_no_signed_url_support_503(self, test_client: TestClient):
        """Test download URL generation when no provider supports signed URLs."""
        mock_db_storage = Mock()
        mock_db_storage.get_article.return_value = {'item_id': 'test123'}
        mock_db_storage.get_artifact.return_value = {
            'gcs_path': 'archives/test123/monolith/output.html'
        }

        mock_file_storage = Mock()
        mock_file_storage.supports_signed_urls = False

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'file_storage_providers', [mock_file_storage]):

            response = test_client.get("/firebase/download/test123/monolith")

            assert response.status_code == 503
            assert "No storage provider supports signed URLs" in response.json()["detail"]

    def test_generate_download_url_fallback_to_gcs_path_field(self, test_client: TestClient):
        """Test download URL generation fallback to gcs_path field."""
        mock_db_storage = Mock()
        mock_db_storage.get_article.return_value = {'item_id': 'test123'}
        mock_db_storage.get_artifact.return_value = {
            'storage_uploads': [],  # No uploads
            'gcs_path': 'archives/test123/monolith/output.html'  # Use old field
        }

        mock_file_storage = Mock()
        mock_file_storage.supports_signed_urls = True
        mock_file_storage.generate_access_url.return_value = "https://storage.googleapis.com/signed-url"

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'file_storage_providers', [mock_file_storage]):

            response = test_client.get("/firebase/download/test123/monolith")

            assert response.status_code == 200
            data = response.json()
            assert data["gcs_path"] == "archives/test123/monolith/output.html"

    def test_save_article_success(self, test_client: TestClient):
        """Test successful basic article saving."""
        mock_db_storage = Mock()
        mock_db_storage.create_article.return_value = True

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'task_manager', Mock()):

            payload = {
                "url": "https://example.com/article",
                "archiver": "monolith",
                "metadata": {"title": "Test Article"}
            }

            response = test_client.post("/firebase/save", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert "article_id" in data
            assert data["article_id"].startswith("article_")
            assert data["status"] == "queued"

    def test_save_article_no_db_storage(self, test_client: TestClient):
        """Test article saving when DB storage not available."""
        with patch.object(test_client.app.state, 'db_storage', None), \
             patch.object(test_client.app.state, 'task_manager', None):

            payload = {
                "url": "https://example.com/article",
                "archiver": "monolith"
            }

            response = test_client.post("/firebase/save", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "saved"  # Still saved but not queued

    def test_save_article_no_task_manager(self, test_client: TestClient):
        """Test article saving when task manager not available."""
        mock_db_storage = Mock()
        mock_db_storage.create_article.return_value = True

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'task_manager', None):

            payload = {
                "url": "https://example.com/article",
                "archiver": "monolith"
            }

            response = test_client.post("/firebase/save", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "saved"
            assert "not queued" in data["message"]

    def test_save_article_database_error_500(self, test_client: TestClient):
        """Test article saving when database operation fails."""
        mock_db_storage = Mock()
        mock_db_storage.create_article.side_effect = Exception("Database error")

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage):
            payload = {
                "url": "https://example.com/article",
                "archiver": "monolith"
            }

            response = test_client.post("/firebase/save", json=payload)

            assert response.status_code == 500
            assert "Failed to save article" in response.json()["detail"]

    def test_archive_article_success(self, test_client: TestClient):
        """Test successful Cloud Function archive trigger."""
        mock_db_storage = Mock()
        mock_db_storage.get_article.return_value = {'item_id': 'test123', 'url': 'https://example.com'}

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'task_manager', Mock()):

            payload = {
                "item_id": "test123",
                "url": "https://example.com/article",
                "archiver": "monolith"
            }

            response = test_client.post("/firebase/archive", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert data["item_id"] == "test123"
            assert data["status"] == "queued"
            assert "monolith" in data["message"]
            assert data["task_id"] is None

    def test_archive_article_no_db_storage_503(self, test_client: TestClient):
        """Test archive trigger when DB storage not available."""
        with patch.object(test_client.app.state, 'db_storage', None):
            payload = {
                "item_id": "test123",
                "url": "https://example.com/article",
                "archiver": "monolith"
            }

            response = test_client.post("/firebase/archive", json=payload)

            assert response.status_code == 503
            assert "Database storage provider not initialized" in response.json()["detail"]

    def test_archive_article_article_not_found_fallback(self, test_client: TestClient):
        """Test archive trigger when article not found (should create fallback)."""
        mock_db_storage = Mock()
        mock_db_storage.get_article.return_value = None  # Not found
        mock_db_storage.create_article.return_value = True

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'task_manager', Mock()):

            payload = {
                "item_id": "test123",
                "url": "https://example.com/article",
                "archiver": "monolith"
            }

            response = test_client.post("/firebase/archive", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "queued"
            # Should have created article and queued it

    def test_archive_article_no_task_manager(self, test_client: TestClient):
        """Test archive trigger when task manager not available."""
        mock_db_storage = Mock()
        mock_db_storage.get_article.return_value = {'item_id': 'test123', 'url': 'https://example.com'}

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'task_manager', None):

            payload = {
                "item_id": "test123",
                "url": "https://example.com/article",
                "archiver": "monolith"
            }

            response = test_client.post("/firebase/archive", json=payload)

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "saved"
            assert "not queued" in data["message"]

    def test_archive_article_database_error_500(self, test_client: TestClient):
        """Test archive trigger when database operation fails."""
        mock_db_storage = Mock()
        mock_db_storage.get_article.side_effect = Exception("Database error")

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage):
            payload = {
                "item_id": "test123",
                "url": "https://example.com/article",
                "archiver": "monolith"
            }

            response = test_client.post("/firebase/archive", json=payload)

            assert response.status_code == 500
            assert "Failed to archive article" in response.json()["detail"]

    def test_add_pocket_article_request_validation(self, test_client: TestClient):
        """Test AddPocketArticleRequest model validation."""
        # Valid request
        valid_payload = {
            "user_id": "user123",
            "url": "https://example.com/article",
            "pocket_data": {"title": "Test"},
            "archiver": "monolith"
        }
        response = test_client.post("/firebase/add-pocket-article", json=valid_payload)
        # Should not fail validation (might fail on business logic)
        assert response.status_code != 422

        # Missing required fields
        invalid_payload = {
            "url": "https://example.com/article"
            # Missing user_id
        }
        response = test_client.post("/firebase/add-pocket-article", json=invalid_payload)
        # Should fail validation
        assert response.status_code == 422

    def test_download_url_request_validation(self, test_client: TestClient):
        """Test download URL parameter validation."""
        mock_db_storage = Mock()
        mock_db_storage.get_article.return_value = {'item_id': 'test123'}
        mock_db_storage.get_artifact.return_value = {'gcs_path': 'test.html'}
        mock_file_storage = Mock()
        mock_file_storage.supports_signed_urls = True

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'file_storage_providers', [mock_file_storage]):

            # Valid request
            response = test_client.get("/firebase/download/test123/monolith")
            assert response.status_code == 200

            # Test with custom expiration
            response = test_client.get("/firebase/download/test123/monolith?expiration_hours=1")
            assert response.status_code == 200

    def test_article_id_consistency_across_endpoints(self, test_client: TestClient):
        """Test that article ID generation is consistent across endpoints."""
        # Mock for save endpoint
        mock_db_storage = Mock()
        mock_db_storage.create_article.return_value = True

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'task_manager', None):

            save_payload = {
                "url": "https://example.com/consistent-test",
                "archiver": "monolith"
            }
            save_response = test_client.post("/firebase/save", json=save_payload)

            # Mock for archive endpoint
            mock_db_storage.get_article.return_value = {'item_id': save_response.json()["article_id"]}

            archive_payload = {
                "item_id": save_response.json()["article_id"],
                "url": "https://example.com/consistent-test",
                "archiver": "monolith"
            }
            archive_response = test_client.post("/firebase/archive", json=archive_payload)

            # Both should work with same article_id
            assert save_response.status_code == 200
            assert archive_response.status_code == 200
            assert save_response.json()["article_id"] == archive_response.json()["item_id"]

    def test_firebase_api_logging(self, test_client: TestClient):
        """Test that Firebase endpoints log properly."""
        mock_db_storage = Mock()
        mock_db_storage.provider_name = "firestore"
        mock_db_storage.create_article.return_value = True

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch('api.firebase.logger') as mock_logger:

            payload = {
                "user_id": "user123",
                "url": "https://example.com/article",
                "archiver": "monolith"
            }
            test_client.post("/firebase/add-pocket-article", json=payload)

            # Should have logged the operation
            assert mock_logger.info.called
            # Check that logging includes expected context
            call_args = mock_logger.info.call_args
            assert any("Created Pocket article" in str(arg) for arg in call_args)

    def test_firebase_response_model_validation(self, test_client: TestClient):
        """Test that Firebase responses match expected models."""
        mock_db_storage = Mock()
        mock_db_storage.provider_name = "firestore"
        mock_db_storage.create_article.return_value = True

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage):
            payload = {
                "user_id": "user123",
                "url": "https://example.com/article",
                "archiver": "monolith"
            }

            response = test_client.post("/firebase/add-pocket-article", json=payload)

            if response.status_code == 200:
                data = response.json()
                required_fields = ["article_id", "status", "message"]
                for field in required_fields:
                    assert field in data

    def test_firebase_api_error_handling(self, test_client: TestClient):
        """Test error handling in Firebase API."""
        # Test with completely invalid JSON
        response = test_client.post(
            "/firebase/add-pocket-article",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422  # Validation error

    def test_firebase_api_edge_cases(self, test_client: TestClient):
        """Test edge cases in Firebase API."""
        # Test with very long URL
        long_url = "https://example.com/" + "a" * 1000

        mock_db_storage = Mock()
        mock_db_storage.provider_name = "firestore"
        mock_db_storage.create_article.return_value = True

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage):
            payload = {
                "user_id": "user123",
                "url": long_url,
                "archiver": "monolith"
            }

            response = test_client.post("/firebase/add-pocket-article", json=payload)
            assert response.status_code in [200, 500]  # Might work or fail gracefully

    def test_gcs_uri_parsing(self, test_client: TestClient):
        """Test GCS URI parsing in download URL generation."""
        mock_db_storage = Mock()
        mock_db_storage.get_article.return_value = {'item_id': 'test123'}
        mock_db_storage.get_artifact.return_value = {
            'storage_uploads': [
                {
                    'success': True,
                    'storage_uri': 'gs://my-bucket/path/to/file.html'
                },
                {
                    'success': True,
                    'storage_uri': 'https://not-gcs-uri.com/file.html'  # Not a GCS URI
                }
            ]
        }

        mock_file_storage = Mock()
        mock_file_storage.supports_signed_urls = True
        mock_file_storage.generate_access_url.return_value = "https://storage.googleapis.com/signed-url"

        with patch.object(test_client.app.state, 'db_storage', mock_db_storage), \
             patch.object(test_client.app.state, 'file_storage_providers', [mock_file_storage]):

            response = test_client.get("/firebase/download/test123/monolith")

            assert response.status_code == 200
            data = response.json()
            # Should find the GCS URI
            assert data["download_url"] == "https://storage.googleapis.com/signed-url"
            assert data["gcs_path"] == "path/to/file.html"