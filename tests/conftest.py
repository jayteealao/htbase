from __future__ import annotations

import sys
from pathlib import Path
from typing import Generator

import pytest

# Ensure the application package is importable as a flat module set
_ROOT = Path(__file__).resolve().parents[1]
_APP = str(_ROOT / "app")
if _APP not in sys.path:
    sys.path.insert(0, _APP)


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
    from core.config import get_settings
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


# ==================== New Fake Fixtures (Phase 1) ====================

@pytest.fixture
def in_memory_file_storage():
    """
    Provide InMemoryFileStorage for tests.

    Fast, deterministic file storage without disk I/O.

    Example:
        def test_upload(in_memory_file_storage, tmp_path):
            file = tmp_path / "test.html"
            file.write_text("<html>test</html>")

            result = in_memory_file_storage.upload_file(file, "test/file.html")
            assert result.success
    """
    from fakes.storage import InMemoryFileStorage
    return InMemoryFileStorage()


@pytest.fixture
def in_memory_db_storage():
    """
    Provide InMemoryDatabaseStorage for tests.

    Fast, deterministic database storage without PostgreSQL/Firestore.

    Example:
        def test_create_article(in_memory_db_storage):
            success = in_memory_db_storage.create_article(
                item_id="test1",
                url="https://example.com"
            )
            assert success

            article = in_memory_db_storage.get_article("test1")
            assert article['url'] == "https://example.com"
    """
    from fakes.storage import InMemoryDatabaseStorage
    return InMemoryDatabaseStorage()


@pytest.fixture
def sync_task_manager():
    """
    Provide SyncTaskManager for tests.

    Processes tasks immediately without threading, making tests deterministic.

    Example:
        def test_task_processing(sync_task_manager):
            def process(task):
                print(f"Processing: {task}")

            manager = SyncTaskManager(process_fn=process)
            manager.submit("task1")

            assert manager.get_processed_count() == 1
            assert manager.get_last_processed() == "task1"
    """
    from fakes.task_manager import SyncTaskManager
    return SyncTaskManager()


@pytest.fixture
def fake_command_runner():
    """
    Provide FakeCommandRunner for tests.

    Returns pre-configured results without subprocess execution.

    Example:
        def test_command(fake_command_runner):
            fake_command_runner.configure_result("monolith", exit_code=0)

            result = fake_command_runner.execute("monolith --output test.html")
            assert result.success
            assert fake_command_runner.get_invocation_count() == 1
    """
    from fakes.command_runner import FakeCommandRunner
    return FakeCommandRunner()


@pytest.fixture
def dummy_archivers(temp_env):
    """
    Provide collection of dummy archivers for tests.

    Returns dict with all archiver types configured with fakes.

    Example:
        def test_all_archivers(dummy_archivers):
            assert "monolith" in dummy_archivers
            assert "failing" in dummy_archivers

            result = dummy_archivers["monolith"].archive(
                url="https://example.com",
                item_id="test"
            )
            assert result.success
    """
    from core.config import get_settings
    from fakes.archivers import (
        FailingArchiver,
        TimeoutArchiver,
        SlowArchiver,
        IntermittentArchiver,
        ConfigurableArchiver
    )
    # Import here to ensure DummyArchiver uses temp_env
    from archivers.base import BaseArchiver
    from models import ArchiveResult
    from core.utils import sanitize_filename

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

    settings = get_settings()

    return {
        "monolith": DummyArchiver(settings),
        "failing": FailingArchiver(settings),
        "timeout": TimeoutArchiver(settings, sleep_seconds=0.1),  # Short timeout for tests
        "slow": SlowArchiver(settings, sleep_seconds=0.1),  # Short sleep for tests
        "intermittent": IntermittentArchiver(settings, fail_count=2),
        "configurable": ConfigurableArchiver(settings),
    }


@pytest.fixture
def test_app_with_fakes(
    temp_env,
    dummy_archivers,
    in_memory_file_storage,
    in_memory_db_storage,
    sync_task_manager
):
    """
    Provide fully configured FastAPI app with all fakes injected.

    Use this for tests that need a complete app with deterministic behavior.

    Example:
        def test_api_with_fakes(test_app_with_fakes):
            from fastapi.testclient import TestClient
            client = TestClient(test_app_with_fakes)

            response = client.post("/archive/monolith", json={
                "id": "test",
                "url": "https://example.com"
            })
            assert response.status_code == 200
    """
    import server
    from core.config import get_settings

    # Reset app state
    server.app.state.archivers = dummy_archivers
    server.app.state.file_storage_providers = [in_memory_file_storage]
    server.app.state.db_storage = in_memory_db_storage

    # Use sync task manager for deterministic tests
    from task_manager import ArchiverTaskManager

    # Create task manager but override its queue with sync manager
    task_manager = ArchiverTaskManager(
        get_settings(),
        server.app.state.archivers,
        summarization=None  # Disable summarization for basic tests
    )
    task_manager._queue = sync_task_manager.queue
    server.app.state.task_manager = task_manager

    return server.app
