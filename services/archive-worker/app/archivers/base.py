"""
Base Archiver class.

All archivers inherit from this base class and implement the archive method.
"""

from __future__ import annotations

import abc
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from shared.config import SharedSettings
from shared.utils import sanitize_filename
from shared.models import ArchiveResult
from shared.storage.file_storage import FileStorageProvider
from shared.storage.database_storage import DatabaseStorageProvider, ArchiveStatus

logger = logging.getLogger(__name__)


class BaseArchiver(abc.ABC):
    """Base class for all archivers."""

    name: str = "base"
    output_extension: str = "html"

    def __init__(
        self,
        settings: SharedSettings,
        command_runner=None,
        file_storage_providers: Optional[List[FileStorageProvider]] = None,
        db_storage: Optional[DatabaseStorageProvider] = None,
    ):
        self.settings = settings
        self.command_runner = command_runner
        self.file_storage_providers = file_storage_providers or []
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

    def upload_to_all_providers(
        self,
        local_path: Path,
        item_id: str
    ) -> List[dict]:
        """Upload file to all configured storage providers.

        Args:
            local_path: Path to the local file to upload
            item_id: Article identifier

        Returns:
            List of upload results (one per provider)
        """
        if not self.file_storage_providers or not local_path.exists():
            return []

        results = []
        storage_path = f"archives/{item_id}/{self.name}/output.{self.output_extension}"

        for provider in self.file_storage_providers:
            try:
                upload_result = provider.upload_file(
                    local_path=local_path,
                    destination_path=storage_path,
                    compress=True
                )

                if upload_result.success:
                    metadata = {
                        'provider_name': provider.provider_name,
                        'storage_uri': upload_result.uri,
                        'original_size': upload_result.original_size,
                        'stored_size': upload_result.stored_size,
                        'compression_ratio': upload_result.compression_ratio,
                        'uploaded_at': datetime.utcnow().isoformat(),
                        'success': True
                    }
                else:
                    metadata = {
                        'provider_name': provider.provider_name,
                        'success': False,
                        'error': upload_result.error
                    }

                results.append(metadata)

            except Exception as e:
                logger.error(f"Upload to {provider.provider_name} failed: {e}")
                results.append({
                    'provider_name': provider.provider_name,
                    'success': False,
                    'error': str(e)
                })

        return results

    def update_database_storage(
        self,
        item_id: str,
        upload_results: List[dict]
    ) -> None:
        """Update database storage with archive metadata.

        Args:
            item_id: Article identifier
            upload_results: Storage metadata from upload_to_all_providers
        """
        if not self.db_storage or not upload_results:
            return

        try:
            # Get GCS path from first successful upload
            gcs_path = None
            for result in upload_results:
                if result.get('success') and result.get('storage_uri'):
                    uri = result.get('storage_uri', '')
                    if uri.startswith('gs://'):
                        gcs_path = uri.replace('gs://', '').split('/', 1)[1]
                        break

            # Update artifact status
            self.db_storage.update_artifact_status(
                item_id=item_id,
                archiver=self.name,
                status=ArchiveStatus.SUCCESS,
                gcs_path=gcs_path
            )
        except Exception as e:
            logger.error(f"Database update failed for {item_id}/{self.name}: {e}")

    def archive_with_storage(
        self,
        *,
        url: str,
        item_id: str
    ) -> ArchiveResult:
        """Archive URL and upload to all configured storage providers.

        This method extends the base archive() method to handle:
        - File storage upload to all configured providers
        - Database storage updates (PostgreSQL or Firestore)

        Args:
            url: URL to archive
            item_id: Article identifier

        Returns:
            ArchiveResult with storage metadata included
        """
        # 1. Run the base archiving logic
        result = self.archive(url=url, item_id=item_id)

        # 2. Upload to all providers if successful
        if result.success and result.saved_path and self.file_storage_providers:
            local_path = Path(result.saved_path)
            upload_results = self.upload_to_all_providers(local_path, item_id)

            # 3. Check if ALL uploads succeeded
            all_succeeded = all(r.get('success', False) for r in upload_results)

            # 4. Store upload results in metadata
            if result.metadata is None:
                result.metadata = {}
            result.metadata['storage_uploads'] = upload_results
            result.metadata['all_uploads_succeeded'] = all_succeeded

            # 5. Update database with upload status
            self.update_database_storage(item_id, upload_results)

            # 6. Update Firestore article status if using Firestore backend
            if self.db_storage and hasattr(self.db_storage, 'provider_name'):
                if self.db_storage.provider_name == "firestore":
                    self._update_firestore_article_status(item_id, result, upload_results)

        return result

    def _update_firestore_article_status(
        self,
        item_id: str,
        result: ArchiveResult,
        upload_results: List[dict]
    ) -> None:
        """Update Firestore article status after archival completes.

        Args:
            item_id: Article identifier
            result: ArchiveResult from archival
            upload_results: List of upload results from storage providers
        """
        if not self.db_storage:
            return

        try:
            # Get GCS path from uploads
            gcs_path = None
            for upload in upload_results:
                if upload.get('success') and upload.get('storage_uri'):
                    uri = upload.get('storage_uri', '')
                    if uri.startswith('gs://'):
                        gcs_path = uri.replace('gs://', '').split('/', 1)[1]
                        break

            # Update artifact status
            self.db_storage.update_artifact_status(
                item_id=item_id,
                archiver=self.name,
                status=ArchiveStatus.SUCCESS if result.success else ArchiveStatus.FAILED,
                gcs_path=gcs_path
            )

            # Update article metadata with completion status
            if result.success and hasattr(self.db_storage, 'update_article_metadata'):
                try:
                    self.db_storage.update_article_metadata(
                        item_id=item_id,
                        metadata={
                            'status': 'completed',
                            'updated_at': datetime.utcnow().isoformat()
                        }
                    )
                    logger.info(f"Updated Firestore article {item_id} status to completed")
                except Exception as e:
                    logger.warning(f"Failed to update article metadata for {item_id}: {e}")

        except Exception as e:
            logger.error(f"Failed to update Firestore for {item_id}/{self.name}: {e}")

    @abc.abstractmethod
    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        """Archive the given URL keyed by item_id; returns result metadata."""
        raise NotImplementedError
