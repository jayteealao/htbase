"""
Fake implementations for testing.

This package contains fake (test double) implementations of core interfaces,
following the "fakes over mocks" philosophy. Fakes are simplified working
implementations that behave like real components but avoid external dependencies.

Key fakes:
- InMemoryFileStorage: In-memory file storage (no disk I/O)
- InMemoryDatabaseStorage: In-memory database (no PostgreSQL/Firestore)
- SyncTaskManager: Synchronous task processing (no threading)
- FakeCommandRunner: Command execution without subprocess
- Enhanced archiver fakes: FailingArchiver, TimeoutArchiver, etc.

Philosophy:
- Fakes implement the same interface as real components
- Fakes use simplified logic but real data structures
- Tests using fakes are fast, deterministic, and maintainable
- Fakes survive refactoring better than mocks

See: tests/conftest.py for existing DummyArchiver pattern
"""

from tests.fakes.storage import InMemoryFileStorage, InMemoryDatabaseStorage
from tests.fakes.task_manager import SyncTaskManager
from tests.fakes.command_runner import FakeCommandRunner
from tests.fakes.archivers import (
    FailingArchiver,
    TimeoutArchiver,
    SlowArchiver,
    DummyArchiver,
)

__all__ = [
    "InMemoryFileStorage",
    "InMemoryDatabaseStorage",
    "SyncTaskManager",
    "FakeCommandRunner",
    "FailingArchiver",
    "TimeoutArchiver",
    "SlowArchiver",
    "DummyArchiver",
]
