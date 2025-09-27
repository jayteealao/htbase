from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field, AliasChoices, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application configuration loaded from environment variables.

    Uses pydantic-settings to support .env and environment overrides.
    """

    data_dir: Path = Field(default=Path("/data"), alias="DATA_DIR")
    # Legacy sqlite path (ignored when using Postgres)
    db_path: Path | None = Field(default=None, alias="DB_PATH")

    # Postgres connection settings
    db_host: str = Field(default="192.168.1.12", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_name: str = Field(default="htbase", alias="DB_NAME")
    db_user: str = Field(default="postgres", alias="DB_USER")
    db_password: str = Field(default="your_password", alias="DB_PASSWORD")

    # Archiver configuration
    ht_bin: str = Field(default="/usr/local/bin/ht", alias="HT_BIN")
    monolith_bin: str = Field(default="/usr/local/bin/monolith", alias="MONOLITH_BIN")
    use_chromium: bool = Field(default=True, alias="USE_CHROMIUM")
    chromium_bin: str = Field(default="/usr/bin/chromium", alias="CHROMIUM_BIN")
    # Extra flags to pass to monolith (space-separated, supports quotes)
    monolith_flags: str = Field(default="", alias="MONOLITH_FLAGS")
    # SingleFile CLI configuration
    singlefile_bin: str = Field(default="/usr/local/bin/single-file", alias="SINGLEFILE_BIN")
    # Extra flags to pass to SingleFile CLI (e.g., --browser-executable-path=/usr/bin/chromium)
    singlefile_flags: str = Field(default="", alias="SINGLEFILE_FLAGS")
    ht_listen: str = Field(default="localhost:7681", alias="HT_LISTEN")
    start_ht: bool = Field(default=True, alias="START_HT")
    # Log all ht stdin/stdout to a file under data dir by default
    ht_log_file: Path = Field(default=Path("/data/ht.log"), alias="HT_LOG_FILE")

    # Skip re-archiving when a successful save already exists for the same
    # item_id or URL (checks the saves table). Disabled by default to preserve
    # current behavior unless explicitly enabled.
    skip_existing_saves: bool = Field(default=False, alias="SKIP_EXISTING_SAVES")

    # Summarization / analysis feature flags and configuration
    enable_summarization: bool = Field(
        default=False, alias="ENABLE_SUMMARIZATION"
    )
    openrouter_api_key: str | None = Field(
        default=None, alias="OPENROUTER_API_KEY"
    )
    summarization_model: str = Field(
        default="openrouter/sonoma-sky-alpha", alias="SUMMARIZATION_MODEL"
    )
    summarization_api_base: str | None = Field(
        default=None, alias="SUMMARIZATION_API_BASE"
    )
    summarization_api_key: str | None = Field(
        default=None, alias="SUMMARIZATION_API_KEY"
    )
    summary_chunk_size: int = Field(
        default=1200, alias="SUMMARY_CHUNK_SIZE"
    )
    summary_max_concurrency: int = Field(
        default=4, alias="SUMMARY_MAX_CONCURRENCY"
    )
    summary_max_bullets: int = Field(
        default=6, alias="SUMMARY_MAX_BULLETS"
    )
    summary_source_archivers_raw: str | None = Field(
        default=None,
        alias="SUMMARY_SOURCE_ARCHIVERS",
    )
    summary_source_archivers: list[str] = Field(default_factory=list)
    summary_tag_whitelist_raw: str | None = Field(
        default=None,
        alias="SUMMARY_TAG_WHITELIST",
    )
    summary_tag_whitelist: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("SUMMARY_TAG_WHITELIST_INTERNAL"),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def _populate_whitelist(self) -> "AppSettings":
        raw = self.summary_tag_whitelist_raw
        if raw is None:
            self.summary_tag_whitelist = []
        elif isinstance(raw, str):
            if not raw.strip():
                self.summary_tag_whitelist = []
            else:
                self.summary_tag_whitelist = [item.strip() for item in raw.split(",") if item.strip()]
        elif isinstance(raw, (list, tuple, set)):
            self.summary_tag_whitelist = [str(item).strip() for item in raw if str(item).strip()]
        else:
            self.summary_tag_whitelist = []
        # print(f"Using summary_tag_whitelist: {self.summary_tag_whitelist}")

        raw_sources = self.summary_source_archivers_raw
        if raw_sources is None:
            parsed_sources = ["readability"]
        elif isinstance(raw_sources, str):
            parsed_sources = [
                item.strip() for item in raw_sources.split(",") if item.strip()
            ]
        elif isinstance(raw_sources, (list, tuple, set)):
            parsed_sources = [
                str(item).strip() for item in raw_sources if str(item).strip()
            ]
        else:
            parsed_sources = []
        self.summary_source_archivers = parsed_sources

        return self

    @property
    def resolved_db_path(self) -> Path:
        return self.db_path or (self.data_dir / "app.db")

    @property
    def database_url(self) -> str:
        """Build a SQLAlchemy DSN for Postgres using psycopg driver.

        Example: postgresql+psycopg://user:pass@host:5432/db
        """
        user = quote_plus(self.db_user)
        pwd = quote_plus(self.db_password)
        host = self.db_host
        port = self.db_port
        name = self.db_name
        return f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/{name}"


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()


