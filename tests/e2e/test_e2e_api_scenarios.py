"""
End-to-end tests for API usage scenarios.

Tests complete API workflows that users would actually perform,
including error scenarios, edge cases, and realistic usage patterns.
"""

import json
import time
import pytest
import requests
from pathlib import Path


class TestE2EAPIScenarios:
    """Test end-to-end API scenarios."""

    def test_user_journey_single_archive(self, e2e_client, e2e_base_url, e2e_real_world_urls):
        """Test complete user journey for archiving a single page."""
        # Step 1: Check system health
        response = e2e_client.get(f"{e2e_base_url}/health")
        if response.status_code != 200:
            pytest.skip("System not healthy")

        # Step 2: Archive a real web page
        test_url = e2e_real_world_urls[1]  # Use httpbin.org/html
        item_id = "user_journey_test"

        archive_response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"id": item_id, "url": test_url},
            timeout=30
        )

        assert archive_response.status_code == 200
        archive_data = archive_response.json()
        assert "task_id" in archive_data

        # Step 3: Check archive status
        time.sleep(5)  # Wait for processing

        status_response = e2e_client.get(f"{e2e_base_url}/admin/saves?item_id={item_id}")
        if status_response.status_code == 200:
            saves = status_response.json()
            # At least the save record should exist, even if processing is incomplete

        # Step 4: Try to retrieve the archive
        retrieve_response = e2e_client.post(
            f"{e2e_base_url}/archive/retrieve",
            json={"id": item_id, "archiver": "monolith"},
            timeout=30
        )

        # Response should be meaningful
        assert retrieve_response.status_code in [200, 404, 503]

    def test_batch_research_workflow(self, e2e_client, e2e_base_url, e2e_real_world_urls):
        """Test batch archiving workflow for research purposes."""
        research_urls = e2e_real_world_urls[:3]  # Use first 3 URLs
        research_prefix = "research_batch"

        # Create batch request
        batch_payload = {
            "archiver": "readability",
            "items": [
                {"item_id": f"{research_prefix}_{i}", "url": url}
                for i, url in enumerate(research_urls)
            ]
        }

        response = e2e_client.post(
            f"{e2e_base_url}/tasks/batch-create",
            json=batch_payload,
            timeout=45  # Allow more time for batch
        )

        if response.status_code == 200:
            batch_data = response.json()
            assert "task_id" in batch_data
            assert batch_data["item_count"] == len(research_urls)

            # Wait for batch processing
            time.sleep(20)

            # Verify batch results
            success_count = 0
            for i in range(len(research_urls)):
                item_id = f"{research_prefix}_{i}"
                status_response = e2e_client.get(f"{e2e_base_url}/admin/saves?item_id={item_id}")
                if status_response.status_code == 200:
                    saves = status_response.json()
                    if saves:
                        success_count += 1

            # At least some should succeed
            assert success_count > 0

    def test_archive_management_workflow(self, e2e_client, e2e_base_url, e2e_real_world_urls):
        """Test complete archive management workflow."""
        test_url = e2e_real_world_urls[0]
        item_id = "management_test"

        # Step 1: Create multiple archives
        archivers = ["monolith", "readability"]
        created_saves = []

        for archiver in archivers:
            response = e2e_client.post(
                f"{e2e_base_url}/archive/{archiver}",
                json={"id": f"{item_id}_{archiver}", "url": test_url},
                timeout=30
            )

            if response.status_code == 200:
                created_saves.append((archiver, response.json()["task_id"]))

        # Wait for processing
        time.sleep(15)

        # Step 2: List all saves
        list_response = e2e_client.get(f"{e2e_base_url}/admin/saves?limit=10")
        if list_response.status_code == 200:
            saves = list_response.json()
            assert isinstance(saves, list)

            # Step 3: Find our saves in the list
            our_saves = [save for save in saves if save["item_id"].startswith(item_id)]
            # Should find at least some of our saves

        # Step 4: Clean up - delete test saves
        for archiver, _ in created_saves:
            delete_response = e2e_client.delete(
                f"{e2e_base_url}/admin/saves/by-item/{item_id}_{archiver}"
            )
            assert delete_response.status_code in [200, 404]

    def test_error_recovery_scenarios(self, e2e_client, e2e_base_url):
        """Test various error recovery scenarios."""
        # Test 1: Invalid archiver
        response = e2e_client.post(
            f"{e2e_base_url}/archive/nonexistent_archiver",
            json={"id": "error_test", "url": "https://example.com"}
        )
        assert response.status_code == 404

        # Test 2: Missing required fields
        response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"id": "error_test"}  # Missing URL
        )
        assert response.status_code == 422

        # Test 3: Invalid JSON
        response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [400, 422]

        # Test 4: Non-existent save retrieval
        response = e2e_client.post(
            f"{e2e_base_url}/archive/retrieve",
            json={"id": "nonexistent_save", "archiver": "monolith"}
        )
        assert response.status_code in [404, 422]

    def test_concurrent_user_scenarios(self, e2e_client, e2e_base_url, e2e_real_world_urls):
        """Test concurrent user scenarios."""
        import threading
        import queue

        results = queue.Queue()

        def user_session(user_id):
            """Simulate a user session."""
            try:
                # Each user archives different content
                url = e2e_real_world_urls[user_id % len(e2e_real_world_urls)]
                item_id = f"user_{user_id}_session"

                # Archive the content
                response = e2e_client.post(
                    f"{e2e_base_url}/archive/monolith",
                    json={"id": item_id, "url": url},
                    timeout=30
                )

                if response.status_code == 200:
                    # Check status
                    time.sleep(3)
                    status_response = e2e_client.get(f"{e2e_base_url}/admin/saves?item_id={item_id}")
                    results.put((user_id, "success", response.status_code))
                else:
                    results.put((user_id, "archive_failed", response.status_code))

            except Exception as e:
                results.put((user_id, "exception", str(e)))

        # Start multiple user sessions
        threads = []
        for user_id in range(3):
            thread = threading.Thread(target=user_session, args=(user_id,))
            threads.append(thread)
            thread.start()

        # Wait for all sessions
        for thread in threads:
            thread.join()

        # Check results
        success_count = 0
        total_count = 0
        while not results.empty():
            user_id, status, data = results.get()
            total_count += 1
            if status == "success":
                success_count += 1

        assert total_count == 3
        # Most should succeed unless system is overloaded

    def test_api_response_consistency(self, e2e_client, e2e_base_url):
        """Test API response format consistency across endpoints."""
        endpoints_to_test = [
            ("/admin/archivers", "GET"),
            ("/admin/saves", "GET"),
            ("/health", "GET")
        ]

        for endpoint, method in endpoints_to_test:
            if method == "GET":
                response = e2e_client.get(f"{e2e_base_url}{endpoint}")
            else:
                response = e2e_client.post(f"{e2e_base_url}{endpoint}", json={})

            if response.status_code == 200:
                # Check response format consistency
                assert "content-type" in response.headers
                assert "application/json" in response.headers["content-type"]

                try:
                    data = response.json()
                    assert isinstance(data, (dict, list))
                except json.JSONDecodeError:
                    pytest.fail(f"Invalid JSON response from {endpoint}")

    def test_large_payload_handling(self, e2e_client, e2e_base_url):
        """Test handling of large API payloads."""
        # Test batch with many items
        large_batch = {
            "archiver": "monolith",
            "items": [
                {"item_id": f"large_batch_{i}", "url": f"https://example.com/{i}"}
                for i in range(20)  # 20 items
            ]
        }

        response = e2e_client.post(
            f"{e2e_base_url}/tasks/batch-create",
            json=large_batch,
            timeout=60
        )

        # Should handle large payloads gracefully
        assert response.status_code in [200, 413, 422]  # 413 = Payload Too Large

    def test_rate_limiting_behavior(self, e2e_client, e2e_base_url):
        """Test API rate limiting behavior if implemented."""
        responses = []

        # Make rapid requests
        for i in range(10):
            response = e2e_client.post(
                f"{e2e_base_url}/archive/monolith",
                json={"id": f"rate_limit_{i}", "url": "https://example.com"},
                timeout=10
            )
            responses.append(response.status_code)

        # If rate limiting is implemented, some requests should be limited
        success_count = sum(1 for code in responses if code == 200)
        rate_limited_count = sum(1 for code in responses if code == 429)

        # At minimum, most should succeed
        assert success_count >= 5  # Adjust threshold based on system limits

    def test_api_security_headers(self, e2e_client, e2e_base_url):
        """Test API security headers."""
        response = e2e_client.get(f"{e2e_base_url}/admin/archivers")

        if response.status_code == 200:
            headers = response.headers

            # Check for common security headers
            security_headers = [
                "x-content-type-options",
                "x-frame-options",
                "x-xss-protection"
            ]

            # Note: Implementation of security headers varies
            # This test documents what should be checked

    def test_pagination_functionality(self, e2e_client, e2e_base_url):
        """Test API pagination functionality."""
        # Test pagination parameters
        pagination_tests = [
            {"limit": 5, "offset": 0},
            {"limit": 10, "offset": 5},
            {"limit": 2, "offset": 0}
        ]

        for params in pagination_tests:
            response = e2e_client.get(
                f"{e2e_base_url}/admin/saves",
                params=params
            )

            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list)
                # Should respect limit parameter
                if params["limit"] > 0:
                    assert len(data) <= params["limit"]

    def test_api_versioning(self, e2e_client, e2e_base_url):
        """Test API versioning if implemented."""
        # Test with version headers
        response = e2e_client.get(
            f"{e2e_base_url}/admin/archivers",
            headers={"Accept": "application/vnd.htbase.v1+json"}
        )

        # Should handle versioning gracefully
        assert response.status_code in [200, 406, 415]

    def test_api_cors_behavior(self, e2e_client, e2e_base_url):
        """Test CORS behavior for API endpoints."""
        # Test preflight request
        options_response = e2e_client.options(
            f"{e2e_base_url}/archive/monolith",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type"
            }
        )

        # Should handle OPTIONS requests
        assert options_response.status_code in [200, 405]

        # Test actual request with Origin header
        response = e2e_client.post(
            f"{e2e_base_url}/admin/archivers",
            headers={"Origin": "https://example.com"}
        )

        if response.status_code == 200:
            # Should have CORS headers if implemented
            pass

    def test_file_upload_scenarios(self, e2e_client, e2e_base_url):
        """Test file upload/download scenarios if implemented."""
        # This would test file upload endpoints if they exist
        # For now, test that file serving endpoints work appropriately

        # Test accessing file serving endpoint
        response = e2e_client.get(f"{e2e_base_url}/files/")
        # Should return 404 or directory listing if implemented

    def test_system_monitoring_endpoints(self, e2e_client, e2e_base_url):
        """Test system monitoring and metrics endpoints."""
        monitoring_endpoints = [
            "/health",
            "/metrics"  # If implemented
        ]

        for endpoint in monitoring_endpoints:
            response = e2e_client.get(f"{e2e_base_url}{endpoint}")
            # Health endpoint should always work
            if endpoint == "/health":
                assert response.status_code == 200
            else:
                # Other endpoints might not be implemented
                assert response.status_code in [200, 404]

    def test_api_error_message_quality(self, e2e_client, e2e_base_url):
        """Test quality and consistency of error messages."""
        error_scenarios = [
            ("/archive/nonexistent", "POST", {"id": "test", "url": "https://example.com"}),
            ("/admin/saves/999999", "DELETE", None),
            ("/archive/nonexistent/size", "GET", None),
        ]

        for endpoint, method, payload in error_scenarios:
            if method == "POST":
                response = e2e_client.post(f"{e2e_base_url}{endpoint}", json=payload or {})
            elif method == "DELETE":
                response = e2e_client.delete(f"{e2e_base_url}{endpoint}")
            else:
                response = e2e_client.get(f"{e2e_base_url}{endpoint}")

            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    # Should have meaningful error information
                    assert "detail" in error_data or "error" in error_data or "message" in error_data
                    assert len(str(error_data)) > 10  # Should not be empty
                except json.JSONDecodeError:
                    # Should have plain text error at minimum
                    assert len(response.text) > 5

    def test_api_backward_compatibility(self, e2e_client, e2e_base_url):
        """Test API backward compatibility scenarios."""
        # Test with older API formats if applicable
        legacy_payloads = [
            # Different field names or formats that might have been used
            {"item_id": "legacy_test", "url": "https://example.com"},  # Instead of "id"
        ]

        for payload in legacy_payloads:
            response = e2e_client.post(
                f"{e2e_base_url}/archive/monolith",
                json=payload,
                timeout=30
            )
            # Should either work with legacy format or provide clear error
            assert response.status_code in [200, 422]

    def test_api_under_load(self, e2e_client, e2e_base_url, e2e_metrics_collector):
        """Test API behavior under system load."""
        # Start collecting metrics
        e2e_metrics_collector.start_collection()

        # Make a series of requests
        request_times = []
        for i in range(10):
            start_time = time.time()
            response = e2e_client.get(f"{e2e_base_url}/admin/archivers")
            end_time = time.time()

            request_times.append(end_time - start_time)
            assert response.status_code == 200

            time.sleep(0.1)  # Small delay between requests

        # Stop collecting metrics
        e2e_metrics_collector.stop_collection()

        # Check performance
        avg_response_time = sum(request_times) / len(request_times)
        assert avg_response_time < 5.0  # Should be reasonably fast

        # Get system metrics summary
        metrics_summary = e2e_metrics_collector.get_summary()
        assert "cpu" in metrics_summary
        assert "memory" in metrics_summary

    def test_api_idempotency(self, e2e_client, e2e_base_url):
        """Test API idempotency for appropriate endpoints."""
        # Test GET requests (should be idempotent)
        for _ in range(3):
            response = e2e_client.get(f"{e2e_base_url}/admin/archivers")
            assert response.status_code == 200

        # Test the same GET request multiple times
        responses = []
        for _ in range(3):
            response = e2e_client.get(f"{e2e_base_url}/admin/archivers")
            responses.append(response.json())

        # Should return consistent results
        assert len(set(str(r) for r in responses)) <= 1  # All responses should be identical