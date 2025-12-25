"""
Fake task manager for testing.

SyncTaskManager provides synchronous task processing for deterministic tests.
"""

from __future__ import annotations

import logging
from typing import TypeVar, Generic, Callable, Optional

from task_manager.base import BackgroundTaskManager

logger = logging.getLogger(__name__)

TaskT = TypeVar("TaskT")


class SyncTaskManager(BackgroundTaskManager, Generic[TaskT]):
    """
    Synchronous task manager for testing.

    Processes tasks immediately in the calling thread instead of queuing
    them for background processing. This makes tests fast and deterministic.

    Features:
    - No threading (immediate processing)
    - Records all processed tasks for assertions
    - No waiting/polling needed in tests

    Usage:
        sync_manager = SyncTaskManager()
        sync_manager.submit(task)
        # Task processed immediately
        assert len(sync_manager.processed_tasks) == 1
        assert sync_manager.processed_tasks[0] == task
    """

    def __init__(self, process_fn: Optional[Callable[[TaskT], None]] = None):
        """
        Initialize synchronous task manager.

        Args:
            process_fn: Optional function to process tasks.
                       If not provided, must override process() method.
        """
        super().__init__()
        self._process_fn = process_fn
        self.processed_tasks: list[TaskT] = []
        self.failed_tasks: list[tuple[TaskT, Exception]] = []

    def start(self) -> None:
        """No-op: synchronous manager is always "running"."""
        # Don't start any threads
        pass

    def submit(self, task: TaskT) -> None:
        """Process task immediately instead of queuing."""
        logger.debug(f"SyncTaskManager processing task immediately: {task}")

        try:
            if self._process_fn:
                self._process_fn(task)
            else:
                self.process(task)

            self.processed_tasks.append(task)
            logger.debug(f"Task processed successfully: {task}")

        except Exception as e:
            logger.error(f"Task failed: {task}, error: {e}")
            self.failed_tasks.append((task, e))
            raise

    def process(self, task: TaskT) -> None:
        """
        Process a single task (must be overridden if process_fn not provided).

        Args:
            task: Task to process

        Raises:
            NotImplementedError: If not overridden and no process_fn provided
        """
        if self._process_fn is None:
            raise NotImplementedError(
                "Either override process() or provide process_fn to constructor"
            )

    # Helper methods for testing

    def clear(self):
        """Clear processed and failed task history."""
        self.processed_tasks.clear()
        self.failed_tasks.clear()

    def get_processed_count(self) -> int:
        """Get number of successfully processed tasks."""
        return len(self.processed_tasks)

    def get_failed_count(self) -> int:
        """Get number of failed tasks."""
        return len(self.failed_tasks)

    def has_processed(self, task: TaskT) -> bool:
        """Check if a specific task was processed."""
        return task in self.processed_tasks

    def get_last_processed(self) -> Optional[TaskT]:
        """Get the last successfully processed task."""
        return self.processed_tasks[-1] if self.processed_tasks else None
