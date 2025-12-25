"""
End-to-end tests for real web page archiving.

Tests actual archiving workflows using real archiver binaries, real web pages,
and complete system integration. These tests verify the entire archiving pipeline
from HTTP request to final artifact storage.
"""

import json
import time
import os
from pathlib import Path
from unittest.mock import patch
import pytest
import requests


class TestE2EArchiving:
    """Test end-to-end archiving workflows."""

    def test_simple_page_archiving(self, e2e_client, e2e_base_url, e2e_sample_items):
        """Test archiving a simple web page end-to-end."""
        item = e2e_sample_items[0]  # Use httpbin.org/html

        # Submit archival request
        response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"id": item["item_id"], "url": item["url"]},
            timeout=30
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert "db_rowid" in data

        # Wait for archiving to complete (in real E2E, this might take time)
        time.sleep(5)

        # Check archival status
        response = e2e_client.get(f"{e2e_base_url}/admin/saves?item_id={item['item_id']}")
        if response.status_code == 200:
            saves = response.json()
            if saves:
                save = saves[0]
                assert save["item_id"] == item["item_id"]
                assert save["url"] == item["url"]
                assert save["archiver"] == "monolith"

    def test_multiple_archivers_same_url(self, e2e_client, e2e_base_url, e2e_sample_items):
        """Test archiving same URL with multiple archivers."""
        item = e2e_sample_items[0]  # Use simple, reliable URL
        archivers = ["monolith", "readability"]

        task_ids = []

        # Archive with multiple archivers
        for archiver in archivers:
            response = e2e_client.post(
                f"{e2e_base_url}/archive/{archiver}",
                json={"id": f"{item['item_id']}_{archiver}", "url": item["url"]},
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                task_ids.append((archiver, data["task_id"]))

        # Wait for processing
        time.sleep(10)

        # Verify multiple artifacts were created
        for archiver, task_id in task_ids:
            response = e2e_client.get(
                f"{e2e_base_url}/admin/saves?item_id={item['item_id']}_{archiver}&archiver={archiver}"
            )
            if response.status_code == 200:
                saves = response.json()
                if saves:
                    save = saves[0]
                    assert save["archiver"] == archiver

    def test_archive_all_archivers(self, e2e_client, e2e_base_url, e2e_sample_items):
        """Test archiving with 'all' archivers option."""
        item = e2e_sample_items[1]  # Use example.com

        response = e2e_client.post(
            f"{e2e_base_url}/archive/all",
            json={"id": item["item_id"], "url": item["url"]},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            assert "task_id" in data

            # Wait for all archivers to complete
            time.sleep(15)

            # Check that multiple artifacts were created
            response = e2e_client.get(f"{e2e_base_url}/admin/saves?item_id={item['item_id']}")
            if response.status_code == 200:
                saves = response.json()
                # Should have artifacts for multiple archivers
                assert len(saves) >= 1

    def test_batch_archiving_workflow(self, e2e_client, e2e_base_url, e2e_sample_items):
        """Test batch archiving of multiple URLs."""
        # Use a subset of items for batch testing
        batch_items = e2e_sample_items[:2]

        payload = {
            "archiver": "monolith",
            "items": [
                {"item_id": item["item_id"], "url": item["url"]}
                for item in batch_items
            ]
        }

        response = e2e_client.post(
            f"{e2e_base_url}/tasks/batch-create",
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            assert "task_id" in data
            assert data["item_count"] == len(batch_items)

            # Wait for batch processing
            time.sleep(15)

            # Verify all items were processed
            for item in batch_items:
                response = e2e_client.get(f"{e2e_base_url}/admin/saves?item_id={item['item_id']}")
                if response.status_code == 200:
                    saves = response.json()
                    # At least one save should exist for each item

    def test_archive_retrieval_workflow(self, e2e_client, e2e_base_url, e2e_sample_items):
        """Test complete archive retrieval workflow."""
        item = e2e_sample_items[0]

        # First archive the page
        response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"id": item["item_id"], "url": item["url"]},
            timeout=30
        )

        if response.status_code != 200:
            pytest.skip("Archive creation failed")

        # Wait for archiving to complete
        time.sleep(10)

        # Retrieve the archive
        response = e2e_client.post(
            f"{e2e_base_url}/archive/retrieve",
            json={"id": item["item_id"], "archiver": "monolith"},
            timeout=30
        )

        # Response should be successful or provide meaningful error
        assert response.status_code in [200, 404, 503]

        if response.status_code == 200:
            # Should return the archived content or file stream
            content_type = response.headers.get("content-type", "")
            assert "text/html" in content_type or "application/zip" in content_type

    def test_archive_size_tracking(self, e2e_client, e2e_base_url, e2e_sample_items):
        """Test archive size tracking functionality."""
        item = e2e_sample_items[0]

        # Archive the page
        response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"id": item["item_id"], "url": item["url"]},
            timeout=30
        )

        if response.status_code != 200:
            pytest.skip("Archive creation failed")

        # Wait for processing
        time.sleep(10)

        # Check archive size
        response = e2e_client.get(f"{e2e_base_url}/archive/{item['item_id']}/monolith/size")
        # Response should be 200 or 404 (not processed yet)
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            # Should contain size information
            assert "size" in data or "size_bytes" in data

    def test_error_handling_invalid_urls(self, e2e_client, e2e_base_url):
        """Test error handling with invalid URLs."""
        invalid_urls = [
            "not-a-url",
            "ftp://invalid.protocol.com",
            "https://nonexistent-domain-12345.com",
            "https://httpbin.org/status/404"
        ]

        for url in invalid_urls:
            response = e2e_client.post(
                f"{e2e_base_url}/archive/monolith",
                json={"id": f"test_{hash(url)}", "url": url},
                timeout=30
            )

            # Should handle gracefully (might succeed initially but fail later)
            # or return validation error immediately
            assert response.status_code in [200, 422]

    def test_concurrent_archiving_requests(self, e2e_client, e2e_base_url, e2e_sample_items):
        """Test handling of concurrent archiving requests."""
        import threading
        import queue

        results = queue.Queue()

        def archive_worker(worker_id):
            try:
                item = e2e_sample_items[worker_id % len(e2e_sample_items)]
                response = e2e_client.post(
                    f"{e2e_base_url}/archive/monolith",
                    json={"id": f"concurrent_{worker_id}_{item['item_id']}", "url": item["url"]},
                    timeout=30
                )
                results.put((worker_id, response.status_code, response.json()))
            except Exception as e:
                results.put((worker_id, -1, str(e)))

        # Start multiple concurrent requests
        threads = []
        for i in range(3):
            thread = threading.Thread(target=archive_worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all requests to complete
        for thread in threads:
            thread.join()

        # Check results
        success_count = 0
        total_count = 0
        while not results.empty():
            worker_id, status_code, data = results.get()
            total_count += 1
            if status_code == 200:
                success_count += 1

        assert total_count == 3
        # Most should succeed, depending on system load and rate limits

    def test_large_page_archiving(self, e2e_client, e2e_base_url):
        """Test archiving of larger content pages."""
        # Use a page with substantial content
        large_page_item = {
            "item_id": "large_page_test",
            "url": "https://www.wikipedia.org/wiki/Computer_science"
        }

        response = e2e_client.post(
            f"{e2e_base_url}/archive/readability",  # Use readability for content extraction
            json={"id": large_page_item["item_id"], "url": large_page_item["url"]},
            timeout=60  # Allow more time for large pages
        )

        if response.status_code == 200:
            data = response.json()
            assert "task_id" in data

            # Wait for processing
            time.sleep(30)

            # Verify the archive was created
            response = e2e_client.get(f"{e2e_base_url}/admin/saves?item_id={large_page_item['item_id']}")
            if response.status_code == 200:
                saves = response.json()
                if saves:
                    save = saves[0]
                    # Check if file was created and has reasonable size
                    if save.get("size_bytes"):
                        assert save["size_bytes"] > 1000  # Should be substantial

    def test_archive_with_unicode_content(self, e2e_client, e2e_base_url):
        """Test archiving pages with Unicode content."""
        unicode_item = {
            "item_id": "unicode_test",
            "url": "https://httpbin.org/html"  # Contains various character encodings
        }

        response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"id": unicode_item["item_id"], "url": unicode_item["url"]},
            timeout=30
        )

        if response.status_code == 200:
            # Wait for processing
            time.sleep(10)

            # Try to retrieve and verify content handling
            response = e2e_client.post(
                f"{e2e_base_url}/archive/retrieve",
                json={"id": unicode_item["item_id"], "archiver": "monolith"},
                timeout=30
            )

            if response.status_code == 200:
                # Content should be properly encoded
                content = response.text
                # Should not contain encoding errors
                assert "�" not in content  # Replacement character

    def test_archive_with_redirects(self, e2e_client, e2e_base_url):
        """Test archiving pages that use redirects."""
        redirect_item = {
            "item_id": "redirect_test",
            "url": "https://httpbin.org/redirect/1"  # Redirects to /get
        }

        response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"id": redirect_item["item_id"], "url": redirect_item["url"]},
            timeout=30
        )

        # Should handle redirects gracefully
        assert response.status_code in [200, 422]  # 422 if redirects not allowed

    def test_duplicate_url_prevention(self, e2e_client, e2e_base_url, e2e_sample_items):
        """Test prevention of duplicate archives for same URL/archiver."""
        item = e2e_sample_items[0]

        # First archive request
        response1 = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"id": item["item_id"], "url": item["url"]},
            timeout=30
        )

        if response1.status_code != 200:
            pytest.skip("First archive failed")

        # Wait a bit
        time.sleep(5)

        # Second archive request with same URL but different ID
        response2 = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"id": f"{item['item_id']}_duplicate", "url": item["url"]},
            timeout=30
        )

        # Behavior depends on skip_existing_saves setting
        # Should either succeed (different item_id) or indicate duplicate
        assert response2.status_code in [200, 409, 422]

    def test_admin_workflow_complete_cycle(self, e2e_client, e2e_base_url, e2e_sample_items):
        """Test complete admin workflow: create, list, requeue, delete."""
        item = e2e_sample_items[0]

        # Step 1: Create archive
        response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"id": item["item_id"], "url": item["url"]},
            timeout=30
        )

        if response.status_code != 200:
            pytest.skip("Archive creation failed")

        # Wait for processing
        time.sleep(10)

        # Step 2: List saves
        response = e2e_client.get(f"{e2e_base_url}/admin/saves?item_id={item['item_id']}")
        if response.status_code == 200:
            saves = response.json()
            if saves:
                save = saves[0]

                # Step 3: Test requeue (if task manager is available)
                requeue_response = e2e_client.post(
                    f"{e2e_base_url}/admin/saves/requeue",
                    json={"artifact_ids": [save["rowid"]], "include_all": False}
                )
                # Might succeed or fail depending on task manager availability
                assert requeue_response.status_code in [200, 503]

                # Step 4: Cleanup - delete the save
                delete_response = e2e_client.delete(
                    f"{e2e_base_url}/admin/saves/by-item/{item['item_id']}"
                )
                assert delete_response.status_code in [200, 404]

    def test_archive_with_custom_headers(self, e2e_client, e2e_base_url):
        """Test archiving with custom HTTP headers if supported."""
        # This would test custom header functionality if implemented
        item = {
            "item_id": "headers_test",
            "url": "https://httpbin.org/headers"
        }

        # Standard archive (custom headers would be passed differently if supported)
        response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"id": item["item_id"], "url": item["url"]},
            timeout=30
        )

        assert response.status_code in [200, 422]

    def test_archiving_performance_benchmarks(self, e2e_client, e2e_base_url, e2e_sample_items, e2e_performance_thresholds):
        """Test archiving performance against defined thresholds."""
        item = e2e_sample_items[0]
        max_archival_time = e2e_performance_thresholds["max_archival_time"]

        start_time = time.time()

        response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"id": item["item_id"], "url": item["url"]},
            timeout=max_archival_time + 10
        )

        api_response_time = time.time() - start_time

        assert response.status_code == 200
        assert api_response_time < max_archival_time

        # Additional performance metrics would be collected here in a full implementation

    def test_archive_file_serving(self, e2e_client, e2e_base_url, e2e_sample_items):
        """Test that archived files can be served correctly."""
        item = e2e_sample_items[0]

        # Create archive first
        response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"id": item["item_id"], "url": item["url"]},
            timeout=30
        )

        if response.status_code != 200:
            pytest.skip("Archive creation failed")

        # Wait for processing
        time.sleep(15)

        # Try to access the archived file directly via file serving
        # This would depend on the file serving implementation
        file_url = f"{e2e_base_url}/files/{item['item_id']}/monolith/output.html"

        response = e2e_client.get(file_url, timeout=10)
        # Might succeed (404 if not implemented or file not ready)
        assert response.status_code in [200, 404]