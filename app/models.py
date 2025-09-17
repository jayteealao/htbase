from __future__ import annotations

from typing import Optional, List

from pydantic import BaseModel, Field, HttpUrl, AliasChoices, model_validator


class SaveRequest(BaseModel):
    url: HttpUrl
    id: str = Field(
        description="Identifier specific to the URL",
        validation_alias=AliasChoices("id", "user_id"),
        serialization_alias="id",
    )


class ArchiveResult(BaseModel):
    success: bool
    exit_code: Optional[int] = None
    saved_path: Optional[str] = None
    metadata: Optional[dict] = None


class SaveResponse(BaseModel):
    ok: bool
    exit_code: Optional[int] = None
    saved_path: Optional[str] = None
    id: str
    db_rowid: Optional[int] = None


class BatchItemRequest(BaseModel):
    url: HttpUrl
    id: str = Field(
        description="Identifier specific to the URL",
        validation_alias=AliasChoices("id", "user_id"),
        serialization_alias="id",
    )


class BatchCreateRequest(BaseModel):
    items: List[BatchItemRequest] = Field(min_length=1)


class TaskAccepted(BaseModel):
    task_id: str
    count: int


class TaskItemStatus(BaseModel):
    url: HttpUrl
    id: str
    name: Optional[str] = None
    status: str
    exit_code: Optional[int] = None
    saved_path: Optional[str] = None
    db_rowid: Optional[int] = None


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    items: List[TaskItemStatus]


class DeleteResponse(BaseModel):
    ok: bool = True
    deleted_count: int
    deleted_rowids: List[int]
    removed_files: List[str] = []
    errors: List[str] = []


class SummarizeRequest(BaseModel):
    rowid: Optional[int] = Field(default=None, ge=1)
    item_id: Optional[str] = None
    url: Optional[HttpUrl] = None

    @model_validator(mode="after")
    def _ensure_target(self) -> "SummarizeRequest":
        if not any((self.rowid, self.item_id, self.url)):
            raise ValueError("rowid, item_id, or url must be provided")
        return self


class SummarizeResponse(BaseModel):
    ok: bool
    archived_url_id: int
    summary_created: bool
