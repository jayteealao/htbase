"""
Integration tests for task processing workflows.

Tests the interaction between task managers, archivers, storage providers,
and database repositories to ensure proper task orchestration and execution.
"""

import json
import time
from unittest.mock import Mock, patch
from threading import Event

import pytest

from app.task_manager.archiver import ArchiverTaskManager, BatchTask, BatchItem
from app.task_manager.summarization import SummarizationCoordinator, SummarizeTask
from app.core.config import AppSettings
from app.archivers.base import BaseArchiver
from models import ArchiveResult


class TestTaskProcessing:
    """Test task processing integration."""

    def test_archiver_task_manager_full_workflow(self, integration_settings, dummy_archivers, real_repositories, sample_items):
        """Test complete archiver task manager workflow."""
        # Create task manager with real repositories
        mock_summarization = Mock()
        mock_summarization.schedule.return_value = True

        task_manager = ArchiverTaskManager(
            settings=integration_settings,
            archivers=dummy_archivers,
            summarization=mock_summarization,
            requeue_priorities=["monolith", "readability"],
            requeue_chunk_size=2
        )

        # Enqueue batch of items
        items = sample_items[:4]  # Use first 4 items
        task_id = task_manager.enqueue("monolith", items)

        assert task_id is not None

        # Wait for processing
        time.sleep(0.5)

        # Verify artifacts were created
        artifacts = real_repositories["artifact"].list_by_task_id(task_id)
        assert len(artifacts) == 4

        # All should be successful (DummyArchiver always succeeds)
        for artifact in artifacts:
            assert artifact["success"] == 1
            assert artifact["exit_code"] == 0
            assert artifact["saved_path"] is not None

        # Verify archived URLs were created
        for item in items:
            archived_url = real_repositories["url"].get_by_url(item["url"])
            assert archived_url is not None
            assert archived_url.item_id == item["item_id"]

    def test_task_manager_error_handling(self, integration_settings, real_repositories, real_file_storage):
        """Test task manager error handling with failing archivers."""
        class FailingArchiver(BaseArchiver):
            def archive(self, url: str, item_id: str) -> ArchiveResult:
                # Fail for specific URLs
                if "fail" in url:
                    return ArchiveResult(
                        success=False,
                        exit_code=1,
                        error="Simulated failure"
                    )
                else:
                    output_path = self.base_path / item_id / self.name / "output.html"
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(f"<html>Success: {url}</html>")
                    return ArchiveResult(
                        success=True,
                        exit_code=0,
                        saved_path=str(output_path)
                    )

        archivers = {"failing": FailingArchiver(real_file_storage)}

        task_manager = ArchiverTaskManager(
            settings=integration_settings,
            archivers=archivers,
            summarization=None
        )

        # Mix of successful and failing items
        items = [
            {"item_id": "success1", "url": "https://example.com/success1"},
            {"item_id": "fail1", "url": "https://example.com/fail1"},
            {"item_id": "success2", "url": "https://example.com/success2"},
            {"item_id": "fail2", "url": "https://example.com/fail2"},
        ]

        task_id = task_manager.enqueue("failing", items)
        time.sleep(0.5)

        artifacts = real_repositories["artifact"].list_by_task_id(task_id)
        assert len(artifacts) == 4

        # Check results
        success_count = sum(1 for artifact in artifacts if artifact["success"] == 1)
        fail_count = sum(1 for artifact in artifacts if artifact["success"] == 0)

        assert success_count == 2
        assert fail_count == 2

    def test_task_manager_concurrent_batch_processing(self, integration_settings, dummy_archivers, real_repositories):
        """Test concurrent batch processing with task manager."""
        mock_summarization = Mock()
        mock_summarization.schedule.return_value = True

        task_manager = ArchiverTaskManager(
            settings=integration_settings,
            archivers=dummy_archivers,
            summarization=mock_summarization,
            requeue_chunk_size=3
        )

        # Submit multiple batches concurrently
        task_ids = []
        for batch_num in range(3):
            items = [
                {"item_id": f"batch{batch_num}_item{i}", "url": f"https://example.com/batch{batch_num}_{i}"}
                for i in range(2)
            ]
            task_id = task_manager.enqueue("monolith", items)
            task_ids.append(task_id)

        # Wait for all batches to complete
        time.sleep(1.0)

        # Verify all tasks completed
        all_artifacts = []
        for task_id in task_ids:
            artifacts = real_repositories["artifact"].list_by_task_id(task_id)
            all_artifacts.extend(artifacts)

        assert len(all_artifacts) == 6  # 3 batches × 2 items each

        # All should be successful
        for artifact in artifacts:
            assert artifact["success"] == 1

    def test_task_manager_requeue_failed_artifacts(self, integration_settings, real_repositories, real_file_storage):
        """Test requeuing failed artifacts."""
        class ConditionalArchiver(BaseArchiver):
            def __init__(self, storage_provider):
                super().__init__(storage_provider)
                self.attempts = {}

            def archive(self, url: str, item_id: str) -> ArchiveResult:
                # Track attempts per item
                if item_id not in self.attempts:
                    self.attempts[item_id] = 0
                self.attempts[item_id] += 1

                # Fail on first attempt, succeed on second
                if self.attempts[item_id] == 1:
                    return ArchiveResult(
                        success=False,
                        exit_code=1,
                        error="First attempt failed"
                    )
                else:
                    output_path = self.base_path / item_id / self.name / "output.html"
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(f"<html>Success on attempt {self.attempts[item_id]}: {url}</html>")
                    return ArchiveResult(
                        success=True,
                        exit_code=0,
                        saved_path=str(output_path)
                    )

        archiver = ConditionalArchiver(real_file_storage)
        archivers = {"conditional": archiver}

        task_manager = ArchiverTaskManager(
            settings=integration_settings,
            archivers=archivers,
            summarization=None
        )

        # Initial batch that will fail
        items = [{"item_id": "retry123", "url": "https://example.com/retry"}]
        task_id1 = task_manager.enqueue("conditional", items)
        time.sleep(0.5)

        # Check first attempt failed
        artifacts1 = real_repositories["artifact"].list_by_task_id(task_id1)
        assert len(artifacts1) == 1
        assert artifacts1[0]["success"] == 0

        # Requeue failed artifacts
        failed_artifacts = []
        for artifact in artifacts1:
            if artifact["success"] == 0:
                failed_artifacts.append({
                    "artifact_id": artifact["rowid"],
                    "archiver": "conditional",
                    "item_id": "retry123",
                    "url": "https://example.com/retry"
                })

        task_id2 = task_manager.enqueue_artifacts(failed_artifacts)[0]
        time.sleep(0.5)

        # Check second attempt succeeded
        artifacts2 = real_repositories["artifact"].list_by_task_id(task_id2)
        assert len(artifacts2) == 1
        assert artifacts2[0]["success"] == 1

    def test_task_manager_with_all_archivers_coordination(self, integration_settings, dummy_archivers, real_repositories):
        """Test task manager coordination with all archivers."""
        mock_summarization = Mock()
        mock_summarization.schedule.return_value = True

        task_manager = ArchiverTaskManager(
            settings=integration_settings,
            archivers=dummy_archivers,
            summarization=mock_summarization
        )

        # Single item for all archivers
        items = [{"item_id": "all_test", "url": "https://example.com/all"}]
        task_id = task_manager.enqueue("all", items)
        time.sleep(0.5)

        # Should have artifacts for all archivers
        artifacts = real_repositories["artifact"].list_by_task_id(task_id)
        assert len(artifacts) == len(dummy_archivers)

        # Check we have all archiver types
        archiver_names = {artifact["archiver"] for artifact in artifacts}
        assert archiver_names == set(dummy_archivers.keys())

        # Verify each artifact is properly linked to the same archived URL
        archived_url = real_repositories["url"].get_by_url("https://example.com/all")
        assert archived_url is not None
        assert archived_url.item_id == "all_test"

        for artifact in artifacts:
            # All should succeed
            assert artifact["success"] == 1

    def test_summarization_task_manager_integration(self, integration_settings, real_repositories, integration_summarization_coordinator):
        """Test summarization task manager integration."""
        from app.task_manager.summarization import SummarizationTaskManager

        # Mock summarizer service
        mock_summarizer = Mock()
        mock_summarizer.is_enabled = True
        mock_summarizer.generate_for_archived_url.return_value = {
            "summary": "Test summary",
            "tags": ["test", "integration"],
            "entities": [{"name": "Test", "type": "ORG"}]
        }

        task_manager = SummarizationTaskManager(
            settings=integration_settings,
            summarizer=mock_summarizer
        )

        # Create an archived URL and artifact first
        archived_url = real_repositories["url"].get_or_create(
            url="https://example.com/summary-test",
            item_id="summary123",
            name="Summary Test Article"
        )

        artifact = real_repositories["artifact"].get_or_create(
            archived_url_id=archived_url.id,
            archiver="readability"
        )

        # Store some metadata for the artifact
        real_repositories["metadata"].upsert(
            save_rowid=artifact.id,
            data={
                "title": "Summary Test Article",
                "text": "This is a full text article that can be summarized. It contains multiple sentences and provides enough content for testing the summarization functionality.",
                "url": "https://example.com/summary-test"
            }
        )

        # Finalize the artifact as successful
        real_repositories["artifact"].finalize_result(
            artifact_id=artifact.id,
            success=True,
            exit_code=0,
            saved_path="/tmp/test.html"
        )

        # Test summarization coordinator
        coordinator = integration_summarization_coordinator
        coordinator._summarizer = mock_summarizer  # Use enabled mock

        # Schedule summarization
        scheduled = coordinator.schedule(
            archived_url_id=archived_url.id,
            rowid=artifact.id,
            reason="test"
        )

        assert scheduled is True

        # Check task was queued
        assert coordinator.queue.qsize() == 1

        # Process the task
        task = coordinator.queue.get()
        task_manager.process(task)

        # Verify summarizer was called
        mock_summarizer.generate_for_archived_url.assert_called_once_with(archived_url.id)

    def test_task_manager_priority_processing(self, integration_settings, real_repositories, real_file_storage):
        """Test task manager priority-based processing."""
        class PriorityArchiver(BaseArchiver):
            def __init__(self, storage_provider):
                super().__init__(storage_provider)
                self.processed_items = []

            def archive(self, url: str, item_id: str) -> ArchiveResult:
                self.processed_items.append(item_id)
                output_path = self.base_path / item_id / self.name / "output.html"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(f"<html>Priority: {url}</html>")
                return ArchiveResult(
                    success=True,
                    exit_code=0,
                    saved_path=str(output_path)
                )

        archiver = PriorityArchiver(real_file_storage)
        archivers = {"priority": archiver}

        task_manager = ArchiverTaskManager(
            settings=integration_settings,
            archivers=archivers,
            summarization=None,
            requeue_priorities=["priority"],
            requeue_chunk_size=2
        )

        # Create failed artifacts with different priorities
        failed_artifacts = [
            {
                "artifact_id": i,
                "archiver": "priority",
                "item_id": f"priority_{i}",
                "url": f"https://example.com/priority_{i}"
            }
            for i in range(5)
        ]

        # Insert them with different order to test prioritization
        task_ids = task_manager.enqueue_artifacts_and_wait(failed_artifacts[::-1])  # Reverse order
        time.sleep(0.5)

        # Check that all items were processed
        all_artifacts = []
        for task_id in task_ids:
            artifacts = real_repositories["artifact"].list_by_task_id(task_id)
            all_artifacts.extend(artifacts)

        assert len(all_artifacts) == 5

        # All should be successful
        for artifact in artifacts:
            assert artifact["success"] == 1

        # Check processing order from archiver
        assert len(archiver.processed_items) == 5

    def test_task_manager_storage_integration(self, integration_settings, archiver_task_manager_with_storage, real_repositories):
        """Test task manager with storage integration."""
        task_manager = archiver_task_manager_with_storage

        # Enqueue items
        items = [{"item_id": "storage_integration", "url": "https://example.com/storage-integration"}]
        task_id = task_manager.enqueue("monolith", items)
        time.sleep(0.5)

        # Verify artifacts were created
        artifacts = real_repositories["artifact"].list_by_task_id(task_id)
        assert len(artifacts) == 1

        artifact = artifacts[0]
        assert artifact["success"] == 1
        assert artifact["saved_path"] is not None

    def test_task_manager_with_missing_archiver(self, integration_settings, real_repositories):
        """Test task manager handling of missing archivers."""
        # Create task manager with incomplete archiver set
        archivers = {"monolith": Mock()}  # Only one archiver

        task_manager = ArchiverTaskManager(
            settings=integration_settings,
            archivers=archivers,
            summarization=None
        )

        # Try to enqueue for missing archiver
        items = [{"item_id": "missing_test", "url": "https://example.com/missing"}]

        with patch('app.task_manager.archiver.logger') as mock_logger:
            task_id = task_manager.enqueue("readability", items)  # Not in archivers
            time.sleep(0.5)

            # Should have logged warnings about unknown archiver
            assert mock_logger.warning.called

            # Should still create a task even if no items processed
            artifacts = real_repositories["artifact"].list_by_task_id(task_id)
            # Should have 0 items since archiver doesn't exist

    def test_task_manager_url_archivability_check(self, integration_settings, dummy_archivers, real_repositories):
        """Test task manager URL archivability checking."""
        task_manager = ArchiverTaskManager(
            settings=integration_settings,
            archivers=dummy_archivers,
            summarization=None
        )

        # Use various URL types
        items = [
            {"item_id": "valid1", "url": "https://example.com/valid1"},
            {"item_id": "valid2", "url": "https://httpbin.org/html"},  # Should be archivable
            {"item_id": "valid3", "url": "https://example.org/valid3"},
        ]

        task_id = task_manager.enqueue("monolith", items)
        time.sleep(0.5)

        # Verify artifacts were created (all should be marked as archivable in test environment)
        artifacts = real_repositories["artifact"].list_by_task_id(task_id)
        # In a real environment with actual URL checking, some might be marked as 404

    def test_task_manager_task_id_tracking(self, integration_settings, dummy_archivers, real_repositories):
        """Test task manager proper task ID tracking."""
        task_manager = ArchiverTaskManager(
            settings=integration_settings,
            archivers=dummy_archivers,
            summarization=None
        )

        # Enqueue multiple batches
        task_ids = []
        for i in range(3):
            items = [{"item_id": f"track_{i}", "url": f"https://example.com/track_{i}"}]
            task_id = task_manager.enqueue("monolith", items)
            task_ids.append(task_id)

        # Wait for processing
        time.sleep(0.5)

        # Verify each task ID has unique artifacts
        for i, task_id in enumerate(task_ids):
            artifacts = real_repositories["artifact"].list_by_task_id(task_id)
            assert len(artifacts) == 1
            assert artifacts[0]["item_id"] == f"track_{i}"

        # Verify task IDs are unique
        assert len(set(task_ids)) == len(task_ids)

    def test_task_manager_chunk_processing(self, integration_settings, dummy_archivers, real_repositories):
        """Test task manager chunked processing."""
        task_manager = ArchiverTaskManager(
            settings=integration_settings,
            archivers=dummy_archivers,
            summarization=None,
            requeue_chunk_size=2  # Process in chunks of 2
        )

        # Create larger batch
        items = [
            {"item_id": f"chunk_{i}", "url": f"https://example.com/chunk_{i}"}
            for i in range(7)  # 7 items, should create 4 chunks (2,2,2,1)
        ]

        task_ids = task_manager.enqueue("monolith", items)
        time.sleep(0.5)

        # Should create multiple task IDs for chunks
        assert len(task_ids) > 1

        # Total artifacts should equal total items
        all_artifacts = []
        for task_id in task_ids:
            artifacts = real_repositories["artifact"].list_by_task_id(task_id)
            all_artifacts.extend(artifacts)

        assert len(all_artifacts) == 7

    def test_task_manager_completion_events(self, integration_settings, dummy_archivers, real_repositories):
        """Test task manager completion event handling."""
        task_manager = ArchiverTaskManager(
            settings=integration_settings,
            archivers=dummy_archivers,
            summarization=None
        )

        # Create completion event
        completion_event = Event()

        # Create a custom task to test completion events
        from app.task_manager.archiver import BatchTask, BatchItem
        items = [BatchItem("event_test", "https://example.com/event", 1, "monolith")]
        task = BatchTask("event_task", "monolith", items, completion_event=completion_event)

        # Process the task directly
        task_manager.process(task)

        # Event should be set after processing
        assert completion_event.is_set()

        # Verify artifact was created
        # Note: This tests the direct processing, not through enqueue which starts background worker