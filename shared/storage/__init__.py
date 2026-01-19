"""
Shared storage module for HTBase microservices.

HTBase uses:
- GCS for artifact/file storage
- Firestore for database storage
"""

from shared.storage.file_storage import (
    FileMetadata,
    UploadResult,
    FileStorageProvider,
)
from shared.storage.gcs_file_storage import GCSFileStorage
from shared.storage.database_storage import (
    ArchiveStatus,
    ArticleMetadata,
    ArchiveArtifact,
    ArticleSummary,
    ArticleEntity,
    ArticleTag,
    ArticleRecord,
    DatabaseStorageProvider,
)
from shared.storage.firestore_storage import FirestoreStorage

__all__ = [
    # File storage - models
    "FileMetadata",
    "UploadResult",
    # File storage - providers
    "FileStorageProvider",
    "GCSFileStorage",
    # Database storage - models
    "ArchiveStatus",
    "ArticleMetadata",
    "ArchiveArtifact",
    "ArticleSummary",
    "ArticleEntity",
    "ArticleTag",
    "ArticleRecord",
    # Database storage - providers
    "DatabaseStorageProvider",
    "FirestoreStorage",
]
