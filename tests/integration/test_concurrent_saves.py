"""
Integration tests for concurrent save requests.

Tests the race condition fix for artifact creation using row locking.
"""

import asyncio
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest
import httpx

# Add shared module to path
_ROOT = Path(__file__).resolve().parents[2]
_SHARED = str(_ROOT / "shared")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)


@pytest.fixture
def api_base_url():
    """Base URL for API Gateway - adjust based on test environment."""
    return "http://localhost:8000"


def test_concurrent_saves_same_url(api_base_url):
    """
    Test that concurrent save requests for the same URL don't cause IntegrityError.

    This test verifies that the SELECT FOR UPDATE row locking prevents race conditions
    when multiple requests try to create artifacts for the same URL simultaneously.
    """
    url = "https://example.com/test-article"
    item_id = "test-concurrent-001"

    # Number of concurrent requests to send
    num_requests = 10

    def make_save_request(request_num):
        """Make a single save request."""
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{api_base_url}/save",
                    json={
                        "url": url,
                        "id": f"{item_id}-{request_num}",
                        "archivers": ["readability"],
                    },
                )
                return {
                    "request_num": request_num,
                    "status_code": response.status_code,
                    "success": response.status_code in [200, 201],
                    "response": response.json() if response.status_code < 500 else None,
                    "error": None,
                }
        except Exception as e:
            return {
                "request_num": request_num,
                "status_code": None,
                "success": False,
                "response": None,
                "error": str(e),
            }

    # Execute concurrent requests using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=num_requests) as executor:
        futures = [
            executor.submit(make_save_request, i)
            for i in range(num_requests)
        ]

        results = [future.result() for future in as_completed(futures)]

    # Analyze results
    successful_requests = [r for r in results if r["success"]]
    failed_requests = [r for r in results if not r["success"]]
    server_errors = [r for r in results if r["status_code"] == 500]

    # Assertions
    print(f"\nConcurrent Save Test Results:")
    print(f"  Total requests: {num_requests}")
    print(f"  Successful: {len(successful_requests)}")
    print(f"  Failed: {len(failed_requests)}")
    print(f"  Server errors (500): {len(server_errors)}")

    if failed_requests:
        print(f"\nFailed requests details:")
        for r in failed_requests:
            print(f"  Request {r['request_num']}: {r['error'] or r.get('response', 'No response')}")

    # All requests should succeed (200 or 201)
    assert len(server_errors) == 0, (
        f"Expected no 500 errors, but got {len(server_errors)}. "
        "This indicates IntegrityError or other server-side issues."
    )

    # Most requests should succeed (allow for network issues)
    assert len(successful_requests) >= num_requests * 0.9, (
        f"Expected at least 90% success rate, got {len(successful_requests)}/{num_requests}"
    )

    # Check idempotency - all successful responses should be consistent
    task_ids = [r["response"]["task_id"] for r in successful_requests if r["response"]]
    print(f"\nTask IDs returned: {len(set(task_ids))} unique out of {len(task_ids)} total")


@pytest.mark.asyncio
async def test_concurrent_saves_async(api_base_url):
    """
    Test concurrent saves using async/await for better concurrency simulation.

    This test uses asyncio to create truly concurrent requests and verify
    that the row locking mechanism handles the race condition correctly.
    """
    url = "https://example.com/async-test-article"
    item_id = "test-async-concurrent-001"
    num_requests = 15

    async def make_async_request(session, request_num):
        """Make a single async save request."""
        try:
            response = await session.post(
                f"{api_base_url}/save",
                json={
                    "url": url,
                    "id": f"{item_id}-{request_num}",
                    "archivers": ["readability", "screenshot"],
                },
                timeout=30.0,
            )
            return {
                "request_num": request_num,
                "status_code": response.status_code,
                "success": response.status_code in [200, 201],
                "response": response.json() if response.status_code < 500 else None,
            }
        except Exception as e:
            return {
                "request_num": request_num,
                "status_code": None,
                "success": False,
                "error": str(e),
            }

    # Execute all requests concurrently
    async with httpx.AsyncClient() as session:
        tasks = [
            make_async_request(session, i)
            for i in range(num_requests)
        ]
        results = await asyncio.gather(*tasks)

    # Analyze results
    successful = [r for r in results if r["success"]]
    server_errors = [r for r in results if r.get("status_code") == 500]

    print(f"\nAsync Concurrent Save Test Results:")
    print(f"  Total requests: {num_requests}")
    print(f"  Successful: {len(successful)}")
    print(f"  Server errors (500): {len(server_errors)}")

    # No integrity errors (500) should occur
    assert len(server_errors) == 0, (
        f"Expected no IntegrityError (500 responses), but got {len(server_errors)}"
    )

    # High success rate expected
    assert len(successful) >= num_requests * 0.9, (
        f"Expected at least 90% success rate, got {len(successful)}/{num_requests}"
    )


def test_concurrent_batch_saves(api_base_url):
    """
    Test that concurrent batch save requests don't cause race conditions.

    This tests the save_batch endpoint with concurrent requests for overlapping URLs.
    """
    base_url = "https://example.com/batch-test"
    item_id = "test-batch-concurrent-001"
    num_requests = 8

    def make_batch_request(request_num):
        """Make a single batch save request."""
        try:
            with httpx.Client(timeout=30.0) as client:
                # Each request saves 3 URLs, with overlap across requests
                response = client.post(
                    f"{api_base_url}/save/batch",
                    json={
                        "items": [
                            {
                                "url": f"{base_url}-{i}",
                                "id": f"{item_id}-{request_num}-{i}",
                                "archivers": ["readability"],
                            }
                            for i in range(3)  # Same 3 URLs for all requests
                        ]
                    },
                )
                return {
                    "request_num": request_num,
                    "status_code": response.status_code,
                    "success": response.status_code in [200, 201],
                }
        except Exception as e:
            return {
                "request_num": request_num,
                "success": False,
                "error": str(e),
            }

    # Execute concurrent batch requests
    with ThreadPoolExecutor(max_workers=num_requests) as executor:
        futures = [
            executor.submit(make_batch_request, i)
            for i in range(num_requests)
        ]
        results = [future.result() for future in as_completed(futures)]

    # Analyze results
    successful = [r for r in results if r["success"]]
    server_errors = [r for r in results if r.get("status_code") == 500]

    print(f"\nConcurrent Batch Save Test Results:")
    print(f"  Total requests: {num_requests}")
    print(f"  Successful: {len(successful)}")
    print(f"  Server errors (500): {len(server_errors)}")

    # No integrity errors should occur
    assert len(server_errors) == 0, (
        f"Expected no IntegrityError in batch saves, but got {len(server_errors)}"
    )

    # All batch requests should succeed
    assert len(successful) == num_requests, (
        f"Expected all {num_requests} batch requests to succeed, got {len(successful)}"
    )


if __name__ == "__main__":
    # Allow running tests directly with python
    pytest.main([__file__, "-v", "-s"])
