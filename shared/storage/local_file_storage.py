"""
Local File System Storage Implementation

Stores files on the local filesystem.
Useful for development, testing, and self-hosted deployments.
"""

import gzip
import logging
import shutil
from pathlib import Path
from typing import Optional, BinaryIO, List
from datetime import datetime, timedelta

from .file_storage import (
    FileStorageProvider,
    FileMetadata,
    UploadResult
)

logger = logging.getLogger(__name__)


class LocalFileStorage(FileStorageProvider):
    """
    Local filesystem storage implementation.

    Files are stored in a local directory with optional compression.
    """

    def __init__(self, root_dir: Path, base_url: Optional[str] = None):
        """
        Initialize local file storage.

        Args:
            root_dir: Root directory for file storage
            base_url: Base URL for serving files (e.g., http://localhost:8080/files)
                     If None, file:/// URLs will be used
        """
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url

    def upload_file(
        self,
        local_path: Path,
        destination_path: str,
        compress: bool = True,
        storage_class: Optional[str] = None
    ) -> UploadResult:
        """Upload file to local storage."""
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

            # Prepare destination
            dest_path = self.root_dir / destination_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            original_size = local_path.stat().st_size

            if compress:
                # Add .gz extension if not present
                if not dest_path.suffix == '.gz':
                    dest_path = dest_path.with_suffix(dest_path.suffix + '.gz')

                # Compress and upload
                with open(local_path, 'rb') as f_in:
                    with gzip.open(dest_path, 'wb', compresslevel=9) as f_out:
                        shutil.copyfileobj(f_in, f_out)

                stored_size = dest_path.stat().st_size
                compression_ratio = (1 - stored_size / original_size) * 100 if original_size > 0 else 0
            else:
                # Direct copy
                shutil.copy2(local_path, dest_path)
                stored_size = dest_path.stat().st_size
                compression_ratio = None

            # Generate URI
            relative_path = dest_path.relative_to(self.root_dir)
            uri = f"file:///{dest_path}" if not self.base_url else f"{self.base_url}/{relative_path}"

            return UploadResult(
                success=True,
                uri=uri,
                original_size=original_size,
                stored_size=stored_size,
                compression_ratio=compression_ratio
            )

        except Exception as e:
            logger.error(f"Local storage upload failed: {e}")
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
        """Download file from local storage."""
        try:
            source_path = self.root_dir / storage_path
            if not source_path.exists():
                return False

            local_path = Path(local_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # Check if file is compressed
            is_compressed = source_path.suffix == '.gz'

            if is_compressed and decompress:
                # Decompress
                with gzip.open(source_path, 'rb') as f_in:
                    with open(local_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
            else:
                # Direct copy
                shutil.copy2(source_path, local_path)

            return True

        except Exception as e:
            logger.error(f"Local storage download failed: {e}")
            return False

    def get_file_stream(self, storage_path: str) -> BinaryIO:
        """Get file stream for reading."""
        file_path = self.root_dir / storage_path

        if file_path.suffix == '.gz':
            return gzip.open(file_path, 'rb')
        else:
            return open(file_path, 'rb')

    def delete_file(self, storage_path: str) -> bool:
        """Delete file from local storage."""
        try:
            file_path = self.root_dir / storage_path
            if file_path.exists():
                file_path.unlink()
            return True
        except Exception as e:
            logger.error(f"Local storage delete failed: {e}")
            return False

    def exists(self, storage_path: str) -> bool:
        """Check if file exists."""
        file_path = self.root_dir / storage_path
        return file_path.exists()

    def get_metadata(self, storage_path: str) -> Optional[FileMetadata]:
        """Get file metadata."""
        file_path = self.root_dir / storage_path
        if not file_path.exists():
            return None

        stat = file_path.stat()
        is_compressed = file_path.suffix == '.gz'

        return FileMetadata(
            path=storage_path,
            size=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_ctime),
            storage_class="LOCAL",
            content_type=self._guess_content_type(file_path),
            compressed=is_compressed,
            compression_ratio=None  # Would need original size to calculate
        )

    def generate_access_url(
        self,
        storage_path: str,
        expiration: timedelta = timedelta(days=7)
    ) -> str:
        """Generate access URL."""
        file_path = self.root_dir / storage_path

        if self.base_url:
            # HTTP URL
            relative_path = file_path.relative_to(self.root_dir)
            return f"{self.base_url}/{relative_path}"
        else:
            # file:/// URL
            return f"file:///{file_path}"

    def list_files(
        self,
        prefix: str = "",
        limit: Optional[int] = None
    ) -> List[FileMetadata]:
        """List files with optional prefix filter."""
        search_path = self.root_dir / prefix if prefix else self.root_dir

        files = []
        for file_path in search_path.rglob('*'):
            if file_path.is_file():
                relative_path = file_path.relative_to(self.root_dir)
                metadata = self.get_metadata(str(relative_path))
                if metadata:
                    files.append(metadata)

                if limit and len(files) >= limit:
                    break

        return files

    @property
    def provider_name(self) -> str:
        """Provider name."""
        return "local"

    @property
    def supports_compression(self) -> bool:
        """Supports compression."""
        return True

    @property
    def supports_signed_urls(self) -> bool:
        """Does not support signed URLs (uses file:/// or HTTP)."""
        return False

    def serve_file(
        self,
        storage_path: str,
        filename: str,
        media_type: str = "application/octet-stream"
    ):
        """Serve file from local storage."""
        from fastapi.responses import FileResponse
        from fastapi import HTTPException

        file_path = self.root_dir / storage_path
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found in storage")

        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=filename
        )

    def download_to_temp(self, storage_path: str) -> Path:
        """For local storage, just return the path directly since it's already local."""
        file_path = self.root_dir / storage_path
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {storage_path}")
        return file_path

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
