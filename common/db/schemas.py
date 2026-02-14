"""Pydantic schemas for database repository responses.

These schemas provide type-safe, validated responses from repository functions
and decouple the API layer from ORM models.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ArtifactStatus(str, Enum):
    """Status values for archive artifacts."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class ArtifactSchema(BaseModel):
    """Archive artifact with related URL information."""

    artifact_id: int
    archiver: str
    status: Optional[str] = None
    task_id: Optional[str] = None
    item_id: Optional[str] = None
    url: str
    archived_url_id: int
    success: Optional[bool] = None
    exit_code: Optional[int] = None
    saved_path: Optional[str] = None
    size_bytes: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ArchivedUrlSchema(BaseModel):
    """Archived URL record."""

    id: int
    url: str
    item_id: Optional[str] = None
    name: Optional[str] = None
    total_size_bytes: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UrlMetadataSchema(BaseModel):
    """URL metadata extracted from readability."""

    id: int
    archived_url_id: int
    source_url: Optional[str] = None
    title: Optional[str] = None
    byline: Optional[str] = None
    site_name: Optional[str] = None
    description: Optional[str] = None
    published: Optional[str] = None
    language: Optional[str] = None
    canonical_url: Optional[str] = None
    top_image: Optional[str] = None
    favicon: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    text: Optional[str] = None
    word_count: Optional[int] = None
    reading_time_minutes: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class ArticleSummarySchema(BaseModel):
    """Article summary from LLM."""

    id: int
    archived_url_id: int
    summary_type: str
    summary_text: str
    bullet_points: Optional[list[Any]] = None
    model_name: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ArticleTagSchema(BaseModel):
    """Article tag extracted or assigned."""

    id: int
    archived_url_id: int
    tag: str
    source: str = "llm"
    confidence: Optional[float] = None
    reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ArticleEntitySchema(BaseModel):
    """Named entity extracted from article."""

    id: int
    archived_url_id: int
    entity: str
    entity_type: Optional[str] = None
    alias: Optional[str] = None
    reason: Optional[str] = None
    confidence: Optional[float] = None
    validated: bool = True

    model_config = ConfigDict(from_attributes=True)


class SizeStatsSchema(BaseModel):
    """Size statistics for an archived URL."""

    total_size_bytes: Optional[int] = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
