from __future__ import annotations

import queue
import threading
from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar


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
                print(f'[{self.__class__.__name__}] Worker already running; skipping start')
                return
            print(f'[{self.__class__.__name__}] Starting worker thread')
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()

    def submit(self, task: TaskT) -> None:
        print(f'[{self.__class__.__name__}] Submitting task: {task}')
        self._queue.put(task)
        self.start()

    def _run(self) -> None:
        print(f'[{self.__class__.__name__}] Worker loop started')
        while True:
            task = self._queue.get()
            try:
                print(f'[{self.__class__.__name__}] Processing task: {task}')
                self.process(task)
                print(f'[{self.__class__.__name__}] Finished task: {task}')
            finally:
                self._queue.task_done()

    @abstractmethod
    def process(self, task: TaskT) -> None:
        """Handle an individual task pulled from the queue."""
        raise NotImplementedError
