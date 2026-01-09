"""
Integration tests for webhook functionality.

Tests end-to-end webhook delivery including API endpoints,
workflow chains, and actual webhook calls.
"""

import hashlib
import hmac
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_webhook_server():
    """Mock webhook server to receive callbacks."""
    received_webhooks = []

    def webhook_handler(request):
        """Mock webhook endpoint."""
        received_webhooks.append({
            "headers": dict(request.headers),
            "body": request.json(),
        })
        return {"status": "ok"}

    return {
        "handler": webhook_handler,
        "received": received_webhooks,
    }


class TestWebhookIntegration:
    """Test webhook integration with API endpoints."""

    @patch('services.archive_worker.app.tasks.webhooks.httpx')
    def test_save_endpoint_with_webhook(self, mock_httpx, test_client, mock_webhook_server):
        """Test /save endpoint with webhook notification."""
        # Mock successful webhook delivery
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.__enter__.return_value.post.return_value = mock_response
        mock_httpx.Client.return_value = mock_client

        # Make request with webhook
        response = test_client.post(
            "/save",
            json={
                "url": "https://example.com/article",
                "id": "test-webhook-123",
                "archivers": ["readability"],
                "webhook_url": "https://webhook.example.com/callback",
                "webhook_secret": "test-secret-123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["count"] >= 1

    def test_save_endpoint_without_webhook(self, test_client):
        """Test /save endpoint without webhook (backward compatibility)."""
        response = test_client.post(
            "/save",
            json={
                "url": "https://example.com/article",
                "id": "test-no-webhook-123",
                "archivers": ["readability"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_webhook_signature_verification(self):
        """Test that webhook signatures can be verified by receiver."""
        # Simulate server-side signature generation
        payload = {
            "event": "task.completed",
            "task_id": "abc123",
            "status": "completed",
            "items": [],
            "timestamp": "2024-01-01T00:00:00Z",
        }
        secret = "webhook-secret"

        # Generate signature (as server would)
        payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        signature_header = f"sha256={signature}"

        # Verify signature (as client would)
        expected_sig = hmac.new(
            secret.encode('utf-8'),
            json.dumps(payload, sort_keys=True).encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        assert signature == expected_sig
        assert signature_header == f"sha256={expected_sig}"

    def test_webhook_signature_mismatch_detection(self):
        """Test that tampered payloads fail signature verification."""
        original_payload = {
            "event": "task.completed",
            "task_id": "abc123",
            "status": "completed",
        }
        secret = "webhook-secret"

        # Generate signature for original
        payload_bytes = json.dumps(original_payload, sort_keys=True).encode('utf-8')
        original_sig = hmac.new(
            secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

        # Tamper with payload
        tampered_payload = original_payload.copy()
        tampered_payload["status"] = "failed"  # Change status

        # Verify with original signature
        tampered_bytes = json.dumps(tampered_payload, sort_keys=True).encode('utf-8')
        tampered_sig = hmac.new(
            secret.encode('utf-8'),
            tampered_bytes,
            hashlib.sha256
        ).hexdigest()

        # Signatures should not match
        assert original_sig != tampered_sig


class TestWebhookPayloadValidation:
    """Test webhook payload validation."""

    def test_webhook_url_validation(self, test_client):
        """Test that invalid webhook URLs are rejected."""
        response = test_client.post(
            "/save",
            json={
                "url": "https://example.com/article",
                "id": "test-invalid-webhook",
                "archivers": ["readability"],
                "webhook_url": "not-a-valid-url",
            },
        )

        # Should fail validation
        assert response.status_code == 422

    def test_webhook_url_optional(self, test_client):
        """Test that webhook_url is optional."""
        response = test_client.post(
            "/save",
            json={
                "url": "https://example.com/article",
                "id": "test-optional-webhook",
                "archivers": ["readability"],
                # No webhook_url provided
            },
        )

        # Should succeed
        assert response.status_code == 200

    def test_webhook_secret_optional(self, test_client):
        """Test that webhook_secret is optional."""
        response = test_client.post(
            "/save",
            json={
                "url": "https://example.com/article",
                "id": "test-optional-secret",
                "archivers": ["readability"],
                "webhook_url": "https://webhook.example.com/callback",
                # No webhook_secret provided
            },
        )

        # Should succeed (webhook will be sent without signature)
        assert response.status_code == 200


class TestWebhookRetryBehavior:
    """Test webhook retry logic."""

    @patch('services.archive_worker.app.tasks.webhooks.httpx')
    def test_webhook_retries_on_server_error(self, mock_httpx):
        """Test that webhook retries on 5xx errors."""
        from services.archive_worker.app.tasks.webhooks import notify_webhook

        # Mock server error response
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_client = MagicMock()
        mock_client.__enter__.return_value.post.return_value = mock_response
        mock_httpx.Client.return_value = mock_client

        status_data = {"status": "completed", "items": []}

        mock_task = MagicMock()
        mock_task.request.retries = 0
        mock_task.retry.side_effect = Exception("Retry triggered")

        # Should trigger retry
        with pytest.raises(Exception, match="Retry triggered"):
            notify_webhook(
                mock_task,
                workflow_id="test-123",
                webhook_url="https://webhook.example.com/callback",
                webhook_secret="secret",
                status_data=status_data,
            )

        mock_task.retry.assert_called_once()

    @patch('services.archive_worker.app.tasks.webhooks.httpx')
    def test_webhook_no_retry_on_client_error(self, mock_httpx):
        """Test that webhook does not retry on 4xx errors."""
        from services.archive_worker.app.tasks.webhooks import notify_webhook

        # Mock client error response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_client = MagicMock()
        mock_client.__enter__.return_value.post.return_value = mock_response
        mock_httpx.Client.return_value = mock_client

        status_data = {"status": "completed", "items": []}

        mock_task = MagicMock()
        mock_task.request.retries = 0

        # Should not retry
        result = notify_webhook(
            mock_task,
            workflow_id="test-123",
            webhook_url="https://webhook.example.com/callback",
            webhook_secret="secret",
            status_data=status_data,
        )

        assert result["success"] is False
        assert result["status_code"] == 400
        mock_task.retry.assert_not_called()


@pytest.fixture
def test_client():
    """Create test client for API."""
    from services.api_gateway.app.main import app
    return TestClient(app)
