"""
Google Cloud Storage Implementation

Stores files in Google Cloud Storage with compression,
lifecycle policies, and signed URL support.
"""

import gzip
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional, BinaryIO, List
from datetime import datetime, timedelta

from google.cloud import storage

from .file_storage import (
    FileStorageProvider,
    FileMetadata,
    UploadResult
)

logger = logging.getLogger(__name__)


class GCSFileStorage(FileStorageProvider):
    """
    Google Cloud Storage implementation.

    Features:
    - Automatic compression
    - Lifecycle policies (tiering, deletion)
    - Signed URLs for secure access
    - Multiple storage classes
    """

    def __init__(
        self,
        bucket_name: str,
        project_id: Optional[str] = None
    ):
        """
        Initialize GCS storage.

        Args:
            bucket_name: GCS bucket name
            project_id: Optional GCP project ID
        """
        self.client = storage.Client(project=project_id)
        self.bucket = self.client.bucket(bucket_name)
        self.bucket_name = bucket_name

    def upload_file(
        self,
        local_path: Path,
        destination_path: str,
        compress: bool = True,
        storage_class: Optional[str] = None
    ) -> UploadResult:
        """Upload file to GCS."""
        try:
            local_path = Path(local_path)
            if not local_path.exists():
                return UploadResult(
                    success=False,
                    uri="",
                    original_size=0,
                    stored_size=0,
                    error=f"Source file not found: {local_path}"
                )

            original_size = local_path.stat().st_size

            if compress:
                # Compress to temp file
                compressed_path = local_path.with_suffix(local_path.suffix + '.gz')
                with open(local_path, 'rb') as f_in:
                    with gzip.open(compressed_path, 'wb', compresslevel=9) as f_out:
                        shutil.copyfileobj(f_in, f_out)

                stored_size = compressed_path.stat().st_size
                compression_ratio = (1 - stored_size / original_size) * 100 if original_size > 0 else 0

                # Add .gz to destination if not present
                if not destination_path.endswith('.gz'):
                    destination_path = destination_path + '.gz'

                upload_path = compressed_path
            else:
                upload_path = local_path
                stored_size = original_size
                compression_ratio = None

            # Upload to GCS
            blob = self.bucket.blob(destination_path)

            # Set metadata
            blob.content_type = self._guess_content_type(Path(destination_path))
            if compress:
                blob.metadata = {'compressed': 'true', 'original_size': str(original_size)}

            blob.upload_from_filename(str(upload_path))

            # Set storage class if specified
            if storage_class:
                blob.update_storage_class(storage_class)

            # Clean up temp compressed file
            if compress and compressed_path.exists():
                compressed_path.unlink()

            uri = f"gs://{self.bucket_name}/{destination_path}"

            return UploadResult(
                success=True,
                uri=uri,
                original_size=original_size,
                stored_size=stored_size,
                compression_ratio=compression_ratio
            )

        except Exception as e:
            logger.error(f"GCS upload failed: {e}")
            return UploadResult(
                success=False,
                uri="",
                original_size=0,
                stored_size=0,
                error=str(e)
            )

    def download_file(
        self,
        storage_path: str,
        local_path: Path,
        decompress: bool = True
    ) -> bool:
        """Download file from GCS."""
        try:
            blob = self.bucket.blob(storage_path)
            if not blob.exists():
                return False

            local_path = Path(local_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            is_compressed = storage_path.endswith('.gz')

            if is_compressed and decompress:
                # Download and decompress
                temp_path = local_path.with_suffix(local_path.suffix + '.gz')
                blob.download_to_filename(str(temp_path))

                with gzip.open(temp_path, 'rb') as f_in:
                    with open(local_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)

                temp_path.unlink()
            else:
                # Direct download
                blob.download_to_filename(str(local_path))

            return True

        except Exception as e:
            logger.error(f"GCS download failed: {e}")
            return False

    def get_file_stream(self, storage_path: str) -> BinaryIO:
        """Get file stream for reading."""
        blob = self.bucket.blob(storage_path)
        return blob.open('rb')

    def delete_file(self, storage_path: str) -> bool:
        """Delete file from GCS."""
        try:
            blob = self.bucket.blob(storage_path)
            if blob.exists():
                blob.delete()
            return True
        except Exception as e:
            logger.error(f"GCS delete failed: {e}")
            return False

    def exists(self, storage_path: str) -> bool:
        """Check if file exists."""
        blob = self.bucket.blob(storage_path)
        return blob.exists()

    def get_metadata(self, storage_path: str) -> Optional[FileMetadata]:
        """Get file metadata."""
        blob = self.bucket.blob(storage_path)
        if not blob.exists():
            return None

        blob.reload()

        is_compressed = storage_path.endswith('.gz')
        original_size = None
        if is_compressed and blob.metadata:
            original_size = blob.metadata.get('original_size')
            original_size = int(original_size) if original_size else None

        compression_ratio = None
        if original_size and blob.size:
            compression_ratio = (1 - blob.size / original_size) * 100

        return FileMetadata(
            path=storage_path,
            size=blob.size,
            created_at=blob.time_created,
            storage_class=blob.storage_class,
            content_type=blob.content_type,
            compressed=is_compressed,
            compression_ratio=compression_ratio
        )

    def generate_access_url(
        self,
        storage_path: str,
        expiration: timedelta = timedelta(days=7)
    ) -> str:
        """Generate signed URL."""
        blob = self.bucket.blob(storage_path)
        url = blob.generate_signed_url(
            version="v4",
            expiration=expiration,
            method="GET"
        )
        return url

    def list_files(
        self,
        prefix: str = "",
        limit: Optional[int] = None
    ) -> List[FileMetadata]:
        """List files with optional prefix filter."""
        blobs = self.client.list_blobs(
            self.bucket_name,
            prefix=prefix,
            max_results=limit
        )

        files = []
        for blob in blobs:
            metadata = self.get_metadata(blob.name)
            if metadata:
                files.append(metadata)

        return files

    def set_lifecycle_policy(self):
        """Set lifecycle policy for automatic tiering and deletion."""
        bucket = self.client.get_bucket(self.bucket_name)

        # Delete files after 3 years
        bucket.add_lifecycle_delete_rule(age=365 * 3)

        # Transition to Nearline after 30 days
        bucket.add_lifecycle_set_storage_class_rule(
            storage_class='NEARLINE',
            age=30
        )

        # Transition to Coldline after 90 days
        bucket.add_lifecycle_set_storage_class_rule(
            storage_class='COLDLINE',
            age=90
        )

        bucket.patch()

    @property
    def provider_name(self) -> str:
        """Provider name."""
        return "gcs"

    @property
    def supports_compression(self) -> bool:
        """Supports compression."""
        return True

    @property
    def supports_signed_urls(self) -> bool:
        """Supports signed URLs."""
        return True

    def serve_file(
        self,
        storage_path: str,
        filename: str,
        media_type: str = "application/octet-stream"
    ):
        """Serve file from GCS by streaming."""
        from fastapi.responses import StreamingResponse
        from fastapi import HTTPException

        blob = self.bucket.blob(storage_path)
        if not blob.exists():
            raise HTTPException(status_code=404, detail="File not found in GCS")

        # Stream file from GCS
        def iterfile():
            with blob.open('rb') as f:
                while chunk := f.read(8192):  # 8KB chunks
                    yield chunk

        headers = {
            'Content-Disposition': f'attachment; filename="{filename}"'
        }

        return StreamingResponse(
            iterfile(),
            media_type=media_type,
            headers=headers
        )

    def download_to_temp(self, storage_path: str) -> Path:
        """Download from GCS to temporary file."""
        blob = self.bucket.blob(storage_path)
        if not blob.exists():
            raise FileNotFoundError(f"File not found in GCS: {storage_path}")

        # Create temp file with proper extension
        suffix = Path(storage_path).suffix
        temp_file = Path(tempfile.mktemp(suffix=suffix))

        # Download (handles decompression if .gz)
        is_compressed = storage_path.endswith('.gz')
        self.download_file(storage_path, temp_file, decompress=is_compressed)

        return temp_file

    def _guess_content_type(self, file_path: Path) -> str:
        """Guess content type from file extension."""
        suffix = file_path.suffix.lower()
        if suffix == '.gz':
            # Get inner suffix
            suffix = file_path.stem.split('.')[-1] if '.' in file_path.stem else ''

        content_types = {
            'html': 'text/html',
            'pdf': 'application/pdf',
            'json': 'application/json',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'txt': 'text/plain'
        }

        return content_types.get(suffix, 'application/octet-stream')
