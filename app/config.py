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
    ht_listen: str = Field(default="0.0.0.0:7681", alias="HT_LISTEN")
    start_ht: bool = Field(default=True, alias="START_HT")

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
