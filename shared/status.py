"""
Task status tracking for HTBase microservices.

Provides enums and data structures for tracking task status
across services via Celery and Redis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    STARTED = "started"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"
    REVOKED = "revoked"

    def is_terminal(self) -> bool:
        """Check if this is a terminal (final) status."""
        return self in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.REVOKED)


class ArchiveStatus(str, Enum):
    """Status of an archive artifact."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"  # Already exists


class SummarizationStatus(str, Enum):
    """Status of summarization task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"  # No content to summarize


class StorageStatus(str, Enum):
    """Status of storage operation."""

    PENDING = "pending"
    UPLOADING = "uploading"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"


@dataclass
class TaskResult:
    """Result of a task execution."""

    task_id: str
    status: TaskStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    traceback: Optional[str] = None
    retries: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "retries": self.retries,
        }


@dataclass
class ArchiveTaskResult(TaskResult):
    """Result of an archive task."""

    archiver: str = ""
    item_id: str = ""
    url: str = ""
    saved_path: Optional[str] = None
    exit_code: Optional[int] = None
    file_size: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        base = super().to_dict()
        base.update({
            "archiver": self.archiver,
            "item_id": self.item_id,
            "url": self.url,
            "saved_path": self.saved_path,
            "exit_code": self.exit_code,
            "file_size": self.file_size,
        })
        return base


@dataclass
class SummarizationTaskResult(TaskResult):
    """Result of a summarization task."""

    item_id: str = ""
    summary_text: Optional[str] = None
    bullet_points: Optional[list[str]] = None
    entities: Optional[list[dict[str, Any]]] = None
    tags: Optional[list[str]] = None
    model_name: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        base = super().to_dict()
        base.update({
            "item_id": self.item_id,
            "summary_text": self.summary_text,
            "bullet_points": self.bullet_points,
            "entities": self.entities,
            "tags": self.tags,
            "model_name": self.model_name,
        })
        return base


@dataclass
class StorageTaskResult(TaskResult):
    """Result of a storage task."""

    item_id: str = ""
    archiver: str = ""
    storage_uri: Optional[str] = None
    original_size: Optional[int] = None
    stored_size: Optional[int] = None
    compression_ratio: Optional[float] = None
    provider: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        base = super().to_dict()
        base.update({
            "item_id": self.item_id,
            "archiver": self.archiver,
            "storage_uri": self.storage_uri,
            "original_size": self.original_size,
            "stored_size": self.stored_size,
            "compression_ratio": self.compression_ratio,
            "provider": self.provider,
        })
        return base


@dataclass
class BatchTaskStatus:
    """Status of a batch of tasks."""

    batch_id: str
    total_tasks: int
    completed_tasks: int = 0
    failed_tasks: int = 0
    pending_tasks: int = 0
    task_results: list[TaskResult] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def progress(self) -> float:
        """Get completion percentage."""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks + self.failed_tasks) / self.total_tasks * 100

    @property
    def is_complete(self) -> bool:
        """Check if all tasks are complete."""
        return self.completed_tasks + self.failed_tasks >= self.total_tasks

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "batch_id": self.batch_id,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "pending_tasks": self.pending_tasks,
            "progress": self.progress,
            "is_complete": self.is_complete,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "task_results": [t.to_dict() for t in self.task_results],
        }
