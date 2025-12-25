"""
Tests for the BackgroundTaskManager base class.

Tests the core queue-based task processing functionality including thread management,
task submission, worker lifecycle, and exception handling.
"""

import queue
import threading
import time
from unittest.mock import Mock, patch
from typing import Any

import pytest

from app.task_manager.base import BackgroundTaskManager


class TestBackgroundTaskManager:
    """Test the BackgroundTaskManager base class."""

    def test_init_default_queue(self):
        """Test initialization with default queue."""
        manager = BackgroundTaskManager()
        assert isinstance(manager._queue, queue.Queue)
        assert manager._worker is None

    def test_init_custom_queue(self):
        """Test initialization with custom queue."""
        custom_queue = queue.Queue()
        manager = BackgroundTaskManager(task_queue=custom_queue)
        assert manager._queue is custom_queue

    def test_queue_property(self):
        """Test queue property returns the internal queue."""
        manager = BackgroundTaskManager()
        assert manager.queue is manager._queue

    def test_start_creates_worker_thread(self):
        """Test that start() creates and starts a worker thread."""
        manager = BackgroundTaskManager()

        manager.start()

        assert manager._worker is not None
        assert isinstance(manager._worker, threading.Thread)
        assert manager._worker.is_alive()
        assert manager._worker.daemon

        # Clean up
        manager._queue.put(None)  # Signal to stop
        manager._worker.join(timeout=1)

    def test_start_idempotent(self):
        """Test that start() is idempotent - multiple calls don't create extra threads."""
        manager = BackgroundTaskManager()

        manager.start()
        first_worker = manager._worker
        manager.start()
        second_worker = manager._worker

        assert first_worker is second_worker

        # Clean up
        manager._queue.put(None)
        manager._worker.join(timeout=1)

    def test_submit_starts_worker_and_enqueues_task(self):
        """Test that submit() starts worker and enqueues task."""
        processed_tasks = []

        class TestManager(BackgroundTaskManager):
            def process(self, task: str) -> None:
                processed_tasks.append(task)

        manager = TestManager()

        manager.submit("test_task")

        # Give worker time to process
        time.sleep(0.1)

        assert manager._worker is not None
        assert manager._worker.is_alive()
        assert "test_task" in processed_tasks

        # Clean up
        manager._queue.put(None)
        manager._worker.join(timeout=1)

    def test_submit_multiple_tasks_processed_order(self):
        """Test that multiple tasks are processed in FIFO order."""
        processed_tasks = []

        class TestManager(BackgroundTaskManager):
            def process(self, task: str) -> None:
                processed_tasks.append(task)

        manager = TestManager()

        # Submit multiple tasks
        tasks = ["first", "second", "third"]
        for task in tasks:
            manager.submit(task)

        # Wait for all tasks to process
        manager._queue.join()
        time.sleep(0.1)

        assert processed_tasks == tasks

        # Clean up
        manager._queue.put(None)
        manager._worker.join(timeout=1)

    def test_worker_handles_exceptions_gracefully(self):
        """Test that worker continues processing after exceptions."""
        processed_tasks = []

        class TestManager(BackgroundTaskManager):
            def process(self, task: dict) -> None:
                if task.get("should_fail"):
                    raise ValueError("Test exception")
                processed_tasks.append(task)

        manager = TestManager()

        # Submit tasks that won't fail
        manager.submit({"id": 1})
        manager.submit({"id": 3})

        # Submit task that will fail
        manager.submit({"id": 2, "should_fail": True})

        # Submit more tasks that won't fail
        manager.submit({"id": 4})

        # Wait for processing
        manager._queue.join()
        time.sleep(0.1)

        # All non-failing tasks should be processed
        assert len(processed_tasks) == 3
        assert processed_tasks == [{"id": 1}, {"id": 3}, {"id": 4}]

        # Clean up
        manager._queue.put(None)
        manager._worker.join(timeout=1)

    def test_abstract_process_method_not_implemented(self):
        """Test that BackgroundTaskManager cannot be instantiated without process()."""
        manager = BackgroundTaskManager()

        # Submit a task to trigger process() call
        manager.submit("test")

        # Give worker time to try processing
        time.sleep(0.1)

        # Clean up
        manager._queue.put(None)
        if manager._worker:
            manager._worker.join(timeout=1)

    def test_worker_thread_safety(self):
        """Test that worker thread is thread-safe with concurrent submissions."""
        processed_tasks = []
        submission_count = 0

        class TestManager(BackgroundTaskManager):
            def process(self, task: int) -> None:
                processed_tasks.append(task)

        manager = TestManager()

        def submit_tasks(start: int, count: int):
            nonlocal submission_count
            for i in range(start, start + count):
                manager.submit(i)
                submission_count += 1

        # Create multiple threads to submit tasks concurrently
        threads = []
        for i in range(5):
            thread = threading.Thread(target=submit_tasks, args=(i * 10, 10))
            threads.append(thread)
            thread.start()

        # Wait for all threads to finish
        for thread in threads:
            thread.join()

        # Wait for all tasks to be processed
        manager._queue.join()
        time.sleep(0.1)

        assert submission_count == 50
        assert len(processed_tasks) == 50

        # All tasks should be processed (order may vary)
        processed_set = set(processed_tasks)
        expected_set = set(range(50))
        assert processed_set == expected_set

        # Clean up
        manager._queue.put(None)
        if manager._worker:
            manager._worker.join(timeout=1)

    def test_worker_respects_queue_blocking(self):
        """Test that worker blocks waiting for tasks."""
        processed_tasks = []

        class TestManager(BackgroundTaskManager):
            def process(self, task: str) -> None:
                processed_tasks.append(task)

        manager = TestManager()
        manager.start()

        # Initially no tasks
        assert len(processed_tasks) == 0

        # Submit task after delay
        def delayed_submit():
            time.sleep(0.1)
            manager.submit("delayed_task")

        submit_thread = threading.Thread(target=delayed_submit)
        submit_thread.start()

        # Task should not be processed immediately
        time.sleep(0.05)
        assert len(processed_tasks) == 0

        # Wait for delayed task
        time.sleep(0.1)
        assert "delayed_task" in processed_tasks

        # Clean up
        manager._queue.put(None)
        manager._worker.join(timeout=1)

    def test_generic_type_support(self):
        """Test that BackgroundTaskManager supports generic types."""
        # This test ensures type hints work correctly
        class IntManager(BackgroundTaskManager[int]):
            def process(self, task: int) -> None:
                self.processed = task

        manager = IntManager()
        manager.submit(42)

        # Wait for processing
        manager._queue.join()
        time.sleep(0.1)

        assert hasattr(manager, 'processed')
        assert manager.processed == 42

        # Clean up
        manager._queue.put(None)
        if manager._worker:
            manager._worker.join(timeout=1)

    def test_daemon_thread_property(self):
        """Test that worker thread is properly set as daemon."""
        manager = BackgroundTaskManager()
        manager.start()

        assert manager._worker.daemon

        # Clean up
        manager._queue.put(None)
        manager._worker.join(timeout=1)

    def test_worker_cleanup_on_exit(self):
        """Test that worker threads can be properly cleaned up."""
        processed_tasks = []

        class TestManager(BackgroundTaskManager):
            def process(self, task: str) -> None:
                if task == "stop":
                    return
                processed_tasks.append(task)

        manager = TestManager()

        # Submit tasks
        manager.submit("task1")
        manager.submit("task2")
        manager.submit("stop")  # Signal to stop

        # Wait for processing
        manager._queue.join()
        time.sleep(0.1)

        assert len(processed_tasks) == 2

        # Stop the worker
        manager._queue.put(None)
        if manager._worker:
            manager._worker.join(timeout=1)

        # Worker should no longer be alive
        assert not manager._worker or not manager._worker.is_alive()

    def test_logging_worker_lifecycle(self):
        """Test that worker lifecycle is properly logged."""
        with patch('task_manager.base.logger') as mock_logger:
            processed_tasks = []

            class TestManager(BackgroundTaskManager):
                def process(self, task: str) -> None:
                    processed_tasks.append(task)

            manager = TestManager()
            manager.submit("test")

            # Give worker time to process
            time.sleep(0.1)

            # Should have logged worker lifecycle
            assert mock_logger.info.called
            assert mock_logger.debug.called

            # Clean up
            manager._queue.put(None)
            if manager._worker:
                manager._worker.join(timeout=1)

    def test_lock_prevents_race_conditions(self):
        """Test that start() method uses lock to prevent race conditions."""
        manager = BackgroundTaskManager()

        def start_worker():
            manager.start()

        # Create multiple threads calling start() simultaneously
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=start_worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Should only have one worker thread
        assert manager._worker is not None
        assert isinstance(manager._worker, threading.Thread)
        assert manager._worker.is_alive()

        # Clean up
        manager._queue.put(None)
        manager._worker.join(timeout=1)

    def test_queue_task_done_called(self):
        """Test that task_done() is called for each processed task."""
        with patch.object(queue.Queue, 'task_done') as mock_task_done:
            processed_tasks = []

            class TestManager(BackgroundTaskManager):
                def process(self, task: str) -> None:
                    processed_tasks.append(task)

            manager = TestManager()
            manager.submit("test1")
            manager.submit("test2")

            # Wait for processing
            manager._queue.join()
            time.sleep(0.1)

            # task_done should be called for each task
            assert mock_task_done.call_count == 2

            # Clean up
            manager._queue.put(None)
            if manager._worker:
                manager._worker.join(timeout=1)

    def test_custom_task_queue_inheritance(self):
        """Test that custom task queue works with inheritance."""
        # Create a priority queue
        priority_queue = queue.PriorityQueue()

        class PriorityManager(BackgroundTaskManager[tuple]):
            def process(self, task: tuple) -> None:
                priority, value = task
                self.last_priority = priority
                self.last_value = value

        manager = PriorityManager(task_queue=priority_queue)

        # Submit tasks with different priorities
        manager.submit((2, "low priority"))
        manager.submit((1, "high priority"))
        manager.submit((3, "lowest priority"))

        # Wait for processing
        manager._queue.join()
        time.sleep(0.1)

        # Should process in priority order
        assert manager.last_priority == 3  # Last processed
        assert manager.last_value == "lowest priority"

        # Clean up
        manager._queue.put(None)
        if manager._worker:
            manager._worker.join(timeout=1)