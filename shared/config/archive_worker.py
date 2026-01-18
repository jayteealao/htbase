"""Archive Worker service configuration.

Extends BaseSettings with Archive Worker-specific configuration:
- Google Cloud Storage for artifact storage
- Local data directory
"""

from pathlib import Path
from typing import Optional
from pydantic import AliasChoices, BaseModel, Field

from .base import BaseSettings


class GCSSettings(BaseModel):
    """Google Cloud Storage settings for artifact storage."""

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


class ArchiveWorkerSettings(BaseSettings):
    """Settings for Archive Worker service.

    Inherits common infrastructure settings and adds:
    - GCS configuration for artifact storage
    - Local data directory for temporary files
    """

    # Service identity
    service_name: str = Field(
        default="archive-worker",
        validation_alias=AliasChoices("SERVICE_NAME"),
    )

    # Data directory
    data_dir: Path = Field(
        default=Path("/data"),
        validation_alias=AliasChoices("DATA_DIR"),
        description="Local directory for temporary artifact files",
    )

    # GCS settings
    gcs: GCSSettings = Field(
        default_factory=GCSSettings,
        description="Google Cloud Storage configuration",
    )
