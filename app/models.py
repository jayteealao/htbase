from __future__ import annotations

from typing import Optional, List

from pydantic import BaseModel, Field, HttpUrl, AliasChoices


class SaveRequest(BaseModel):
    url: HttpUrl
    id: str = Field(
        description="Identifier specific to the URL",
        validation_alias=AliasChoices("id", "user_id"),
        serialization_alias="id",
    )
    name: Optional[str] = None


class ArchiveResult(BaseModel):
    success: bool
    exit_code: Optional[int] = None
    saved_path: Optional[str] = None


class SaveResponse(BaseModel):
    ok: bool
    exit_code: Optional[int] = None
    saved_path: Optional[str] = None
    ht_preview_url: str
    id: str
    db_rowid: Optional[int] = None


class BatchItemRequest(BaseModel):
    url: HttpUrl
    id: str = Field(
        description="Identifier specific to the URL",
        validation_alias=AliasChoices("id", "user_id"),
        serialization_alias="id",
    )
    name: Optional[str] = None


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
