"""
End-to-end test configuration and fixtures.

E2E tests run against a full HTBase system using Docker Compose with
real PostgreSQL, actual archiver binaries, and complete system integration.
"""

import os
import time
import pytest
import requests
from pathlib import Path
from typing import Generator, Dict, Any

# Test URLs that should be consistently available
TEST_URLS = [
    "https://httpbin.org/html",  # Simple HTML page
    "https://www.iana.org/help/example-domains",   # JSON response
    "https://example.com",        # Basic HTML
    "https://www.iana.org/numbers",  # Text file
]


@pytest.fixture(scope="session")
def e2e_settings() -> Dict[str, Any]:
    """Get E2E test settings from environment."""
    return {
        "base_url": os.getenv("HTBASE_E2E_BASE_URL", "http://localhost:8000"),
        "timeout": int(os.getenv("HTBASE_E2E_TIMEOUT", "60")),
        "retry_attempts": int(os.getenv("HTBASE_E2E_RETRY_ATTEMPTS", "3")),
        "docker_compose_file": os.getenv("HTBASE_E2E_DOCKER_COMPOSE", "docker-compose.e2e.yml"),
    }


@pytest.fixture(scope="session")
def e2e_session() -> requests.Session:
    """Create requests session for E2E tests."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "HTBase-E2E-Tests/1.0",
        "Content-Type": "application/json"
    })
    return session


@pytest.fixture(scope="session")
def htbase_service(e2e_settings) -> Generator[Dict[str, Any], None, None]:
    """Ensure HTBase service is running and healthy."""
    base_url = e2e_settings["base_url"]
    timeout = e2e_settings["timeout"]

    # Wait for service to be ready - use /healthz (the actual endpoint)
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{base_url}/healthz", timeout=5)
            if response.status_code == 200:
                print(f"HTBase service is ready at {base_url}")
                yield {
                    "base_url": base_url,
                    "healthy": True,
                    "startup_time": time.time() - start_time
                }
                return
        except requests.exceptions.RequestException:
            time.sleep(2)
            continue

    pytest.fail(f"HTBase service not ready after {timeout} seconds at {base_url}")


@pytest.fixture(scope="session")
def docker_compose_setup(e2e_settings) -> Generator[None, None, None]:
    """Set up and tear down Docker Compose environment if needed."""
    # This fixture would handle Docker Compose setup
    # For now, assume services are already running
    yield


@pytest.fixture
def e2e_client(e2e_session, htbase_service):
    """Create HTTP client for E2E tests."""
    return e2e_session


@pytest.fixture
def e2e_base_url(htbase_service):
    """Get base URL for E2E tests."""
    return htbase_service["base_url"]


@pytest.fixture
def e2e_sample_items():
    """Sample items for E2E testing."""
    return [
        {
            "item_id": "e2e_test_001",
            "url": "https://httpbin.org/html",
            "expected_content": ["Herman Melville", "Moby-Dick"]
        },
        {
            "item_id": "e2e_test_002",
            "url": "https://example.com",
            "expected_content": ["Example Domain"]
        },
        {
            "item_id": "e2e_test_003",
            "url": "https://httpbin.org/robots.txt",
            "expected_content": ["User-agent", "Disallow"]
        }
    ]


@pytest.fixture
def e2e_test_archivers():
    """List of archivers to test in E2E - all 5 production archivers."""
    return ["readability", "monolith", "singlefile-cli", "screenshot", "pdf"]


@pytest.fixture
def e2e_reliable_archivers():
    """Subset of archivers that are most reliable for quick tests."""
    return ["monolith", "readability"]


@pytest.fixture
def e2e_temp_directory():
    """Create temporary directory for E2E test artifacts."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def e2e_wait_for_completion():
    """Helper to wait for archiving completion."""
    def _wait_for_completion(item_id: str, archiver: str, timeout: int = 60):
        """Wait for archiving to complete and return artifact info."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    f"{os.getenv('HTBASE_E2E_BASE_URL', 'http://localhost:8000')}"
                    f"/admin/saves?item_id={item_id}&archiver={archiver}",
                    timeout=5
                )
                if response.status_code == 200:
                    saves = response.json()
                    if saves:
                        save = saves[0]
                        if save.get("status") in ["success", "failed"]:
                            return save
            except requests.exceptions.RequestException:
                pass

            time.sleep(2)

        raise TimeoutError(f"Archiving did not complete within {timeout} seconds")

    return _wait_for_completion


@pytest.fixture
def e2e_cleanup_data():
    """Helper to clean up test data after tests."""
    def _cleanup_data(item_id: str = None, archiver: str = None):
        """Clean up test data."""
        base_url = os.getenv('HTBASE_E2E_BASE_URL', 'http://localhost:8000')

        try:
            if item_id and archiver:
                # Delete specific artifact
                response = requests.delete(
                    f"{base_url}/admin/saves/by-item/{item_id}",
                    timeout=10
                )
                return response.status_code in [200, 404]
        except requests.exceptions.RequestException:
            return False

        return True

    return _cleanup_data


@pytest.fixture(autouse=True)
def e2e_isolation():
    """Ensure test isolation and cleanup."""
    yield
    # Cleanup would happen here in a real implementation
    pass


@pytest.fixture
def e2e_archival_health_check():
    """Check if archiving binaries are available and working."""
    def _check_archiver_health(archiver: str) -> bool:
        """Check if specific archiver is healthy."""
        try:
            # This would test actual archiver availability
            # For now, assume archivers are available in Docker environment
            return archiver in ["monolith", "readability"]
        except Exception:
            return False

    return _check_archiver_health


@pytest.fixture
def e2e_metrics_collector():
    """Collect metrics during E2E tests."""
    import psutil
    import threading
    from collections import defaultdict

    class MetricsCollector:
        def __init__(self):
            self.metrics = defaultdict(list)
            self.collecting = False
            self.thread = None

        def start_collection(self):
            """Start collecting metrics."""
            self.collecting = True
            self.thread = threading.Thread(target=self._collect_loop)
            self.thread.start()

        def stop_collection(self):
            """Stop collecting metrics."""
            self.collecting = False
            if self.thread:
                self.thread.join()

        def _collect_loop(self):
            """Main collection loop."""
            while self.collecting:
                try:
                    # Collect system metrics
                    cpu_percent = psutil.cpu_percent()
                    memory = psutil.virtual_memory()

                    self.metrics["cpu"].append(cpu_percent)
                    self.metrics["memory"].append(memory.percent)
                    self.metrics["timestamp"].append(time.time())

                    time.sleep(1)
                except Exception:
                    break

        def get_summary(self):
            """Get metrics summary."""
            summary = {}
            for key, values in self.metrics.items():
                if values and key != "timestamp":
                    summary[key] = {
                        "min": min(values),
                        "max": max(values),
                        "avg": sum(values) / len(values),
                        "count": len(values)
                    }
            return summary

    collector = MetricsCollector()

    yield collector

    # Ensure collection is stopped
    collector.stop_collection()


@pytest.fixture
def e2e_performance_thresholds():
    """Performance thresholds for E2E tests."""
    return {
        "max_archival_time": 120,  # seconds
        "max_api_response_time": 5,  # seconds
        "max_memory_usage": 80,  # percent
        "max_cpu_usage": 90,  # percent
        "min_success_rate": 0.9,  # 90% success rate
    }


@pytest.fixture
def e2e_retry_mechanism():
    """Retry mechanism for flaky E2E operations."""
    def _retry_operation(func, max_attempts: int = 3, delay: float = 1.0):
        """Retry an operation with exponential backoff."""
        for attempt in range(max_attempts):
            try:
                return func()
            except Exception as e:
                if attempt == max_attempts - 1:
                    raise

                wait_time = delay * (2 ** attempt)  # Exponential backoff
                time.sleep(wait_time)

        raise RuntimeError("All retry attempts failed")

    return _retry_operation


@pytest.fixture
def e2e_network_conditions():
    """Test various network conditions."""
    import contextlib

    @contextlib.contextmanager
    def _simulate_network_condition(condition: str):
        """Simulate network condition for testing."""
        # This would use tools like tc (traffic control) to simulate conditions
        # For now, it's a placeholder that documents the intention
        if condition == "slow":
            print("Simulating slow network...")
            yield
        elif condition == "unreliable":
            print("Simulating unreliable network...")
            yield
        else:
            yield

    return _simulate_network_condition


@pytest.fixture
def e2e_real_world_urls():
    """Real-world URLs that should work in E2E tests."""
    return [
        "https://httpbin.org/html",
        "https://example.com",
        "https://www.iana.org/help/example-domains",
    ]


@pytest.fixture
def e2e_wait_for_task():
    """Helper to wait for a task to complete by polling /tasks/{task_id}."""
    def _wait_for_task(base_url: str, task_id: str, timeout: int = 120) -> Dict[str, Any]:
        """
        Poll task status until completion or timeout.

        Returns:
            Task status response with items and overall status
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    f"{base_url}/tasks/{task_id}",
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status", "pending")
                    if status in ["success", "failed"]:
                        return data
                elif response.status_code == 404:
                    # Task not found yet, keep polling
                    pass
            except requests.exceptions.RequestException:
                pass

            time.sleep(2)

        raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds")

    return _wait_for_task


@pytest.fixture
def e2e_api_client():
    """Enhanced API client with helper methods for common operations."""
    class E2EAPIClient:
        def __init__(self, base_url: str):
            self.base_url = base_url
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": "HTBase-E2E-Tests/1.0",
                "Content-Type": "application/json"
            })

        def healthz(self) -> bool:
            """Check if service is healthy."""
            try:
                resp = self.session.get(f"{self.base_url}/healthz", timeout=5)
                return resp.status_code == 200
            except requests.exceptions.RequestException:
                return False

        def save(self, item_id: str, url: str) -> Dict[str, Any]:
            """Submit async save request via POST /save."""
            resp = self.session.post(
                f"{self.base_url}/save",
                json={"id": item_id, "url": url},
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()

        def save_batch(self, items: list) -> Dict[str, Any]:
            """Submit batch save request via POST /save/batch."""
            resp = self.session.post(
                f"{self.base_url}/save/batch",
                json={"items": items},
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()

        def archive(self, archiver: str, item_id: str, url: str) -> Dict[str, Any]:
            """Submit archive request via POST /archive/{archiver}."""
            resp = self.session.post(
                f"{self.base_url}/archive/{archiver}",
                json={"id": item_id, "url": url},
                timeout=60
            )
            resp.raise_for_status()
            return resp.json()

        def archive_batch(self, archiver: str, items: list) -> Dict[str, Any]:
            """Submit batch archive request via POST /archive/{archiver}/batch."""
            resp = self.session.post(
                f"{self.base_url}/archive/{archiver}/batch",
                json={"items": items},
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()

        def get_task_status(self, task_id: str) -> Dict[str, Any]:
            """Get task status via GET /tasks/{task_id}."""
            resp = self.session.get(
                f"{self.base_url}/tasks/{task_id}",
                timeout=10
            )
            resp.raise_for_status()
            return resp.json()

        def list_saves(self, limit: int = 100, offset: int = 0) -> list:
            """List saves via GET /saves."""
            resp = self.session.get(
                f"{self.base_url}/saves",
                params={"limit": limit, "offset": offset},
                timeout=10
            )
            resp.raise_for_status()
            return resp.json()

        def list_archivers(self) -> list:
            """List available archivers via GET /archivers."""
            resp = self.session.get(
                f"{self.base_url}/archivers",
                timeout=10
            )
            resp.raise_for_status()
            return resp.json()

        def retrieve(self, item_id: str = None, url: str = None, archiver: str = "all"):
            """Retrieve archived content via POST /archive/retrieve."""
            payload = {"archiver": archiver}
            if item_id:
                payload["id"] = item_id
            if url:
                payload["url"] = url
            resp = self.session.post(
                f"{self.base_url}/archive/retrieve",
                json=payload,
                timeout=30
            )
            return resp

        def delete_by_item(self, item_id: str, remove_files: bool = False) -> Dict[str, Any]:
            """Delete saves by item_id via DELETE /saves/by-item/{item_id}."""
            resp = self.session.delete(
                f"{self.base_url}/saves/by-item/{item_id}",
                params={"remove_files": remove_files},
                timeout=10
            )
            if resp.status_code == 404:
                return {"deleted_count": 0, "ok": True}
            resp.raise_for_status()
            return resp.json()

        def delete_by_url(self, url: str, remove_files: bool = False) -> Dict[str, Any]:
            """Delete saves by URL via DELETE /saves/by-url."""
            resp = self.session.delete(
                f"{self.base_url}/saves/by-url",
                params={"url": url, "remove_files": remove_files},
                timeout=10
            )
            if resp.status_code == 404:
                return {"deleted_count": 0, "ok": True}
            resp.raise_for_status()
            return resp.json()

        def requeue(self, artifact_ids: list = None, status: str = None, include_all: bool = False) -> Dict[str, Any]:
            """Requeue failed/pending saves via POST /saves/requeue."""
            payload = {"include_all": include_all}
            if artifact_ids:
                payload["artifact_ids"] = artifact_ids
            if status:
                payload["status"] = status
            resp = self.session.post(
                f"{self.base_url}/saves/requeue",
                json=payload,
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()

        def summarize(self, rowid: int = None, item_id: str = None, url: str = None) -> Dict[str, Any]:
            """Trigger summarization via POST /summarize."""
            payload = {}
            if rowid:
                payload["rowid"] = rowid
            if item_id:
                payload["item_id"] = item_id
            if url:
                payload["url"] = url
            resp = self.session.post(
                f"{self.base_url}/summarize",
                json=payload,
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()

        def get_archive_size(self, archived_url_id: int) -> Dict[str, Any]:
            """Get archive size via GET /archive/{archived_url_id}/size."""
            resp = self.session.get(
                f"{self.base_url}/archive/{archived_url_id}/size",
                timeout=10
            )
            resp.raise_for_status()
            return resp.json()

        # Command history endpoints
        def list_executions(self, archived_url_id: int = None, archiver: str = None, limit: int = 100) -> list:
            """List command executions via GET /commands/executions."""
            params = {"limit": limit}
            if archived_url_id:
                params["archived_url_id"] = archived_url_id
            if archiver:
                params["archiver"] = archiver
            resp = self.session.get(
                f"{self.base_url}/commands/executions",
                params=params,
                timeout=10
            )
            resp.raise_for_status()
            return resp.json()

        def get_execution_detail(self, execution_id: int) -> Dict[str, Any]:
            """Get execution detail via GET /commands/executions/{id}."""
            resp = self.session.get(
                f"{self.base_url}/commands/executions/{execution_id}",
                timeout=10
            )
            resp.raise_for_status()
            return resp.json()

        # Firebase endpoints
        def firebase_add_pocket_article(self, user_id: str, url: str, pocket_data: dict = None, archiver: str = "all") -> Dict[str, Any]:
            """Add Pocket article via POST /firebase/add-pocket-article."""
            resp = self.session.post(
                f"{self.base_url}/firebase/add-pocket-article",
                json={
                    "user_id": user_id,
                    "url": url,
                    "pocket_data": pocket_data or {},
                    "archiver": archiver
                },
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()

        def firebase_download_url(self, item_id: str, archiver: str, expiration_hours: int = 24) -> Dict[str, Any]:
            """Get download URL via GET /firebase/download/{item_id}/{archiver}."""
            resp = self.session.get(
                f"{self.base_url}/firebase/download/{item_id}/{archiver}",
                params={"expiration_hours": expiration_hours},
                timeout=10
            )
            resp.raise_for_status()
            return resp.json()

        def firebase_save(self, url: str, archiver: str = "all", metadata: dict = None) -> Dict[str, Any]:
            """Save article via POST /firebase/save."""
            resp = self.session.post(
                f"{self.base_url}/firebase/save",
                json={
                    "url": url,
                    "archiver": archiver,
                    "metadata": metadata or {}
                },
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()

        def firebase_archive(self, item_id: str, url: str, archiver: str = "all") -> Dict[str, Any]:
            """Archive article via POST /firebase/archive."""
            resp = self.session.post(
                f"{self.base_url}/firebase/archive",
                json={
                    "item_id": item_id,
                    "url": url,
                    "archiver": archiver
                },
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()

        # Sync endpoints
        def sync_postgres_to_firestore(self, article_id: str = None, limit: int = 100) -> Dict[str, Any]:
            """Sync PostgreSQL to Firestore via POST /sync/postgres-to-firestore."""
            payload = {"limit": limit}
            if article_id:
                payload["article_id"] = article_id
            resp = self.session.post(
                f"{self.base_url}/sync/postgres-to-firestore",
                json=payload,
                timeout=60
            )
            resp.raise_for_status()
            return resp.json()

        def sync_firestore_to_postgres(self, item_id: str) -> Dict[str, Any]:
            """Sync Firestore to PostgreSQL via POST /sync/firestore-to-postgres."""
            resp = self.session.post(
                f"{self.base_url}/sync/firestore-to-postgres",
                json={"item_id": item_id},
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()

    def _create_client(base_url: str) -> E2EAPIClient:
        return E2EAPIClient(base_url)

    return _create_client


# =============================================================================
# Firestore and GCS Integration Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def firestore_client():
    """
    Create Firestore client for integration tests.

    Requires:
    - GOOGLE_APPLICATION_CREDENTIALS or FIRESTORE_PROJECT_ID env var
    - Valid GCP credentials

    Skips tests if Firestore is not available.
    """
    try:
        from google.cloud import firestore

        project_id = os.getenv('FIRESTORE_PROJECT_ID') or os.getenv('GCP_PROJECT_ID')
        if not project_id:
            pytest.skip("FIRESTORE_PROJECT_ID not set - skipping Firestore tests")

        client = firestore.Client(project=project_id)

        # Test connection by listing collections (will fail if not authenticated)
        try:
            list(client.collections())
        except Exception as e:
            pytest.skip(f"Firestore connection failed: {e}")

        yield client

    except ImportError:
        pytest.skip("google-cloud-firestore not installed")
    except Exception as e:
        pytest.skip(f"Firestore client creation failed: {e}")


@pytest.fixture(scope="session")
def gcs_client():
    """
    Create GCS client for integration tests.

    Requires:
    - GOOGLE_APPLICATION_CREDENTIALS or GCS_PROJECT_ID env var
    - GCS_BUCKET env var
    - Valid GCP credentials

    Skips tests if GCS is not available.
    """
    try:
        from google.cloud import storage

        project_id = os.getenv('GCS_PROJECT_ID') or os.getenv('GCP_PROJECT_ID')
        bucket_name = os.getenv('GCS_BUCKET')

        if not project_id:
            pytest.skip("GCS_PROJECT_ID not set - skipping GCS tests")
        if not bucket_name:
            pytest.skip("GCS_BUCKET not set - skipping GCS tests")

        client = storage.Client(project=project_id)
        bucket = client.bucket(bucket_name)

        # Test connection
        try:
            bucket.exists()
        except Exception as e:
            pytest.skip(f"GCS connection failed: {e}")

        yield {
            "client": client,
            "bucket": bucket,
            "bucket_name": bucket_name,
            "project_id": project_id
        }

    except ImportError:
        pytest.skip("google-cloud-storage not installed")
    except Exception as e:
        pytest.skip(f"GCS client creation failed: {e}")


@pytest.fixture
def firestore_test_user_id():
    """Get test user ID for Firestore tests."""
    return os.getenv('FIRESTORE_TEST_USER_ID', 'e2e_test_user')


@pytest.fixture
def firestore_test_collection():
    """Get test collection name for Firestore tests."""
    return os.getenv('FIRESTORE_TEST_COLLECTION', 'articles')


@pytest.fixture
def e2e_firestore_article(firestore_client, firestore_test_user_id):
    """
    Create a test article in Firestore and clean up after test.

    Yields:
        dict with article_id, user_id, url, and doc_ref
    """
    import uuid

    article_id = f"e2e_test_{uuid.uuid4().hex[:12]}"
    test_url = "https://example.com"

    # Create article in user's subcollection
    doc_ref = (
        firestore_client
        .collection('users')
        .document(firestore_test_user_id)
        .collection('articles')
        .document(article_id)
    )

    article_data = {
        "url": test_url,
        "title": "E2E Test Article",
        "created_at": time.time(),
        "status": "pending",
        "archives": {}
    }

    doc_ref.set(article_data)

    yield {
        "article_id": article_id,
        "user_id": firestore_test_user_id,
        "url": test_url,
        "doc_ref": doc_ref,
        "data": article_data
    }

    # Cleanup
    try:
        doc_ref.delete()
    except Exception:
        pass

    # Also cleanup from main articles collection if it was synced there
    try:
        main_ref = firestore_client.collection('articles').document(article_id)
        if main_ref.get().exists:
            main_ref.delete()
    except Exception:
        pass


@pytest.fixture
def e2e_gcs_cleanup(gcs_client):
    """
    Helper to clean up GCS files created during tests.

    Returns a function that takes a prefix and deletes all matching blobs.
    """
    prefixes_to_cleanup = []

    def _register_cleanup(prefix: str):
        """Register a prefix for cleanup after test."""
        prefixes_to_cleanup.append(prefix)

    yield _register_cleanup

    # Cleanup all registered prefixes
    bucket = gcs_client["bucket"]
    for prefix in prefixes_to_cleanup:
        try:
            blobs = list(bucket.list_blobs(prefix=prefix))
            for blob in blobs:
                try:
                    blob.delete()
                except Exception:
                    pass
        except Exception:
            pass


@pytest.fixture
def e2e_wait_for_firestore_archive(firestore_client):
    """
    Helper to wait for archive status in Firestore to update.

    Polls the Firestore document until archives field is updated.
    """
    def _wait_for_archive(
        article_id: str,
        archiver: str = None,
        timeout: int = 180,
        collection: str = "articles"
    ) -> Dict[str, Any]:
        """
        Wait for archive to appear in Firestore document.

        Args:
            article_id: The article ID to check
            archiver: Specific archiver to wait for (or None for any)
            timeout: Max wait time in seconds
            collection: Firestore collection to check

        Returns:
            The archives dict from Firestore
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                doc_ref = firestore_client.collection(collection).document(article_id)
                doc = doc_ref.get()

                if doc.exists:
                    data = doc.to_dict()
                    archives = data.get("archives", {})

                    if archiver:
                        # Wait for specific archiver
                        if archiver in archives:
                            archive_data = archives[archiver]
                            if archive_data.get("status") in ["success", "failed"]:
                                return archives
                    else:
                        # Wait for any archive with completed status
                        for arch_name, arch_data in archives.items():
                            if arch_data.get("status") in ["success", "failed"]:
                                return archives

            except Exception as e:
                print(f"Error checking Firestore: {e}")

            time.sleep(5)

        raise TimeoutError(f"Archive status not updated within {timeout} seconds")

    return _wait_for_archive


@pytest.fixture
def e2e_verify_gcs_files(gcs_client):
    """
    Helper to verify files exist in GCS.

    Returns a function that checks for files matching a pattern.
    """
    def _verify_files(item_id: str, archivers: list = None) -> Dict[str, bool]:
        """
        Verify files exist in GCS for the given item.

        Args:
            item_id: The item ID to check
            archivers: List of archivers to check (or None for all)

        Returns:
            Dict mapping archiver name to bool (True if files found)
        """
        if archivers is None:
            archivers = ["readability", "monolith", "singlefile-cli", "screenshot", "pdf"]

        bucket = gcs_client["bucket"]
        results = {}

        for archiver in archivers:
            # Check common path patterns
            prefixes = [
                f"archives/{item_id}/{archiver}/",
                f"{item_id}/{archiver}/",
            ]

            found = False
            for prefix in prefixes:
                try:
                    blobs = list(bucket.list_blobs(prefix=prefix, max_results=1))
                    if blobs:
                        found = True
                        break
                except Exception:
                    pass

            results[archiver] = found

        return results

    return _verify_files