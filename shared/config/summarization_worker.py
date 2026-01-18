"""Summarization Worker service configuration.

Extends BaseSettings with Summarization Worker-specific configuration:
- Summarization model and API settings
- GCS access for reading archived content
"""

from pathlib import Path
from typing import Optional, List
from pydantic import AliasChoices, Field, field_validator

from .base import BaseSettings
from .archive_worker import GCSSettings


class SummarizationSettings(BaseSettings):
    """Summarization service settings."""

    enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_SUMMARIZATION", "SUMMARIZATION__ENABLED"),
    )
    providers: List[str] = Field(
        default_factory=lambda: ["huggingface"],
        validation_alias=AliasChoices("SUMMARY_PROVIDERS", "SUMMARIZATION__PROVIDERS"),
    )
    api_base: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "SUMMARIZATION_API_BASE", "SUMMARIZATION__API_BASE"
        ),
    )
    api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "SUMMARIZATION_API_KEY", "SUMMARIZATION__API_KEY"
        ),
    )
    model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("SUMMARIZATION_MODEL", "SUMMARIZATION__MODEL"),
    )
    max_concurrency: int = Field(
        default=4,
        validation_alias=AliasChoices(
            "SUMMARY_MAX_CONCURRENCY", "SUMMARIZATION__MAX_CONCURRENCY"
        ),
    )
    chunk_size: int = Field(
        default=1200,
        validation_alias=AliasChoices("SUMMARY_CHUNK_SIZE", "SUMMARIZATION__CHUNK_SIZE"),
    )
    source_archivers: List[str] = Field(
        default_factory=lambda: ["readability"],
        validation_alias=AliasChoices(
            "SUMMARY_SOURCE_ARCHIVERS", "SUMMARIZATION__SOURCE_ARCHIVERS"
        ),
    )

    @field_validator("providers", mode="before")
    @classmethod
    def parse_providers(cls, v):
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v or ["huggingface"]

    @field_validator("source_archivers", mode="before")
    @classmethod
    def parse_source_archivers(cls, v):
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v or ["readability"]


class SummarizationWorkerSettings(BaseSettings):
    """Settings for Summarization Worker service.

    Inherits common infrastructure settings and adds:
    - Summarization model and API configuration
    - GCS access for reading archived content
    - API keys for summarization providers
    """

    # Service identity
    service_name: str = Field(
        default="summarization-worker",
        validation_alias=AliasChoices("SERVICE_NAME"),
    )

    # Summarization configuration
    summarization: SummarizationSettings = Field(
        default_factory=SummarizationSettings,
        description="Summarization service configuration",
    )

    # API keys for summarization providers
    openai_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY"),
        description="OpenAI API key for GPT models",
    )
    huggingface_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("HUGGINGFACE_API_KEY", "HF_API_KEY"),
        description="Hugging Face API key for models",
    )

    # GCS settings (for reading archived content)
    gcs: GCSSettings = Field(
        default_factory=GCSSettings,
        description="Google Cloud Storage configuration for reading archives",
    )
