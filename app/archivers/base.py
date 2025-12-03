from __future__ import annotations

import abc
from pathlib import Path
from typing import Optional

from core.config import AppSettings
from core.utils import sanitize_filename
from models import ArchiveResult
from ..storage.file_storage import FileStorageProvider
from ..storage.database_storage import DatabaseStorageProvider


class BaseArchiver(abc.ABC):
    name: str = "base"
    output_extension: str = "html"  # Subclasses can override (e.g., "pdf", "png")

    def __init__(
        self,
        settings: AppSettings,
        file_storage: Optional[FileStorageProvider] = None,
        db_storage: Optional[DatabaseStorageProvider] = None
    ):
        self.settings = settings
        self.file_storage = file_storage
        self.db_storage = db_storage

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

    def handle_file_storage(
        self,
        local_path: Path,
        item_id: str
    ) -> dict:
        """Handle file storage upload and return storage metadata.

        Args:
            local_path: Path to the local file to upload
            item_id: Article identifier

        Returns:
            Dictionary with storage metadata (gcs_path, compressed_size, etc.)
        """
        if not self.file_storage or not local_path.exists():
            return {}

        try:
            # Determine storage path
            storage_path = f"archives/{item_id}/{self.name}/output.{self.output_extension}"

            # Upload to storage (will compress if supported)
            upload_result = self.file_storage.upload_file(
                local_path=local_path,
                destination_path=storage_path,
                compress=True
            )

            return {
                'gcs_path': upload_result.storage_path,
                'gcs_bucket': getattr(upload_result, 'bucket_name', None),
                'compressed_size': upload_result.compressed_size,
                'compression_ratio': upload_result.compression_ratio,
                'file_size': upload_result.compressed_size,
            }
        except Exception as e:
            # Log error but don't fail the archiving process
            print(f"Storage upload failed for {item_id}/{self.name}: {e}")
            return {}

    def update_database_storage(
        self,
        item_id: str,
        archive_result: dict
    ) -> None:
        """Update database storage with archive metadata.

        Args:
            item_id: Article identifier
            archive_result: Storage metadata from handle_file_storage
        """
        if not self.db_storage or not archive_result:
            return

        try:
            from ..storage.database_storage import ArchiveArtifact, ArchiveStatus

            # Update artifact status with storage metadata
            self.db_storage.update_artifact_status(
                item_id=item_id,
                archiver=self.name,
                status=ArchiveStatus.SUCCESS,
                gcs_path=archive_result.get('gcs_path'),
                gcs_bucket=archive_result.get('gcs_bucket'),
                file_size=archive_result.get('compressed_size'),
                compression_ratio=archive_result.get('compression_ratio')
            )
        except Exception as e:
            # Log error but don't fail the archiving process
            print(f"Database update failed for {item_id}/{self.name}: {e}")

    def archive_with_storage(
        self,
        *,
        url: str,
        item_id: str
    ) -> ArchiveResult:
        """Archive URL with storage abstraction integration.

        This method extends the base archive() method to handle:
        - File storage upload (local or GCS)
        - Database storage updates (PostgreSQL or Firestore)

        Args:
            url: URL to archive
            item_id: Article identifier

        Returns:
            ArchiveResult with storage metadata included
        """
        # 1. Run the base archiving logic
        result = self.archive(url=url, item_id=item_id)

        # 2. Handle file storage upload if successful
        if result.success and result.saved_path and self.file_storage:
            storage_metadata = self.handle_file_storage(
                Path(result.saved_path),
                item_id
            )

            # Add storage metadata to result
            if storage_metadata:
                if result.metadata is None:
                    result.metadata = {}
                result.metadata.update(storage_metadata)

                # Update database with storage info
                self.update_database_storage(item_id, storage_metadata)

        return result

    @abc.abstractmethod
    def archive(self, *, url: str, item_id: str) -> ArchiveResult:  # noqa: D401
        """Archive the given URL keyed by item_id; returns result metadata."""
        raise NotImplementedError
