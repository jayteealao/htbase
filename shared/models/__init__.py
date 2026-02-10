"""
Shared Pydantic models for HTBase microservices.

These models define the data structures used in API requests/responses
and inter-service communication.
"""

from __future__ import annotations

from typing import Optional, List, Any

from pydantic import BaseModel, Field, HttpUrl, AliasChoices, model_validator


# ==================== API Request Models ====================

class SaveRequest(BaseModel):
    """Request to save/archive a URL."""
    url: HttpUrl
    id: str = Field(
        description="Identifier specific to the URL",
        validation_alias=AliasChoices("id", "user_id", "item_id"),
        serialization_alias="id",
    )
    archivers: Optional[List[str]] = Field(
        default=None,
        description="List of archivers to use, or None for all"
    )
    priority: int = Field(
        default=0,
        ge=0,
        le=10,
        description="Task priority (0=lowest, 10=highest)"
    )


class BatchSaveRequest(BaseModel):
    """Request to save multiple URLs."""
    items: List[SaveRequest] = Field(min_length=1)


class ArchiveRetrieveRequest(BaseModel):
    """Request to retrieve archived content."""
    url: Optional[HttpUrl] = None
    id: Optional[str] = Field(
        default=None,
        description="Identifier specific to the URL (optional if url provided)",
        validation_alias=AliasChoices("id", "user_id", "item_id"),
        serialization_alias="id",
    )
    archiver: str = Field(
        default="all",
        description="Archiver name or 'all' to download every archived artifact",
    )

    @model_validator(mode="after")
    def _validate_target(self) -> "ArchiveRetrieveRequest":
        if not any((self.id, self.url)):
            raise ValueError("id or url must be provided")
        archiver = (self.archiver or "all").strip() or "all"
        self.archiver = archiver
        return self


class SummarizeRequest(BaseModel):
    """Request to summarize an article."""
    rowid: Optional[int] = Field(default=None, ge=1)
    item_id: Optional[str] = None
    url: Optional[HttpUrl] = None
    force: bool = Field(
        default=False,
        description="Force re-summarization even if summary exists"
    )

    @model_validator(mode="after")
    def _ensure_target(self) -> "SummarizeRequest":
        if not any((self.rowid, self.item_id, self.url)):
            raise ValueError("rowid, item_id, or url must be provided")
        return self


# ==================== API Response Models ====================

class ArchiveResult(BaseModel):
    """Result of an archive operation."""
    success: bool
    exit_code: Optional[int] = None
    saved_path: Optional[str] = None
    metadata: Optional[dict] = None


class SaveResponse(BaseModel):
    """Response from save operation."""
    ok: bool
    exit_code: Optional[int] = None
    saved_path: Optional[str] = None
    id: str
    db_rowid: Optional[int] = None


class TaskAccepted(BaseModel):
    """Response when task is accepted for async processing."""
    task_id: str
    count: int
    message: str = "Task accepted"


class TaskItemStatus(BaseModel):
    """Status of individual item in a task."""
    url: HttpUrl
    id: str
    name: Optional[str] = None
    status: str
    exit_code: Optional[int] = None
    saved_path: Optional[str] = None
    db_rowid: Optional[int] = None


class TaskStatusResponse(BaseModel):
    """Response with task status."""
    task_id: str
    status: str
    progress: float = 0.0
    items: List[TaskItemStatus] = Field(default_factory=list)


class DeleteResponse(BaseModel):
    """Response from delete operation."""
    ok: bool = True
    deleted_count: int
    deleted_rowids: List[int]
    removed_files: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class SummarizeResponse(BaseModel):
    """Response from summarize operation."""
    ok: bool
    archived_url_id: int
    summary_created: bool
    summary_text: Optional[str] = None
    bullet_points: Optional[List[str]] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str = "1.0.0"
    services: dict[str, str] = Field(default_factory=dict)


# ==================== Inter-Service Message Models ====================

class ArchiveTaskMessage(BaseModel):
    """Message for archive task queue."""
    item_id: str
    url: str
    archiver: str
    archived_url_id: int
    artifact_id: int
    rewritten_url: Optional[str] = None
    priority: int = 0


class SummarizationTaskMessage(BaseModel):
    """Message for summarization task queue."""
    item_id: str
    archived_url_id: int
    source_archiver: str = "readability"
    content_path: Optional[str] = None
    force: bool = False


class StorageTaskMessage(BaseModel):
    """Message for storage task queue."""
    item_id: str
    archiver: str
    artifact_id: int
    local_path: str
    providers: List[str] = Field(default_factory=lambda: ["gcs"])


class ArchiveCompleteMessage(BaseModel):
    """Message sent when archive task completes."""
    item_id: str
    archiver: str
    artifact_id: int
    archived_url_id: int
    success: bool
    saved_path: Optional[str] = None
    exit_code: Optional[int] = None
    file_size: Optional[int] = None


class SummarizationCompleteMessage(BaseModel):
    """Message sent when summarization completes."""
    item_id: str
    archived_url_id: int
    success: bool
    summary_id: Optional[int] = None
    error: Optional[str] = None


class StorageCompleteMessage(BaseModel):
    """Message sent when storage upload completes."""
    item_id: str
    archiver: str
    artifact_id: int
    success: bool
    storage_uri: Optional[str] = None
    provider: str = ""
    error: Optional[str] = None


# ==================== Workflow Models ====================

class ArchiveWorkflowRequest(BaseModel):
    """Request for complete archive workflow."""
    item_id: str
    url: str
    archivers: List[str] = Field(default_factory=lambda: ["all"])
    summarize: bool = True
    upload_to_storage: bool = True
    priority: int = 0


class WorkflowStatus(BaseModel):
    """Status of a complete workflow."""
    workflow_id: str
    item_id: str
    url: str
    status: str
    archive_status: dict[str, str] = Field(default_factory=dict)
    summarization_status: Optional[str] = None
    storage_status: dict[str, str] = Field(default_factory=dict)
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


__all__ = [
    # Request models
    "SaveRequest",
    "BatchSaveRequest",
    "ArchiveRetrieveRequest",
    "SummarizeRequest",
    # Response models
    "ArchiveResult",
    "SaveResponse",
    "TaskAccepted",
    "TaskItemStatus",
    "TaskStatusResponse",
    "DeleteResponse",
    "SummarizeResponse",
    "HealthResponse",
    # Inter-service messages
    "ArchiveTaskMessage",
    "SummarizationTaskMessage",
    "StorageTaskMessage",
    "ArchiveCompleteMessage",
    "SummarizationCompleteMessage",
    "StorageCompleteMessage",
    # Workflow models
    "ArchiveWorkflowRequest",
    "WorkflowStatus",
]
