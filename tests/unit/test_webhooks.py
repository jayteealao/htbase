"""
Tests for webhook notification functionality.

Tests webhook delivery, signature verification, retry logic, and integration
with the archive workflow.
"""

import hashlib
import hmac
import json
from unittest.mock import Mock, patch, MagicMock
import pytest
from datetime import datetime

# Mock httpx before importing webhook tasks
import sys
from unittest.mock import MagicMock
sys.modules['httpx'] = MagicMock()

from services.archive_worker.app.tasks.webhooks import (
    notify_webhook,
    gather_status,
    _generate_signature,
    WebhookEvent,
)


class TestSignatureGeneration:
    """Test HMAC signature generation."""

    def test_generate_signature_basic(self):
        """Test basic signature generation."""
        payload = {"event": "test", "data": "value"}
        secret = "test-secret"

        signature = _generate_signature(payload, secret)

        # Verify format
        assert signature.startswith("sha256=")
        assert len(signature) == 71  # "sha256=" + 64 hex chars

    def test_generate_signature_consistency(self):
        """Test that same payload+secret produces same signature."""
        payload = {"event": "test", "data": "value", "timestamp": "2024-01-01T00:00:00Z"}
        secret = "test-secret"

        sig1 = _generate_signature(payload, secret)
        sig2 = _generate_signature(payload, secret)

        assert sig1 == sig2

    def test_generate_signature_key_order_independence(self):
        """Test that signature is independent of key order (due to sort_keys)."""
        payload1 = {"a": 1, "b": 2, "c": 3}
        payload2 = {"c": 3, "a": 1, "b": 2}
        secret = "test-secret"

        sig1 = _generate_signature(payload1, secret)
        sig2 = _generate_signature(payload2, secret)

        assert sig1 == sig2

    def test_generate_signature_different_secrets(self):
        """Test that different secrets produce different signatures."""
        payload = {"event": "test"}
        secret1 = "secret-1"
        secret2 = "secret-2"

        sig1 = _generate_signature(payload, secret1)
        sig2 = _generate_signature(payload, secret2)

        assert sig1 != sig2

    def test_verify_signature_client_side(self):
        """Test signature verification from client perspective."""
        payload = {"event": "task.completed", "task_id": "abc123"}
        secret = "webhook-secret"

        # Generate signature (server-side)
        signature = _generate_signature(payload, secret)

        # Verify signature (client-side)
        payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')
        expected_sig = hmac.new(
            secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

        assert signature == f"sha256={expected_sig}"


class TestGatherStatus:
    """Test status gathering from database."""

    @patch('services.archive_worker.app.tasks.webhooks.get_session')
    def test_gather_status_all_success(self, mock_get_session):
        """Test gathering status when all tasks succeeded."""
        # Mock database session
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Mock artifacts
        mock_artifact1 = MagicMock()
        mock_artifact1.success = True
        mock_artifact1.archiver = "readability"
        mock_artifact1.exit_code = 0
        mock_artifact1.saved_path = "/data/test/readability/output.json"

        mock_artifact2 = MagicMock()
        mock_artifact2.success = True
        mock_artifact2.archiver = "screenshot"
        mock_artifact2.exit_code = 0
        mock_artifact2.saved_path = "/data/test/screenshot/screenshot.png"

        mock_url = MagicMock()
        mock_url.url = "https://example.com"
        mock_url.item_id = "test-123"

        mock_session.execute.return_value.all.return_value = [
            (mock_artifact1, mock_url),
            (mock_artifact2, mock_url),
        ]

        # Execute
        result = gather_status(None, None, task_id="workflow-123")

        # Verify
        assert result["status"] == "completed"
        assert result["task_id"] == "workflow-123"
        assert len(result["items"]) == 2
        assert result["items"][0]["status"] == "success"
        assert result["items"][1]["status"] == "success"

    @patch('services.archive_worker.app.tasks.webhooks.get_session')
    def test_gather_status_all_failed(self, mock_get_session):
        """Test gathering status when all tasks failed."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        mock_artifact = MagicMock()
        mock_artifact.success = False
        mock_artifact.archiver = "readability"
        mock_artifact.exit_code = 1
        mock_artifact.saved_path = None

        mock_url = MagicMock()
        mock_url.url = "https://example.com"
        mock_url.item_id = "test-123"

        mock_session.execute.return_value.all.return_value = [
            (mock_artifact, mock_url),
        ]

        result = gather_status(None, None, task_id="workflow-123")

        assert result["status"] == "failed"
        assert result["items"][0]["status"] == "failed"

    @patch('services.archive_worker.app.tasks.webhooks.get_session')
    def test_gather_status_partial_success(self, mock_get_session):
        """Test gathering status when some tasks succeeded."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        mock_artifact1 = MagicMock()
        mock_artifact1.success = True
        mock_artifact1.archiver = "readability"
        mock_artifact1.exit_code = 0
        mock_artifact1.saved_path = "/data/test/readability/output.json"

        mock_artifact2 = MagicMock()
        mock_artifact2.success = False
        mock_artifact2.archiver = "screenshot"
        mock_artifact2.exit_code = 1
        mock_artifact2.saved_path = None

        mock_url = MagicMock()
        mock_url.url = "https://example.com"
        mock_url.item_id = "test-123"

        mock_session.execute.return_value.all.return_value = [
            (mock_artifact1, mock_url),
            (mock_artifact2, mock_url),
        ]

        result = gather_status(None, None, task_id="workflow-123")

        assert result["status"] == "partial"
        assert len(result["items"]) == 2

    @patch('services.archive_worker.app.tasks.webhooks.get_session')
    def test_gather_status_no_artifacts(self, mock_get_session):
        """Test gathering status when no artifacts found."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.all.return_value = []

        result = gather_status(None, None, task_id="workflow-123")

        assert result["status"] == "unknown"
        assert result["items"] == []


class TestWebhookDelivery:
    """Test webhook notification delivery."""

    @patch('services.archive_worker.app.tasks.webhooks.httpx')
    def test_notify_webhook_success(self, mock_httpx):
        """Test successful webhook delivery."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.__enter__.return_value.post.return_value = mock_response
        mock_httpx.Client.return_value = mock_client

        # Prepare test data
        status_data = {
            "status": "completed",
            "items": [
                {
                    "url": "https://example.com",
                    "id": "test-123",
                    "archiver": "readability",
                    "status": "success",
                }
            ],
        }

        # Execute
        result = notify_webhook(
            None,
            workflow_id="workflow-123",
            webhook_url="https://webhook.example.com/callback",
            webhook_secret="test-secret",
            status_data=status_data,
            event_type=WebhookEvent.TASK_COMPLETED,
        )

        # Verify
        assert result["success"] is True
        assert result["status_code"] == 200

        # Verify POST was called with correct parameters
        mock_client.__enter__.return_value.post.assert_called_once()
        call_args = mock_client.__enter__.return_value.post.call_args

        assert call_args[0][0] == "https://webhook.example.com/callback"
        assert "X-HTBase-Signature" in call_args[1]["headers"]
        assert call_args[1]["headers"]["X-HTBase-Event"] == "task.completed"
        assert call_args[1]["timeout"] == 10.0

    @patch('services.archive_worker.app.tasks.webhooks.httpx')
    def test_notify_webhook_without_secret(self, mock_httpx):
        """Test webhook delivery without signature."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.__enter__.return_value.post.return_value = mock_response
        mock_httpx.Client.return_value = mock_client

        status_data = {"status": "completed", "items": []}

        result = notify_webhook(
            None,
            workflow_id="workflow-123",
            webhook_url="https://webhook.example.com/callback",
            webhook_secret=None,
            status_data=status_data,
        )

        assert result["success"] is True

        # Verify no signature header was added
        call_args = mock_client.__enter__.return_value.post.call_args
        assert "X-HTBase-Signature" not in call_args[1]["headers"]

    @patch('services.archive_worker.app.tasks.webhooks.httpx')
    def test_notify_webhook_client_error_no_retry(self, mock_httpx):
        """Test that 4xx errors don't trigger retry."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        mock_client = MagicMock()
        mock_client.__enter__.return_value.post.return_value = mock_response
        mock_httpx.Client.return_value = mock_client

        status_data = {"status": "completed", "items": []}

        # Create mock task with retry method
        mock_task = MagicMock()
        mock_task.request.retries = 0

        result = notify_webhook(
            mock_task,
            workflow_id="workflow-123",
            webhook_url="https://webhook.example.com/callback",
            webhook_secret="test-secret",
            status_data=status_data,
        )

        # Should not retry, should return error
        assert result["success"] is False
        assert result["status_code"] == 404
        mock_task.retry.assert_not_called()

    @patch('services.archive_worker.app.tasks.webhooks.httpx')
    def test_notify_webhook_server_error_retry(self, mock_httpx):
        """Test that 5xx errors trigger retry."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client = MagicMock()
        mock_client.__enter__.return_value.post.return_value = mock_response
        mock_httpx.Client.return_value = mock_client

        status_data = {"status": "completed", "items": []}

        # Create mock task with retry method
        mock_task = MagicMock()
        mock_task.request.retries = 0
        mock_task.retry.side_effect = Exception("Retry triggered")

        with pytest.raises(Exception, match="Retry triggered"):
            notify_webhook(
                mock_task,
                workflow_id="workflow-123",
                webhook_url="https://webhook.example.com/callback",
                webhook_secret="test-secret",
                status_data=status_data,
            )

        mock_task.retry.assert_called_once()

    @patch('services.archive_worker.app.tasks.webhooks.httpx')
    def test_notify_webhook_timeout_retry(self, mock_httpx):
        """Test that timeout errors trigger retry."""
        mock_client = MagicMock()
        mock_client.__enter__.return_value.post.side_effect = mock_httpx.TimeoutException("Timeout")
        mock_httpx.Client.return_value = mock_client

        status_data = {"status": "completed", "items": []}

        mock_task = MagicMock()
        mock_task.request.retries = 0
        mock_task.retry.side_effect = Exception("Retry triggered")

        with pytest.raises(Exception, match="Retry triggered"):
            notify_webhook(
                mock_task,
                workflow_id="workflow-123",
                webhook_url="https://webhook.example.com/callback",
                webhook_secret="test-secret",
                status_data=status_data,
            )

        mock_task.retry.assert_called_once()

    @patch('services.archive_worker.app.tasks.webhooks.httpx')
    def test_notify_webhook_network_error_retry(self, mock_httpx):
        """Test that network errors trigger retry."""
        mock_client = MagicMock()
        mock_client.__enter__.return_value.post.side_effect = mock_httpx.RequestError("Network error")
        mock_httpx.Client.return_value = mock_client

        status_data = {"status": "completed", "items": []}

        mock_task = MagicMock()
        mock_task.request.retries = 0
        mock_task.retry.side_effect = Exception("Retry triggered")

        with pytest.raises(Exception, match="Retry triggered"):
            notify_webhook(
                mock_task,
                workflow_id="workflow-123",
                webhook_url="https://webhook.example.com/callback",
                webhook_secret="test-secret",
                status_data=status_data,
            )

        mock_task.retry.assert_called_once()


class TestWebhookPayloadFormat:
    """Test webhook payload structure."""

    @patch('services.archive_worker.app.tasks.webhooks.httpx')
    def test_payload_structure(self, mock_httpx):
        """Test that webhook payload has correct structure."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.__enter__.return_value.post.return_value = mock_response
        mock_httpx.Client.return_value = mock_client

        status_data = {
            "status": "completed",
            "items": [
                {
                    "url": "https://example.com",
                    "id": "test-123",
                    "archiver": "readability",
                    "status": "success",
                    "exit_code": 0,
                    "saved_path": "/data/test/output.json",
                }
            ],
        }

        notify_webhook(
            None,
            workflow_id="workflow-123",
            webhook_url="https://webhook.example.com/callback",
            webhook_secret="test-secret",
            status_data=status_data,
            event_type=WebhookEvent.TASK_COMPLETED,
        )

        # Extract the payload sent
        call_args = mock_client.__enter__.return_value.post.call_args
        payload = call_args[1]["json"]

        # Verify structure
        assert "event" in payload
        assert "task_id" in payload
        assert "status" in payload
        assert "items" in payload
        assert "timestamp" in payload

        assert payload["event"] == "task.completed"
        assert payload["task_id"] == "workflow-123"
        assert payload["status"] == "completed"
        assert len(payload["items"]) == 1
        assert payload["timestamp"].endswith("Z")  # ISO format with Z suffix


class TestWebhookEvents:
    """Test different webhook event types."""

    def test_webhook_event_constants(self):
        """Test that webhook event constants are defined."""
        assert hasattr(WebhookEvent, "TASK_CREATED")
        assert hasattr(WebhookEvent, "TASK_COMPLETED")
        assert hasattr(WebhookEvent, "TASK_FAILED")
        assert hasattr(WebhookEvent, "ARCHIVE_SUCCESS")
        assert hasattr(WebhookEvent, "ARCHIVE_FAILED")

        assert WebhookEvent.TASK_CREATED == "task.created"
        assert WebhookEvent.TASK_COMPLETED == "task.completed"
        assert WebhookEvent.TASK_FAILED == "task.failed"
