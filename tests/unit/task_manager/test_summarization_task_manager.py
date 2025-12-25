"""
Tests for the SummarizationTaskManager and SummarizationCoordinator.

Tests the summarization task processing functionality including task scheduling,
metadata validation, summarizer integration, and background processing.
"""

import queue
from unittest.mock import Mock, patch, MagicMock
from typing import Any, Optional

import pytest

from core.config import AppSettings
from app.task_manager.summarization import (
    SummarizationTaskManager,
    SummarizeTask,
    SummarizationCoordinator
)


class TestSummarizationTaskManager:
    """Test the SummarizationTaskManager class."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = Mock(spec=AppSettings)
        settings.data_dir = Mock()
        return settings

    @pytest.fixture
    def mock_summarizer(self):
        """Mock summarizer service."""
        summarizer = Mock()
        summarizer.is_enabled = True
        return summarizer

    @pytest.fixture
    def task_manager(self, mock_settings, mock_summarizer):
        """Create SummarizationTaskManager instance for testing."""
        return SummarizationTaskManager(
            settings=mock_settings,
            summarizer=mock_summarizer
        )

    def test_init_with_summarizer(self, mock_settings, mock_summarizer):
        """Test initialization with enabled summarizer."""
        manager = SummarizationTaskManager(
            settings=mock_settings,
            summarizer=mock_summarizer
        )

        assert manager.settings == mock_settings
        assert manager._summarizer == mock_summarizer
        assert isinstance(manager.queue, queue.Queue)

    def test_init_with_custom_queue(self, mock_settings, mock_summarizer):
        """Test initialization with custom task queue."""
        custom_queue = queue.Queue()
        manager = SummarizationTaskManager(
            settings=mock_settings,
            summarizer=mock_summarizer,
            task_queue=custom_queue
        )

        assert manager.queue is custom_queue

    def test_init_without_summarizer(self, mock_settings):
        """Test initialization without summarizer."""
        manager = SummarizationTaskManager(
            settings=mock_settings,
            summarizer=None
        )

        assert manager._summarizer is None

    def test_process_task_with_enabled_summarizer(self, task_manager, mock_summarizer):
        """Test process task when summarizer is enabled."""
        task = SummarizeTask(
            rowid=123,
            archived_url_id=456,
            reason="test"
        )

        task_manager.process(task)

        mock_summarizer.generate_for_archived_url.assert_called_once_with(456)

    def test_process_task_with_disabled_summarizer(self, mock_settings):
        """Test process task when summarizer is disabled."""
        mock_summarizer = Mock()
        mock_summarizer.is_enabled = False

        manager = SummarizationTaskManager(
            settings=mock_settings,
            summarizer=mock_summarizer
        )

        task = SummarizeTask(
            rowid=123,
            archived_url_id=456,
            reason="test"
        )

        # Should not raise exception
        manager.process(task)

        # Should not call generate_for_archived_url
        mock_summarizer.generate_for_archived_url.assert_not_called()

    def test_process_task_without_summarizer(self, mock_settings):
        """Test process task when no summarizer is set."""
        manager = SummarizationTaskManager(
            settings=mock_settings,
            summarizer=None
        )

        task = SummarizeTask(
            rowid=123,
            archived_url_id=456,
            reason="test"
        )

        # Should not raise exception
        manager.process(task)

    def test_process_task_summarizer_exception(self, task_manager, mock_summarizer):
        """Test process task handles summarizer exceptions gracefully."""
        mock_summarizer.generate_for_archived_url.side_effect = Exception("Summarization failed")

        task = SummarizeTask(
            rowid=123,
            archived_url_id=456,
            reason="test"
        )

        # Should not raise exception
        task_manager.process(task)


class TestSummarizationCoordinator:
    """Test the SummarizationCoordinator class."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = Mock(spec=AppSettings)
        settings.data_dir = Mock()
        return settings

    @pytest.fixture
    def mock_summarizer(self):
        """Mock summarizer service."""
        summarizer = Mock()
        summarizer.is_enabled = True
        return summarizer

    @pytest.fixture
    def coordinator(self, mock_settings, mock_summarizer):
        """Create SummarizationCoordinator instance for testing."""
        return SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer
        )

    def test_init_with_background_enabled(self, mock_settings, mock_summarizer):
        """Test initialization with background processing enabled."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            use_background=True
        )

        assert coordinator.settings == mock_settings
        assert coordinator._summarizer == mock_summarizer
        assert coordinator._use_background is True
        assert isinstance(coordinator.queue, queue.Queue)

    def test_init_with_background_disabled(self, mock_settings, mock_summarizer):
        """Test initialization with background processing disabled."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            use_background=False
        )

        assert coordinator._use_background is False

    def test_init_with_custom_queue(self, mock_settings, mock_summarizer):
        """Test initialization with custom queue."""
        custom_queue = queue.Queue()
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            task_queue=custom_queue
        )

        assert coordinator.queue is custom_queue

    def test_is_enabled_true(self, mock_settings, mock_summarizer):
        """Test is_enabled property when summarizer is enabled."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer
        )

        assert coordinator.is_enabled is True

    def test_is_enabled_false_disabled_summarizer(self, mock_settings):
        """Test is_enabled property when summarizer is disabled."""
        mock_summarizer = Mock()
        mock_summarizer.is_enabled = False

        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer
        )

        assert coordinator.is_enabled is False

    def test_is_enabled_false_no_summarizer(self, mock_settings):
        """Test is_enabled property when no summarizer is set."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=None
        )

        assert coordinator.is_enabled is False

    def test_schedule_with_disabled_summarizer(self, mock_settings):
        """Test schedule returns False when summarizer is disabled."""
        mock_summarizer = Mock()
        mock_summarizer.is_enabled = False

        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer
        )

        result = coordinator.schedule(
            archived_url_id=123,
            reason="test"
        )

        assert result is False

    def test_schedule_without_summarizer(self, mock_settings):
        """Test schedule returns False when no summarizer is set."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=None
        )

        result = coordinator.schedule(
            archived_url_id=123,
            reason="test"
        )

        assert result is False

    def test_schedule_inline_processing_enabled(self, mock_settings, mock_summarizer):
        """Test schedule processes inline when background is disabled."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            use_background=False
        )

        with patch('task_manager.summarization.ArchiveArtifactRepository') as mock_repo_class, \
             patch('task_manager.summarization.UrlMetadataRepository') as mock_metadata_class:

            # Mock metadata repository return
            mock_metadata = Mock()
            mock_metadata.text = "Sample article text content"
            mock_metadata_repo = Mock()
            mock_metadata_repo.get_by_archived_url.return_value = mock_metadata
            mock_metadata_class.return_value = mock_metadata_repo

            result = coordinator.schedule(
                archived_url_id=123,
                reason="test"
            )

            assert result is True
            mock_summarizer.generate_for_archived_url.assert_called_once_with(123)

    def test_schedule_inline_processing_force_inline(self, mock_settings, mock_summarizer):
        """Test schedule processes inline when force_inline is True."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            use_background=True
        )

        with patch('task_manager.summarization.ArchiveArtifactRepository') as mock_repo_class, \
             patch('task_manager.summarization.UrlMetadataRepository') as mock_metadata_class:

            # Mock metadata repository return
            mock_metadata = Mock()
            mock_metadata.text = "Sample article text content"
            mock_metadata_repo = Mock()
            mock_metadata_repo.get_by_archived_url.return_value = mock_metadata
            mock_metadata_class.return_value = mock_metadata_repo

            result = coordinator.schedule(
                archived_url_id=123,
                reason="test",
                force_inline=True
            )

            assert result is True
            mock_summarizer.generate_for_archived_url.assert_called_once_with(123)

    def test_schedule_background_processing(self, mock_settings, mock_summarizer):
        """Test schedule enqueues task for background processing."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            use_background=True
        )

        with patch('task_manager.summarization.ArchiveArtifactRepository') as mock_repo_class, \
             patch('task_manager.summarization.UrlMetadataRepository') as mock_metadata_class:

            # Mock metadata repository return
            mock_metadata = Mock()
            mock_metadata.text = "Sample article text content"
            mock_metadata_repo = Mock()
            mock_metadata_repo.get_by_archived_url.return_value = mock_metadata
            mock_metadata_class.return_value = mock_metadata_repo

            result = coordinator.schedule(
                archived_url_id=123,
                reason="test"
            )

            assert result is True
            # Should not call summarizer inline
            mock_summarizer.generate_for_archived_url.assert_not_called()

            # Check task was enqueued
            assert coordinator.queue.qsize() == 1

    def test_schedule_resolves_archived_url_id_from_rowid(self, mock_settings, mock_summarizer):
        """Test schedule resolves archived_url_id from rowid when needed."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            use_background=False
        )

        with patch('task_manager.summarization.ArchiveArtifactRepository') as mock_repo_class, \
             patch('task_manager.summarization.UrlMetadataRepository') as mock_metadata_class:

            # Mock artifact repository
            mock_artifact = Mock()
            mock_artifact.archived_url_id = 456
            mock_artifact_repo = Mock()
            mock_artifact_repo.get_by_id.return_value = mock_artifact
            mock_repo_class.return_value = mock_artifact_repo

            # Mock metadata repository
            mock_metadata = Mock()
            mock_metadata.text = "Sample article text content"
            mock_metadata_repo = Mock()
            mock_metadata_repo.get_by_archived_url.return_value = mock_metadata
            mock_metadata_class.return_value = mock_metadata_repo

            result = coordinator.schedule(
                rowid=123,
                reason="test"
            )

            assert result is True
            mock_artifact_repo.get_by_id.assert_called_once_with(123)
            mock_metadata_repo.get_by_archived_url.assert_called_once_with(456)

    def test_schedule_missing_artifact(self, mock_settings, mock_summarizer):
        """Test schedule returns False when artifact is not found."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            use_background=False
        )

        with patch('task_manager.summarization.ArchiveArtifactRepository') as mock_repo_class:
            mock_artifact_repo = Mock()
            mock_artifact_repo.get_by_id.return_value = None
            mock_repo_class.return_value = mock_artifact_repo

            result = coordinator.schedule(
                rowid=123,
                reason="test"
            )

            assert result is False

    def test_schedule_missing_archived_url_id(self, mock_settings, mock_summarizer):
        """Test schedule returns False when archived_url_id cannot be resolved."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            use_background=False
        )

        with patch('task_manager.summarization.ArchiveArtifactRepository') as mock_repo_class:
            # Mock artifact with None archived_url_id
            mock_artifact = Mock()
            mock_artifact.archived_url_id = None
            mock_artifact_repo = Mock()
            mock_artifact_repo.get_by_id.return_value = mock_artifact
            mock_repo_class.return_value = mock_artifact_repo

            result = coordinator.schedule(
                rowid=123,
                reason="test"
            )

            assert result is False

    def test_schedule_missing_metadata(self, mock_settings, mock_summarizer):
        """Test schedule returns False when metadata is not available."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            use_background=False
        )

        with patch('task_manager.summarization.ArchiveArtifactRepository') as mock_repo_class, \
             patch('task_manager.summarization.UrlMetadataRepository') as mock_metadata_class:

            # Mock artifact repository
            mock_artifact = Mock()
            mock_artifact.archived_url_id = 456
            mock_artifact_repo = Mock()
            mock_artifact_repo.get_by_id.return_value = mock_artifact
            mock_repo_class.return_value = mock_artifact_repo

            # Mock missing metadata
            mock_metadata_repo = Mock()
            mock_metadata_repo.get_by_archived_url.return_value = None
            mock_metadata_class.return_value = mock_metadata_repo

            result = coordinator.schedule(
                archived_url_id=456,
                reason="test"
            )

            assert result is False

    def test_schedule_empty_metadata_text(self, mock_settings, mock_summarizer):
        """Test schedule returns False when metadata text is empty."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            use_background=False
        )

        with patch('task_manager.summarization.ArchiveArtifactRepository') as mock_repo_class, \
             patch('task_manager.summarization.UrlMetadataRepository') as mock_metadata_class:

            # Mock metadata with empty text
            mock_metadata = Mock()
            mock_metadata.text = ""  # Empty string
            mock_metadata_repo = Mock()
            mock_metadata_repo.get_by_archived_url.return_value = mock_metadata
            mock_metadata_class.return_value = mock_metadata_repo

            result = coordinator.schedule(
                archived_url_id=123,
                reason="test"
            )

            assert result is False

    def test_schedule_whitespace_only_metadata_text(self, mock_settings, mock_summarizer):
        """Test schedule returns False when metadata text contains only whitespace."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            use_background=False
        )

        with patch('task_manager.summarization.ArchiveArtifactRepository') as mock_repo_class, \
             patch('task_manager.summarization.UrlMetadataRepository') as mock_metadata_class:

            # Mock metadata with whitespace-only text
            mock_metadata = Mock()
            mock_metadata.text = "   \n\t  "  # Only whitespace
            mock_metadata_repo = Mock()
            mock_metadata_repo.get_by_archived_url.return_value = mock_metadata
            mock_metadata_class.return_value = mock_metadata_repo

            result = coordinator.schedule(
                archived_url_id=123,
                reason="test"
            )

            assert result is False

    def test_schedule_none_metadata_text(self, mock_settings, mock_summarizer):
        """Test schedule returns False when metadata text is None."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            use_background=False
        )

        with patch('task_manager.summarization.ArchiveArtifactRepository') as mock_repo_class, \
             patch('task_manager.summarization.UrlMetadataRepository') as mock_metadata_class:

            # Mock metadata with None text
            mock_metadata = Mock()
            mock_metadata.text = None
            mock_metadata_repo = Mock()
            mock_metadata_repo.get_by_archived_url.return_value = mock_metadata
            mock_metadata_class.return_value = mock_metadata_repo

            result = coordinator.schedule(
                archived_url_id=123,
                reason="test"
            )

            assert result is False

    def test_schedule_exception_handling(self, mock_settings, mock_summarizer):
        """Test schedule handles exceptions gracefully."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            use_background=False
        )

        with patch('task_manager.summarization.ArchiveArtifactRepository') as mock_repo_class:
            mock_repo_class.side_effect = Exception("Database error")

            result = coordinator.schedule(
                archived_url_id=123,
                reason="test"
            )

            assert result is False

    def test_schedule_default_reason(self, mock_settings, mock_summarizer):
        """Test schedule uses default reason when none provided."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            use_background=False
        )

        with patch('task_manager.summarization.ArchiveArtifactRepository') as mock_repo_class, \
             patch('task_manager.summarization.UrlMetadataRepository') as mock_metadata_class:

            # Mock metadata repository return
            mock_metadata = Mock()
            mock_metadata.text = "Sample article text content"
            mock_metadata_repo = Mock()
            mock_metadata_repo.get_by_archived_url.return_value = mock_metadata
            mock_metadata_class.return_value = mock_metadata_repo

            result = coordinator.schedule(
                archived_url_id=123
                # No reason provided
            )

            assert result is True

    def test_schedule_with_both_ids_and_reason(self, mock_settings, mock_summarizer):
        """Test schedule with both rowid and archived_url_id provided."""
        coordinator = SummarizationCoordinator(
            settings=mock_settings,
            summarizer=mock_summarizer,
            use_background=False
        )

        with patch('task_manager.summarization.ArchiveArtifactRepository') as mock_repo_class, \
             patch('task_manager.summarization.UrlMetadataRepository') as mock_metadata_class:

            # Mock metadata repository return
            mock_metadata = Mock()
            mock_metadata.text = "Sample article text content"
            mock_metadata_repo = Mock()
            mock_metadata_repo.get_by_archived_url.return_value = mock_metadata
            mock_metadata_class.return_value = mock_metadata_repo

            result = coordinator.schedule(
                rowid=123,
                archived_url_id=456,
                reason="custom_reason"
            )

            assert result is True
            # Should use the provided archived_url_id, not resolve from rowid
            mock_metadata_repo.get_by_archived_url.assert_called_once_with(456)