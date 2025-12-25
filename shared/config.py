"""
Shared configuration for HTBase microservices.

Provides environment-based configuration with Pydantic settings.
Each service can extend this base configuration with service-specific settings.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from pydantic import AliasChoices, BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    """Database connection settings."""

    host: str = Field(
        default="localhost",
        validation_alias=AliasChoices("DB_HOST", "DATABASE__HOST"),
    )
    port: int = Field(
        default=5432,
        validation_alias=AliasChoices("DB_PORT", "DATABASE__PORT"),
    )
    name: str = Field(
        default="htbase",
        validation_alias=AliasChoices("DB_NAME", "DATABASE__NAME"),
    )
    user: str = Field(
        default="postgres",
        validation_alias=AliasChoices("DB_USER", "DATABASE__USER"),
    )
    password: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("DB_PASSWORD", "DATABASE__PASSWORD"),
    )
    socket: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("DB_SOCKET", "DATABASE__SOCKET"),
        description="Cloud SQL socket path for Unix socket connections",
    )
    pool_size: int = Field(
        default=5,
        validation_alias=AliasChoices("DB_POOL_SIZE", "DATABASE__POOL_SIZE"),
    )
    max_overflow: int = Field(
        default=10,
        validation_alias=AliasChoices("DB_MAX_OVERFLOW", "DATABASE__MAX_OVERFLOW"),
    )

    def sqlalchemy_url(self) -> str:
        """Build SQLAlchemy database URL."""
        user = quote_plus(self.user)
        pwd = quote_plus(self.password.get_secret_value())

        if self.socket:
            # Cloud SQL Unix socket connection
            return f"postgresql+psycopg://{user}:{pwd}@/{self.name}?host={self.socket}"

        return f"postgresql+psycopg://{user}:{pwd}@{self.host}:{self.port}/{self.name}"


class RedisSettings(BaseModel):
    """Redis connection settings."""

    host: str = Field(
        default="localhost",
        validation_alias=AliasChoices("REDIS_HOST", "REDIS__HOST"),
    )
    port: int = Field(
        default=6379,
        validation_alias=AliasChoices("REDIS_PORT", "REDIS__PORT"),
    )
    db: int = Field(
        default=0,
        validation_alias=AliasChoices("REDIS_DB", "REDIS__DB"),
    )
    password: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("REDIS_PASSWORD", "REDIS__PASSWORD"),
    )

    def url(self) -> str:
        """Build Redis URL."""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class GCSSettings(BaseModel):
    """Google Cloud Storage settings."""

    bucket: str = Field(
        default="htbase-archives",
        validation_alias=AliasChoices("GCS_BUCKET", "STORAGE__GCS_BUCKET"),
    )
    project_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GCS_PROJECT_ID", "GOOGLE_CLOUD_PROJECT"),
    )
    credentials_path: Optional[Path] = Field(
        default=None,
        validation_alias=AliasChoices(
            "GCS_CREDENTIALS_PATH", "GOOGLE_APPLICATION_CREDENTIALS"
        ),
    )

    def is_configured(self) -> bool:
        """Check if GCS is properly configured."""
        return bool(self.bucket)


class FirestoreSettings(BaseModel):
    """Firestore settings for mobile client sync."""

    project_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "FIRESTORE_PROJECT_ID", "GOOGLE_CLOUD_PROJECT", "GCS_PROJECT_ID"
        ),
    )
    collection_name: str = Field(
        default="articles",
        validation_alias=AliasChoices("FIRESTORE_COLLECTION", "FIRESTORE__COLLECTION"),
    )

    def is_configured(self) -> bool:
        """Check if Firestore is properly configured."""
        return bool(self.project_id)


class SummarizationSettings(BaseModel):
    """Summarization service settings."""

    enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_SUMMARIZATION", "SUMMARIZATION__ENABLED"),
    )
    providers: list[str] = Field(
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
    source_archivers: list[str] = Field(
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


class SharedSettings(BaseSettings):
    """Shared configuration for all HTBase services."""

    # Service identification
    service_name: str = Field(
        default="htbase",
        validation_alias=AliasChoices("SERVICE_NAME"),
    )
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("ENVIRONMENT", "ENV"),
    )

    # Data directory
    data_dir: Path = Field(
        default=Path("/data"),
        validation_alias=AliasChoices("DATA_DIR"),
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("LOG_LEVEL"),
    )
    log_format: str = Field(
        default="json",
        validation_alias=AliasChoices("LOG_FORMAT"),
        description="Log format: 'json' or 'text'",
    )

    # Nested settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    gcs: GCSSettings = Field(default_factory=GCSSettings)
    firestore: FirestoreSettings = Field(default_factory=FirestoreSettings)
    summarization: SummarizationSettings = Field(default_factory=SummarizationSettings)

    # Storage configuration
    storage_backend: str = Field(
        default="local",
        validation_alias=AliasChoices("STORAGE_BACKEND", "STORAGE__BACKEND"),
        description="File storage backend: 'local' or 'gcs'",
    )
    enable_storage_integration: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "ENABLE_STORAGE_INTEGRATION", "STORAGE__ENABLE_INTEGRATION"
        ),
    )
    enable_local_cleanup: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_LOCAL_CLEANUP", "STORAGE__ENABLE_CLEANUP"),
    )
    local_workspace_retention_hours: int = Field(
        default=24,
        validation_alias=AliasChoices(
            "LOCAL_WORKSPACE_RETENTION_HOURS", "STORAGE__RETENTION_HOURS"
        ),
    )

    # Celery configuration
    celery_broker_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("CELERY_BROKER_URL"),
    )
    celery_result_backend: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("CELERY_RESULT_BACKEND"),
    )

    @property
    def effective_celery_broker_url(self) -> str:
        """Get Celery broker URL, defaulting to Redis."""
        return self.celery_broker_url or self.redis.url()

    @property
    def effective_celery_result_backend(self) -> str:
        """Get Celery result backend URL, defaulting to Redis."""
        return self.celery_result_backend or self.redis.url()

    @property
    def database_url(self) -> str:
        """Get database connection string."""
        return self.database.sqlalchemy_url()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )


@lru_cache
def get_settings() -> SharedSettings:
    """Get cached settings instance."""
    return SharedSettings()


def configure_logging(settings: Optional[SharedSettings] = None) -> None:
    """Configure logging based on settings.

    Args:
        settings: Optional settings instance, uses cached settings if not provided
    """
    import logging
    import sys

    if settings is None:
        settings = get_settings()

    # Set log level
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if settings.log_format == "json":
        # JSON format for production
        import json

        class JSONFormatter(logging.Formatter):
            def format(self, record):
                log_record = {
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "service": settings.service_name,
                }
                if record.exc_info:
                    log_record["exception"] = self.formatException(record.exc_info)
                if hasattr(record, "extra"):
                    log_record.update(record.extra)
                return json.dumps(log_record)

        handler.setFormatter(JSONFormatter())
    else:
        # Text format for development
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)

    root_logger.addHandler(handler)
