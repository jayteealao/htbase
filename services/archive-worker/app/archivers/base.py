"""
Base Archiver class.

All archivers inherit from this base class and implement the archive method.
"""

from __future__ import annotations

import abc
import logging
from pathlib import Path
from typing import Optional

from shared.config import SharedSettings
from shared.utils import sanitize_filename
from shared.models import ArchiveResult

logger = logging.getLogger(__name__)


class BaseArchiver(abc.ABC):
    """Base class for all archivers."""

    name: str = "base"
    output_extension: str = "html"

    def __init__(
        self,
        settings: SharedSettings,
        command_runner=None,
    ):
        self.settings = settings
        self.command_runner = command_runner

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

    def has_existing_output(self, item_id: str) -> Path | None:
        """Check if this archiver already has output files for the given item_id.

        Returns the path to an existing output file if found, None otherwise.
        """
        safe_item = sanitize_filename(item_id)
        out_dir = self.settings.data_dir / safe_item / self.name

        if not out_dir.exists():
            return None

        # Check for standard output file
        standard_path = out_dir / f"output.{self.output_extension}"
        if standard_path.exists() and standard_path.stat().st_size > 0:
            return standard_path

        # Check for numbered variants
        for numbered_file in out_dir.glob(f"output (*).{self.output_extension}"):
            if numbered_file.exists() and numbered_file.stat().st_size > 0:
                return numbered_file

        return None

    def validate_output(
        self,
        path: Path,
        exit_code: int | None,
        min_size: int = 1,
    ) -> bool:
        """Validate that archiver output meets success criteria."""
        return (
            exit_code == 0
            and path.exists()
            and path.stat().st_size >= min_size
        )

    def create_result(
        self,
        path: Path,
        exit_code: int | None,
        metadata: dict | None = None,
        min_size: int = 1,
    ) -> ArchiveResult:
        """Create a standardized ArchiveResult from archiver execution."""
        success = self.validate_output(path, exit_code, min_size)
        return ArchiveResult(
            success=success,
            exit_code=exit_code,
            saved_path=str(path) if success else None,
            metadata=metadata,
        )

    @abc.abstractmethod
    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        """Archive the given URL keyed by item_id; returns result metadata."""
        raise NotImplementedError
