from __future__ import annotations

import sys
from pathlib import Path
from typing import Generator, Dict, Any
from datetime import datetime
from unittest.mock import Mock, MagicMock

import pytest

# Ensure the application package is importable as a flat module set
_ROOT = Path(__file__).resolve().parents[1]
_APP = str(_ROOT / "app")
if _APP not in sys.path:
    sys.path.insert(0, _APP)


# Mock Firestore classes for testing
class MockDocument:
    """Mock Firestore document."""
    def __init__(self, data: Dict[str, Any] = None):
        self._data = data or {}

    def to_dict(self) -> Dict[str, Any]:
        return self._data

    def exists(self) -> bool:
        return bool(self._data)


class MockDocumentReference:
    """Mock Firestore document reference."""
    def __init__(self, collection_name: str, doc_id: str, storage: Dict):
        self.collection_name = collection_name
        self.doc_id = doc_id
        self._storage = storage

    def get(self) -> MockDocument:
        key = f"{self.collection_name}/{self.doc_id}"
        return MockDocument(self._storage.get(key))

    def set(self, data: Dict[str, Any], merge: bool = False):
        key = f"{self.collection_name}/{self.doc_id}"
        if merge and key in self._storage:
            self._storage[key].update(data)
        else:
            self._storage[key] = dict(data)

    def update(self, data: Dict[str, Any]):
        key = f"{self.collection_name}/{self.doc_id}"
        if key in self._storage:
            self._storage[key].update(data)
        else:
            self._storage[key] = dict(data)

    def delete(self):
        key = f"{self.collection_name}/{self.doc_id}"
        if key in self._storage:
            del self._storage[key]


class MockQuery:
    """Mock Firestore query."""
    def __init__(self, collection_name: str, storage: Dict, filters: Dict = None):
        self.collection_name = collection_name
        self._storage = storage
        self._filters = filters or {}

    def where(self, field: str, op: str, value: Any):
        """Add a filter to the query."""
        new_filters = self._filters.copy()
        new_filters[field] = (op, value)
        return MockQuery(self.collection_name, self._storage, new_filters)

    def limit(self, count: int):
        """Limit query results."""
        self._limit = count
        return self

    def stream(self):
        """Stream query results."""
        results = []
        for key, data in self._storage.items():
            if key.startswith(f"{self.collection_name}/"):
                # Apply filters
                match = True
                for field, (op, value) in self._filters.items():
                    if op == "==":
                        if data.get(field) != value:
                            match = False
                            break
                if match:
                    results.append(MockDocument(data))

        # Apply limit if set
        if hasattr(self, '_limit'):
            results = results[:self._limit]

        return iter(results)


class MockCollection:
    """Mock Firestore collection."""
    def __init__(self, collection_name: str, storage: Dict):
        self.collection_name = collection_name
        self._storage = storage

    def document(self, doc_id: str = None) -> MockDocumentReference:
        if doc_id is None:
            # Generate a random document ID
            import uuid
            doc_id = str(uuid.uuid4())
        return MockDocumentReference(self.collection_name, doc_id, self._storage)

    def where(self, field: str, op: str, value: Any):
        """Create a query with a filter."""
        return MockQuery(self.collection_name, self._storage).where(field, op, value)

    def limit(self, count: int):
        """Create a limited query."""
        return MockQuery(self.collection_name, self._storage).limit(count)

    def stream(self):
        """Stream all documents in collection."""
        return MockQuery(self.collection_name, self._storage).stream()


class MockFirestoreClient:
    """Mock Firestore client for testing."""
    def __init__(self):
        self._storage = {}

    def collection(self, collection_name: str) -> MockCollection:
        return MockCollection(collection_name, self._storage)


# Fixtures for repository tests
@pytest.fixture
def mock_firestore_client():
    """Provide a mock Firestore client."""
    return MockFirestoreClient()


@pytest.fixture
def article_repository(mock_firestore_client):
    """Provide an ArticleRepository with mock Firestore."""
    from shared.database.repositories import ArticleRepository
    return ArticleRepository(mock_firestore_client)


@pytest.fixture
def artifact_repository(mock_firestore_client):
    """Provide an ArtifactRepository with mock Firestore."""
    from shared.database.repositories import ArtifactRepository
    return ArtifactRepository(mock_firestore_client)


@pytest.fixture
def sample_article_data():
    """Provide sample article data for testing."""
    return {
        "item_id": "test-article-123",
        "url": "https://example.com/test-article",
        "title": "Test Article Title",
        "byline": "Test Author",
        "excerpt": "This is a test article excerpt",
    }


@pytest.fixture
def mock_celery_app():
    """Provide a mocked Celery app."""
    mock_app = Mock()
    mock_app.send_task = Mock(return_value=Mock(id="mock-task-id"))
    return mock_app


@pytest.fixture()
def temp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Configure app to use a temp data dir and disable ht runner
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "app.db"))
    monkeypatch.setenv("START_HT", "false")


@pytest.fixture()
def test_client(temp_env) -> Generator:
    # Import here so env vars apply before settings load
    from fastapi.testclient import TestClient
    import server

    client = TestClient(server.app)
    # Install dummy archiver to avoid external binaries
    from archivers.base import BaseArchiver
    from shared.config import get_settings
    from models import ArchiveResult
    from core.utils import sanitize_filename
    from task_manager import ArchiverTaskManager

    class DummyArchiver(BaseArchiver):
        name = "monolith"

        def archive(self, *, url: str, item_id: str) -> ArchiveResult:
            settings = get_settings()
            safe_item = sanitize_filename(item_id)
            out_dir = Path(settings.data_dir) / safe_item / self.name
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "output.html"
            out_path.write_text(f"<html><body>Dummy saved: {url}</body></html>", encoding="utf-8")
            return ArchiveResult(success=True, exit_code=0, saved_path=str(out_path))

    server.app.state.archivers = {"monolith": DummyArchiver(get_settings())}
    server.app.state.task_manager = ArchiverTaskManager(
        get_settings(),
        server.app.state.archivers,
        summarization=getattr(server.app.state, "summarization", None),
    )

    try:
        yield client
    finally:
        client.close()
