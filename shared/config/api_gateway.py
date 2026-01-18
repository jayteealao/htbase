"""API Gateway service configuration.

Extends BaseSettings with API Gateway-specific configuration:
- CORS origins for frontend
- Feature flags (summarization)
"""

from typing import List
from pydantic import AliasChoices, Field, field_validator

from .base import BaseSettings


class APIGatewaySettings(BaseSettings):
    """Settings for API Gateway service.

    Inherits common infrastructure settings and adds:
    - CORS configuration for frontend origins
    - Summarization feature flag
    """

    # Service identity
    service_name: str = Field(
        default="api-gateway",
        validation_alias=AliasChoices("SERVICE_NAME"),
    )

    # CORS configuration
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        validation_alias=AliasChoices("CORS_ORIGINS"),
        description="List of allowed CORS origins (comma-separated in env)",
    )

    # Feature flags
    summarization_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("ENABLE_SUMMARIZATION", "SUMMARIZATION__ENABLED"),
        description="Enable summarization features in API",
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
