"""
Base Archiver class.

All archivers inherit from this base class and implement the archive method.
Uses temporary files and uploads directly to GCS - no local file storage.
"""

from __future__ import annotations

import abc
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from shared.config import SharedSettings
from shared.storage.gcs_file_storage import GCSFileStorage
from shared.utils import sanitize_filename
from shared.models import ArchiveResult

logger = logging.getLogger(__name__)


class BaseArchiver(abc.ABC):
    """Base class for all archivers with GCS-only storage."""

    name: str = "base"
    output_extension: str = "html"

    def __init__(
        self,
        settings: SharedSettings,
        command_runner=None,
    ):
        self.settings = settings
        self.command_runner = command_runner

        # Initialize GCS file storage with compression support
        self.gcs_storage = GCSFileStorage(
            bucket_name=settings.gcs.bucket,
            project_id=settings.gcs.project_id,
        )

    def get_gcs_path(self, item_id: str) -> str:
        """Get GCS object path for this archiver.

        Args:
            item_id: Article identifier

        Returns:
            GCS path like "archives/{item_id}/{archiver}/output.{ext}"
        """
        safe_item = sanitize_filename(item_id)
        return f"archives/{safe_item}/{self.name}/output.{self.output_extension}"

    def validate_output(
        self,
        path: Path,
        exit_code: int | None,
        min_size: int = 1,
    ) -> bool:
        """Validate that archiver output meets success criteria."""
        exists = path.exists()
        size = path.stat().st_size if exists else 0

        valid = exit_code == 0 and exists and size >= min_size

        if not valid:
            logger.warning(
                f"Validation failed: exit_code={exit_code}, exists={exists}, size={size}, min_size={min_size}",
                extra={"archiver": self.name, "path": str(path)}
            )

        return valid

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

    def upload_to_gcs(self, local_path: Path, item_id: str) -> dict:
        """Upload file to GCS with automatic compression for compressible formats.

        Uses GCSFileStorage which handles gzip compression automatically.
        Binary formats (PDF, PNG, JPEG) skip compression as they're already compressed.

        Args:
            local_path: Path to temporary file
            item_id: Article identifier

        Returns:
            Upload metadata dict with gcs_path, sizes, compression info, etc.
        """
        gcs_path = self.get_gcs_path(item_id)

        # Determine if we should compress (skip for already-compressed formats)
        compress = self._should_compress()

        # Upload using GCSFileStorage (handles compression automatically)
        result = self.gcs_storage.upload_file(
            local_path=local_path,
            destination_path=gcs_path,
            compress=compress,
        )

        if not result.success:
            raise RuntimeError(f"GCS upload failed: {result.error}")

        return {
            "gcs_path": result.uri,
            "gcs_bucket": self.settings.gcs.bucket,
            "original_size": result.original_size,
            "stored_size": result.stored_size,
            "compressed": compress,
            "compression_ratio": result.compression_ratio,
            "uploaded_at": datetime.utcnow().isoformat(),
        }

    def _should_compress(self) -> bool:
        """Check if this archiver's output should be compressed.

        Binary formats like PDF, PNG, JPEG are already compressed,
        so we skip compression for those to avoid wasting CPU.
        """
        skip_compression = {'pdf', 'png', 'jpg', 'jpeg', 'webp', 'gif'}
        return self.output_extension.lower() not in skip_compression

    def _get_content_type(self) -> str:
        """Get content type for GCS upload based on extension."""
        content_types = {
            "html": "text/html",
            "json": "application/json",
            "pdf": "application/pdf",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
        }
        return content_types.get(self.output_extension, "application/octet-stream")

    def archive_and_upload_to_gcs(
        self,
        *,
        url: str,
        item_id: str
    ) -> ArchiveResult:
        """Archive URL to temporary file and upload to Google Cloud Storage.

        This is the main entry point for all archivers. It handles the complete workflow:
        1. Create temporary file
        2. Run archiver (saves to temp file)
        3. Upload to GCS if successful
        4. Delete temp file
        5. Return result with GCS metadata

        Args:
            url: URL to archive
            item_id: Article identifier

        Returns:
            ArchiveResult with GCS metadata including gcs_path, gcs_bucket, and file size
        """
        # Create temporary file
        temp_fd, temp_path_str = tempfile.mkstemp(
            suffix=f".{self.output_extension}",
            prefix=f"{self.name}_",
        )
        temp_path = Path(temp_path_str)

        try:
            # Close the file descriptor (we'll use the path)
            import os
            os.close(temp_fd)

            # Run archiver (saves to temp_path)
            result = self.archive(url=url, item_id=item_id, output_path=temp_path)

            # Upload to GCS if successful
            if result.success and temp_path.exists():
                try:
                    upload_metadata = self.upload_to_gcs(temp_path, item_id)

                    # Add upload metadata to result
                    if result.metadata is None:
                        result.metadata = {}
                    result.metadata.update(upload_metadata)

                    logger.info(
                        f"Uploaded {self.name} archive to GCS",
                        extra={
                            "item_id": item_id,
                            "gcs_path": upload_metadata["gcs_path"],
                            "size": upload_metadata["stored_size"],
                        }
                    )

                except Exception as e:
                    logger.error(f"GCS upload failed for {item_id}/{self.name}: {e}", exc_info=True)
                    # Mark result as failed if upload fails
                    result.success = False
                    if result.metadata is None:
                        result.metadata = {}
                    result.metadata["upload_error"] = str(e)

            return result

        finally:
            # Always cleanup temp file
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_path}: {e}")

    def archive_with_storage(
        self,
        *,
        url: str,
        item_id: str
    ) -> ArchiveResult:
        """DEPRECATED: Use archive_and_upload_to_gcs() instead.

        This method is maintained for backward compatibility only.

        Args:
            url: URL to archive
            item_id: Article identifier

        Returns:
            ArchiveResult with GCS metadata
        """
        logger.warning(
            "archive_with_storage() is deprecated, use archive_and_upload_to_gcs() instead",
            extra={"archiver": self.name, "item_id": item_id}
        )
        return self.archive_and_upload_to_gcs(url=url, item_id=item_id)

    @abc.abstractmethod
    def archive(self, *, url: str, item_id: str, output_path: Path) -> ArchiveResult:
        """Archive the given URL and save to output_path.

        This method must be implemented by all archiver subclasses.

        Args:
            url: URL to archive
            item_id: Article identifier
            output_path: Path to save the archived content

        Returns:
            ArchiveResult indicating success/failure
        """
        raise NotImplementedError
