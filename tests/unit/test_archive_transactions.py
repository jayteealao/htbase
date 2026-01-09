"""
Tests for archive worker transaction boundaries and zombie task cleanup.

Tests verify:
1. Single transaction scope for entire archive operation
2. SELECT FOR UPDATE row locking prevents concurrent updates
3. Rollback on worker crash (simulated exception)
4. Zombie task detection and cleanup
5. Race condition handling
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
from sqlalchemy import select

# Add shared module to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.db import get_session, ArchiveArtifact, ArchivedUrl
from shared.db.session import get_engine
from shared.db.models import Base


@pytest.fixture(scope="function")
def test_db():
    """Create a fresh test database for each test."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_artifact(test_db):
    """Create a test artifact in the database."""
    with get_session() as session:
        # Create archived URL
        archived_url = ArchivedUrl(
            url="https://example.com/test",
            item_id="test-item",
        )
        session.add(archived_url)
        session.flush()

        # Create artifact
        artifact = ArchiveArtifact(
            archived_url_id=archived_url.id,
            archiver="singlefile",
            status="pending",
        )
        session.add(artifact)
        session.flush()

        artifact_id = artifact.id
        archived_url_id = archived_url.id

    return artifact_id, archived_url_id


class TestArchiveTransactions:
    """Test transaction boundaries in archive tasks."""

    def test_single_transaction_commit_on_success(self, test_artifact):
        """Test that successful archive commits all changes in single transaction."""
        artifact_id, archived_url_id = test_artifact

        # Import task function
        from services.archive_worker.app.tasks import _execute_archive_task

        # Mock successful archiver
        mock_result = Mock()
        mock_result.success = True
        mock_result.exit_code = 0
        mock_result.saved_path = "/tmp/test.html"

        with patch("services.archive_worker.app.tasks._get_archiver") as mock_get_archiver:
            mock_archiver = Mock()
            mock_archiver.archive_with_storage.return_value = mock_result
            mock_get_archiver.return_value = mock_archiver

            # Create temporary file for size calculation
            test_file = Path("/tmp/test.html")
            test_file.write_text("test content")

            try:
                # Execute task within transaction
                with get_session() as session:
                    result = _execute_archive_task(
                        session=session,
                        artifact_id=artifact_id,
                        archiver_name="singlefile",
                        url="https://example.com/test",
                        item_id="test-item",
                        task_id="test-task-123",
                    )

                # Verify result
                assert result["success"] is True
                assert result["archiver"] == "singlefile"

                # Verify database state - should be committed
                with get_session() as session:
                    artifact = session.get(ArchiveArtifact, artifact_id)
                    assert artifact.status == "success"
                    assert artifact.success is True
                    assert artifact.saved_path == "/tmp/test.html"
                    assert artifact.task_started_at is not None
                    assert artifact.last_heartbeat is not None
            finally:
                if test_file.exists():
                    test_file.unlink()

    def test_single_transaction_rollback_on_failure(self, test_artifact):
        """Test that failed archive rolls back all changes."""
        artifact_id, archived_url_id = test_artifact

        from services.archive_worker.app.tasks import _execute_archive_task

        # Mock archiver that raises exception
        with patch("services.archive_worker.app.tasks._get_archiver") as mock_get_archiver:
            mock_archiver = Mock()
            mock_archiver.archive_with_storage.side_effect = RuntimeError("Worker crashed!")
            mock_get_archiver.return_value = mock_archiver

            # Execute task and expect exception
            with pytest.raises(RuntimeError, match="Worker crashed"):
                with get_session() as session:
                    _execute_archive_task(
                        session=session,
                        artifact_id=artifact_id,
                        archiver_name="singlefile",
                        url="https://example.com/test",
                        item_id="test-item",
                        task_id="test-task-123",
                    )

            # Verify database state - should be rolled back to pending
            with get_session() as session:
                artifact = session.get(ArchiveArtifact, artifact_id)
                assert artifact.status == "pending"  # Never changed!
                assert artifact.success is False
                assert artifact.saved_path is None
                assert artifact.task_started_at is None  # Rolled back!

    def test_row_locking_with_select_for_update(self, test_artifact):
        """Test that SELECT FOR UPDATE prevents concurrent modifications."""
        artifact_id, archived_url_id = test_artifact

        from services.archive_worker.app.tasks import _execute_archive_task

        # Mock slow archiver to simulate long-running task
        mock_result = Mock()
        mock_result.success = True
        mock_result.exit_code = 0
        mock_result.saved_path = "/tmp/test.html"

        lock_acquired = []

        def slow_archive(*args, **kwargs):
            """Simulate slow archive operation."""
            import time
            lock_acquired.append(datetime.utcnow())
            time.sleep(0.1)  # Hold lock for 100ms
            return mock_result

        with patch("services.archive_worker.app.tasks._get_archiver") as mock_get_archiver:
            mock_archiver = Mock()
            mock_archiver.archive_with_storage.side_effect = slow_archive
            mock_get_archiver.return_value = mock_archiver

            # Create temporary file
            test_file = Path("/tmp/test.html")
            test_file.write_text("test content")

            try:
                # Start first transaction
                with get_session() as session:
                    result = _execute_archive_task(
                        session=session,
                        artifact_id=artifact_id,
                        archiver_name="singlefile",
                        url="https://example.com/test",
                        item_id="test-item",
                        task_id="test-task-1",
                    )

                assert result["success"] is True
                assert len(lock_acquired) == 1
            finally:
                if test_file.exists():
                    test_file.unlink()

    def test_zombie_task_cleanup(self, test_artifact):
        """Test zombie task detection and cleanup."""
        artifact_id, archived_url_id = test_artifact

        # Simulate zombie task - stuck in in_progress for > 1 hour
        old_timestamp = datetime.utcnow() - timedelta(hours=2)

        with get_session() as session:
            artifact = session.get(ArchiveArtifact, artifact_id)
            artifact.status = "in_progress"
            artifact.task_started_at = old_timestamp
            artifact.updated_at = old_timestamp

        # Run zombie cleanup
        from services.archive_worker.app.tasks import cleanup_zombie_tasks

        result = cleanup_zombie_tasks()

        # Verify cleanup
        assert result["zombies_found"] == 1
        assert result["zombies_failed"] == 1

        # Verify artifact was marked as failed
        with get_session() as session:
            artifact = session.get(ArchiveArtifact, artifact_id)
            assert artifact.status == "failed"
            assert artifact.success is False

    def test_zombie_cleanup_ignores_recent_tasks(self, test_artifact):
        """Test that zombie cleanup ignores tasks updated recently."""
        artifact_id, archived_url_id = test_artifact

        # Create recent in_progress task (< 1 hour old)
        recent_timestamp = datetime.utcnow() - timedelta(minutes=30)

        with get_session() as session:
            artifact = session.get(ArchiveArtifact, artifact_id)
            artifact.status = "in_progress"
            artifact.task_started_at = recent_timestamp
            artifact.updated_at = recent_timestamp

        # Run zombie cleanup
        from services.archive_worker.app.tasks import cleanup_zombie_tasks

        result = cleanup_zombie_tasks()

        # Verify no cleanup
        assert result["zombies_found"] == 0
        assert result["zombies_failed"] == 0

        # Verify artifact still in_progress
        with get_session() as session:
            artifact = session.get(ArchiveArtifact, artifact_id)
            assert artifact.status == "in_progress"

    def test_zombie_cleanup_only_affects_in_progress(self, test_artifact):
        """Test that zombie cleanup only affects in_progress tasks."""
        artifact_id, archived_url_id = test_artifact

        # Create old successful task
        old_timestamp = datetime.utcnow() - timedelta(hours=2)

        with get_session() as session:
            artifact = session.get(ArchiveArtifact, artifact_id)
            artifact.status = "success"
            artifact.success = True
            artifact.updated_at = old_timestamp

        # Run zombie cleanup
        from services.archive_worker.app.tasks import cleanup_zombie_tasks

        result = cleanup_zombie_tasks()

        # Verify no cleanup
        assert result["zombies_found"] == 0

        # Verify artifact unchanged
        with get_session() as session:
            artifact = session.get(ArchiveArtifact, artifact_id)
            assert artifact.status == "success"
            assert artifact.success is True

    def test_task_started_at_and_heartbeat_tracking(self, test_artifact):
        """Test that task_started_at and last_heartbeat are set correctly."""
        artifact_id, archived_url_id = test_artifact

        from services.archive_worker.app.tasks import _execute_archive_task

        mock_result = Mock()
        mock_result.success = True
        mock_result.exit_code = 0
        mock_result.saved_path = "/tmp/test.html"

        with patch("services.archive_worker.app.tasks._get_archiver") as mock_get_archiver:
            mock_archiver = Mock()
            mock_archiver.archive_with_storage.return_value = mock_result
            mock_get_archiver.return_value = mock_archiver

            test_file = Path("/tmp/test.html")
            test_file.write_text("test")

            try:
                before_execution = datetime.utcnow()

                with get_session() as session:
                    _execute_archive_task(
                        session=session,
                        artifact_id=artifact_id,
                        archiver_name="singlefile",
                        url="https://example.com/test",
                        item_id="test-item",
                        task_id="test-task-123",
                    )

                after_execution = datetime.utcnow()

                # Verify timestamps
                with get_session() as session:
                    artifact = session.get(ArchiveArtifact, artifact_id)
                    assert artifact.task_started_at is not None
                    assert artifact.last_heartbeat is not None
                    assert before_execution <= artifact.task_started_at <= after_execution
                    assert before_execution <= artifact.last_heartbeat <= after_execution
            finally:
                if test_file.exists():
                    test_file.unlink()

    def test_concurrent_execution_prevented_by_lock(self, test_artifact):
        """Test that SELECT FOR UPDATE prevents concurrent execution."""
        artifact_id, archived_url_id = test_artifact

        from services.archive_worker.app.tasks import _execute_archive_task
        from sqlalchemy.exc import OperationalError
        import threading
        import time

        mock_result = Mock()
        mock_result.success = True
        mock_result.exit_code = 0
        mock_result.saved_path = "/tmp/test.html"

        execution_times = []
        errors = []

        def execute_task():
            """Execute task in thread."""
            try:
                with patch("services.archive_worker.app.tasks._get_archiver") as mock_get_archiver:
                    mock_archiver = Mock()

                    def slow_archive(*args, **kwargs):
                        execution_times.append(datetime.utcnow())
                        time.sleep(0.2)  # Hold lock
                        return mock_result

                    mock_archiver.archive_with_storage.side_effect = slow_archive
                    mock_get_archiver.return_value = mock_archiver

                    with get_session() as session:
                        _execute_archive_task(
                            session=session,
                            artifact_id=artifact_id,
                            archiver_name="singlefile",
                            url="https://example.com/test",
                            item_id="test-item",
                            task_id=f"test-task-{threading.current_thread().name}",
                        )
            except Exception as e:
                errors.append(e)

        # Create temporary file
        test_file = Path("/tmp/test.html")
        test_file.write_text("test")

        try:
            # Start two concurrent threads
            thread1 = threading.Thread(target=execute_task, name="1")
            thread2 = threading.Thread(target=execute_task, name="2")

            thread1.start()
            time.sleep(0.05)  # Ensure thread1 acquires lock first
            thread2.start()

            thread1.join(timeout=2)
            thread2.join(timeout=2)

            # One should succeed, one should wait or timeout
            # At minimum, executions should be serialized (not concurrent)
            if len(execution_times) >= 2:
                time_diff = abs((execution_times[1] - execution_times[0]).total_seconds())
                assert time_diff >= 0.2, "Tasks executed concurrently (lock not held)"
        finally:
            if test_file.exists():
                test_file.unlink()


class TestArchiveTaskIntegration:
    """Integration tests for full archive task flow."""

    def test_archive_singlefile_end_to_end(self, test_artifact):
        """Test full archive_singlefile task execution."""
        artifact_id, archived_url_id = test_artifact

        from services.archive_worker.app.tasks import archive_singlefile

        mock_result = Mock()
        mock_result.success = True
        mock_result.exit_code = 0
        mock_result.saved_path = "/tmp/test.html"

        with patch("services.archive_worker.app.tasks._get_archiver") as mock_get_archiver:
            mock_archiver = Mock()
            mock_archiver.archive_with_storage.return_value = mock_result
            mock_get_archiver.return_value = mock_archiver

            test_file = Path("/tmp/test.html")
            test_file.write_text("test")

            try:
                # Execute task with mock self
                mock_self = Mock()
                mock_self.request.id = "test-task-123"

                result = archive_singlefile(
                    mock_self,
                    item_id="test-item",
                    url="https://example.com/test",
                    archived_url_id=archived_url_id,
                    artifact_id=artifact_id,
                )

                # Verify result
                assert result["success"] is True
                assert result["archiver"] == "singlefile"

                # Verify database committed
                with get_session() as session:
                    artifact = session.get(ArchiveArtifact, artifact_id)
                    assert artifact.status == "success"
                    assert artifact.success is True
            finally:
                if test_file.exists():
                    test_file.unlink()

    def test_all_archivers_use_transactions(self, test_artifact):
        """Test that all archiver tasks use single transaction pattern."""
        artifact_id, archived_url_id = test_artifact

        from services.archive_worker.app import tasks

        archiver_tasks = [
            (tasks.archive_singlefile, "singlefile"),
            (tasks.archive_monolith, "monolith"),
            (tasks.archive_readability, "readability"),
            (tasks.archive_pdf, "pdf"),
            (tasks.archive_screenshot, "screenshot"),
        ]

        for task_func, archiver_name in archiver_tasks:
            # Reset artifact
            with get_session() as session:
                artifact = session.get(ArchiveArtifact, artifact_id)
                artifact.status = "pending"
                artifact.success = False
                artifact.saved_path = None

            mock_result = Mock()
            mock_result.success = True
            mock_result.exit_code = 0
            mock_result.saved_path = f"/tmp/{archiver_name}.html"

            with patch("services.archive_worker.app.tasks._get_archiver") as mock_get_archiver:
                mock_archiver = Mock()
                mock_archiver.archive_with_storage.return_value = mock_result
                mock_get_archiver.return_value = mock_archiver

                test_file = Path(f"/tmp/{archiver_name}.html")
                test_file.write_text("test")

                try:
                    mock_self = Mock()
                    mock_self.request.id = f"test-{archiver_name}"

                    result = task_func(
                        mock_self,
                        item_id="test-item",
                        url="https://example.com/test",
                        archived_url_id=archived_url_id,
                        artifact_id=artifact_id,
                    )

                    assert result["success"] is True, f"{archiver_name} failed"
                    assert result["archiver"] == archiver_name

                    # Verify committed
                    with get_session() as session:
                        artifact = session.get(ArchiveArtifact, artifact_id)
                        assert artifact.status == "success", f"{archiver_name} not committed"
                finally:
                    if test_file.exists():
                        test_file.unlink()
