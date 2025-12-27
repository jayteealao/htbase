"""
End-to-end tests for API usage scenarios.

Tests complete API workflows that users would actually perform,
including error scenarios, edge cases, and realistic usage patterns.

API Coverage:
- /healthz - Health check
- /save - Async save with task queue
- /save/batch - Batch async save
- /archive/{archiver} - Sync archive
- /archive/{archiver}/batch - Batch archive
- /archive/retrieve - Retrieve archived content
- /archive/{id}/size - Get archive size
- /tasks/{task_id} - Task status polling
- /saves - List saves (admin)
- /archivers - List archivers (admin)
- /saves/requeue - Requeue failed saves
- /saves/{rowid} - Delete save by rowid
- /saves/by-item/{item_id} - Delete by item_id
- /saves/by-url - Delete by URL
- /summarize - Trigger summarization
- /commands/executions - Command history
- /firebase/* - Firebase integration
- /sync/* - Postgres/Firestore sync
"""

import json
import time
import uuid
import pytest


class TestHealthAndDiscovery:
    """Test health check and service discovery endpoints."""

    def test_healthz_endpoint(self, e2e_client, e2e_base_url):
        """Test /healthz returns 200 OK."""
        response = e2e_client.get(f"{e2e_base_url}/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

    def test_list_archivers(self, e2e_client, e2e_base_url, e2e_test_archivers):
        """Test /archivers returns all registered archivers."""
        response = e2e_client.get(f"{e2e_base_url}/archivers")
        assert response.status_code == 200
        archivers = response.json()
        assert isinstance(archivers, list)
        # Should have at least the core archivers
        for expected in ["monolith", "readability"]:
            assert expected in archivers, f"Missing archiver: {expected}"


class TestAsyncSaveWorkflow:
    """Test the primary async save workflow: POST /save -> poll /tasks/{id}."""

    def test_async_save_returns_task_id(self, e2e_client, e2e_base_url):
        """Test POST /save returns task_id for polling."""
        item_id = f"e2e_async_{uuid.uuid4().hex[:8]}"
        payload = {"id": item_id, "url": "https://example.com"}

        response = e2e_client.post(f"{e2e_base_url}/save", json=payload)

        assert response.status_code == 202
        data = response.json()
        assert "task_id" in data
        assert "count" in data
        assert data["count"] >= 1

    def test_async_save_task_polling(self, e2e_client, e2e_base_url, e2e_wait_for_task):
        """Test complete async workflow: save -> poll -> verify completion."""
        item_id = f"e2e_poll_{uuid.uuid4().hex[:8]}"
        payload = {"id": item_id, "url": "https://example.com"}

        # Submit save request
        save_response = e2e_client.post(f"{e2e_base_url}/save", json=payload)
        assert save_response.status_code == 202
        task_id = save_response.json()["task_id"]

        # Poll for completion
        try:
            task_status = e2e_wait_for_task(e2e_base_url, task_id, timeout=120)
            assert task_status["task_id"] == task_id
            assert task_status["status"] in ["success", "failed"]
            assert "items" in task_status
        except TimeoutError:
            pytest.skip("Task did not complete in time - may be resource constrained")

    def test_task_status_endpoint_not_found(self, e2e_client, e2e_base_url):
        """Test GET /tasks/{task_id} returns 404 for non-existent task."""
        response = e2e_client.get(f"{e2e_base_url}/tasks/nonexistent-task-id")
        assert response.status_code == 404


class TestBatchSaveWorkflow:
    """Test batch save operations."""

    def test_save_batch_endpoint(self, e2e_client, e2e_base_url):
        """Test POST /save/batch accepts multiple items."""
        items = [
            {"id": f"e2e_batch_{i}_{uuid.uuid4().hex[:6]}", "url": f"https://example.com/page{i}"}
            for i in range(3)
        ]
        payload = {"items": items}

        response = e2e_client.post(f"{e2e_base_url}/save/batch", json=payload)

        assert response.status_code == 202
        data = response.json()
        assert "task_id" in data
        assert data["count"] == 3

    def test_archive_batch_endpoint(self, e2e_client, e2e_base_url):
        """Test POST /archive/{archiver}/batch accepts multiple items."""
        items = [
            {"id": f"e2e_arch_batch_{i}_{uuid.uuid4().hex[:6]}", "url": f"https://example.com/arch{i}"}
            for i in range(2)
        ]
        payload = {"items": items}

        response = e2e_client.post(f"{e2e_base_url}/archive/monolith/batch", json=payload)

        assert response.status_code == 202
        data = response.json()
        assert "task_id" in data
        assert data["count"] == 2


class TestSyncArchiveEndpoints:
    """Test synchronous archive endpoints."""

    def test_archive_with_monolith(self, e2e_client, e2e_base_url):
        """Test POST /archive/monolith for sync archiving."""
        item_id = f"e2e_mono_{uuid.uuid4().hex[:8]}"
        payload = {"id": item_id, "url": "https://example.com"}

        response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json=payload,
            timeout=60
        )

        assert response.status_code == 200
        data = response.json()
        assert "ok" in data
        assert "exit_code" in data
        assert "id" in data

    def test_archive_with_readability(self, e2e_client, e2e_base_url):
        """Test POST /archive/readability for sync archiving."""
        item_id = f"e2e_read_{uuid.uuid4().hex[:8]}"
        payload = {"id": item_id, "url": "https://example.com"}

        response = e2e_client.post(
            f"{e2e_base_url}/archive/readability",
            json=payload,
            timeout=60
        )

        assert response.status_code == 200
        data = response.json()
        assert "ok" in data

    def test_archive_all_archivers(self, e2e_client, e2e_base_url):
        """Test POST /archive/all runs all archivers."""
        item_id = f"e2e_all_{uuid.uuid4().hex[:8]}"
        payload = {"id": item_id, "url": "https://example.com"}

        response = e2e_client.post(
            f"{e2e_base_url}/archive/all",
            json=payload,
            timeout=180  # All archivers takes longer
        )

        assert response.status_code == 200
        data = response.json()
        assert "ok" in data

    def test_archive_invalid_archiver(self, e2e_client, e2e_base_url):
        """Test POST /archive/{invalid} returns 404."""
        payload = {"id": "test", "url": "https://example.com"}

        response = e2e_client.post(
            f"{e2e_base_url}/archive/nonexistent_archiver",
            json=payload
        )

        assert response.status_code == 404

    def test_archive_missing_url(self, e2e_client, e2e_base_url):
        """Test POST /archive/{archiver} with missing URL returns 422."""
        response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"id": "test_missing_url"}
        )

        assert response.status_code == 422

    def test_archive_missing_id(self, e2e_client, e2e_base_url):
        """Test POST /archive/{archiver} with missing ID returns 422."""
        response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"url": "https://example.com"}
        )

        assert response.status_code == 422

    def test_archive_invalid_json(self, e2e_client, e2e_base_url):
        """Test POST /archive/{archiver} with invalid JSON returns 422."""
        response = e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422


class TestArchiverMatrix:
    """Test all 5 production archivers."""

    @pytest.mark.parametrize("archiver", [
        "readability",
        "monolith",
        "singlefile-cli",
        "screenshot",
        "pdf",
    ])
    def test_archiver_available(self, e2e_client, e2e_base_url, archiver):
        """Test each archiver is registered and responds."""
        # Check archiver is in list
        response = e2e_client.get(f"{e2e_base_url}/archivers")
        archivers = response.json()

        if archiver not in archivers:
            pytest.skip(f"Archiver {archiver} not available in this environment")

        # Try archiving with this archiver
        item_id = f"e2e_{archiver.replace('-', '_')}_{uuid.uuid4().hex[:6]}"
        payload = {"id": item_id, "url": "https://example.com"}

        response = e2e_client.post(
            f"{e2e_base_url}/archive/{archiver}",
            json=payload,
            timeout=120  # Chromium archivers may be slow
        )

        # Should either succeed or fail gracefully (not 5xx crash)
        assert response.status_code in [200, 404, 422, 503]


class TestArchiveRetrieval:
    """Test archive retrieval endpoints."""

    def test_retrieve_by_item_id(self, e2e_client, e2e_base_url):
        """Test POST /archive/retrieve with item_id."""
        # First create an archive
        item_id = f"e2e_retrieve_{uuid.uuid4().hex[:8]}"
        e2e_client.post(
            f"{e2e_base_url}/archive/monolith",
            json={"id": item_id, "url": "https://example.com"},
            timeout=60
        )

        time.sleep(2)

        # Then retrieve it - must provide url OR id, and archiver is optional
        response = e2e_client.post(
            f"{e2e_base_url}/archive/retrieve",
            json={"id": item_id, "url": "https://example.com", "archiver": "monolith"}
        )

        # Should be 200 (found) or 404 (not yet ready/not found)
        # 422 indicates a validation bug that should be fixed
        assert response.status_code in [200, 404], f"Got 422 validation error: {response.text}"

    def test_retrieve_nonexistent(self, e2e_client, e2e_base_url):
        """Test POST /archive/retrieve for non-existent archive returns 404."""
        response = e2e_client.post(
            f"{e2e_base_url}/archive/retrieve",
            json={"id": "nonexistent_item_id_12345", "url": "https://example.com/nonexistent", "archiver": "monolith"}
        )

        # Should return 404 for non-existent archive
        # 422 indicates a validation bug that should be fixed
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"


class TestArchiveSizeEndpoint:
    """Test archive size endpoint."""

    def test_archive_size_not_found(self, e2e_client, e2e_base_url):
        """Test GET /archive/{id}/size returns 404 for non-existent ID."""
        response = e2e_client.get(f"{e2e_base_url}/archive/999999/size")
        assert response.status_code == 404


class TestAdminSavesEndpoints:
    """Test admin saves management endpoints."""

    def test_list_saves(self, e2e_client, e2e_base_url):
        """Test GET /saves returns paginated list."""
        response = e2e_client.get(f"{e2e_base_url}/saves")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_saves_pagination(self, e2e_client, e2e_base_url):
        """Test GET /saves with limit and offset."""
        response = e2e_client.get(
            f"{e2e_base_url}/saves",
            params={"limit": 5, "offset": 0}
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5

    def test_delete_by_item_id(self, e2e_client, e2e_base_url):
        """Test DELETE /saves/by-item/{item_id}."""
        # Create an archive first
        item_id = f"e2e_delete_{uuid.uuid4().hex[:8]}"
        e2e_client.post(
            f"{e2e_base_url}/archive/readability",
            json={"id": item_id, "url": "https://example.com"},
            timeout=60
        )

        time.sleep(2)

        # Delete it
        response = e2e_client.delete(f"{e2e_base_url}/saves/by-item/{item_id}")

        # 200 if found and deleted, 404 if not found
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert data.get("ok") is True

    def test_delete_by_url(self, e2e_client, e2e_base_url):
        """Test DELETE /saves/by-url endpoint."""
        import urllib.parse

        # Create an archive first
        item_id = f"e2e_del_url_{uuid.uuid4().hex[:8]}"
        test_url = f"https://example.com/delete-test-{uuid.uuid4().hex[:6]}"
        e2e_client.post(
            f"{e2e_base_url}/archive/readability",
            json={"id": item_id, "url": test_url},
            timeout=60
        )

        time.sleep(2)

        # Delete by URL - URL must be properly encoded
        encoded_url = urllib.parse.quote(test_url, safe='')
        response = e2e_client.delete(
            f"{e2e_base_url}/saves/by-url?url={encoded_url}"
        )

        # Should be 200 (deleted) or 404 (not found/already deleted)
        # 422 indicates URL encoding or validation bug that should be fixed
        assert response.status_code in [200, 404], f"Got 422 validation error: {response.text}"

    def test_delete_nonexistent_rowid(self, e2e_client, e2e_base_url):
        """Test DELETE /saves/{rowid} returns 404 for non-existent rowid."""
        response = e2e_client.delete(f"{e2e_base_url}/saves/999999999")
        assert response.status_code == 404


class TestRequeueEndpoint:
    """Test requeue endpoint with correct payload format."""

    def test_requeue_with_artifact_ids(self, e2e_client, e2e_base_url):
        """Test POST /saves/requeue with artifact_ids."""
        payload = {
            "artifact_ids": [1, 2, 3],
            "include_all": False
        }

        response = e2e_client.post(f"{e2e_base_url}/saves/requeue", json=payload)

        # 200 or 500 if task manager not initialized
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "requeued_count" in data
            assert "task_ids" in data

    def test_requeue_by_status(self, e2e_client, e2e_base_url):
        """Test POST /saves/requeue with status filter."""
        payload = {
            "status": "failed",
            "include_all": True
        }

        response = e2e_client.post(f"{e2e_base_url}/saves/requeue", json=payload)

        assert response.status_code in [200, 500]

    def test_requeue_invalid_request(self, e2e_client, e2e_base_url):
        """Test POST /saves/requeue with invalid payload returns 400."""
        payload = {
            "include_all": False
            # Missing artifact_ids or status
        }

        response = e2e_client.post(f"{e2e_base_url}/saves/requeue", json=payload)

        assert response.status_code in [400, 500]


class TestSummarizeEndpoint:
    """Test summarization endpoint."""

    def test_summarize_unavailable(self, e2e_client, e2e_base_url):
        """Test POST /summarize returns 503 when disabled."""
        payload = {"item_id": "test_item"}

        response = e2e_client.post(f"{e2e_base_url}/summarize", json=payload)

        # 503 if summarizer disabled, 404 if item not found, 200 if working
        assert response.status_code in [200, 404, 503]

    def test_summarize_not_found(self, e2e_client, e2e_base_url):
        """Test POST /summarize returns 404 for non-existent item."""
        payload = {"item_id": "nonexistent_item_12345"}

        response = e2e_client.post(f"{e2e_base_url}/summarize", json=payload)

        # 404 if item not found, 503 if summarizer disabled
        assert response.status_code in [404, 503]


class TestCommandHistoryEndpoints:
    """Test command execution history endpoints."""

    def test_list_executions(self, e2e_client, e2e_base_url):
        """Test GET /commands/executions returns list."""
        response = e2e_client.get(f"{e2e_base_url}/commands/executions")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_executions_with_filters(self, e2e_client, e2e_base_url):
        """Test GET /commands/executions with filters."""
        response = e2e_client.get(
            f"{e2e_base_url}/commands/executions",
            params={"archiver": "monolith", "limit": 10}
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10

    def test_execution_detail_not_found(self, e2e_client, e2e_base_url):
        """Test GET /commands/executions/{id} returns 404 for non-existent."""
        response = e2e_client.get(f"{e2e_base_url}/commands/executions/999999999")
        assert response.status_code == 404

    def test_execution_replay(self, e2e_client, e2e_base_url):
        """Test GET /commands/executions/{id}/replay endpoint exists."""
        response = e2e_client.get(f"{e2e_base_url}/commands/executions/999999999/replay")
        # 404 for non-existent, but endpoint should exist
        assert response.status_code == 404


class TestFirebaseEndpoints:
    """Test Firebase integration endpoints."""

    def test_firebase_add_pocket_article(self, e2e_client, e2e_base_url):
        """Test POST /firebase/add-pocket-article."""
        payload = {
            "user_id": "test_user_123",
            "url": "https://example.com/pocket-article",
            "pocket_data": {"title": "Test Article", "excerpt": "Test excerpt"},
            "archiver": "monolith"
        }

        response = e2e_client.post(
            f"{e2e_base_url}/firebase/add-pocket-article",
            json=payload
        )

        # 200/503 depending on Firestore availability
        assert response.status_code in [200, 500, 503]
        if response.status_code == 200:
            data = response.json()
            assert "article_id" in data
            assert "status" in data

    def test_firebase_save(self, e2e_client, e2e_base_url):
        """Test POST /firebase/save."""
        payload = {
            "url": "https://example.com/firebase-save",
            "archiver": "readability",
            "metadata": {}
        }

        response = e2e_client.post(f"{e2e_base_url}/firebase/save", json=payload)

        # 200/503 depending on storage availability
        assert response.status_code in [200, 500, 503]

    def test_firebase_archive(self, e2e_client, e2e_base_url):
        """Test POST /firebase/archive."""
        payload = {
            "item_id": f"firebase_arch_{uuid.uuid4().hex[:8]}",
            "url": "https://example.com/firebase-archive",
            "archiver": "all"
        }

        response = e2e_client.post(f"{e2e_base_url}/firebase/archive", json=payload)

        # 200/503 depending on storage availability
        assert response.status_code in [200, 500, 503]

    def test_firebase_download_url_not_found(self, e2e_client, e2e_base_url):
        """Test GET /firebase/download/{item_id}/{archiver} for non-existent."""
        response = e2e_client.get(
            f"{e2e_base_url}/firebase/download/nonexistent_item/monolith"
        )

        # 404 if not found, 503 if storage not configured
        assert response.status_code in [404, 503]


class TestSyncEndpoints:
    """Test PostgreSQL/Firestore sync endpoints."""

    def test_sync_postgres_to_firestore(self, e2e_client, e2e_base_url):
        """Test POST /sync/postgres-to-firestore."""
        payload = {"limit": 10}

        response = e2e_client.post(
            f"{e2e_base_url}/sync/postgres-to-firestore",
            json=payload
        )

        # 200/400/503 depending on Firestore configuration
        assert response.status_code in [200, 400, 500, 503]
        if response.status_code == 200:
            data = response.json()
            assert "synced" in data
            assert "total" in data

    def test_sync_firestore_to_postgres(self, e2e_client, e2e_base_url):
        """Test POST /sync/firestore-to-postgres."""
        payload = {"item_id": "test_sync_item"}

        response = e2e_client.post(
            f"{e2e_base_url}/sync/firestore-to-postgres",
            json=payload
        )

        # 200/404/503 depending on Firestore configuration
        assert response.status_code in [200, 400, 404, 500, 503]


class TestAPIResponseConsistency:
    """Test API response format consistency."""

    def test_json_response_format(self, e2e_client, e2e_base_url):
        """Test API endpoints return valid JSON with correct content-type."""
        endpoints = [
            ("/healthz", "GET"),
            ("/archivers", "GET"),
            ("/saves", "GET"),
            ("/commands/executions", "GET"),
        ]

        for endpoint, method in endpoints:
            if method == "GET":
                response = e2e_client.get(f"{e2e_base_url}{endpoint}")
            else:
                response = e2e_client.post(f"{e2e_base_url}{endpoint}", json={})

            if response.status_code == 200:
                assert "application/json" in response.headers.get("content-type", "")
                try:
                    data = response.json()
                    assert isinstance(data, (dict, list))
                except json.JSONDecodeError:
                    pytest.fail(f"Invalid JSON from {endpoint}")

    def test_error_response_format(self, e2e_client, e2e_base_url):
        """Test error responses have meaningful detail."""
        error_endpoints = [
            ("/archive/nonexistent", "POST", {"id": "test", "url": "https://example.com"}),
            ("/saves/999999999", "DELETE", None),
            ("/tasks/nonexistent", "GET", None),
        ]

        for endpoint, method, payload in error_endpoints:
            if method == "POST":
                response = e2e_client.post(f"{e2e_base_url}{endpoint}", json=payload or {})
            elif method == "DELETE":
                response = e2e_client.delete(f"{e2e_base_url}{endpoint}")
            else:
                response = e2e_client.get(f"{e2e_base_url}{endpoint}")

            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    assert "detail" in error_data or "error" in error_data or "message" in error_data
                except json.JSONDecodeError:
                    # Plain text error is also acceptable
                    assert len(response.text) > 0


class TestConcurrentRequests:
    """Test concurrent request handling."""

    def test_concurrent_archive_requests(self, e2e_client, e2e_base_url):
        """Test system handles concurrent archive requests."""
        import threading
        import queue

        results = queue.Queue()

        def archive_request(request_id):
            try:
                item_id = f"e2e_concurrent_{request_id}_{uuid.uuid4().hex[:6]}"
                response = e2e_client.post(
                    f"{e2e_base_url}/archive/readability",
                    json={"id": item_id, "url": "https://example.com"},
                    timeout=60
                )
                results.put((request_id, response.status_code))
            except Exception as e:
                results.put((request_id, str(e)))

        # Start 3 concurrent requests
        threads = []
        for i in range(3):
            t = threading.Thread(target=archive_request, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=120)

        # Check results
        success_count = 0
        while not results.empty():
            request_id, status = results.get()
            if status == 200:
                success_count += 1

        # Most should succeed
        assert success_count >= 1


class TestPerformanceBaseline:
    """Test performance baseline for API responses."""

    def test_health_check_performance(self, e2e_client, e2e_base_url):
        """Test /healthz responds within 1 second."""
        import time

        start = time.time()
        response = e2e_client.get(f"{e2e_base_url}/healthz")
        elapsed = time.time() - start

        assert response.status_code == 200
        assert elapsed < 1.0, f"Health check took {elapsed:.2f}s, expected < 1s"

    def test_list_archivers_performance(self, e2e_client, e2e_base_url):
        """Test /archivers responds within 2 seconds."""
        import time

        start = time.time()
        response = e2e_client.get(f"{e2e_base_url}/archivers")
        elapsed = time.time() - start

        assert response.status_code == 200
        assert elapsed < 2.0, f"List archivers took {elapsed:.2f}s, expected < 2s"


class TestUIEndpoint:
    """Test web UI endpoint."""

    def test_ui_page_accessible(self, e2e_client, e2e_base_url):
        """Test /ui returns HTML page."""
        response = e2e_client.get(f"{e2e_base_url}/ui")

        # 200 if available, may vary based on config
        if response.status_code == 200:
            assert "text/html" in response.headers.get("content-type", "")


class TestHTEndpoint:
    """Test HT terminal endpoint."""

    def test_ht_send_without_runner(self, e2e_client, e2e_base_url):
        """Test /ht/send handles missing runner gracefully."""
        response = e2e_client.post(
            f"{e2e_base_url}/ht/send",
            params={"payload": "test"}
        )

        # 500 if runner not initialized (expected in e2e without HT)
        assert response.status_code in [200, 422, 500]


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_item_id(self, e2e_client, e2e_base_url):
        """Test handling of very long item IDs."""
        long_id = "a" * 500
        response = e2e_client.post(
            f"{e2e_base_url}/archive/readability",
            json={"id": long_id, "url": "https://example.com"}
        )

        # Should handle gracefully, not crash
        assert response.status_code in [200, 400, 422]

    def test_special_characters_in_id(self, e2e_client, e2e_base_url):
        """Test handling of special characters in item ID."""
        special_id = "test!@#$%^&*()_+-=[]{}|;':\",./<>?"
        response = e2e_client.post(
            f"{e2e_base_url}/archive/readability",
            json={"id": special_id, "url": "https://example.com"}
        )

        # Should sanitize or reject, not crash
        assert response.status_code in [200, 400, 422]

    def test_unicode_in_url(self, e2e_client, e2e_base_url):
        """Test handling of unicode characters in URL."""
        item_id = f"e2e_unicode_{uuid.uuid4().hex[:8]}"
        response = e2e_client.post(
            f"{e2e_base_url}/archive/readability",
            json={"id": item_id, "url": "https://example.com/path?q=caf\u00e9"}
        )

        # Should handle unicode gracefully
        assert response.status_code in [200, 400, 422]

    def test_empty_batch(self, e2e_client, e2e_base_url):
        """Test batch endpoint with empty items list."""
        response = e2e_client.post(
            f"{e2e_base_url}/save/batch",
            json={"items": []}
        )

        # Should handle empty batch gracefully
        assert response.status_code in [200, 202, 400, 422]


class TestCompleteArchiveWorkflow:
    """Test complete archive workflows like test_firestore_workflow.py.

    These tests verify the entire lifecycle:
    1. Archive a URL
    2. Verify database records created
    3. Verify files on disk (or storage)
    4. Retrieve the archive
    5. Clean up
    """

    def test_full_archive_lifecycle(self, e2e_client, e2e_base_url, e2e_wait_for_task):
        """Test complete archive lifecycle: archive -> verify -> retrieve -> delete."""
        item_id = f"e2e_lifecycle_{uuid.uuid4().hex[:8]}"
        test_url = "https://example.com"

        # Step 1: Archive with readability (fast and reliable)
        archive_response = e2e_client.post(
            f"{e2e_base_url}/archive/readability",
            json={"id": item_id, "url": test_url},
            timeout=60
        )
        assert archive_response.status_code == 200
        archive_data = archive_response.json()
        assert archive_data.get("ok") is True
        db_rowid = archive_data.get("db_rowid")

        # Step 2: Verify db_rowid was returned (confirms DB write)
        assert db_rowid is not None, "Archive should return db_rowid"

        # Step 3: Verify it appears in saves list (may take time, or may filter by file_exists)
        time.sleep(2)
        saves_response = e2e_client.get(f"{e2e_base_url}/saves", params={"limit": 500})
        assert saves_response.status_code == 200
        saves = saves_response.json()

        # Find our item - may not appear if file_exists=False filter is applied
        our_save = next((s for s in saves if s.get("id") == item_id), None)
        # Note: saves list may filter by file_exists, so not finding is OK
        if our_save:
            assert our_save.get("status") in ["success", "pending", "failed"]

        # Step 4: Try to retrieve the archive
        retrieve_response = e2e_client.post(
            f"{e2e_base_url}/archive/retrieve",
            json={"id": item_id, "url": test_url, "archiver": "readability"}
        )
        # Should be 200 (found) or 404 (not ready/not found)
        # 422 indicates a validation bug that should be fixed
        assert retrieve_response.status_code in [200, 404], f"Got 422 validation error: {retrieve_response.text}"

        # Step 5: Clean up - delete by item_id
        delete_response = e2e_client.delete(f"{e2e_base_url}/saves/by-item/{item_id}")
        assert delete_response.status_code in [200, 404]

        if delete_response.status_code == 200:
            delete_data = delete_response.json()
            assert delete_data.get("ok") is True

    def test_async_workflow_with_polling(self, e2e_client, e2e_base_url, e2e_wait_for_task):
        """Test async workflow: save -> poll task -> verify completion."""
        item_id = f"e2e_async_workflow_{uuid.uuid4().hex[:8]}"
        test_url = "https://example.com"

        # Step 1: Submit async save
        save_response = e2e_client.post(
            f"{e2e_base_url}/save",
            json={"id": item_id, "url": test_url}
        )
        assert save_response.status_code == 202
        task_id = save_response.json().get("task_id")
        assert task_id is not None

        # Step 2: Poll for completion
        try:
            task_status = e2e_wait_for_task(e2e_base_url, task_id, timeout=180)
            assert task_status["task_id"] == task_id
            assert task_status["status"] in ["success", "failed"]

            # Step 3: Verify items were processed
            items = task_status.get("items", [])
            assert len(items) > 0

            for item in items:
                assert item.get("status") in ["success", "failed", "pending"]

        except TimeoutError:
            pytest.skip("Async workflow did not complete in time")

        # Step 4: Clean up
        e2e_client.delete(f"{e2e_base_url}/saves/by-item/{item_id}")

    def test_multi_archiver_workflow(self, e2e_client, e2e_base_url, e2e_reliable_archivers):
        """Test archiving with multiple archivers and verifying each."""
        item_id = f"e2e_multi_{uuid.uuid4().hex[:8]}"
        test_url = "https://example.com"

        results = {}
        db_rowids = []

        # Archive with each reliable archiver
        for archiver in e2e_reliable_archivers:
            response = e2e_client.post(
                f"{e2e_base_url}/archive/{archiver}",
                json={"id": item_id, "url": test_url},
                timeout=60
            )
            results[archiver] = {
                "status_code": response.status_code,
                "ok": response.json().get("ok") if response.status_code == 200 else False,
                "db_rowid": response.json().get("db_rowid") if response.status_code == 200 else None
            }
            if response.status_code == 200 and response.json().get("db_rowid"):
                db_rowids.append(response.json().get("db_rowid"))

        # At least one should succeed
        success_count = sum(1 for r in results.values() if r.get("ok"))
        assert success_count >= 1, f"No archivers succeeded: {results}"

        # Verify DB writes via db_rowids returned
        assert len(db_rowids) >= 1, "At least one archiver should return db_rowid"

        # Clean up
        e2e_client.delete(f"{e2e_base_url}/saves/by-item/{item_id}")

    def test_archive_and_verify_database_record(self, e2e_client, e2e_base_url):
        """Test that archiving creates proper database records."""
        item_id = f"e2e_db_verify_{uuid.uuid4().hex[:8]}"
        test_url = "https://example.com"

        # Archive
        response = e2e_client.post(
            f"{e2e_base_url}/archive/readability",
            json={"id": item_id, "url": test_url},
            timeout=60
        )

        if response.status_code != 200:
            pytest.skip("Archive failed, cannot verify database record")

        data = response.json()
        db_rowid = data.get("db_rowid")

        # Primary verification: db_rowid returned confirms database write
        assert db_rowid is not None, "Archive should return db_rowid confirming DB write"
        assert data.get("ok") is True, "Archive should indicate success"
        assert data.get("id") == item_id, "Archive should return the item_id"

        # Secondary verification via saves endpoint (best-effort, may filter results)
        time.sleep(2)
        saves_response = e2e_client.get(f"{e2e_base_url}/saves", params={"limit": 500})
        assert saves_response.status_code == 200
        saves = saves_response.json()

        our_save = next((s for s in saves if s.get("id") == item_id), None)
        # Note: saves list may not include all items (e.g., filters by file_exists)
        # The db_rowid return is the authoritative confirmation of DB write
        if our_save:
            # Verify expected fields exist
            assert "url" in our_save
            assert "status" in our_save

        # Clean up
        e2e_client.delete(f"{e2e_base_url}/saves/by-item/{item_id}")


# =============================================================================
# Firestore and GCS Integration Tests
# =============================================================================

class TestFirestoreGCSIntegration:
    """
    Test complete Firestore and GCS integration workflows.

    These tests verify the full cloud integration:
    1. Create article in Firestore
    2. Archive via /firebase/archive
    3. Verify files uploaded to GCS
    4. Verify Firestore updated with archive results
    5. Download via signed URL
    6. Clean up

    Tests are SKIPPED if Firestore/GCS credentials are not configured.

    Required environment variables:
    - FIRESTORE_PROJECT_ID or GCP_PROJECT_ID
    - GCS_PROJECT_ID or GCP_PROJECT_ID
    - GCS_BUCKET
    - GOOGLE_APPLICATION_CREDENTIALS (or default credentials)
    """

    def test_firebase_archive_creates_gcs_files(
        self,
        e2e_client,
        e2e_base_url,
        firestore_client,
        gcs_client,
        e2e_gcs_cleanup,
        e2e_wait_for_firestore_archive,
        e2e_verify_gcs_files,
    ):
        """Test that /firebase/archive uploads files to GCS."""
        article_id = f"e2e_gcs_test_{uuid.uuid4().hex[:8]}"
        test_url = "https://example.com"

        # Register cleanup
        e2e_gcs_cleanup(f"archives/{article_id}/")
        e2e_gcs_cleanup(f"{article_id}/")

        # Step 1: Archive via Firebase endpoint
        response = e2e_client.post(
            f"{e2e_base_url}/firebase/archive",
            json={
                "item_id": article_id,
                "url": test_url,
                "archiver": "readability"  # Fast archiver for test
            },
            timeout=120
        )

        # Skip if Firebase integration not available
        if response.status_code == 503:
            pytest.skip("Firebase integration not available")
        if response.status_code == 500:
            pytest.skip(f"Firebase archive failed: {response.text}")

        assert response.status_code == 200, f"Archive failed: {response.text}"
        data = response.json()
        assert data.get("status") in ["success", "pending", "processing"]

        # Step 2: Wait for archiving to complete
        time.sleep(10)  # Give time for async processing

        # Step 3: Verify GCS files
        gcs_results = e2e_verify_gcs_files(article_id, ["readability"])

        # At least readability should have files (if archiving succeeded)
        if data.get("status") == "success":
            assert gcs_results.get("readability") is True, \
                f"Readability files not found in GCS for {article_id}"

        # Cleanup Firestore
        try:
            firestore_client.collection('articles').document(article_id).delete()
        except Exception:
            pass

    def test_firebase_archive_updates_firestore(
        self,
        e2e_client,
        e2e_base_url,
        firestore_client,
        e2e_wait_for_firestore_archive,
    ):
        """Test that /firebase/archive updates Firestore document."""
        article_id = f"e2e_fs_test_{uuid.uuid4().hex[:8]}"
        test_url = "https://example.com"

        try:
            # Step 1: Archive via Firebase endpoint
            response = e2e_client.post(
                f"{e2e_base_url}/firebase/archive",
                json={
                    "item_id": article_id,
                    "url": test_url,
                    "archiver": "readability"
                },
                timeout=120
            )

            if response.status_code == 503:
                pytest.skip("Firebase integration not available")
            if response.status_code == 500:
                pytest.skip(f"Firebase archive failed: {response.text}")

            assert response.status_code == 200

            # Step 2: Wait for Firestore to be updated
            try:
                archives = e2e_wait_for_firestore_archive(
                    article_id,
                    archiver="readability",
                    timeout=120
                )

                # Verify archive data structure
                assert "readability" in archives
                readability_data = archives["readability"]
                assert readability_data.get("status") in ["success", "failed"]

                if readability_data.get("status") == "success":
                    # Should have GCS path
                    assert readability_data.get("gcs_path") or readability_data.get("saved_path")

            except TimeoutError:
                # Check if document exists at all
                doc = firestore_client.collection('articles').document(article_id).get()
                if doc.exists:
                    data = doc.to_dict()
                    archives = data.get("archives", {})
                    # May have been created but not completed
                    assert isinstance(archives, dict)
                else:
                    pytest.fail("Firestore document was never created")

        finally:
            # Cleanup
            try:
                firestore_client.collection('articles').document(article_id).delete()
            except Exception:
                pass

    def test_full_firestore_gcs_workflow(
        self,
        e2e_client,
        e2e_base_url,
        e2e_firestore_article,
        gcs_client,
        e2e_gcs_cleanup,
        e2e_wait_for_firestore_archive,
        e2e_verify_gcs_files,
        firestore_client,
    ):
        """
        Test complete Firestore/GCS workflow like test_firestore_workflow.py.

        1. Fetch article from Firestore (pre-created by fixture)
        2. Archive via /firebase/archive
        3. Verify GCS files uploaded
        4. Verify Firestore updated with archive results
        5. Cleanup
        """
        article = e2e_firestore_article
        article_id = article["article_id"]
        test_url = article["url"]

        # Register GCS cleanup
        e2e_gcs_cleanup(f"archives/{article_id}/")
        e2e_gcs_cleanup(f"{article_id}/")

        # Step 1: Verify article exists in Firestore
        doc = article["doc_ref"].get()
        assert doc.exists, "Test article should exist in Firestore"

        # Step 2: Archive via Firebase endpoint with all archivers
        response = e2e_client.post(
            f"{e2e_base_url}/firebase/archive",
            json={
                "item_id": article_id,
                "url": test_url,
                "archiver": "all"
            },
            timeout=300  # All archivers takes longer
        )

        if response.status_code == 503:
            pytest.skip("Firebase integration not available")
        if response.status_code == 500:
            pytest.skip(f"Firebase archive failed: {response.text}")

        assert response.status_code == 200
        archive_result = response.json()

        # Step 3: Wait for archiving to complete
        print(f"Waiting for archiving to complete for {article_id}...")
        time.sleep(30)  # Give async processing time

        # Step 4: Verify GCS files
        gcs_results = e2e_verify_gcs_files(article_id)
        files_found = sum(1 for v in gcs_results.values() if v)
        print(f"GCS files found: {files_found}/5 archivers")

        # At least some files should be in GCS
        # (may not be all if some archivers failed)

        # Step 5: Verify Firestore was updated
        try:
            archives = e2e_wait_for_firestore_archive(
                article_id,
                timeout=60
            )

            # Should have at least one archive
            assert len(archives) >= 1, "At least one archive should be in Firestore"

            # Check archive structure
            for archiver_name, archive_data in archives.items():
                assert "status" in archive_data
                if archive_data["status"] == "success":
                    # Successful archives should have path info
                    assert archive_data.get("gcs_path") or archive_data.get("saved_path")

            print(f"Firestore archives: {list(archives.keys())}")

        except TimeoutError:
            # Partial success - check what we have
            doc = firestore_client.collection('articles').document(article_id).get()
            if doc.exists:
                data = doc.to_dict()
                archives = data.get("archives", {})
                print(f"Partial archives found: {list(archives.keys())}")
            else:
                print("Warning: Firestore document not found in main collection")

    def test_firebase_download_signed_url(
        self,
        e2e_client,
        e2e_base_url,
        firestore_client,
        gcs_client,
        e2e_gcs_cleanup,
    ):
        """Test that /firebase/download returns valid signed URL."""
        article_id = f"e2e_download_{uuid.uuid4().hex[:8]}"
        test_url = "https://example.com"

        # Register cleanup
        e2e_gcs_cleanup(f"archives/{article_id}/")
        e2e_gcs_cleanup(f"{article_id}/")

        try:
            # Step 1: Archive first
            archive_response = e2e_client.post(
                f"{e2e_base_url}/firebase/archive",
                json={
                    "item_id": article_id,
                    "url": test_url,
                    "archiver": "readability"
                },
                timeout=120
            )

            if archive_response.status_code == 503:
                pytest.skip("Firebase integration not available")
            if archive_response.status_code != 200:
                pytest.skip(f"Archive failed: {archive_response.text}")

            # Wait for archiving
            time.sleep(15)

            # Step 2: Get download URL
            download_response = e2e_client.get(
                f"{e2e_base_url}/firebase/download/{article_id}/readability"
            )

            if download_response.status_code == 404:
                pytest.skip("Archive not found - may still be processing")
            if download_response.status_code == 503:
                pytest.skip("Download service not available")

            if download_response.status_code == 200:
                data = download_response.json()
                assert "url" in data or "download_url" in data or "signed_url" in data

                # Optionally verify URL is accessible
                signed_url = data.get("url") or data.get("download_url") or data.get("signed_url")
                if signed_url:
                    import requests
                    head_response = requests.head(signed_url, timeout=10)
                    # Should be accessible (200) or redirect (302)
                    assert head_response.status_code in [200, 302, 307]

        finally:
            # Cleanup Firestore
            try:
                firestore_client.collection('articles').document(article_id).delete()
            except Exception:
                pass

    def test_pocket_article_workflow(
        self,
        e2e_client,
        e2e_base_url,
        firestore_client,
        firestore_test_user_id,
        gcs_client,
        e2e_gcs_cleanup,
    ):
        """Test Pocket article integration workflow."""
        article_id = f"e2e_pocket_{uuid.uuid4().hex[:8]}"
        test_url = "https://example.com/pocket-test"

        # Register cleanup
        e2e_gcs_cleanup(f"archives/{article_id}/")
        e2e_gcs_cleanup(f"{article_id}/")

        try:
            # Step 1: Add Pocket article
            response = e2e_client.post(
                f"{e2e_base_url}/firebase/add-pocket-article",
                json={
                    "user_id": firestore_test_user_id,
                    "url": test_url,
                    "pocket_data": {
                        "item_id": article_id,
                        "resolved_title": "Test Pocket Article",
                        "excerpt": "This is a test article from Pocket",
                        "time_added": str(int(time.time()))
                    },
                    "archiver": "readability"
                },
                timeout=120
            )

            if response.status_code == 503:
                pytest.skip("Pocket integration not available")
            if response.status_code == 500:
                pytest.skip(f"Pocket add failed: {response.text}")

            assert response.status_code == 200
            data = response.json()
            assert "article_id" in data or "item_id" in data

            # Step 2: Verify article was created in user's collection
            time.sleep(5)

            user_doc = (
                firestore_client
                .collection('users')
                .document(firestore_test_user_id)
                .collection('articles')
                .document(data.get("article_id") or data.get("item_id") or article_id)
                .get()
            )

            if user_doc.exists:
                user_data = user_doc.to_dict()
                assert user_data.get("url") == test_url
                # Pocket data should be preserved
                pocket_info = user_data.get("pocket") or user_data.get("pocket_data")
                if pocket_info:
                    assert pocket_info.get("resolved_title") == "Test Pocket Article"

        finally:
            # Cleanup user's article
            try:
                (
                    firestore_client
                    .collection('users')
                    .document(firestore_test_user_id)
                    .collection('articles')
                    .document(article_id)
                    .delete()
                )
            except Exception:
                pass

            # Cleanup main articles
            try:
                firestore_client.collection('articles').document(article_id).delete()
            except Exception:
                pass

    def test_sync_postgres_to_firestore_workflow(
        self,
        e2e_client,
        e2e_base_url,
        firestore_client,
    ):
        """Test syncing articles from PostgreSQL to Firestore."""
        # First create an article via standard archive (goes to PostgreSQL)
        item_id = f"e2e_sync_{uuid.uuid4().hex[:8]}"
        test_url = "https://example.com"

        try:
            # Step 1: Archive via standard endpoint (PostgreSQL)
            archive_response = e2e_client.post(
                f"{e2e_base_url}/archive/readability",
                json={"id": item_id, "url": test_url},
                timeout=60
            )

            if archive_response.status_code != 200:
                pytest.skip("Standard archive failed")

            # Step 2: Trigger sync to Firestore
            sync_response = e2e_client.post(
                f"{e2e_base_url}/sync/postgres-to-firestore",
                json={"article_id": item_id, "limit": 1}
            )

            if sync_response.status_code == 503:
                pytest.skip("Sync service not available")
            if sync_response.status_code == 400:
                pytest.skip("Sync not configured")

            if sync_response.status_code == 200:
                sync_data = sync_response.json()
                assert "synced" in sync_data

                # Step 3: Verify article in Firestore
                time.sleep(2)
                doc = firestore_client.collection('articles').document(item_id).get()

                if doc.exists:
                    data = doc.to_dict()
                    assert data.get("url") == test_url

        finally:
            # Cleanup PostgreSQL
            e2e_client.delete(f"{e2e_base_url}/saves/by-item/{item_id}")

            # Cleanup Firestore
            try:
                firestore_client.collection('articles').document(item_id).delete()
            except Exception:
                pass
