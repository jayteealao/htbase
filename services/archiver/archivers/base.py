from __future__ import annotations

import abc
from pathlib import Path
from typing import Optional

from core.config import AppSettings
from core.utils import sanitize_filename
from models import ArchiveResult
from storage.file_storage import FileStorageProvider
from storage.database_storage import DatabaseStorageProvider


class BaseArchiver(abc.ABC):
    name: str = "base"
    output_extension: str = "html"  # Subclasses can override (e.g., "pdf", "png")

    def __init__(
        self,
        settings: AppSettings,
        file_storage_providers: Optional[list[FileStorageProvider]] = None,
        db_storage: Optional[DatabaseStorageProvider] = None
    ):
        self.settings = settings
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

    def upload_to_all_providers(
        self,
        local_path: Path,
        item_id: str
    ) -> list[dict]:
        """Upload file to all configured storage providers.

        Args:
            local_path: Path to the local file to upload
            item_id: Article identifier

        Returns:
            List of upload results (one per provider)
        """
        import logging
        from datetime import datetime

        logger = logging.getLogger(__name__)

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
                        'uploaded_at': datetime.utcnow(),
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
            from storage.database_storage import ArchiveArtifact, ArchiveStatus

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
        """Archive URL and upload to all configured storage providers.

        This method extends the base archive() method to handle:
        - File storage upload to all configured providers
        - Database storage updates (PostgreSQL or Firestore)
        - Local file cleanup scheduling (only after ALL uploads succeed)

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
            # Extract first upload result (GCS takes priority if multiple providers)
            primary_result = upload_results[0] if upload_results else {}
            self.update_database_storage(item_id, primary_result)

            # 6. Update Firestore article status if using Firestore backend
            if self.db_storage and self.db_storage.provider_name == "firestore":
                self._update_firestore_article_status(item_id, result, upload_results)

            # 7. Schedule cleanup only if ALL uploads succeeded
            if all_succeeded and self.settings.enable_local_cleanup:
                artifact_id = self._get_artifact_id(item_id)
                if artifact_id:
                    self.schedule_local_cleanup(
                        local_path=local_path,
                        artifact_id=artifact_id,
                        retention_hours=self.settings.local_workspace_retention_hours
                    )

        return result

    def schedule_local_cleanup(
        self,
        local_path: Path,
        artifact_id: int,
        retention_hours: int
    ) -> None:
        """Schedule cleanup of local file after retention period.

        Args:
            local_path: Path to local file to clean up
            artifact_id: Artifact database ID for tracking
            retention_hours: Hours to wait before cleanup
        """
        if not self.settings.enable_local_cleanup:
            return

        cleanup_manager = getattr(self, '_cleanup_manager', None)
        if cleanup_manager:
            cleanup_manager.schedule_cleanup(local_path, artifact_id, retention_hours)

    def _get_artifact_id(self, item_id: str) -> Optional[int]:
        """Get artifact ID from database for this archiver and item.

        Args:
            item_id: Article identifier

        Returns:
            Artifact ID or None if not found
        """
        try:
            from db import ArchiveArtifactRepository
            repo = ArchiveArtifactRepository(
                self.settings.database.resolved_path(self.settings.data_dir)
            )
            artifact = repo.find_successful(item_id=item_id, archiver=self.name)
            return artifact.id if artifact else None
        except Exception:
            return None

    def _update_firestore_article_status(
        self,
        item_id: str,
        result,
        upload_results: list[dict]
    ) -> None:
        """Update Firestore article status after archival completes.

        Args:
            item_id: Article identifier
            result: ArchiveResult from archival
            upload_results: List of upload results from storage providers
        """
        import logging
        from datetime import datetime

        logger = logging.getLogger(__name__)

        if not self.db_storage:
            return

        try:
            # Check if any archiver has completed successfully
            # (we only update article status to "completed" when at least one archiver succeeds)
            # The Cloud Function onArchiveStatusChange will handle sync to PostgreSQL if needed

            # Update specific archiver status in archives map
            gcs_path = None
            for upload in upload_results:
                if upload.get('success') and upload.get('storage_uri'):
                    # Extract GCS path from storage URI
                    uri = upload.get('storage_uri', '')
                    if uri.startswith('gs://'):
                        gcs_path = uri.replace('gs://', '').split('/', 1)[1]
                        break

            # Update artifact status
            from storage.database_storage import ArchiveStatus
            self.db_storage.update_artifact_status(
                item_id=item_id,
                archiver=self.name,
                status=ArchiveStatus.SUCCESS if result.success else ArchiveStatus.FAILED,
                gcs_path=gcs_path
            )

            # Update article metadata with completion status
            # Only mark as "completed" if this archival was successful
            if result.success:
                try:
                    self.db_storage.update_article_metadata(
                        item_id=item_id,
                        metadata={
                            'status': 'completed',
                            'updated_at': datetime.utcnow()
                        }
                    )
                    logger.info(f"Updated Firestore article {item_id} status to completed")
                except Exception as e:
                    logger.warning(f"Failed to update article metadata for {item_id}: {e}")

        except Exception as e:
            # Log error but don't fail the archival if Firestore update fails
            logger.error(f"Failed to update Firestore for {item_id}/{self.name}: {e}")

    @abc.abstractmethod
    def archive(self, *, url: str, item_id: str) -> ArchiveResult:  # noqa: D401
        """Archive the given URL keyed by item_id; returns result metadata."""
        raise NotImplementedError
