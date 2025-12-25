"""
Tests for the ArchiverTaskManager.

Tests the archiver task processing functionality including task enqueuing,
URL rewriting, paywall handling, artifact management, and summary scheduling.
"""

import uuid
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from threading import Event
from typing import Any, Dict, List

import pytest

from core.config import AppSettings
from models import ArchiveResult
from app.task_manager.archiver import (
    ArchiverTaskManager,
    BatchTask,
    BatchItem,
    DEFAULT_REQUEUE_PRIORITIES,
    DEFAULT_REQUEUE_CHUNK_SIZE
)


class TestArchiverTaskManager:
    """Test the ArchiverTaskManager class."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = Mock(spec=AppSettings)
        settings.data_dir = Path("/tmp/test_data")
        settings.database = Mock()
        settings.database.resolved_path.return_value = "sqlite:///test.db"
        settings.skip_existing_saves = False
        settings.enable_storage_integration = False
        settings.summary_source_archivers = ["readability", "monolith"]
        return settings

    @pytest.fixture
    def mock_archivers(self):
        """Mock archivers for testing."""
        return {
            "monolith": Mock(),
            "readability": Mock(),
            "singlefile-cli": Mock()
        }

    @pytest.fixture
    def mock_summarization(self):
        """Mock summarization coordinator."""
        return Mock()

    @pytest.fixture
    def task_manager(self, mock_settings, mock_archivers, mock_summarization):
        """Create ArchiverTaskManager instance for testing."""
        with patch('task_manager.archiver.ArchiveArtifactRepository'), \
             patch('task_manager.archiver.ArchivedUrlRepository'), \
             patch('task_manager.archiver.UrlMetadataRepository'):
            return ArchiverTaskManager(
                settings=mock_settings,
                archivers=mock_archivers,
                summarization=mock_summarization
            )

    def test_init_default_values(self, mock_settings, mock_archivers):
        """Test initialization with default values."""
        with patch('task_manager.archiver.ArchiveArtifactRepository'), \
             patch('task_manager.archiver.ArchivedUrlRepository'), \
             patch('task_manager.archiver.UrlMetadataRepository'):
            manager = ArchiverTaskManager(
                settings=mock_settings,
                archivers=mock_archivers
            )

            assert manager.settings == mock_settings
            assert manager.archivers == mock_archivers
            assert manager._summarization is None
            assert manager.requeue_priorities == list(DEFAULT_REQUEUE_PRIORITIES)
            assert manager.requeue_chunk_size == DEFAULT_REQUEUE_CHUNK_SIZE
            assert manager.summary_source_archivers == {"readability", "monolith"}

    def test_init_custom_values(self, mock_settings, mock_archivers, mock_summarization):
        """Test initialization with custom values."""
        custom_priorities = ["monolith", "readability"]
        custom_chunk_size = 20

        with patch('task_manager.archiver.ArchiveArtifactRepository'), \
             patch('task_manager.archiver.ArchivedUrlRepository'), \
             patch('task_manager.archiver.UrlMetadataRepository'):
            manager = ArchiverTaskManager(
                settings=mock_settings,
                archivers=mock_archivers,
                summarization=mock_summarization,
                requeue_priorities=custom_priorities,
                requeue_chunk_size=custom_chunk_size
            )

            assert manager._summarization == mock_summarization
            assert manager.requeue_priorities == custom_priorities
            assert manager.requeue_chunk_size == custom_chunk_size

    def test_insert_pending_artifact(self, task_manager):
        """Test _insert_pending_artifact creates pending records."""
        with patch.object(task_manager.url_repo, 'get_or_create') as mock_get_url, \
             patch.object(task_manager.artifact_repo, 'get_or_create') as mock_get_artifact:

            mock_url = Mock()
            mock_url.id = 123
            mock_get_url.return_value = mock_url

            mock_artifact = Mock()
            mock_artifact.id = 456
            mock_get_artifact.return_value = mock_artifact

            result = task_manager._insert_pending_artifact(
                item_id="test123",
                url="https://example.com",
                task_id="task789",
                archiver_name="monolith",
                name="Test Article"
            )

            mock_get_url.assert_called_once_with(
                url="https://example.com",
                item_id="test123",
                name="Test Article"
            )
            mock_get_artifact.assert_called_once_with(
                archived_url_id=123,
                archiver="monolith",
                task_id="task789"
            )
            assert result == 456

    def test_enqueue_single_archiver(self, task_manager):
        """Test enqueue with single archiver."""
        items = [
            {"item_id": "test1", "url": "https://example1.com"},
            {"item_id": "test2", "url": "https://example2.com"}
        ]

        with patch.object(task_manager, '_insert_pending_artifact') as mock_insert, \
             patch.object(task_manager, 'submit') as mock_submit:
            mock_insert.return_value = 1

            task_id = task_manager.enqueue("monolith", items)

            assert len(task_id) == 32  # UUID hex length
            mock_submit.assert_called_once()

            # Check submit call arguments
            call_args = mock_submit.call_args[0][0]
            assert isinstance(call_args, BatchTask)
            assert call_args.archiver_name == "monolith"
            assert len(call_args.items) == 2

    def test_enqueue_all_archivers(self, task_manager):
        """Test enqueue with 'all' archivers."""
        items = [{"item_id": "test1", "url": "https://example.com"}]

        with patch.object(task_manager, '_insert_pending_artifact') as mock_insert, \
             patch.object(task_manager, 'submit') as mock_submit:
            mock_insert.return_value = 1

            task_id = task_manager.enqueue("all", items)

            assert task_id is not None
            mock_submit.assert_called_once()

            # Should create items for each archiver
            call_args = mock_submit.call_args[0][0]
            assert len(call_args.items) == len(task_manager.archivers)

    def test_enqueue_with_skip_existing_saves(self, task_manager):
        """Test enqueue respects skip_existing_saves setting."""
        task_manager.settings.skip_existing_saves = True
        items = [{"item_id": "test1", "url": "https://example.com"}]

        with patch.object(task_manager.artifact_repo, 'find_successful') as mock_find, \
             patch.object(task_manager, '_insert_pending_artifact') as mock_insert, \
             patch.object(task_manager, 'submit') as mock_submit:

            # Simulate existing save found
            mock_find.return_value = Mock()
            mock_insert.return_value = 1

            task_id = task_manager.enqueue("monolith", items)

            # Should not insert new artifact since existing was found
            mock_insert.assert_not_called()
            mock_submit.assert_called_once()

            # Check that task has no items (all skipped)
            call_args = mock_submit.call_args[0][0]
            assert len(call_args.items) == 0

    def test_enqueue_with_url_rewriting(self, task_manager):
        """Test enqueue handles paywall URL rewriting."""
        items = [{"item_id": "test1", "url": "https://medium.com/article"}]

        with patch('task_manager.archiver.rewrite_paywalled_url') as mock_rewrite, \
             patch.object(task_manager, '_insert_pending_artifact') as mock_insert, \
             patch.object(task_manager, 'submit') as mock_submit:

            mock_rewrite.return_value = "https://freedium.cfd/https://medium.com/article"
            mock_insert.return_value = 1

            task_id = task_manager.enqueue("monolith", items)

            mock_rewrite.assert_called_once_with("https://medium.com/article")

            # Check BatchItem has rewritten_url
            call_args = mock_submit.call_args[0][0]
            assert len(call_args.items) == 1
            assert call_args.items[0].url == "https://medium.com/article"  # Original
            assert call_args.items[0].rewritten_url == "https://freedium.cfd/https://medium.com/article"

    def test_process_batch_task(self, task_manager):
        """Test process method handles BatchTask correctly."""
        items = [
            BatchItem("test1", "https://example1.com", 1, "monolith"),
            BatchItem("test2", "https://example2.com", 2, "readability")
        ]
        task = BatchTask("task123", "monolith", items)

        with patch.object(task_manager, '_process_item') as mock_process_item:
            task_manager.process(task)

            assert mock_process_item.call_count == 2
            mock_process_item.assert_any_call(task_id="task123", item=items[0])
            mock_process_item.assert_any_call(task_id="task123", item=items[1])

    def test_process_batch_task_with_completion_event(self, task_manager):
        """Test process method handles completion event."""
        event = Event()
        items = [BatchItem("test1", "https://example.com", 1, "monolith")]
        task = BatchTask("task123", "monolith", items, completion_event=event)

        with patch.object(task_manager, '_process_item'):
            task_manager.process(task)

            # Event should be set after processing
            assert event.is_set()

    def test_process_item_missing_archiver(self, task_manager):
        """Test _process_item handles missing archiver."""
        item = BatchItem("test1", "https://example.com", 1, "unknown_archiver")

        with patch.object(task_manager, '_finalize_missing_archiver') as mock_finalize:
            task_manager._process_item(task_id="task123", item=item)

            mock_finalize.assert_called_once_with(item)

    def test_process_item_url_not_archivable(self, task_manager):
        """Test _process_item handles non-archivable URLs."""
        item = BatchItem("test1", "https://404.example.com", 1, "monolith")

        with patch('task_manager.archiver.check_url_archivability') as mock_check, \
             patch.object(task_manager.artifact_repo, 'finalize_result') as mock_finalize:

            mock_check.return_value = Mock(should_archive=False, status_code=404)

            result = task_manager._process_item(task_id="task123", item=item)

            mock_finalize.assert_called_once()
            assert mock_finalize.call_args[1]['exit_code'] == 404

    def test_process_item_reuse_existing_save(self, task_manager):
        """Test _process_item reuses existing saves when enabled."""
        task_manager.settings.skip_existing_saves = True
        item = BatchItem("test1", "https://example.com", 1, "monolith")

        with patch('task_manager.archiver.check_url_archivability') as mock_check, \
             patch.object(task_manager, '_reuse_existing_save') as mock_reuse:

            mock_check.return_value = Mock(should_archive=True)
            mock_reuse.return_value = True

            result = task_manager._process_item(task_id="task123", item=item)

            mock_reuse.assert_called_once_with(item=item, archiver=task_manager.archivers["monolith"])

    def test_process_item_successful_archiving(self, task_manager):
        """Test _process_item handles successful archiving."""
        item = BatchItem("test1", "https://example.com", 1, "monolith")
        archiver = task_manager.archivers["monolith"]

        mock_result = ArchiveResult(
            success=True,
            exit_code=0,
            saved_path="/tmp/test.html",
            start_time=0,
            end_time=1
        )
        archiver.archive.return_value = mock_result

        with patch('task_manager.archiver.check_url_archivability') as mock_check, \
             patch.object(task_manager, '_record_result') as mock_record:
            mock_check.return_value = Mock(should_archive=True)

            task_manager._process_item(task_id="task123", item=item)

            archiver.archive.assert_called_once_with(url="https://example.com", item_id="test1")
            mock_record.assert_called_once_with(item=item, result=mock_result)

    def test_process_item_storage_integration(self, task_manager):
        """Test _process_item uses storage integration when enabled."""
        task_manager.settings.enable_storage_integration = True
        item = BatchItem("test1", "https://example.com", 1, "monolith")
        archiver = task_manager.archivers["monolith"]

        mock_result = ArchiveResult(
            success=True,
            exit_code=0,
            saved_path="/tmp/test.html",
            start_time=0,
            end_time=1
        )
        archiver.archive_with_storage.return_value = mock_result

        with patch('task_manager.archiver.check_url_archivability') as mock_check, \
             patch.object(task_manager, '_record_result') as mock_record:
            mock_check.return_value = Mock(should_archive=True)

            task_manager._process_item(task_id="task123", item=item)

            archiver.archive_with_storage.assert_called_once_with(url="https://example.com", item_id="test1")
            archiver.archive.assert_not_called()

    def test_process_item_archiver_exception(self, task_manager):
        """Test _process_item handles archiver exceptions."""
        item = BatchItem("test1", "https://example.com", 1, "monolith")
        archiver = task_manager.archivers["monolith"]
        archiver.archive.side_effect = Exception("Test error")

        with patch('task_manager.archiver.check_url_archivability') as mock_check, \
             patch.object(task_manager, '_handle_archiver_exception') as mock_handle:
            mock_check.return_value = Mock(should_archive=True)

            task_manager._process_item(task_id="task123", item=item)

            mock_handle.assert_called_once_with(item=item, error=archiver.archive.side_effect)

    def test_reuse_existing_save_found_in_db(self, task_manager):
        """Test _reuse_existing_save finds existing save in database."""
        item = BatchItem("test1", "https://example.com", 1, "monolith")
        archiver = task_manager.archivers["monolith"]

        with patch.object(task_manager.artifact_repo, 'find_successful') as mock_find, \
             patch.object(task_manager.artifact_repo, 'finalize_result') as mock_finalize, \
             patch.object(task_manager, '_schedule_summary') as mock_schedule, \
             patch('pathlib.Path.exists') as mock_exists:

            # Simulate existing artifact found
            mock_existing = Mock()
            mock_existing.saved_path = "/tmp/existing.html"
            mock_existing.archived_url_id = 123
            mock_find.return_value = mock_existing
            mock_exists.return_value = True

            result = task_manager._reuse_existing_save(item=item, archiver=archiver)

            assert result is True
            mock_finalize.assert_called_once_with(
                rowid=1,
                success=True,
                exit_code=0,
                saved_path="/tmp/existing.html"
            )
            mock_schedule.assert_called_once()

    def test_reuse_existing_save_found_on_disk(self, task_manager):
        """Test _reuse_existing_save finds existing save on disk."""
        item = BatchItem("test1", "https://example.com", 1, "monolith")
        archiver = task_manager.archivers["monolith"]

        with patch.object(task_manager.artifact_repo, 'find_successful') as mock_find, \
             patch.object(task_manager.artifact_repo, 'finalize_result') as mock_finalize, \
             patch('pathlib.Path.exists') as mock_exists:

            # No existing in database
            mock_find.return_value = None

            # Found on disk
            archiver.has_existing_output.return_value = Path("/tmp/existing.html")
            mock_exists.return_value = True

            result = task_manager._reuse_existing_save(item=item, archiver=archiver)

            assert result is True
            archiver.has_existing_output.assert_called_once_with("test1")
            mock_finalize.assert_called_once()

    def test_record_result_success(self, task_manager):
        """Test _record_result handles successful results."""
        item = BatchItem("test1", "https://example.com", 1, "monolith")
        result = ArchiveResult(
            success=True,
            exit_code=0,
            saved_path="/tmp/test.html",
            start_time=0,
            end_time=1
        )

        with patch.object(task_manager.artifact_repo, 'get_by_id') as mock_get, \
             patch.object(task_manager.artifact_repo, 'finalize_result') as mock_finalize, \
             patch.object(task_manager.url_repo, 'update_total_size') as mock_update_size, \
             patch('task_manager.archiver.get_directory_size') as mock_get_size, \
             patch('pathlib.Path.exists') as mock_exists:

            mock_artifact = Mock()
            mock_artifact.archived_url_id = 123
            mock_get.return_value = mock_artifact
            mock_exists.return_value = True
            mock_get_size.return_value = 1024

            task_manager._record_result(item=item, result=result)

            mock_finalize.assert_called_once_with(
                rowid=1,
                success=True,
                exit_code=0,
                saved_path="/tmp/test.html",
                size_bytes=1024
            )
            mock_update_size.assert_called_once_with(archived_url_id=123)

    def test_record_result_readability_metadata(self, task_manager):
        """Test _record_result stores readability metadata."""
        item = BatchItem("test1", "https://example.com", 1, "readability")
        result = ArchiveResult(
            success=True,
            exit_code=0,
            saved_path="/tmp/test.html",
            start_time=0,
            end_time=1,
            metadata={"title": "Test Title", "text": "Test content"}
        )

        with patch.object(task_manager.artifact_repo, 'finalize_result'), \
             patch.object(task_manager.metadata_repo, 'upsert') as mock_upsert:

            task_manager._record_result(item=item, result=result)

            mock_upsert.assert_called_once_with(
                save_rowid=1,
                data={"title": "Test Title", "text": "Test content"}
            )

    def test_record_result_schedules_summary(self, task_manager, mock_summarization):
        """Test _record_result schedules summary for successful results."""
        item = BatchItem("test1", "https://example.com", 1, "readability")
        result = ArchiveResult(
            success=True,
            exit_code=0,
            saved_path="/tmp/test.html",
            start_time=0,
            end_time=1
        )

        with patch.object(task_manager.artifact_repo, 'get_by_id') as mock_get, \
             patch.object(task_manager.artifact_repo, 'finalize_result'):
            mock_artifact = Mock()
            mock_artifact.archived_url_id = 123
            mock_get.return_value = mock_artifact

            task_manager._record_result(item=item, result=result)

            mock_summarization.schedule.assert_called_once_with(
                archived_url_id=123,
                rowid=1,
                source="readability",
                reason="task-readability"
            )

    def test_schedule_summary_skips_non_source_archivers(self, task_manager, mock_summarization):
        """Test _schedule_summary skips non-configured archivers."""
        task_manager._schedule_summary(
            archived_url_id=123,
            rowid=1,
            source="screenshot",  # Not in summary_source_archivers
            reason="test"
        )

        mock_summarization.schedule.assert_not_called()

    def test_schedule_summary_with_missing_summarization(self, task_manager):
        """Test _schedule_summary handles missing summarization manager."""
        task_manager._summarization = None

        # Should not raise exception
        task_manager._schedule_summary(
            archived_url_id=123,
            rowid=1,
            source="readability",
            reason="test"
        )

    def test_resolve_priorities_with_custom_priorities(self, task_manager):
        """Test _resolve_priorities with custom priorities."""
        custom_priorities = ["custom1", "custom2", ""]
        result = task_manager._resolve_priorities(custom_priorities)

        assert result == ["custom1", "custom2"]

    def test_resolve_priorities_with_none(self, task_manager):
        """Test _resolve_priorities with None."""
        result = task_manager._resolve_priorities(None)

        assert result == task_manager.requeue_priorities

    def test_enqueue_artifacts(self, task_manager):
        """Test enqueue_artifacts method."""
        artifacts = [
            {"archiver": "monolith", "url": "https://example.com", "artifact_id": 1},
            {"archiver": "readability", "url": "https://example.org", "artifact_id": 2}
        ]

        with patch.object(task_manager, '_submit_artifact_records') as mock_submit:
            mock_submit.return_value = ["task1", "task2"]

            result = task_manager.enqueue_artifacts(artifacts)

            assert result == ["task1", "task2"]
            mock_submit.assert_called_once_with(
                artifacts,
                wait_for_completion=False,
                priorities=None
            )

    def test_enqueue_artifacts_unknown_archiver(self, task_manager):
        """Test enqueue_artifacts handles unknown archivers."""
        artifacts = [
            {"archiver": "unknown", "url": "https://example.com", "artifact_id": 1}
        ]

        with patch.object(task_manager, '_submit_artifact_records') as mock_submit, \
             patch.object(task_manager.artifact_repo, 'finalize_result') as mock_finalize:
            mock_submit.return_value = []

            result = task_manager.enqueue_artifacts(artifacts)

            assert result == []
            mock_finalize.assert_called_once_with(
                rowid=1,
                success=False,
                exit_code=127,
                saved_path=None
            )

    def test_resume_pending_artifacts(self, task_manager):
        """Test resume_pending_artifacts method."""
        with patch.object(task_manager.artifact_repo, 'list_by_status') as mock_list, \
             patch.object(task_manager, 'enqueue_artifacts_and_wait') as mock_enqueue:

            mock_schemas = [
                Mock(spec=dict),
                Mock(spec=dict)
            ]
            mock_schemas[0].model_dump.return_value = {"archiver": "monolith", "artifact_id": 1}
            mock_schemas[1].model_dump.return_value = {"archiver": "readability", "artifact_id": 2}
            mock_list.return_value = mock_schemas
            mock_enqueue.return_value = ["task1", "task2"]

            result = task_manager.resume_pending_artifacts()

            assert result == ["task1", "task2"]
            mock_list.assert_called_once_with(["pending"])
            mock_enqueue.assert_called_once()

    def test_resume_pending_artifacts_custom_statuses(self, task_manager):
        """Test resume_pending_artifacts with custom statuses."""
        with patch.object(task_manager.artifact_repo, 'list_by_status') as mock_list, \
             patch.object(task_manager, 'enqueue_artifacts_and_wait') as mock_enqueue:

            mock_list.return_value = []
            mock_enqueue.return_value = []

            result = task_manager.resume_pending_artifacts(statuses=["pending", "failed"])

            assert result == []
            mock_list.assert_called_once_with(["pending", "failed"])

    def test_resume_pending_artifacts_no_statuses(self, task_manager):
        """Test resume_pending_artifacts with no statuses returns empty."""
        result = task_manager.resume_pending_artifacts(statuses=[])

        assert result == []

    def test_enqueue_artifacts_and_wait(self, task_manager):
        """Test enqueue_artifacts_and_wait method."""
        artifacts = [
            {"archiver": "monolith", "artifact_id": 1},
            {"archiver": "readability", "artifact_id": 2}
        ]

        with patch.object(task_manager, '_submit_artifact_records') as mock_submit:
            mock_submit.return_value = ["task1", "task2"]

            result = task_manager.enqueue_artifacts_and_wait(
                artifacts,
                chunk_size=5,
                priorities=["monolith", "readability"]
            )

            assert result == ["task1", "task2"]
            mock_submit.assert_called_once()

    def test_handle_archiver_exception(self, task_manager):
        """Test _handle_archiver_exception method."""
        item = BatchItem("test1", "https://example.com", 1, "monolith")
        error = Exception("Test error")

        with patch.object(task_manager.artifact_repo, 'finalize_result') as mock_finalize:
            task_manager._handle_archiver_exception(item=item, error=error)

            mock_finalize.assert_called_once_with(
                rowid=1,
                success=False,
                exit_code=1,
                saved_path=None
            )