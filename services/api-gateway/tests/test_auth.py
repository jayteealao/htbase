"""
Tests for API key authentication.

Tests the authentication middleware for the API Gateway.
"""

import os
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from shared.auth import verify_api_key

# Create a minimal test app
app = FastAPI()


@app.get("/protected", dependencies=[Depends(verify_api_key)])
async def protected_endpoint():
    """Protected endpoint requiring authentication."""
    return {"message": "Access granted"}


@app.get("/public")
async def public_endpoint():
    """Public endpoint without authentication."""
    return {"message": "Public access"}


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_api_keys():
    """Set up API keys for testing."""
    # Save original value
    original = os.getenv("API_KEYS")

    # Set test API keys
    os.environ["API_KEYS"] = "test_key_1,test_key_2,test_key_3"

    yield

    # Restore original value
    if original is not None:
        os.environ["API_KEYS"] = original
    else:
        os.environ.pop("API_KEYS", None)


def test_public_endpoint_no_auth(client):
    """Test that public endpoints work without authentication."""
    response = client.get("/public")
    assert response.status_code == 200
    assert response.json() == {"message": "Public access"}


def test_protected_endpoint_no_auth(client):
    """Test that protected endpoints reject requests without authentication."""
    response = client.get("/protected")
    assert response.status_code == 403  # FastAPI returns 403 for missing credentials


def test_protected_endpoint_invalid_auth(client):
    """Test that protected endpoints reject invalid API keys."""
    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer invalid_key"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key"


def test_protected_endpoint_valid_auth(client):
    """Test that protected endpoints accept valid API keys."""
    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer test_key_1"}
    )
    assert response.status_code == 200
    assert response.json() == {"message": "Access granted"}


def test_protected_endpoint_valid_auth_key2(client):
    """Test that all configured API keys work."""
    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer test_key_2"}
    )
    assert response.status_code == 200
    assert response.json() == {"message": "Access granted"}


def test_protected_endpoint_valid_auth_key3(client):
    """Test that all configured API keys work."""
    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer test_key_3"}
    )
    assert response.status_code == 200
    assert response.json() == {"message": "Access granted"}


def test_protected_endpoint_malformed_auth(client):
    """Test that malformed authorization headers are rejected."""
    # Missing Bearer prefix
    response = client.get(
        "/protected",
        headers={"Authorization": "test_key_1"}
    )
    assert response.status_code == 403


def test_protected_endpoint_empty_bearer(client):
    """Test that empty bearer tokens are rejected."""
    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer "}
    )
    assert response.status_code == 401


def test_no_api_keys_configured(client):
    """Test that missing API_KEYS configuration returns 500."""
    # Remove API_KEYS temporarily
    os.environ.pop("API_KEYS", None)

    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer test_key_1"}
    )
    assert response.status_code == 500
    assert "Authentication not configured" in response.json()["detail"]

    # Restore for other tests
    os.environ["API_KEYS"] = "test_key_1,test_key_2,test_key_3"


def test_empty_api_keys_configured(client):
    """Test that empty API_KEYS configuration returns 500."""
    # Set empty API_KEYS
    os.environ["API_KEYS"] = ""

    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer test_key_1"}
    )
    assert response.status_code == 500
    assert "Authentication not configured" in response.json()["detail"]

    # Restore for other tests
    os.environ["API_KEYS"] = "test_key_1,test_key_2,test_key_3"


def test_whitespace_in_api_keys(client):
    """Test that API keys with whitespace are handled correctly."""
    # Set API keys with whitespace
    os.environ["API_KEYS"] = " test_key_1 , test_key_2 , test_key_3 "

    # Should still work because we strip whitespace
    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer test_key_1"}
    )
    assert response.status_code == 200

    # Restore for other tests
    os.environ["API_KEYS"] = "test_key_1,test_key_2,test_key_3"


def test_case_sensitive_api_keys(client):
    """Test that API keys are case-sensitive."""
    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer TEST_KEY_1"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API key"
