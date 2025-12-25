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
from shared.storage.gcs_file_storage import GCSFileStorage
from shared.storage.local_file_storage import LocalFileStorage
from shared.storage.database_storage import (
    ArchiveStatus,
    ArticleMetadata,
    ArchiveArtifact,
    PocketData,
    ArticleSummary,
    ArticleEntity,
    ArticleTag,
    ArticleRecord,
    DatabaseStorageProvider,
)
from shared.storage.firestore_storage import FirestoreStorage
from shared.storage.postgres_storage import PostgresStorage
from shared.storage.dual_database_storage import DualDatabaseStorage
from shared.storage.sync_filter import SyncFilter

__all__ = [
    # File storage - models
    "FileMetadata",
    "UploadResult",
    # File storage - providers
    "FileStorageProvider",
    "GCSFileStorage",
    "LocalFileStorage",
    # Database storage - models
    "ArchiveStatus",
    "ArticleMetadata",
    "ArchiveArtifact",
    "PocketData",
    "ArticleSummary",
    "ArticleEntity",
    "ArticleTag",
    "ArticleRecord",
    # Database storage - providers
    "DatabaseStorageProvider",
    "FirestoreStorage",
    "PostgresStorage",
    "DualDatabaseStorage",
    # Utilities
    "SyncFilter",
]
