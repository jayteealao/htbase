import httpx
import pytest
import time
from urllib.parse import quote

# --- Test Configuration ---
API_GATEWAY_URL = "http://localhost:8000"
DATA_SERVICE_URL = "http://localhost:8000/data" # Accessed via gateway
TEST_URL = "https://example.com"
TEST_ID = "integration-test-user"

@pytest.mark.integration
def test_end_to_end_archive_flow():
    """
    Tests the full microservices flow:
    1. Sends a request to the API Gateway to start an archive.
    2. Polls the Data Service (via the gateway) to verify that the
       ArchivedUrl and ArchiveArtifact records are created.
    """
    # --- 1. Start the Archive ---
    archive_payload = {"url": TEST_URL, "id": TEST_ID}
    with httpx.Client() as client:
        response = client.post(f"{API_GATEWAY_URL}/archive", json=archive_payload)
        assert response.status_code == 202
        task_id = response.json()["task_id"]
        assert task_id

    # --- 2. Poll for Results ---
    max_retries = 10
    retry_delay = 5  # seconds
    archived_url = None
    artifacts = []

    for i in range(max_retries):
        print(f"Polling attempt {i+1}/{max_retries}...")
        try:
            # Check for the ArchivedUrl record
            with httpx.Client() as client:
                # URL encode the test URL to use it in a query parameter
                encoded_url = quote(TEST_URL, safe='')
                url_response = client.get(f"{DATA_SERVICE_URL}/urls/by_url?url={encoded_url}")

                if url_response.status_code == 200:
                    archived_url = url_response.json()
                    print(f"Found ArchivedUrl: {archived_url}")

                    # Now check for artifacts associated with this URL
                    # This requires an endpoint like /artifacts/by_url_id/{id} which we'll assume exists
                    artifact_response = client.get(f"{DATA_SERVICE_URL}/artifacts/by_url_id/{archived_url['id']}")
                    if artifact_response.status_code == 200 and artifact_response.json():
                        artifacts = artifact_response.json()
                        print(f"Found artifacts: {artifacts}")
                        break # Success!

        except httpx.RequestError as e:
            print(f"Request failed: {e}")

        time.sleep(retry_delay)

    # --- 3. Assertions ---
    assert archived_url is not None, "ArchivedUrl record was not created in time."
    assert archived_url["url"] == TEST_URL
    assert archived_url["item_id"] == TEST_ID

    assert len(artifacts) > 0, "No ArchiveArtifact records were created in time."
    # Check that at least one artifact was successful
    assert any(a["success"] for a in artifacts)
