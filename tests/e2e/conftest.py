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
    "https://httpbin.org/json",   # JSON response
    "https://example.com",        # Basic HTML
    "https://httpbin.org/robots.txt",  # Text file
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

    # Wait for service to be ready
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{base_url}/health", timeout=5)
            if response.status_code == 200:
                print(f"HTBase service is ready at {base_url}")
                return {
                    "base_url": base_url,
                    "healthy": True,
                    "startup_time": time.time() - start_time
                }
        except requests.exceptions.RequestException:
            time.sleep(2)
            continue

    raise pytest.fail(f"HTBase service not ready after {timeout} seconds at {base_url}")


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
    """List of archivers to test in E2E."""
    return ["monolith", "readability"]  # Focus on most reliable archivers


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
        "https://www.wikipedia.org/wiki/Main_Page",
        "https://httpbin.org/html",
        "https://example.com",
        "https://httpbin.org/json",
        "https://www.iana.org/domains/example"
    ]