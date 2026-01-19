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

from google.cloud import storage

from shared.config import SharedSettings
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

        # Initialize GCS client
        self.gcs_client = storage.Client(project=settings.gcs.project_id)
        self.gcs_bucket = self.gcs_client.bucket(settings.gcs.bucket)

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
        """Upload file directly to GCS and return metadata.

        Args:
            local_path: Path to temporary file
            item_id: Article identifier

        Returns:
            Upload metadata dict with gcs_path, sizes, etc.
        """
        gcs_path = self.get_gcs_path(item_id)
        blob = self.gcs_bucket.blob(gcs_path)

        # Get original file size
        original_size = local_path.stat().st_size

        # Upload file (GCS handles compression if configured)
        blob.upload_from_filename(
            str(local_path),
            content_type=self._get_content_type(),
        )

        # Get stored size
        blob.reload()
        stored_size = blob.size

        return {
            "gcs_path": f"gs://{self.settings.gcs.bucket}/{gcs_path}",
            "gcs_bucket": self.settings.gcs.bucket,
            "original_size": original_size,
            "stored_size": stored_size,
            "compression_ratio": stored_size / original_size if original_size > 0 else 1.0,
            "uploaded_at": datetime.utcnow().isoformat(),
        }

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
                    logger.debug(f"Deleted temp file: {temp_path}")
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
