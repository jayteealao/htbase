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

    def has_existing_output(self, item_id: str) -> Path | None:
        """Check if this archiver already has output files for the given item_id.

        Returns the path to an existing output file if found, None otherwise.
        Checks for both the standard output file and any numbered variants.
        """
        safe_item = sanitize_filename(item_id)
        out_dir = self.settings.data_dir / safe_item / self.name

        if not out_dir.exists():
            return None

        # Check for standard output file
        standard_path = out_dir / f"output.{self.output_extension}"
        if standard_path.exists() and standard_path.stat().st_size > 0:
            return standard_path

        # Check for numbered variants: output (2).html, output (3).html, etc.
        # Pattern: output (*).{extension} where * is any characters
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
        """Validate that archiver output meets success criteria.

        Args:
            path: Path to the output file
            exit_code: Exit code from the archiver command
            min_size: Minimum file size in bytes (default: 1)

        Returns:
            True if output is valid (exit code 0, file exists, size >= min_size)
        """
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
        """Create a standardized ArchiveResult from archiver execution.

        Args:
            path: Path to the output file
            exit_code: Exit code from the archiver command
            metadata: Optional metadata dictionary
            min_size: Minimum file size for success validation (default: 1)

        Returns:
            ArchiveResult with success status and saved path
        """
        success = self.validate_output(path, exit_code, min_size)
        return ArchiveResult(
            success=success,
            exit_code=exit_code,
            saved_path=str(path) if success else None,
            metadata=metadata,
        )

    @abc.abstractmethod
    def archive(self, *, url: str, item_id: str) -> ArchiveResult:  # noqa: D401
        """Archive the given URL keyed by item_id; returns result metadata."""
        raise NotImplementedError
