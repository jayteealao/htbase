"""
Shared storage module for HTBase microservices.

Provides file storage and database storage provider interfaces
and implementations.
"""

from shared.storage.file_storage import (
    FileMetadata,
    UploadResult,
    FileStorageProvider,
)
from shared.storage.database_storage import (
    ArchiveStatus,
    ArticleMetadata,
    ArchiveArtifact,
    DatabaseStorageProvider,
)

__all__ = [
    # File storage
    "FileMetadata",
    "UploadResult",
    "FileStorageProvider",
    # Database storage
    "ArchiveStatus",
    "ArticleMetadata",
    "ArchiveArtifact",
    "DatabaseStorageProvider",
]
