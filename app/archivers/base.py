from __future__ import annotations

import abc
from pathlib import Path

from core.config import AppSettings
from core.utils import sanitize_filename
from models import ArchiveResult


class BaseArchiver(abc.ABC):
    name: str = "base"
    output_extension: str = "html"  # Subclasses can override (e.g., "pdf", "png")

    def __init__(self, settings: AppSettings):
        self.settings = settings

    def get_output_path(self, item_id: str) -> tuple[Path, Path]:
        """Return (output_dir, output_file_path) for this archiver.

        Args:
            item_id: Item identifier (will be sanitized)

        Returns:
            Tuple of (output_directory, output_file_path)
        """
        safe_item = sanitize_filename(item_id)
        out_dir = self.settings.data_dir / safe_item / self.name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"output.{self.output_extension}"
        return out_dir, out_path

    @abc.abstractmethod
    def archive(self, *, url: str, item_id: str) -> ArchiveResult:  # noqa: D401
        """Archive the given URL keyed by item_id; returns result metadata."""
        raise NotImplementedError
