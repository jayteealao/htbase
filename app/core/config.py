from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import AliasChoices, BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    path: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("DB_PATH", "DATABASE__PATH"),
    )
    host: str = Field(
        default="192.168.1.12",
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
        default=SecretStr("your_password"),
        validation_alias=AliasChoices("DB_PASSWORD", "DATABASE__PASSWORD"),
    )

    def sqlalchemy_url(self) -> str:
        user = quote_plus(self.user)
        pwd = quote_plus(self.password.get_secret_value())
        return f"postgresql+psycopg://{user}:{pwd}@{self.host}:{self.port}/{self.name}"

    def resolved_path(self, data_dir: Path) -> Path:
        """Get resolved database path with fallback to data_dir/app.db."""
        return self.path or (data_dir / "app.db")


class ChromiumSettings(BaseModel):
    enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("USE_CHROMIUM", "CHROMIUM__ENABLED"),
    )
    binary: str = Field(
        default="/usr/bin/chromium",
        validation_alias=AliasChoices("CHROMIUM_BIN", "CHROMIUM__BIN"),
    )
    user_data_dir: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("CHROMIUM_USER_DATA_DIR", "CHROMIUM__USER_DATA_DIR"),
    )
    profile_directory: str = Field(
        default="Default",
        validate_default=True,
        validation_alias=AliasChoices(
            "CHROMIUM_PROFILE_DIRECTORY",
            "CHROMIUM__PROFILE_DIRECTORY",
        ),
    )

    @field_validator("profile_directory", mode="before")
    @classmethod
    def _normalize_profile_directory(cls, value: str | Path | None) -> str:
        if value is None:
            return "Default"
        profile = str(value).strip()
        return profile or "Default"

    def resolved_user_data_dir(self, data_dir: Path) -> Path:
        """Get resolved chromium user data directory with fallback to data_dir/chromium-user-data."""
        return self.user_data_dir or (data_dir / "chromium-user-data")


class HuggingFaceProviderSettings(BaseModel):
    """HuggingFace TGI provider configuration."""

    api_base: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SUMMARIZATION_API_BASE",
            "SUMMARIZATION__HUGGINGFACE__API_BASE",
        ),
    )
    api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SUMMARIZATION_API_KEY",
            "SUMMARIZATION__HUGGINGFACE__API_KEY",
        ),
    )
    max_concurrency: int = Field(
        default=4,
        validation_alias=AliasChoices(
            "SUMMARY_MAX_CONCURRENCY",
            "SUMMARIZATION__HUGGINGFACE__MAX_CONCURRENCY",
        ),
    )


class OpenAIProviderSettings(BaseModel):
    """OpenAI API provider configuration."""

    api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "OPENAI_API_KEY",
            "SUMMARIZATION__OPENAI__API_KEY",
        ),
    )
    model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices(
            "OPENAI_MODEL",
            "SUMMARIZATION__OPENAI__MODEL",
        ),
    )
    temperature: float = Field(
        default=0.2,
        validation_alias=AliasChoices(
            "OPENAI_TEMPERATURE",
            "SUMMARIZATION__OPENAI__TEMPERATURE",
        ),
    )
    max_tokens: int = Field(
        default=400,
        validation_alias=AliasChoices(
            "OPENAI_MAX_TOKENS",
            "SUMMARIZATION__OPENAI__MAX_TOKENS",
        ),
    )


class SummarizationSettings(BaseModel):
    enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_SUMMARIZATION", "SUMMARIZATION__ENABLED"),
    )
    providers: list[str] = Field(
        default_factory=lambda: ["huggingface"],
        validation_alias=AliasChoices("SUMMARY_PROVIDERS", "SUMMARIZATION__PROVIDERS"),
    )
    provider_sticky: bool = Field(
        default=True,
        validation_alias=AliasChoices("SUMMARY_PROVIDER_STICKY", "SUMMARIZATION__PROVIDER_STICKY"),
    )

    # Provider-specific settings
    huggingface: HuggingFaceProviderSettings = Field(
        default_factory=HuggingFaceProviderSettings
    )
    openai: OpenAIProviderSettings = Field(
        default_factory=OpenAIProviderSettings
    )

    # Legacy fields for backward compatibility
    openrouter_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "OPENROUTER_API_KEY",
            "SUMMARIZATION__OPENROUTER_API_KEY",
        ),
    )
    model: str = Field(
        default="openrouter/sonoma-sky-alpha",
        validation_alias=AliasChoices("SUMMARIZATION_MODEL", "SUMMARIZATION__MODEL"),
    )

    # Orchestration settings
    chunk_size: int = Field(
        default=1200,
        validation_alias=AliasChoices("SUMMARY_CHUNK_SIZE", "SUMMARIZATION__CHUNK_SIZE"),
    )
    max_bullets: int = Field(
        default=6,
        validation_alias=AliasChoices("SUMMARY_MAX_BULLETS", "SUMMARIZATION__MAX_BULLETS"),
    )
    source_archivers: list[str] = Field(
        default_factory=lambda: ["readability"],
        validation_alias=AliasChoices(
            "SUMMARY_SOURCE_ARCHIVERS",
            "SUMMARIZATION__SOURCE_ARCHIVERS",
        ),
    )
    tag_whitelist: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "SUMMARY_TAG_WHITELIST",
            "SUMMARY_TAG_WHITELIST_INTERNAL",
            "SUMMARIZATION__TAG_WHITELIST",
        ),
    )

    @field_validator("providers", mode="before")
    @classmethod
    def _parse_providers(cls, value):
        if value is None:
            return ["huggingface"]
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
            return items or ["huggingface"]
        if isinstance(value, (list, tuple, set)):
            items = [str(item).strip() for item in value if str(item).strip()]
            return items or ["huggingface"]
        return ["huggingface"]

    @field_validator("source_archivers", mode="before")
    @classmethod
    def _parse_source_archivers(cls, value):
        if value is None:
            return ["readability"]
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
            return items or ["readability"]
        if isinstance(value, (list, tuple, set)):
            items = [str(item).strip() for item in value if str(item).strip()]
            return items or ["readability"]
        return ["readability"]

    @field_validator("tag_whitelist", mode="before")
    @classmethod
    def _parse_tag_whitelist(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return []


class AppSettings(BaseSettings):
    """Application configuration loaded from environment variables.

    Uses pydantic-settings to support .env and environment overrides.
    """

    data_dir: Path = Field(default=Path("/data"), validation_alias=AliasChoices("DATA_DIR"))
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    ht_bin: str = Field(default="/usr/local/bin/ht", validation_alias=AliasChoices("HT_BIN"))
    monolith_bin: str = Field(
        default="/usr/local/bin/monolith",
        validation_alias=AliasChoices("MONOLITH_BIN"),
    )
    chromium: ChromiumSettings = Field(default_factory=ChromiumSettings)
    monolith_flags: str = Field(default="", validation_alias=AliasChoices("MONOLITH_FLAGS"))
    singlefile_bin: str = Field(
        default="/usr/local/bin/single-file",
        validation_alias=AliasChoices("SINGLEFILE_BIN"),
    )
    singlefile_flags: str = Field(
        default="", validation_alias=AliasChoices("SINGLEFILE_FLAGS"),
    )
    ht_listen: str = Field(default="localhost:7681", validation_alias=AliasChoices("HT_LISTEN"))
    start_ht: bool = Field(default=True, validation_alias=AliasChoices("START_HT"))
    ht_log_file: Path = Field(
        default=Path("/data/ht.log"),
        validation_alias=AliasChoices("HT_LOG_FILE"),
    )
    log_level: str = Field(default="INFO", validation_alias=AliasChoices("LOG_LEVEL"))
    skip_existing_saves: bool = Field(
        default=True,
        validation_alias=AliasChoices("SKIP_EXISTING_SAVES"),
    )
    summarization: SummarizationSettings = Field(default_factory=SummarizationSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
        env_nested_delimiter="__",
    )


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
