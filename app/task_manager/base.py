from __future__ import annotations

import logging
import queue
import threading
from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar

logger = logging.getLogger(__name__)

TaskT = TypeVar("TaskT")


class BackgroundTaskManager(ABC, Generic[TaskT]):
    """Generic background worker that processes tasks from a queue."""

    def __init__(self, *, task_queue: "queue.Queue[TaskT]" | None = None) -> None:
        self._queue: "queue.Queue[TaskT]" = task_queue or queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def queue(self) -> "queue.Queue[TaskT]":
        return self._queue

    def start(self) -> None:
        with self._lock:
            if self._worker and self._worker.is_alive():
                logger.debug("Worker already running; skipping start", extra={"manager": self.__class__.__name__})
                return
            logger.info("Starting worker thread", extra={"manager": self.__class__.__name__})
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()

    def submit(self, task: TaskT) -> None:
        logger.debug("Submitting task", extra={"manager": self.__class__.__name__, "task": str(task)})
        self._queue.put(task)
        self.start()

    def _run(self) -> None:
        logger.info("Worker loop started", extra={"manager": self.__class__.__name__})
        while True:
            task = self._queue.get()
            try:
                logger.debug("Processing task", extra={"manager": self.__class__.__name__, "task": str(task)})
                self.process(task)
                logger.debug("Finished task", extra={"manager": self.__class__.__name__, "task": str(task)})
            finally:
                self._queue.task_done()

    @abstractmethod
    def process(self, task: TaskT) -> None:
        """Handle an individual task pulled from the queue."""
        raise NotImplementedError
