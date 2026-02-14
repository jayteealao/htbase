"""
Database Storage Abstraction Layer

Provides a unified interface for storing and retrieving article metadata,
archive artifacts, and related data across different database backends.
Implementations: PostgresStorage, FirestoreStorage, etc.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum


class ArchiveStatus(Enum):
    """Status of an archive artifact."""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class ArticleMetadata:
    """Core article metadata."""
    item_id: str
    url: str
    title: Optional[str] = None
    byline: Optional[str] = None
    excerpt: Optional[str] = None
    text_content: Optional[str] = None
    word_count: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class ArchiveArtifact:
    """Archive artifact information."""
    item_id: str
    archiver: str
    status: ArchiveStatus
    gcs_path: Optional[str] = None
    gcs_bucket: Optional[str] = None
    local_path: Optional[str] = None
    file_size: Optional[int] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class PocketData:
    """Pocket-specific metadata."""
    item_id: str
    resolved_id: Optional[str] = None
    word_count: Optional[int] = None
    time_added: Optional[datetime] = None
    time_read: Optional[datetime] = None
    favorite: bool = False
    status: Optional[int] = None
    images: Optional[List[Dict[str, Any]]] = None
    authors: Optional[List[Dict[str, Any]]] = None


@dataclass
class ArticleSummary:
    """AI-generated article summary."""
    item_id: str
    summary: str
    created_at: Optional[datetime] = None


@dataclass
class ArticleEntity:
    """Extracted entity from article."""
    item_id: str
    entity_type: str  # PERSON, ORG, LOC, etc.
    entity_value: str
    confidence: Optional[float] = None


@dataclass
class ArticleTag:
    """Article tag/category."""
    item_id: str
    tag: str
    confidence: Optional[float] = None


@dataclass
class ArticleRecord:
    """Complete article record with all related data."""
    metadata: ArticleMetadata
    archives: List[ArchiveArtifact]
    pocket: Optional[PocketData] = None
    summary: Optional[ArticleSummary] = None
    entities: Optional[List[ArticleEntity]] = None
    tags: Optional[List[ArticleTag]] = None


class DatabaseStorageProvider(ABC):
    """
    Abstract base class for database storage providers.

    All implementations must provide:
    - Article metadata storage and retrieval
    - Archive artifact tracking
    - Pocket data integration
    - AI-generated content (summaries, entities, tags)
    - Batch operations
    """

    # ==================== Article Operations ====================

    @abstractmethod
    def create_article(self, metadata: ArticleMetadata) -> bool:
        """
        Create a new article record.

        Args:
            metadata: Article metadata

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def get_article(self, item_id: str) -> Optional[ArticleRecord]:
        """
        Get complete article record by item_id.

        Args:
            item_id: Article identifier

        Returns:
            ArticleRecord or None if not found
        """
        pass

    @abstractmethod
    def get_article_by_url(self, url: str) -> Optional[ArticleRecord]:
        """
        Get article record by URL.

        Args:
            url: Article URL

        Returns:
            ArticleRecord or None if not found
        """
        pass

    @abstractmethod
    def update_article_metadata(self, item_id: str, metadata: Dict[str, Any]) -> bool:
        """
        Update article metadata fields.

        Args:
            item_id: Article identifier
            metadata: Fields to update

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def delete_article(self, item_id: str) -> bool:
        """
        Delete article and all related data.

        Args:
            item_id: Article identifier

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def list_articles(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ArticleRecord]:
        """
        List articles with optional filtering.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            filters: Filter criteria (e.g., {"favorite": True, "status": 0})

        Returns:
            List of ArticleRecord
        """
        pass

    # ==================== Archive Artifact Operations ====================

    @abstractmethod
    def create_artifact(self, artifact: ArchiveArtifact) -> bool:
        """
        Create or update archive artifact.

        Args:
            artifact: Archive artifact data

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def get_artifacts(self, item_id: str) -> List[ArchiveArtifact]:
        """
        Get all artifacts for an article.

        Args:
            item_id: Article identifier

        Returns:
            List of ArchiveArtifact
        """
        pass

    @abstractmethod
    def get_artifact(self, item_id: str, archiver: str) -> Optional[ArchiveArtifact]:
        """
        Get specific artifact by archiver name.

        Args:
            item_id: Article identifier
            archiver: Archiver name

        Returns:
            ArchiveArtifact or None if not found
        """
        pass

    @abstractmethod
    def update_artifact_status(
        self,
        item_id: str,
        archiver: str,
        status: ArchiveStatus,
        **kwargs
    ) -> bool:
        """
        Update artifact status and related fields.

        Args:
            item_id: Article identifier
            archiver: Archiver name
            status: New status
            **kwargs: Additional fields to update (gcs_path, error_message, etc.)

        Returns:
            True if successful
        """
        pass

    # ==================== Pocket Data Operations ====================

    @abstractmethod
    def create_pocket_data(self, pocket: PocketData) -> bool:
        """
        Create or update Pocket metadata.

        Args:
            pocket: Pocket data

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def get_pocket_data(self, item_id: str) -> Optional[PocketData]:
        """
        Get Pocket metadata for an article.

        Args:
            item_id: Article identifier

        Returns:
            PocketData or None if not found
        """
        pass

    # ==================== AI Content Operations ====================

    @abstractmethod
    def create_summary(self, summary: ArticleSummary) -> bool:
        """
        Store article summary.

        Args:
            summary: Article summary

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def get_summary(self, item_id: str) -> Optional[ArticleSummary]:
        """
        Get article summary.

        Args:
            item_id: Article identifier

        Returns:
            ArticleSummary or None if not found
        """
        pass

    @abstractmethod
    def create_entities(self, entities: List[ArticleEntity]) -> bool:
        """
        Store extracted entities (batch).

        Args:
            entities: List of entities

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def get_entities(self, item_id: str) -> List[ArticleEntity]:
        """
        Get all entities for an article.

        Args:
            item_id: Article identifier

        Returns:
            List of ArticleEntity
        """
        pass

    @abstractmethod
    def create_tags(self, tags: List[ArticleTag]) -> bool:
        """
        Store article tags (batch).

        Args:
            tags: List of tags

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def get_tags(self, item_id: str) -> List[ArticleTag]:
        """
        Get all tags for an article.

        Args:
            item_id: Article identifier

        Returns:
            List of ArticleTag
        """
        pass

    # ==================== Batch Operations ====================

    @abstractmethod
    def batch_create_articles(self, articles: List[ArticleMetadata]) -> int:
        """
        Create multiple articles in batch.

        Args:
            articles: List of article metadata

        Returns:
            Number of articles created
        """
        pass

    @abstractmethod
    def batch_update_artifacts(self, artifacts: List[ArchiveArtifact]) -> int:
        """
        Update multiple artifacts in batch.

        Args:
            artifacts: List of artifacts

        Returns:
            Number of artifacts updated
        """
        pass

    # ==================== Query Operations ====================

    @abstractmethod
    def count_articles(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count articles matching filters.

        Args:
            filters: Filter criteria

        Returns:
            Count of matching articles
        """
        pass

    @abstractmethod
    def search_articles(
        self,
        query: str,
        limit: Optional[int] = None
    ) -> List[ArticleRecord]:
        """
        Full-text search articles.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching ArticleRecord
        """
        pass

    # ==================== Provider Info ====================

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the database provider (e.g., 'postgres', 'firestore')."""
        pass

    @property
    @abstractmethod
    def supports_transactions(self) -> bool:
        """Whether this provider supports ACID transactions."""
        pass

    @property
    @abstractmethod
    def supports_full_text_search(self) -> bool:
        """Whether this provider supports full-text search."""
        pass
