"""Base configuration shared by all HTBase services.

Provides common settings (Firestore, Redis, Celery, logging) that all services need.
Service-specific settings are defined in separate modules (api_gateway.py, etc.).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus

from pydantic import AliasChoices, BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings as PydanticBaseSettings, SettingsConfigDict


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


class FirestoreSettings(BaseModel):
    """Firestore settings - primary database for HTBase."""

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


class BaseSettings(PydanticBaseSettings):
    """Base settings shared by all HTBase services.

    Contains common infrastructure configuration:
    - Service identity (name, environment)
    - Logging configuration
    - Firestore database
    - Redis for Celery
    - Celery broker/backend settings

    Service-specific settings should extend this class.
    """

    # Service identification
    service_name: str = Field(
        default="htbase",
        validation_alias=AliasChoices("SERVICE_NAME"),
    )
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("ENVIRONMENT", "ENV"),
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

    # Nested settings - common infrastructure
    redis: RedisSettings = Field(default_factory=RedisSettings)
    firestore: FirestoreSettings = Field(default_factory=FirestoreSettings)

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )


def configure_logging(settings: BaseSettings) -> None:
    """Configure logging based on settings.

    Args:
        settings: Settings instance with log_level and log_format
    """
    import logging
    import sys

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
