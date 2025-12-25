"""
Fake storage implementations for testing.

InMemoryFileStorage and InMemoryDatabaseStorage provide fast, deterministic
testing without external dependencies (no disk I/O, no database connections).
"""

from __future__ import annotations

import gzip
import io
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, BinaryIO
from dataclasses import dataclass, field

from app.storage.file_storage import (
    FileStorageProvider,
    FileMetadata,
    UploadResult
)
from app.storage.database_storage import DatabaseStorageProvider


class InMemoryFileStorage(FileStorageProvider):
    """
    In-memory fake file storage for testing.

    Stores files in memory (dict) instead of disk/cloud, with real compression.

    Features:
    - No disk I/O (fast tests)
    - Real gzip compression/decompression
    - Metadata tracking
    - Configurable failure modes

    Usage:
        storage = InMemoryFileStorage()
        result = storage.upload_file(Path("test.html"), "archives/test.html")
        assert result.success
    """

    def __init__(self, fail_on_paths: Optional[list[str]] = None):
        """
        Initialize in-memory storage.

        Args:
            fail_on_paths: Optional list of paths that should fail (for error testing)
        """
        self._files: dict[str, bytes] = {}  # {path: content}
        self._metadata: dict[str, FileMetadata] = {}  # {path: metadata}
        self._fail_on_paths = fail_on_paths or []

    def upload_file(
        self,
        local_path: Path,
        destination_path: str,
        compress: bool = True,
        storage_class: Optional[str] = None
    ) -> UploadResult:
        """Upload file to memory storage."""
        # Check for configured failure
        if destination_path in self._fail_on_paths:
            return UploadResult(
                success=False,
                uri=f"memory://{destination_path}",
                original_size=0,
                stored_size=0,
                error=f"Configured to fail for path: {destination_path}"
            )

        # Read original file
        try:
            with open(local_path, 'rb') as f:
                original_content = f.read()
        except Exception as e:
            return UploadResult(
                success=False,
                uri=f"memory://{destination_path}",
                original_size=0,
                stored_size=0,
                error=f"Failed to read local file: {e}"
            )

        original_size = len(original_content)

        # Compress if requested
        if compress:
            compressed_buffer = io.BytesIO()
            with gzip.GzipFile(fileobj=compressed_buffer, mode='wb', compresslevel=9) as gz:
                gz.write(original_content)
            stored_content = compressed_buffer.getvalue()
        else:
            stored_content = original_content

        stored_size = len(stored_content)
        compression_ratio = None
        if compress and original_size > 0:
            compression_ratio = ((original_size - stored_size) / original_size) * 100

        # Store in memory
        self._files[destination_path] = stored_content

        # Store metadata
        self._metadata[destination_path] = FileMetadata(
            path=destination_path,
            size=stored_size,
            created_at=datetime.utcnow(),
            storage_class=storage_class,
            content_type=self._guess_content_type(local_path),
            compressed=compress,
            compression_ratio=compression_ratio
        )

        return UploadResult(
            success=True,
            uri=f"memory://{destination_path}",
            original_size=original_size,
            stored_size=stored_size,
            compression_ratio=compression_ratio
        )

    def download_file(
        self,
        storage_path: str,
        local_path: Path,
        decompress: bool = True
    ) -> bool:
        """Download file from memory to local path."""
        if storage_path not in self._files:
            return False

        content = self._files[storage_path]
        metadata = self._metadata.get(storage_path)

        # Decompress if needed
        if decompress and metadata and metadata.compressed:
            try:
                decompressed_buffer = io.BytesIO(content)
                with gzip.GzipFile(fileobj=decompressed_buffer, mode='rb') as gz:
                    content = gz.read()
            except Exception:
                return False

        # Write to local file
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with open(local_path, 'wb') as f:
                f.write(content)
            return True
        except Exception:
            return False

    def get_file_stream(self, storage_path: str) -> BinaryIO:
        """Get file stream from memory."""
        if storage_path not in self._files:
            raise FileNotFoundError(f"File not found: {storage_path}")

        content = self._files[storage_path]
        metadata = self._metadata.get(storage_path)

        # Decompress if compressed
        if metadata and metadata.compressed:
            decompressed_buffer = io.BytesIO(content)
            with gzip.GzipFile(fileobj=decompressed_buffer, mode='rb') as gz:
                decompressed = gz.read()
            return io.BytesIO(decompressed)

        return io.BytesIO(content)

    def delete_file(self, storage_path: str) -> bool:
        """Delete file from memory."""
        if storage_path not in self._files:
            return False

        del self._files[storage_path]
        if storage_path in self._metadata:
            del self._metadata[storage_path]
        return True

    def exists(self, storage_path: str) -> bool:
        """Check if file exists in memory."""
        return storage_path in self._files

    def get_metadata(self, storage_path: str) -> Optional[FileMetadata]:
        """Get file metadata."""
        return self._metadata.get(storage_path)

    def generate_access_url(
        self,
        storage_path: str,
        expiration: timedelta = timedelta(days=7)
    ) -> str:
        """Generate memory:// URL."""
        # For in-memory storage, just return a memory:// URI
        # In real tests, this would be checked for correctness
        return f"memory://{storage_path}?expires={(datetime.utcnow() + expiration).isoformat()}"

    def serve_file(
        self,
        storage_path: str,
        filename: str,
        media_type: str = "application/octet-stream"
    ):
        """Serve file from memory as StreamingResponse."""
        from fastapi.responses import StreamingResponse

        if storage_path not in self._files:
            raise FileNotFoundError(f"File not found: {storage_path}")

        stream = self.get_file_stream(storage_path)

        return StreamingResponse(
            io.BytesIO(stream.read()),
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    def download_to_temp(self, storage_path: str) -> Path:
        """Download file to temporary location."""
        import tempfile

        if storage_path not in self._files:
            raise FileNotFoundError(f"File not found: {storage_path}")

        # Create temp file
        fd, temp_path = tempfile.mkstemp(suffix=Path(storage_path).suffix)
        try:
            temp_file = Path(temp_path)
            if not self.download_file(storage_path, temp_file, decompress=False):
                raise FileNotFoundError(f"Failed to download: {storage_path}")
            return temp_file
        finally:
            import os
            os.close(fd)

    def list_files(
        self,
        prefix: str = "",
        limit: Optional[int] = None
    ) -> list[FileMetadata]:
        """List files with optional prefix filter."""
        matching = [
            self._metadata[path]
            for path in self._files.keys()
            if path.startswith(prefix)
        ]

        # Sort by created_at descending
        matching.sort(key=lambda m: m.created_at, reverse=True)

        if limit:
            matching = matching[:limit]

        return matching

    @property
    def provider_name(self) -> str:
        """Provider name."""
        return "memory"

    @property
    def supports_compression(self) -> bool:
        """Supports compression."""
        return True

    @property
    def supports_signed_urls(self) -> bool:
        """Supports signed URLs (fake implementation)."""
        return True

    def _guess_content_type(self, path: Path) -> str:
        """Guess content type from file extension."""
        suffix = path.suffix.lower()
        content_types = {
            '.html': 'text/html',
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.json': 'application/json',
            '.txt': 'text/plain',
        }
        return content_types.get(suffix, 'application/octet-stream')

    # Helper methods for testing

    def get_file_count(self) -> int:
        """Get number of stored files."""
        return len(self._files)

    def clear(self):
        """Clear all stored files."""
        self._files.clear()
        self._metadata.clear()

    def get_raw_content(self, storage_path: str) -> Optional[bytes]:
        """Get raw (possibly compressed) content for testing."""
        return self._files.get(storage_path)


class InMemoryDatabaseStorage(DatabaseStorageProvider):
    """
    In-memory fake database storage for testing.

    Stores all data in dicts instead of PostgreSQL/Firestore.

    Features:
    - No database connections (fast tests)
    - Realistic query behavior (filtering, pagination)
    - Relationship management
    - Atomic operations

    Usage:
        storage = InMemoryDatabaseStorage()
        storage.create_article(item_id="test1", url="https://example.com")
        article = storage.get_article("test1")
    """

    @dataclass
    class _Article:
        """Internal article representation."""
        item_id: str
        url: str
        created_at: datetime = field(default_factory=datetime.utcnow)
        pocket_data: dict = field(default_factory=dict)
        metadata: dict = field(default_factory=dict)

    @dataclass
    class _Artifact:
        """Internal artifact representation."""
        item_id: str
        archiver: str
        status: str = "pending"
        gcs_path: Optional[str] = None
        gcs_bucket: Optional[str] = None
        compressed_size: Optional[int] = None
        compression_ratio: Optional[float] = None
        exit_code: Optional[int] = None
        created_at: datetime = field(default_factory=datetime.utcnow)
        updated_at: datetime = field(default_factory=datetime.utcnow)
        storage_uploads: list[dict] = field(default_factory=list)

    def __init__(self):
        """Initialize in-memory database."""
        self._articles: dict[str, InMemoryDatabaseStorage._Article] = {}
        self._artifacts: dict[tuple[str, str], InMemoryDatabaseStorage._Artifact] = {}
        self._summaries: dict[str, dict] = {}
        self._entities: dict[str, list[dict]] = {}
        self._tags: dict[str, list[dict]] = {}

    def create_article(
        self,
        item_id: str,
        url: str,
        pocket_data: Optional[dict] = None,
        metadata: Optional[dict] = None
    ) -> bool:
        """Create article in memory."""
        if item_id in self._articles:
            # Article exists, optionally update
            return False

        self._articles[item_id] = self._Article(
            item_id=item_id,
            url=url,
            pocket_data=pocket_data or {},
            metadata=metadata or {}
        )
        return True

    def get_article(self, item_id: str) -> Optional[dict]:
        """Get article from memory."""
        article = self._articles.get(item_id)
        if not article:
            return None

        return {
            'item_id': article.item_id,
            'url': article.url,
            'created_at': article.created_at,
            'pocket_data': article.pocket_data,
            'metadata': article.metadata,
        }

    def update_artifact_status(
        self,
        item_id: str,
        archiver: str,
        status: str,
        gcs_path: Optional[str] = None,
        gcs_bucket: Optional[str] = None,
        compressed_size: Optional[int] = None,
        compression_ratio: Optional[float] = None,
        exit_code: Optional[int] = None,
        storage_uploads: Optional[list[dict]] = None
    ) -> bool:
        """Update artifact status in memory."""
        key = (item_id, archiver)

        if key not in self._artifacts:
            # Create new artifact
            self._artifacts[key] = self._Artifact(
                item_id=item_id,
                archiver=archiver,
                status=status,
                gcs_path=gcs_path,
                gcs_bucket=gcs_bucket,
                compressed_size=compressed_size,
                compression_ratio=compression_ratio,
                exit_code=exit_code,
                storage_uploads=storage_uploads or []
            )
        else:
            # Update existing
            artifact = self._artifacts[key]
            artifact.status = status
            artifact.updated_at = datetime.utcnow()
            if gcs_path is not None:
                artifact.gcs_path = gcs_path
            if gcs_bucket is not None:
                artifact.gcs_bucket = gcs_bucket
            if compressed_size is not None:
                artifact.compressed_size = compressed_size
            if compression_ratio is not None:
                artifact.compression_ratio = compression_ratio
            if exit_code is not None:
                artifact.exit_code = exit_code
            if storage_uploads is not None:
                artifact.storage_uploads = storage_uploads

        return True

    def get_artifact(self, item_id: str, archiver: str) -> Optional[dict]:
        """Get artifact from memory."""
        key = (item_id, archiver)
        artifact = self._artifacts.get(key)
        if not artifact:
            return None

        return {
            'item_id': artifact.item_id,
            'archiver': artifact.archiver,
            'status': artifact.status,
            'gcs_path': artifact.gcs_path,
            'gcs_bucket': artifact.gcs_bucket,
            'compressed_size': artifact.compressed_size,
            'compression_ratio': artifact.compression_ratio,
            'exit_code': artifact.exit_code,
            'created_at': artifact.created_at,
            'updated_at': artifact.updated_at,
            'storage_uploads': artifact.storage_uploads,
        }

    def list_artifacts(
        self,
        item_id: Optional[str] = None,
        archiver: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None
    ) -> list[dict]:
        """List artifacts with filtering."""
        results = []

        for artifact in self._artifacts.values():
            # Apply filters
            if item_id and artifact.item_id != item_id:
                continue
            if archiver and artifact.archiver != archiver:
                continue
            if status and artifact.status != status:
                continue

            results.append({
                'item_id': artifact.item_id,
                'archiver': artifact.archiver,
                'status': artifact.status,
                'gcs_path': artifact.gcs_path,
                'gcs_bucket': artifact.gcs_bucket,
                'compressed_size': artifact.compressed_size,
                'compression_ratio': artifact.compression_ratio,
                'exit_code': artifact.exit_code,
                'created_at': artifact.created_at,
                'updated_at': artifact.updated_at,
                'storage_uploads': artifact.storage_uploads,
            })

        # Sort by created_at descending
        results.sort(key=lambda a: a['created_at'], reverse=True)

        if limit:
            results = results[:limit]

        return results

    def list_articles(
        self,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> list[dict]:
        """List articles with pagination."""
        articles = list(self._articles.values())
        articles.sort(key=lambda a: a.created_at, reverse=True)

        if offset:
            articles = articles[offset:]

        if limit:
            articles = articles[:limit]

        return [
            {
                'item_id': a.item_id,
                'url': a.url,
                'created_at': a.created_at,
                'pocket_data': a.pocket_data,
                'metadata': a.metadata,
            }
            for a in articles
        ]

    def get_article_by_url(self, url: str) -> Optional[dict]:
        """Get article by URL."""
        for article in self._articles.values():
            if article.url == url:
                return {
                    'item_id': article.item_id,
                    'url': article.url,
                    'created_at': article.created_at,
                    'pocket_data': article.pocket_data,
                    'metadata': article.metadata,
                }
        return None

    def update_article_metadata(self, item_id: str, metadata: dict) -> bool:
        """Update article metadata."""
        if item_id not in self._articles:
            return False
        self._articles[item_id].metadata.update(metadata)
        return True

    def delete_article(self, item_id: str) -> bool:
        """Delete article and related data."""
        if item_id not in self._articles:
            return False

        # Delete article
        del self._articles[item_id]

        # Delete related artifacts
        keys_to_delete = [k for k in self._artifacts.keys() if k[0] == item_id]
        for key in keys_to_delete:
            del self._artifacts[key]

        # Delete related data
        self._summaries.pop(item_id, None)
        self._entities.pop(item_id, None)
        self._tags.pop(item_id, None)

        return True

    def create_artifact(self, artifact_data: dict) -> bool:
        """Create artifact from dict."""
        item_id = artifact_data.get('item_id')
        archiver = artifact_data.get('archiver')

        if not item_id or not archiver:
            return False

        key = (item_id, archiver)
        if key in self._artifacts:
            return False

        self._artifacts[key] = self._Artifact(
            item_id=item_id,
            archiver=archiver,
            status=artifact_data.get('status', 'pending'),
            gcs_path=artifact_data.get('gcs_path'),
            gcs_bucket=artifact_data.get('gcs_bucket'),
            compressed_size=artifact_data.get('compressed_size'),
            compression_ratio=artifact_data.get('compression_ratio'),
            exit_code=artifact_data.get('exit_code'),
            storage_uploads=artifact_data.get('storage_uploads', [])
        )
        return True

    def get_artifacts(self, item_id: str) -> list[dict]:
        """Get all artifacts for an item."""
        return self.list_artifacts(item_id=item_id)

    def create_pocket_data(self, pocket_data: dict) -> bool:
        """Create or update pocket data for an article."""
        item_id = pocket_data.get('item_id')
        if not item_id or item_id not in self._articles:
            return False
        self._articles[item_id].pocket_data = pocket_data
        return True

    def get_pocket_data(self, item_id: str) -> Optional[dict]:
        """Get pocket data for an article."""
        if item_id not in self._articles:
            return None
        return self._articles[item_id].pocket_data

    def create_summary(self, summary_data: dict) -> bool:
        """Create or update summary."""
        item_id = summary_data.get('item_id')
        if not item_id:
            return False
        self._summaries[item_id] = summary_data
        return True

    def get_summary(self, item_id: str) -> Optional[dict]:
        """Get summary for an article."""
        return self._summaries.get(item_id)

    def create_entities(self, entities: list[dict]) -> bool:
        """Create entities for an article."""
        if not entities:
            return False
        item_id = entities[0].get('item_id')
        if not item_id:
            return False
        self._entities[item_id] = entities
        return True

    def get_entities(self, item_id: str) -> list[dict]:
        """Get entities for an article."""
        return self._entities.get(item_id, [])

    def create_tags(self, tags: list[dict]) -> bool:
        """Create tags for an article."""
        if not tags:
            return False
        item_id = tags[0].get('item_id')
        if not item_id:
            return False
        self._tags[item_id] = tags
        return True

    def get_tags(self, item_id: str) -> list[dict]:
        """Get tags for an article."""
        return self._tags.get(item_id, [])

    def batch_create_articles(self, articles: list[dict]) -> int:
        """Batch create articles."""
        count = 0
        for article_data in articles:
            if self.create_article(
                item_id=article_data.get('item_id'),
                url=article_data.get('url'),
                pocket_data=article_data.get('pocket_data'),
                metadata=article_data.get('metadata')
            ):
                count += 1
        return count

    def batch_update_artifacts(self, artifacts: list[dict]) -> int:
        """Batch update artifacts."""
        count = 0
        for artifact_data in artifacts:
            if self.update_artifact_status(
                item_id=artifact_data.get('item_id'),
                archiver=artifact_data.get('archiver'),
                status=artifact_data.get('status'),
                gcs_path=artifact_data.get('gcs_path'),
                gcs_bucket=artifact_data.get('gcs_bucket'),
                compressed_size=artifact_data.get('compressed_size'),
                compression_ratio=artifact_data.get('compression_ratio'),
                exit_code=artifact_data.get('exit_code'),
                storage_uploads=artifact_data.get('storage_uploads')
            ):
                count += 1
        return count

    def count_articles(self, filters: Optional[dict] = None) -> int:
        """Count articles with optional filtering."""
        if not filters:
            return len(self._articles)

        # Simple filtering implementation
        count = 0
        for article in self._articles.values():
            matches = True
            for key, value in filters.items():
                if getattr(article, key, None) != value:
                    matches = False
                    break
            if matches:
                count += 1
        return count

    def search_articles(
        self,
        query: str,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> list[dict]:
        """Search articles by text query."""
        # Simple text search in url and metadata
        results = []
        query_lower = query.lower()

        for article in self._articles.values():
            if (query_lower in article.url.lower() or
                query_lower in str(article.metadata).lower()):
                results.append({
                    'item_id': article.item_id,
                    'url': article.url,
                    'created_at': article.created_at,
                    'pocket_data': article.pocket_data,
                    'metadata': article.metadata,
                })

        # Sort by created_at descending
        results.sort(key=lambda a: a['created_at'], reverse=True)

        if offset:
            results = results[offset:]
        if limit:
            results = results[:limit]

        return results

    @property
    def supports_full_text_search(self) -> bool:
        """Whether provider supports full-text search."""
        return True  # Simple implementation

    @property
    def supports_transactions(self) -> bool:
        """Whether provider supports transactions."""
        return False  # In-memory doesn't need transactions

    @property
    def provider_name(self) -> str:
        """Provider name."""
        return "memory"

    # Helper methods for testing

    def clear(self):
        """Clear all data."""
        self._articles.clear()
        self._artifacts.clear()
        self._summaries.clear()
        self._entities.clear()
        self._tags.clear()

    def get_article_count(self) -> int:
        """Get number of articles."""
        return len(self._articles)

    def get_artifact_count(self) -> int:
        """Get number of artifacts."""
        return len(self._artifacts)
