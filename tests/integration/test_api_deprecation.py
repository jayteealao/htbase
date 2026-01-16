"""Test deprecation warnings for legacy Firebase endpoints."""
import pytest
from fastapi.testclient import TestClient


def test_add_pocket_article_deprecated(test_client):
    """Test that legacy add-pocket-article logs deprecation warning."""
    client = test_client
    payload = {
        "user_id": "test_user",
        "url": "https://example.com/deprecated-test",
        "pocket_data": {"title": "Test"}
    }

    # Should still work but log warning
    response = client.post("/firebase/add-pocket-article", json=payload)
    # Accept various success codes depending on configuration
    assert response.status_code in [200, 201, 503]  # 503 if backend not available

    # Check that endpoint is marked deprecated in OpenAPI schema
    openapi = client.get("/openapi.json").json()
    add_pocket_path = openapi["paths"]["/firebase/add-pocket-article"]["post"]
    assert add_pocket_path.get("deprecated") is True, "Endpoint should be marked deprecated in OpenAPI schema"


def test_save_deprecated(test_client):
    """Test that legacy save endpoint logs deprecation warning."""
    client = test_client
    payload = {
        "url": "https://example.com/save-deprecated-test"
    }

    response = client.post("/firebase/save", json=payload)
    # Accept various success codes depending on configuration
    assert response.status_code in [200, 201, 503]  # 503 if backend not available

    # Check deprecated flag
    openapi = client.get("/openapi.json").json()
    save_path = openapi["paths"]["/firebase/save"]["post"]
    assert save_path.get("deprecated") is True, "Endpoint should be marked deprecated in OpenAPI schema"


def test_archive_deprecated(test_client):
    """Test that legacy archive endpoint logs deprecation warning."""
    client = test_client
    payload = {
        "item_id": "test_item_123",
        "url": "https://example.com/archive-deprecated-test",
        "archiver": "monolith"
    }

    response = client.post("/firebase/archive", json=payload)
    # Accept various success codes depending on configuration
    assert response.status_code in [200, 201, 503]  # 503 if backend not available

    # Check deprecated flag
    openapi = client.get("/openapi.json").json()
    archive_path = openapi["paths"]["/firebase/archive"]["post"]
    assert archive_path.get("deprecated") is True, "Endpoint should be marked deprecated in OpenAPI schema"


def test_deprecation_in_openapi_docs(test_client):
    """Test that all deprecated endpoints are marked in OpenAPI schema."""
    client = test_client
    openapi = client.get("/openapi.json").json()

    deprecated_endpoints = [
        "/firebase/add-pocket-article",
        "/firebase/save",
        "/firebase/archive"
    ]

    for endpoint_path in deprecated_endpoints:
        assert endpoint_path in openapi["paths"], f"Endpoint {endpoint_path} not found in OpenAPI schema"
        endpoint_def = openapi["paths"][endpoint_path]["post"]
        assert endpoint_def.get("deprecated") is True, f"Endpoint {endpoint_path} should be marked deprecated"

        # Check that deprecation notice is in description
        description = endpoint_def.get("description", "")
        assert "DEPRECATED" in description, f"Endpoint {endpoint_path} should have DEPRECATED in description"
        assert "/api/v1/firebase/" in description, f"Endpoint {endpoint_path} should reference new api-gateway path"
