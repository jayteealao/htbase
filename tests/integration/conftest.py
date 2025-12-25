"""
Integration test configuration and fixtures.

Integration tests use real PostgreSQL database and test the interaction
between different components of the HTBase system.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock
import pytest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import AppSettings
from app.db.models import Base
from app.db.repositories import (
    ArchiveArtifactRepository,
    ArchivedUrlRepository,
    UrlMetadataRepository,
)
from app.task_manager.archiver import ArchiverTaskManager
from app.task_manager.summarization import SummarizationCoordinator, SummarizationTaskManager
from app.storage.file_storage import FileStorageProvider
from app.storage.local_file_storage import LocalFileStorage
from tests.fakes.storage import InMemoryFileStorage, InMemoryDatabaseStorage
from tests.fakes.task_manager import SyncTaskManager
from tests.fakes.archivers import DummyArchiver
from tests.fakes.command_runner import FakeCommandRunner

from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def test_client(integration_settings):
    """Create FastAPI TestClient for integration tests."""
    from app.server import app

    # Override settings for integration tests
    app.state.settings = integration_settings

    return TestClient(app)


@pytest.fixture(scope="session")
def test_db_url():
    """Get test database URL from environment or use in-memory SQLite for CI."""
    import os

    # Check if we have PostgreSQL test database configured
    if os.getenv("TEST_POSTGRES_URL"):
        return os.getenv("TEST_POSTGRES_URL")

    # Fall back to in-memory SQLite for testing
    return "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_engine(test_db_url):
    """Create database engine for tests."""
    engine = create_engine(test_db_url)

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Clean up - drop all tables
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create database session for tests."""
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def integration_temp_dir():
    """Create temporary directory for integration tests."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture(scope="function")
def integration_settings(integration_temp_dir, test_db_url):
    """Create settings for integration tests."""
    settings = AppSettings()
    settings.data_dir = integration_temp_dir
    settings.database_url = test_db_url
    settings.enable_summarization = False  # Disabled for integration tests
    settings.skip_existing_saves = False
    settings.start_ht = False  # Disable HT runner for tests
    return settings


@pytest.fixture(scope="function")
def real_file_storage(integration_temp_dir):
    """Create real file storage for integration tests."""
    return LocalFileStorage(root_dir=integration_temp_dir)


@pytest.fixture(scope="function")
def memory_file_storage():
    """Create in-memory file storage for tests."""
    return InMemoryFileStorage()


@pytest.fixture(scope="function")
def real_repositories(integration_settings):
    """Create real database repositories for integration tests."""
    artifact_repo = ArchiveArtifactRepository(
        integration_settings.database.resolved_path(integration_settings.data_dir)
    )
    url_repo = ArchivedUrlRepository(
        integration_settings.database.resolved_path(integration_settings.data_dir)
    )
    metadata_repo = UrlMetadataRepository(
        integration_settings.database.resolved_path(integration_settings.data_dir)
    )

    return {
        "artifact": artifact_repo,
        "url": url_repo,
        "metadata": metadata_repo
    }


@pytest.fixture(scope="function")
def dummy_archivers(real_file_storage):
    """Create dummy archivers for integration testing."""
    return {
        "monolith": DummyArchiver(real_file_storage),
        "readability": DummyArchiver(real_file_storage),
        "singlefile-cli": DummyArchiver(real_file_storage),
        "pdf": DummyArchiver(real_file_storage),
        "screenshot": DummyArchiver(real_file_storage),
    }


@pytest.fixture(scope="function")
def fake_command_runner():
    """Create fake command runner for integration tests."""
    return FakeCommandRunner()


@pytest.fixture(scope="function")
def sync_task_manager():
    """Create synchronous task manager for deterministic testing."""
    return SyncTaskManager()


@pytest.fixture(scope="function")
def integration_archiver_task_manager(integration_settings, dummy_archivers):
    """Create ArchiverTaskManager for integration tests."""
    # Mock summarization coordinator
    mock_summarization = Mock(spec=SummarizationCoordinator)
    mock_summarization.schedule.return_value = True

    return ArchiverTaskManager(
        settings=integration_settings,
        archivers=dummy_archivers,
        summarization=mock_summarization,
        requeue_priorities=["monolith", "readability", "singlefile-cli", "pdf", "screenshot"],
        requeue_chunk_size=5
    )


@pytest.fixture(scope="function")
def integration_summarization_coordinator(integration_settings):
    """Create SummarizationCoordinator for integration tests."""
    # Mock summarizer
    mock_summarizer = Mock()
    mock_summarizer.is_enabled = False  # Disabled for tests

    return SummarizationCoordinator(
        settings=integration_settings,
        summarizer=mock_summarizer,
        use_background=False  # Use sync processing for tests
    )


@pytest.fixture(scope="function")
def integration_summarization_task_manager(integration_settings):
    """Create SummarizationTaskManager for integration tests."""
    mock_summarizer = Mock()
    mock_summarizer.is_enabled = False  # Disabled for tests

    return SummarizationTaskManager(
        settings=integration_settings,
        summarizer=mock_summarizer
    )


@pytest.fixture(scope="function")
def sample_urls():
    """Sample URLs for integration testing."""
    return [
        "https://example.com/article1",
        "https://example.org/article2",
        "https://example.net/article3",
        "https://test.com/simple-page",
        "https://news.example.org/article"
    ]


@pytest.fixture(scope="function")
def sample_items():
    """Sample item data for integration testing."""
    return [
        {"item_id": "test123", "url": "https://example.com/article1"},
        {"item_id": "test456", "url": "https://example.org/article2"},
        {"item_id": "test789", "url": "https://example.net/article3"},
        {"item_id": "simple1", "url": "https://test.com/simple-page"},
        {"item_id": "news1", "url": "https://news.example.org/article"}
    ]


@pytest.fixture(scope="function")
def archiver_task_manager_with_storage(integration_settings, dummy_archivers):
    """Create ArchiverTaskManager with storage integration enabled."""
    integration_settings.enable_storage_integration = True

    mock_summarization = Mock(spec=SummarizationCoordinator)
    mock_summarization.schedule.return_value = True

    return ArchiverTaskManager(
        settings=integration_settings,
        archivers=dummy_archivers,
        summarization=mock_summarization,
        requeue_priorities=["monolith", "readability", "singlefile-cli", "pdf", "screenshot"],
        requeue_chunk_size=3
    )


@pytest.fixture(autouse=True)
def cleanup_temp_files(integration_temp_dir):
    """Automatically clean up temporary files after each test."""
    yield

    # Clean up any remaining files
    if integration_temp_dir.exists():
        import shutil
        shutil.rmtree(integration_temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def mock_ht_runner():
    """Mock HTRunner for integration tests."""
    with pytest.MonkeyPatch().context() as m:
        mock_runner = Mock()
        mock_runner.send_command_and_snapshot.return_value = Mock(
            exit_code=0,
            combined_output=["Archive completed successfully"]
        )
        m.setattr("app.archivers.base.ht_runner", mock_runner)
        yield mock_runner


@pytest.fixture(scope="function")
def disable_real_network():
    """Disable real network calls for integration tests."""
    import pytest

    with pytest.MonkeyPatch().context() as m:
        # Mock urllib requests to prevent real network calls
        import urllib.request
        import urllib.error

        def mock_urlopen(url, data=None, timeout=...):
            raise urllib.error.URLError("Network disabled for tests")

        m.setattr(urllib.request, "urlopen", mock_urlopen)
        yield


@pytest.fixture(scope="function")
def sample_article_metadata():
    """Sample article metadata for integration tests."""
    return {
        "title": "Test Article",
        "author": "John Doe",
        "byline": "By John Doe",
        "excerpt": "This is a test article excerpt",
        "text": "This is the full text content of the test article. It contains multiple sentences and paragraphs for testing purposes.",
        "site_name": "Example Site",
        "word_count": 25,
        "length": 150,
        "published_date": "2023-01-01",
        "url": "https://example.com/article1"
    }


@pytest.fixture(scope="function")
def postgres_storage(integration_settings):
    """Create PostgreSQL storage provider for integration tests."""
    from app.storage.postgres_storage import PostgresStorage
    return PostgresStorage()


@pytest.fixture(scope="function")
def firestore_storage(integration_settings):
    """Create Firestore storage provider for integration tests."""
    from app.storage.firestore_storage import FirestoreStorage
    import os

    # Only create if Firestore project ID is configured
    project_id = os.getenv("FIRESTORE_PROJECT_ID") or os.getenv("FIRESTORE__PROJECT_ID")
    if not project_id:
        pytest.skip("Firestore project ID not configured")

    return FirestoreStorage(project_id=project_id)


@pytest.fixture(scope="function")
def test_item_id():
    """Generate unique test item ID."""
    import uuid
    return f"test_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="function")
def cleanup_test_data(postgres_storage, firestore_storage):
    """Cleanup test data from both databases after tests."""
    cleaned_ids = []

    def _cleanup(item_id: str):
        """Register item_id for cleanup."""
        cleaned_ids.append(item_id)

    yield _cleanup

    # Cleanup all registered test data
    for item_id in cleaned_ids:
        try:
            # Clean from PostgreSQL
            postgres_storage.delete_article(item_id)
        except Exception as e:
            pass  # Ignore cleanup failures

        try:
            # Clean from Firestore
            firestore_storage.delete_article(item_id)
        except Exception as e:
            pass  # Ignore cleanup failures