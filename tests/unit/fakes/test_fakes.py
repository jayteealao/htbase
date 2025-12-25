"""
Validation tests for all fake implementations.

These tests ensure the fakes properly implement their interfaces and
behave correctly for testing purposes.
"""

import gzip
import io
from pathlib import Path

import pytest

from tests.fakes.storage import InMemoryFileStorage, InMemoryDatabaseStorage
from tests.fakes.task_manager import SyncTaskManager
from tests.fakes.command_runner import FakeCommandRunner, ConfiguredResult
from tests.fakes.archivers import (
    FailingArchiver,
    TimeoutArchiver,
    SlowArchiver,
    IntermittentArchiver,
    ConfigurableArchiver
)
from app.storage.file_storage import UploadResult


# ==================== InMemoryFileStorage Tests ====================

class TestInMemoryFileStorage:
    """Test InMemoryFileStorage fake implementation."""

    def test_upload_file_without_compression(self, tmp_path):
        """Test uploading file without compression."""
        storage = InMemoryFileStorage()

        # Create test file
        test_file = tmp_path / "test.html"
        test_file.write_text("<html>test content</html>", encoding="utf-8")

        # Upload without compression
        result = storage.upload_file(test_file, "path/to/file.html", compress=False)

        assert result.success
        assert result.uri == "memory://path/to/file.html"
        assert result.original_size == len("<html>test content</html>")
        assert result.stored_size == result.original_size
        assert result.compression_ratio is None
        assert storage.exists("path/to/file.html")

    def test_upload_file_with_compression(self, tmp_path):
        """Test uploading file with gzip compression."""
        storage = InMemoryFileStorage()

        # Create test file
        test_file = tmp_path / "test.html"
        content = "<html>" + "x" * 1000 + "</html>"  # Compressible content
        test_file.write_text(content, encoding="utf-8")

        # Upload with compression
        result = storage.upload_file(test_file, "path/to/file.html.gz", compress=True)

        assert result.success
        assert result.stored_size < result.original_size  # Compressed
        assert result.compression_ratio is not None
        assert result.compression_ratio > 0

        # Verify metadata
        metadata = storage.get_metadata("path/to/file.html.gz")
        assert metadata is not None
        assert metadata.compressed is True

    def test_download_file_decompresses(self, tmp_path):
        """Test downloading compressed file with decompression."""
        storage = InMemoryFileStorage()

        # Upload compressed file
        upload_file = tmp_path / "upload.html"
        original_content = "<html>test content</html>"
        upload_file.write_text(original_content, encoding="utf-8")

        storage.upload_file(upload_file, "test/file.html", compress=True)

        # Download and decompress
        download_file = tmp_path / "download.html"
        success = storage.download_file("test/file.html", download_file, decompress=True)

        assert success
        assert download_file.exists()
        assert download_file.read_text(encoding="utf-8") == original_content

    def test_download_file_without_decompression(self, tmp_path):
        """Test downloading compressed file without decompression."""
        storage = InMemoryFileStorage()

        # Upload compressed file
        upload_file = tmp_path / "upload.html"
        upload_file.write_text("<html>test</html>", encoding="utf-8")
        storage.upload_file(upload_file, "test/file.html", compress=True)

        # Download without decompression (get raw compressed bytes)
        download_file = tmp_path / "download.html.gz"
        success = storage.download_file("test/file.html", download_file, decompress=False)

        assert success
        assert download_file.exists()

        # Verify it's actually compressed
        with gzip.open(download_file, 'rt', encoding='utf-8') as f:
            content = f.read()
            assert content == "<html>test</html>"

    def test_get_file_stream(self, tmp_path):
        """Test getting file stream."""
        storage = InMemoryFileStorage()

        # Upload file
        upload_file = tmp_path / "test.html"
        upload_file.write_text("<html>stream test</html>", encoding="utf-8")
        storage.upload_file(upload_file, "test/file.html", compress=True)

        # Get stream (should auto-decompress)
        stream = storage.get_file_stream("test/file.html")

        assert stream is not None
        content = stream.read().decode('utf-8')
        assert content == "<html>stream test</html>"

    def test_delete_file(self, tmp_path):
        """Test deleting file."""
        storage = InMemoryFileStorage()

        # Upload file
        upload_file = tmp_path / "test.html"
        upload_file.write_text("<html>test</html>", encoding="utf-8")
        storage.upload_file(upload_file, "test/file.html")

        assert storage.exists("test/file.html")

        # Delete
        success = storage.delete_file("test/file.html")

        assert success
        assert not storage.exists("test/file.html")

    def test_exists(self, tmp_path):
        """Test file existence check."""
        storage = InMemoryFileStorage()

        assert not storage.exists("nonexistent/file.html")

        # Upload file
        upload_file = tmp_path / "test.html"
        upload_file.write_text("<html>test</html>", encoding="utf-8")
        storage.upload_file(upload_file, "test/file.html")

        assert storage.exists("test/file.html")

    def test_get_metadata(self, tmp_path):
        """Test getting file metadata."""
        storage = InMemoryFileStorage()

        # Non-existent file
        assert storage.get_metadata("nonexistent.html") is None

        # Upload file
        upload_file = tmp_path / "test.html"
        upload_file.write_text("<html>test</html>", encoding="utf-8")
        result = storage.upload_file(upload_file, "test/file.html", compress=True)

        metadata = storage.get_metadata("test/file.html")

        assert metadata is not None
        assert metadata.path == "test/file.html"
        assert metadata.size == result.stored_size
        assert metadata.content_type == "text/html"
        assert metadata.compressed is True
        assert metadata.compression_ratio is not None

    def test_generate_access_url(self, tmp_path):
        """Test generating access URL."""
        from datetime import timedelta

        storage = InMemoryFileStorage()

        # Upload file
        upload_file = tmp_path / "test.html"
        upload_file.write_text("<html>test</html>", encoding="utf-8")
        storage.upload_file(upload_file, "test/file.html")

        # Generate URL
        url = storage.generate_access_url("test/file.html", expiration=timedelta(days=7))

        assert url.startswith("memory://test/file.html")
        assert "expires=" in url

    def test_list_files_with_prefix(self, tmp_path):
        """Test listing files with prefix filter."""
        storage = InMemoryFileStorage()

        # Upload multiple files
        for i in range(5):
            f = tmp_path / f"test{i}.html"
            f.write_text(f"<html>content {i}</html>", encoding="utf-8")
            storage.upload_file(f, f"archives/test{i}.html")

        # Upload file with different prefix
        other = tmp_path / "other.html"
        other.write_text("<html>other</html>", encoding="utf-8")
        storage.upload_file(other, "other/file.html")

        # List with prefix
        files = storage.list_files(prefix="archives/")

        assert len(files) == 5
        assert all(f.path.startswith("archives/") for f in files)

    def test_list_files_with_limit(self, tmp_path):
        """Test listing files with limit."""
        storage = InMemoryFileStorage()

        # Upload 10 files
        for i in range(10):
            f = tmp_path / f"test{i}.html"
            f.write_text(f"<html>{i}</html>", encoding="utf-8")
            storage.upload_file(f, f"test{i}.html")

        # List with limit
        files = storage.list_files(limit=5)

        assert len(files) == 5

    def test_configured_failure_mode(self, tmp_path):
        """Test configured failure on specific paths."""
        storage = InMemoryFileStorage(fail_on_paths=["fail/path.html"])

        # Normal upload should work
        normal_file = tmp_path / "normal.html"
        normal_file.write_text("<html>normal</html>", encoding="utf-8")
        result = storage.upload_file(normal_file, "normal/path.html")
        assert result.success

        # Configured failure path should fail
        fail_file = tmp_path / "fail.html"
        fail_file.write_text("<html>fail</html>", encoding="utf-8")
        result = storage.upload_file(fail_file, "fail/path.html")
        assert not result.success
        assert result.error is not None

    def test_provider_properties(self):
        """Test provider properties."""
        storage = InMemoryFileStorage()

        assert storage.provider_name == "memory"
        assert storage.supports_compression is True
        assert storage.supports_signed_urls is True

    def test_helper_methods(self, tmp_path):
        """Test helper methods for testing."""
        storage = InMemoryFileStorage()

        # get_file_count
        assert storage.get_file_count() == 0

        upload_file = tmp_path / "test.html"
        upload_file.write_text("<html>test</html>", encoding="utf-8")
        storage.upload_file(upload_file, "test1.html")
        storage.upload_file(upload_file, "test2.html")

        assert storage.get_file_count() == 2

        # get_raw_content
        raw = storage.get_raw_content("test1.html")
        assert raw is not None

        # clear
        storage.clear()
        assert storage.get_file_count() == 0


# ==================== InMemoryDatabaseStorage Tests ====================

class TestInMemoryDatabaseStorage:
    """Test InMemoryDatabaseStorage fake implementation."""

    def test_create_article(self):
        """Test creating article."""
        storage = InMemoryDatabaseStorage()

        success = storage.create_article(
            item_id="test1",
            url="https://example.com",
            pocket_data={"itemId": "123"},
            metadata={"title": "Test"}
        )

        assert success
        assert storage.get_article_count() == 1

    def test_create_duplicate_article_fails(self):
        """Test creating duplicate article returns False."""
        storage = InMemoryDatabaseStorage()

        storage.create_article(item_id="test1", url="https://example.com")

        # Try to create again
        success = storage.create_article(item_id="test1", url="https://example.com/different")

        assert not success  # Should fail

    def test_get_article(self):
        """Test getting article."""
        storage = InMemoryDatabaseStorage()

        # Non-existent
        assert storage.get_article("nonexistent") is None

        # Create and get
        storage.create_article(
            item_id="test1",
            url="https://example.com",
            pocket_data={"itemId": "123"}
        )

        article = storage.get_article("test1")

        assert article is not None
        assert article['item_id'] == "test1"
        assert article['url'] == "https://example.com"
        assert article['pocket_data'] == {"itemId": "123"}

    def test_update_artifact_status_creates_new(self):
        """Test updating artifact status creates new artifact."""
        storage = InMemoryDatabaseStorage()

        success = storage.update_artifact_status(
            item_id="test1",
            archiver="monolith",
            status="success",
            gcs_path="gs://bucket/path",
            exit_code=0
        )

        assert success
        assert storage.get_artifact_count() == 1

    def test_update_artifact_status_updates_existing(self):
        """Test updating existing artifact."""
        storage = InMemoryDatabaseStorage()

        # Create
        storage.update_artifact_status(
            item_id="test1",
            archiver="monolith",
            status="pending"
        )

        # Update
        storage.update_artifact_status(
            item_id="test1",
            archiver="monolith",
            status="success",
            gcs_path="gs://bucket/path",
            exit_code=0
        )

        artifact = storage.get_artifact("test1", "monolith")

        assert artifact['status'] == "success"
        assert artifact['gcs_path'] == "gs://bucket/path"
        assert artifact['exit_code'] == 0

    def test_get_artifact(self):
        """Test getting artifact."""
        storage = InMemoryDatabaseStorage()

        # Non-existent
        assert storage.get_artifact("test1", "monolith") is None

        # Create and get
        storage.update_artifact_status(
            item_id="test1",
            archiver="monolith",
            status="success"
        )

        artifact = storage.get_artifact("test1", "monolith")

        assert artifact is not None
        assert artifact['item_id'] == "test1"
        assert artifact['archiver'] == "monolith"
        assert artifact['status'] == "success"

    def test_list_artifacts_no_filter(self):
        """Test listing all artifacts."""
        storage = InMemoryDatabaseStorage()

        # Create multiple artifacts
        storage.update_artifact_status("test1", "monolith", "success")
        storage.update_artifact_status("test1", "singlefile", "success")
        storage.update_artifact_status("test2", "monolith", "failed")

        artifacts = storage.list_artifacts()

        assert len(artifacts) == 3

    def test_list_artifacts_filter_by_item_id(self):
        """Test filtering artifacts by item_id."""
        storage = InMemoryDatabaseStorage()

        storage.update_artifact_status("test1", "monolith", "success")
        storage.update_artifact_status("test1", "singlefile", "success")
        storage.update_artifact_status("test2", "monolith", "failed")

        artifacts = storage.list_artifacts(item_id="test1")

        assert len(artifacts) == 2
        assert all(a['item_id'] == "test1" for a in artifacts)

    def test_list_artifacts_filter_by_archiver(self):
        """Test filtering artifacts by archiver."""
        storage = InMemoryDatabaseStorage()

        storage.update_artifact_status("test1", "monolith", "success")
        storage.update_artifact_status("test1", "singlefile", "success")
        storage.update_artifact_status("test2", "monolith", "failed")

        artifacts = storage.list_artifacts(archiver="monolith")

        assert len(artifacts) == 2
        assert all(a['archiver'] == "monolith" for a in artifacts)

    def test_list_artifacts_filter_by_status(self):
        """Test filtering artifacts by status."""
        storage = InMemoryDatabaseStorage()

        storage.update_artifact_status("test1", "monolith", "success")
        storage.update_artifact_status("test1", "singlefile", "failed")
        storage.update_artifact_status("test2", "monolith", "success")

        artifacts = storage.list_artifacts(status="success")

        assert len(artifacts) == 2
        assert all(a['status'] == "success" for a in artifacts)

    def test_list_artifacts_with_limit(self):
        """Test limiting artifacts list."""
        storage = InMemoryDatabaseStorage()

        for i in range(10):
            storage.update_artifact_status(f"test{i}", "monolith", "success")

        artifacts = storage.list_artifacts(limit=5)

        assert len(artifacts) == 5

    def test_list_articles(self):
        """Test listing articles."""
        storage = InMemoryDatabaseStorage()

        for i in range(5):
            storage.create_article(f"test{i}", f"https://example.com/{i}")

        articles = storage.list_articles()

        assert len(articles) == 5

    def test_list_articles_with_pagination(self):
        """Test article pagination."""
        storage = InMemoryDatabaseStorage()

        for i in range(10):
            storage.create_article(f"test{i}", f"https://example.com/{i}")

        # Get first page
        page1 = storage.list_articles(limit=5, offset=0)
        assert len(page1) == 5

        # Get second page
        page2 = storage.list_articles(limit=5, offset=5)
        assert len(page2) == 5

        # No overlap
        page1_ids = {a['item_id'] for a in page1}
        page2_ids = {a['item_id'] for a in page2}
        assert len(page1_ids & page2_ids) == 0

    def test_provider_name(self):
        """Test provider name."""
        storage = InMemoryDatabaseStorage()
        assert storage.provider_name == "memory"

    def test_clear(self):
        """Test clearing all data."""
        storage = InMemoryDatabaseStorage()

        storage.create_article("test1", "https://example.com")
        storage.update_artifact_status("test1", "monolith", "success")

        assert storage.get_article_count() > 0
        assert storage.get_artifact_count() > 0

        storage.clear()

        assert storage.get_article_count() == 0
        assert storage.get_artifact_count() == 0


# ==================== SyncTaskManager Tests ====================

class TestSyncTaskManager:
    """Test SyncTaskManager fake implementation."""

    def test_submit_processes_immediately(self):
        """Test that submit processes task immediately."""
        processed_tasks = []

        def process(task):
            processed_tasks.append(task)

        manager = SyncTaskManager(process_fn=process)
        manager.submit("task1")

        assert len(processed_tasks) == 1
        assert processed_tasks[0] == "task1"

    def test_multiple_tasks(self):
        """Test processing multiple tasks."""
        processed_tasks = []

        def process(task):
            processed_tasks.append(task)

        manager = SyncTaskManager(process_fn=process)

        for i in range(5):
            manager.submit(f"task{i}")

        assert len(processed_tasks) == 5

    def test_records_processed_tasks(self):
        """Test that processed tasks are recorded."""
        manager = SyncTaskManager(process_fn=lambda x: None)

        manager.submit("task1")
        manager.submit("task2")

        assert manager.get_processed_count() == 2
        assert manager.has_processed("task1")
        assert manager.has_processed("task2")

    def test_get_last_processed(self):
        """Test getting last processed task."""
        manager = SyncTaskManager(process_fn=lambda x: None)

        assert manager.get_last_processed() is None

        manager.submit("task1")
        assert manager.get_last_processed() == "task1"

        manager.submit("task2")
        assert manager.get_last_processed() == "task2"

    def test_failed_tasks_recorded(self):
        """Test that failed tasks are recorded."""
        def failing_process(task):
            if task == "fail":
                raise ValueError("Task failed")

        manager = SyncTaskManager(process_fn=failing_process)

        manager.submit("success")

        with pytest.raises(ValueError):
            manager.submit("fail")

        assert manager.get_processed_count() == 1
        assert manager.get_failed_count() == 1

    def test_clear(self):
        """Test clearing task history."""
        manager = SyncTaskManager(process_fn=lambda x: None)

        manager.submit("task1")
        assert manager.get_processed_count() == 1

        manager.clear()

        assert manager.get_processed_count() == 0
        assert manager.get_failed_count() == 0

    def test_start_is_noop(self):
        """Test that start() is a no-op."""
        manager = SyncTaskManager(process_fn=lambda x: None)

        # Should not raise
        manager.start()
        manager.start()  # Can call multiple times


# ==================== FakeCommandRunner Tests ====================

class TestFakeCommandRunner:
    """Test FakeCommandRunner fake implementation."""

    def test_default_result(self):
        """Test default success result."""
        runner = FakeCommandRunner()

        result = runner.execute("any command")

        assert result.success
        assert result.exit_code == 0
        assert not result.timed_out

    def test_configure_success_result(self):
        """Test configuring success result."""
        runner = FakeCommandRunner()

        runner.configure_result(
            pattern="monolith",
            exit_code=0,
            stdout_lines=["<html>output</html>"]
        )

        result = runner.execute("monolith --output test.html https://example.com")

        assert result.success
        assert result.stdout_lines == ["<html>output</html>"]

    def test_configure_failure_result(self):
        """Test configuring failure result."""
        runner = FakeCommandRunner()

        runner.configure_result(
            pattern="singlefile",
            exit_code=1,
            stderr_lines=["Error: command failed"]
        )

        result = runner.execute("singlefile-cli test.html")

        assert not result.success
        assert result.exit_code == 1
        assert "Error: command failed" in result.stderr_lines

    def test_configure_timeout_result(self):
        """Test configuring timeout result."""
        runner = FakeCommandRunner()

        runner.configure_result(
            pattern="slow-command",
            timed_out=True
        )

        result = runner.execute("slow-command")

        assert result.timed_out
        assert not result.success
        assert result.exit_code is None

    def test_pattern_matching(self):
        """Test pattern-based result matching."""
        runner = FakeCommandRunner()

        runner.configure_result("monolith", exit_code=0)
        runner.configure_result("singlefile", exit_code=1)

        result1 = runner.execute("monolith --output test.html")
        result2 = runner.execute("singlefile-cli test.html")

        assert result1.exit_code == 0
        assert result2.exit_code == 1

    def test_invocation_recording(self):
        """Test that invocations are recorded."""
        runner = FakeCommandRunner()

        runner.execute("command1")
        runner.execute("command2")

        assert runner.get_invocation_count() == 2

    def test_was_command_executed(self):
        """Test checking if command was executed."""
        runner = FakeCommandRunner()

        runner.execute("monolith --output test.html")

        assert runner.was_command_executed("monolith")
        assert not runner.was_command_executed("singlefile")

    def test_get_invocations_matching(self):
        """Test getting invocations by pattern."""
        runner = FakeCommandRunner()

        runner.execute("monolith --output test1.html")
        runner.execute("monolith --output test2.html")
        runner.execute("singlefile test.html")

        monolith_invocations = runner.get_invocations_matching("monolith")

        assert len(monolith_invocations) == 2

    def test_get_last_invocation(self):
        """Test getting last invocation."""
        runner = FakeCommandRunner()

        assert runner.get_last_invocation() is None

        runner.execute("command1")
        runner.execute("command2")

        last = runner.get_last_invocation()
        assert last is not None
        assert last.command == "command2"

    def test_clear_and_reset(self):
        """Test clearing state."""
        runner = FakeCommandRunner()

        runner.configure_result("test", exit_code=1)
        runner.execute("test command")

        runner.reset()

        assert runner.get_invocation_count() == 0
        # Configurations should be cleared too
        result = runner.execute("test command")
        assert result.exit_code == 0  # Back to default


# ==================== Enhanced Archiver Fakes Tests ====================

class TestFailingArchiver:
    """Test FailingArchiver fake."""

    def test_always_fails(self, temp_env):
        """Test that FailingArchiver always fails."""
        from core.config import get_settings

        archiver = FailingArchiver(get_settings(), exit_code=1)

        result = archiver.archive(url="https://example.com", item_id="test")

        assert not result.success
        assert result.exit_code == 1
        assert result.saved_path is None

    def test_custom_exit_code(self, temp_env):
        """Test custom exit code."""
        from core.config import get_settings

        archiver = FailingArchiver(get_settings(), exit_code=127)

        result = archiver.archive(url="https://example.com", item_id="test")

        assert result.exit_code == 127


class TestIntermittentArchiver:
    """Test IntermittentArchiver fake."""

    def test_fails_then_succeeds(self, temp_env):
        """Test failing N times then succeeding."""
        from core.config import get_settings

        archiver = IntermittentArchiver(get_settings(), fail_count=2)

        # First attempt fails
        result1 = archiver.archive(url="https://example.com", item_id="test1")
        assert not result1.success

        # Second attempt fails
        result2 = archiver.archive(url="https://example.com", item_id="test2")
        assert not result2.success

        # Third attempt succeeds
        result3 = archiver.archive(url="https://example.com", item_id="test3")
        assert result3.success
        assert result3.saved_path is not None

    def test_reset(self, temp_env):
        """Test resetting attempt counter."""
        from core.config import get_settings

        archiver = IntermittentArchiver(get_settings(), fail_count=1)

        # First fails
        result1 = archiver.archive(url="https://example.com", item_id="test1")
        assert not result1.success

        # Second succeeds
        result2 = archiver.archive(url="https://example.com", item_id="test2")
        assert result2.success

        # Reset and first fails again
        archiver.reset()
        result3 = archiver.archive(url="https://example.com", item_id="test3")
        assert not result3.success


class TestConfigurableArchiver:
    """Test ConfigurableArchiver fake."""

    def test_configure_success(self, temp_env):
        """Test configuring for success."""
        from core.config import get_settings

        archiver = ConfigurableArchiver(get_settings())
        archiver.configure(success=True, exit_code=0)

        result = archiver.archive(url="https://example.com", item_id="test")

        assert result.success
        assert result.exit_code == 0
        assert result.saved_path is not None

    def test_configure_failure(self, temp_env):
        """Test configuring for failure."""
        from core.config import get_settings

        archiver = ConfigurableArchiver(get_settings())
        archiver.configure(success=False, exit_code=1)

        result = archiver.archive(url="https://example.com", item_id="test")

        assert not result.success
        assert result.exit_code == 1
        assert result.saved_path is None

    def test_reconfigure(self, temp_env):
        """Test reconfiguring behavior."""
        from core.config import get_settings

        archiver = ConfigurableArchiver(get_settings())

        # Configure to succeed
        archiver.configure(success=True)
        result1 = archiver.archive(url="https://example.com", item_id="test1")
        assert result1.success

        # Reconfigure to fail
        archiver.configure(success=False, exit_code=2)
        result2 = archiver.archive(url="https://example.com", item_id="test2")
        assert not result2.success
        assert result2.exit_code == 2


# ==================== Summary ====================

def test_all_fakes_importable():
    """Smoke test that all fakes can be imported."""
    from fakes import (
        InMemoryFileStorage,
        InMemoryDatabaseStorage,
        SyncTaskManager,
        FakeCommandRunner,
        FailingArchiver,
        TimeoutArchiver,
        SlowArchiver,
    )

    # Just verify they're all importable
    assert InMemoryFileStorage is not None
    assert InMemoryDatabaseStorage is not None
    assert SyncTaskManager is not None
    assert FakeCommandRunner is not None
    assert FailingArchiver is not None
    assert TimeoutArchiver is not None
    assert SlowArchiver is not None
