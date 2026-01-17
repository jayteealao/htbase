"""
Shared configuration for HTBase microservices.

Provides environment-based configuration with Pydantic settings.
Each service can extend this base configuration with service-specific settings.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus

from pydantic import AliasChoices, BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    """Database settings (for backward compatibility during PostgreSQL removal).

    NOTE: HTBase now uses Firestore exclusively. This class remains only for
    backward compatibility with legacy scripts during the transition period.
    """

    path: Optional[Path] = Field(
        default=None,
        validation_alias=AliasChoices("DB_PATH", "DATABASE__PATH"),
    )
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

    def sqlalchemy_url(self) -> str:
        """Generate SQLAlchemy database URL.

        NOTE: This method is deprecated as HTBase no longer uses PostgreSQL.
        It remains for backward compatibility with legacy scripts only.
        """
        if self.path:
            return f"sqlite:///{self.path}"
        user = quote_plus(self.user)
        pwd = quote_plus(self.password.get_secret_value())
        return f"postgresql+psycopg://{user}:{pwd}@{self.host}:{self.port}/{self.name}"

    def resolved_path(self, data_dir: Path) -> Path:
        """Get resolved database path with fallback to data_dir/app.db.

        NOTE: This method is deprecated as HTBase no longer uses SQLite.
        It remains for backward compatibility with legacy scripts only.
        """
        return self.path or (data_dir / "app.db")


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
    """Google Cloud Storage settings - now required for all storage operations."""

    bucket: str = Field(
        ...,  # Required field
        validation_alias=AliasChoices("GCS_BUCKET", "STORAGE__GCS_BUCKET"),
        description="GCS bucket name for artifact storage",
    )
    project_id: str = Field(
        ...,  # Required field
        validation_alias=AliasChoices("GCS_PROJECT_ID", "GOOGLE_CLOUD_PROJECT"),
        description="Google Cloud project ID",
    )
    credentials_path: Optional[Path] = Field(
        default=None,
        validation_alias=AliasChoices(
            "GCS_CREDENTIALS_PATH", "GOOGLE_APPLICATION_CREDENTIALS"
        ),
        description="Path to service account credentials JSON file",
    )


class FirestoreSettings(BaseModel):
    """Firestore settings - now the primary database for HTBase."""

    project_id: str = Field(
        ...,  # Required field
        validation_alias=AliasChoices(
            "FIRESTORE_PROJECT_ID", "GOOGLE_CLOUD_PROJECT", "GCS_PROJECT_ID"
        ),
        description="Google Cloud project ID for Firestore database",
    )
    collection_name: str = Field(
        default="articles",
        validation_alias=AliasChoices("FIRESTORE_COLLECTION", "FIRESTORE__COLLECTION"),
        description="Firestore collection name for articles",
    )

    def is_configured(self) -> bool:
        """Check if Firestore is properly configured."""
        return bool(self.project_id)


class ArchiverSettings(BaseModel):
    """Archiver execution timeout settings (in seconds)."""

    singlefile_timeout: float = Field(
        default=300.0,
        ge=1.0,
        validation_alias=AliasChoices("ARCHIVER_SINGLEFILE_TIMEOUT", "ARCHIVERS__SINGLEFILE_TIMEOUT"),
        description="Timeout for singlefile archiver (seconds)",
    )
    monolith_timeout: float = Field(
        default=300.0,
        ge=1.0,
        validation_alias=AliasChoices("ARCHIVER_MONOLITH_TIMEOUT", "ARCHIVERS__MONOLITH_TIMEOUT"),
        description="Timeout for monolith archiver (seconds)",
    )
    pdf_timeout: float = Field(
        default=120.0,
        ge=1.0,
        validation_alias=AliasChoices("ARCHIVER_PDF_TIMEOUT", "ARCHIVERS__PDF_TIMEOUT"),
        description="Timeout for PDF archiver (seconds)",
    )
    screenshot_timeout: float = Field(
        default=60.0,
        ge=1.0,
        validation_alias=AliasChoices("ARCHIVER_SCREENSHOT_TIMEOUT", "ARCHIVERS__SCREENSHOT_TIMEOUT"),
        description="Timeout for screenshot archiver (seconds)",
    )
    readability_timeout: float = Field(
        default=30.0,
        ge=1.0,
        validation_alias=AliasChoices("ARCHIVER_READABILITY_TIMEOUT", "ARCHIVERS__READABILITY_TIMEOUT"),
        description="Timeout for readability archiver (seconds)",
    )


class TaskSettings(BaseModel):
    """Celery task retry and timeout settings."""

    default_retry_delay: int = Field(
        default=60,
        ge=1,
        validation_alias=AliasChoices("TASK_DEFAULT_RETRY_DELAY", "TASKS__DEFAULT_RETRY_DELAY"),
        description="Default retry delay in seconds",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        validation_alias=AliasChoices("TASK_MAX_RETRIES", "TASKS__MAX_RETRIES"),
        description="Default maximum retries for tasks",
    )
    retry_backoff_max: int = Field(
        default=300,
        ge=1,
        validation_alias=AliasChoices("TASK_RETRY_BACKOFF_MAX", "TASKS__RETRY_BACKOFF_MAX"),
        description="Maximum backoff delay in seconds",
    )
    webhook_retry_delay: int = Field(
        default=60,
        ge=1,
        validation_alias=AliasChoices("TASK_WEBHOOK_RETRY_DELAY", "TASKS__WEBHOOK_RETRY_DELAY"),
        description="Webhook task retry delay in seconds",
    )
    webhook_max_retries: int = Field(
        default=5,
        ge=0,
        validation_alias=AliasChoices("TASK_WEBHOOK_MAX_RETRIES", "TASKS__WEBHOOK_MAX_RETRIES"),
        description="Maximum retries for webhook tasks",
    )
    webhook_retry_backoff_max: int = Field(
        default=600,
        ge=1,
        validation_alias=AliasChoices("TASK_WEBHOOK_RETRY_BACKOFF_MAX", "TASKS__WEBHOOK_RETRY_BACKOFF_MAX"),
        description="Maximum backoff delay for webhook tasks in seconds",
    )
    storage_max_retries: int = Field(
        default=5,
        ge=0,
        validation_alias=AliasChoices("TASK_STORAGE_MAX_RETRIES", "TASKS__STORAGE_MAX_RETRIES"),
        description="Maximum retries for storage tasks",
    )


class HTTPSettings(BaseModel):
    """HTTP client timeout settings (in seconds)."""

    default_timeout: float = Field(
        default=30.0,
        ge=1.0,
        validation_alias=AliasChoices("HTTP_DEFAULT_TIMEOUT", "HTTP__DEFAULT_TIMEOUT"),
        description="Default HTTP request timeout (seconds)",
    )
    # REMOVED: health_check_timeout - never used in codebase
    # Health checks use hardcoded timeouts in their respective endpoints
    webhook_timeout: float = Field(
        default=10.0,
        ge=1.0,
        validation_alias=AliasChoices("HTTP_WEBHOOK_TIMEOUT", "HTTP__WEBHOOK_TIMEOUT"),
        description="Timeout for webhook delivery (seconds)",
    )


# REMOVED: BatchSettings class
# These settings were defined but never actually used in the codebase:
# - max_batch_size: Hardcoded to 100 in API validation (CreateArchiveRequest.items)
# - requeue_chunk_size: Hardcoded to DEFAULT_REQUEUE_CHUNK_SIZE (10) in archiver.py
# - worker_max_tasks_per_child: Hardcoded in Celery worker configs
# If you need these to be configurable, use the constants directly where needed.

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

    # CORS configuration
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        validation_alias=AliasChoices("CORS_ORIGINS"),
        description="List of allowed CORS origins (comma-separated in env)",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v) -> List[str]:
        """Parse comma-separated CORS origins into a list."""
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            if not v:
                return []
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # Nested settings
    database: DatabaseSettings = Field(
        default_factory=DatabaseSettings,
        description="Legacy database settings (deprecated - HTBase uses Firestore)"
    )
    redis: RedisSettings = Field(default_factory=RedisSettings)
    gcs: GCSSettings = Field(default_factory=GCSSettings)
    firestore: FirestoreSettings = Field(default_factory=FirestoreSettings)
    archivers: ArchiverSettings = Field(default_factory=ArchiverSettings)
    tasks: TaskSettings = Field(default_factory=TaskSettings)
    http: HTTPSettings = Field(default_factory=HTTPSettings)
    summarization: SummarizationSettings = Field(default_factory=SummarizationSettings)

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
        """Get database connection string.

        NOTE: This property is deprecated as HTBase no longer uses PostgreSQL.
        It remains for backward compatibility with legacy scripts only.
        """
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
