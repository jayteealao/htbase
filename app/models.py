from __future__ import annotations

from typing import Optional

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
