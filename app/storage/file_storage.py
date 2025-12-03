"""
File Storage Abstraction Layer

Provides a unified interface for file storage operations.
Implementations: LocalFileStorage, GCSFileStorage, S3FileStorage, etc.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Tuple, BinaryIO
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class FileMetadata:
    """Metadata about a stored file."""
    path: str
    size: int
    created_at: datetime
    storage_class: Optional[str] = None
    content_type: Optional[str] = None
    compressed: bool = False
    compression_ratio: Optional[float] = None


@dataclass
class UploadResult:
    """Result of a file upload operation."""
    success: bool
    uri: str  # Full URI (file:///path or gs://bucket/path)
    original_size: int
    stored_size: int
    compression_ratio: Optional[float] = None
    error: Optional[str] = None


class FileStorageProvider(ABC):
    """
    Abstract base class for file storage providers.

    All implementations must provide:
    - upload/download operations
    - URL generation for access
    - metadata retrieval
    - deletion
    """

    @abstractmethod
    def upload_file(
        self,
        local_path: Path,
        destination_path: str,
        compress: bool = True,
        storage_class: Optional[str] = None
    ) -> UploadResult:
        """
        Upload a file to storage.

        Args:
            local_path: Local file to upload
            destination_path: Destination path (relative to storage root)
            compress: Whether to compress before upload
            storage_class: Storage tier (STANDARD, NEARLINE, COLDLINE, etc.)

        Returns:
            UploadResult with details about the upload
        """
        pass

    @abstractmethod
    def download_file(
        self,
        storage_path: str,
        local_path: Path,
        decompress: bool = True
    ) -> bool:
        """
        Download a file from storage.

        Args:
            storage_path: Path in storage
            local_path: Local destination
            decompress: Whether to decompress if compressed

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def get_file_stream(self, storage_path: str) -> BinaryIO:
        """
        Get a file stream for reading.

        Args:
            storage_path: Path in storage

        Returns:
            Binary file stream
        """
        pass

    @abstractmethod
    def delete_file(self, storage_path: str) -> bool:
        """
        Delete a file from storage.

        Args:
            storage_path: Path in storage

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def exists(self, storage_path: str) -> bool:
        """
        Check if a file exists.

        Args:
            storage_path: Path in storage

        Returns:
            True if file exists
        """
        pass

    @abstractmethod
    def get_metadata(self, storage_path: str) -> Optional[FileMetadata]:
        """
        Get file metadata.

        Args:
            storage_path: Path in storage

        Returns:
            FileMetadata or None if not found
        """
        pass

    @abstractmethod
    def generate_access_url(
        self,
        storage_path: str,
        expiration: timedelta = timedelta(days=7)
    ) -> str:
        """
        Generate a URL for accessing the file.

        For local storage: file:/// URL
        For GCS: signed URL
        For S3: presigned URL

        Args:
            storage_path: Path in storage
            expiration: How long the URL should be valid

        Returns:
            Access URL
        """
        pass

    @abstractmethod
    def list_files(
        self,
        prefix: str = "",
        limit: Optional[int] = None
    ) -> list[FileMetadata]:
        """
        List files with optional prefix filter.

        Args:
            prefix: Path prefix to filter by
            limit: Maximum number of files to return

        Returns:
            List of FileMetadata
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the storage provider (e.g., 'local', 'gcs', 's3')."""
        pass

    @property
    @abstractmethod
    def supports_compression(self) -> bool:
        """Whether this provider supports transparent compression."""
        pass

    @property
    @abstractmethod
    def supports_signed_urls(self) -> bool:
        """Whether this provider supports signed/presigned URLs."""
        pass
