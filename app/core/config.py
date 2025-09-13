from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application configuration loaded from environment variables.

    Uses pydantic-settings to support .env and environment overrides.
    """

    data_dir: Path = Field(default=Path("/data"), alias="DATA_DIR")
    db_path: Path | None = Field(default=None, alias="DB_PATH")
    ht_bin: str = Field(default="/usr/local/bin/ht", alias="HT_BIN")
    monolith_bin: str = Field(default="/usr/local/bin/monolith", alias="MONOLITH_BIN")
    use_chromium: bool = Field(default=True, alias="USE_CHROMIUM")
    chromium_bin: str = Field(default="/usr/bin/chromium", alias="CHROMIUM_BIN")
    # Extra flags to pass to monolith (space-separated, supports quotes)
    monolith_flags: str = Field(default="", alias="MONOLITH_FLAGS")
    ht_listen: str = Field(default="localhost:7681", alias="HT_LISTEN")
    start_ht: bool = Field(default=True, alias="START_HT")
    # Log all ht stdin/stdout to a file under data dir by default
    ht_log_file: Path = Field(default=Path("/data/ht.log"), alias="HT_LOG_FILE")

    # Skip re-archiving when a successful save already exists for the same
    # item_id or URL (checks the saves table). Disabled by default to preserve
    # current behavior unless explicitly enabled.
    skip_existing_saves: bool = Field(default=False, alias="SKIP_EXISTING_SAVES")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def resolved_db_path(self) -> Path:
        return self.db_path or (self.data_dir / "app.db")


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()

