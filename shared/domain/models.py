"""Rich domain models for HTBase microservices.

Provides type-safe domain classes with encapsulated business logic:
- Article: Core article with business methods
- Archive: Archive artifact with status tracking
- Summary: Article summary with metadata
- Metadata: Extracted article metadata
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum


class ArticleStatus(str, Enum):
    """Article processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Metadata:
    """Article metadata extracted during processing."""

    author: Optional[str] = None
    published_date: Optional[datetime] = None
    word_count: Optional[int] = None
    language: Optional[str] = None
    error: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Metadata":
        """Create Metadata from dictionary."""
        return cls(
            author=data.get("author"),
            published_date=data.get("published_date"),
            word_count=data.get("word_count"),
            language=data.get("language"),
            error=data.get("error"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert Metadata to dictionary."""
        result = {}
        if self.author:
            result["author"] = self.author
        if self.published_date:
            result["published_date"] = self.published_date
        if self.word_count:
            result["word_count"] = self.word_count
        if self.language:
            result["language"] = self.language
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class Archive:
    """Archive artifact for an article."""

    archive_type: str
    status: str
    gcs_path: Optional[str] = None
    created_at: Optional[datetime] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def mark_completed(self, gcs_path: str) -> None:
        """Mark archive as completed."""
        self.status = "completed"
        self.gcs_path = gcs_path
        self.created_at = datetime.utcnow()
        self.error = None

    def mark_failed(self, error: str) -> None:
        """Mark archive as failed."""
        self.status = "failed"
        self.error = error
        self.created_at = datetime.utcnow()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Archive":
        """Create Archive from dictionary."""
        return cls(
            archive_type=data.get("archive_type", ""),
            status=data.get("status", "pending"),
            gcs_path=data.get("gcs_path"),
            created_at=data.get("created_at"),
            error=data.get("error"),
            metadata=data.get("metadata"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert Archive to dictionary."""
        result = {
            "archive_type": self.archive_type,
            "status": self.status,
        }
        if self.gcs_path:
            result["gcs_path"] = self.gcs_path
        if self.created_at:
            result["created_at"] = self.created_at
        if self.error:
            result["error"] = self.error
        if self.metadata:
            result["metadata"] = self.metadata
        return result


@dataclass
class Summary:
    """Article summary with extracted content."""

    text: str
    status: str
    created_at: Optional[datetime] = None
    model: Optional[str] = None
    tokens_used: Optional[int] = None
    error: Optional[str] = None
    entities: List[Dict[str, Any]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def mark_completed(self, model: str, tokens_used: int) -> None:
        """Mark summary as completed."""
        self.status = "completed"
        self.created_at = datetime.utcnow()
        self.model = model
        self.tokens_used = tokens_used
        self.error = None

    def mark_failed(self, error: str) -> None:
        """Mark summary as failed."""
        self.status = "failed"
        self.error = error
        self.created_at = datetime.utcnow()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Summary":
        """Create Summary from dictionary."""
        return cls(
            text=data.get("text", ""),
            status=data.get("status", "pending"),
            created_at=data.get("created_at"),
            model=data.get("model"),
            tokens_used=data.get("tokens_used"),
            error=data.get("error"),
            entities=data.get("entities", []),
            tags=data.get("tags", []),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert Summary to dictionary."""
        result = {
            "text": self.text,
            "status": self.status,
        }
        if self.created_at:
            result["created_at"] = self.created_at
        if self.model:
            result["model"] = self.model
        if self.tokens_used:
            result["tokens_used"] = self.tokens_used
        if self.error:
            result["error"] = self.error
        if self.entities:
            result["entities"] = self.entities
        if self.tags:
            result["tags"] = self.tags
        return result


@dataclass
class Article:
    """Rich domain model for articles with business logic."""

    # Core fields
    id: str
    url: str
    title: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    status: ArticleStatus = ArticleStatus.PENDING

    # Archives
    archives: Dict[str, Archive] = field(default_factory=dict)

    # Summary
    summary: Optional[Summary] = None

    # Metadata
    metadata: Optional[Metadata] = None

    def add_archive(self, archive_type: str, archive: Archive) -> None:
        """Add an archive to this article."""
        self.archives[archive_type] = archive
        self.updated_at = datetime.utcnow()

    def has_archive(self, archive_type: str) -> bool:
        """Check if article has specific archive type."""
        return (
            archive_type in self.archives
            and self.archives[archive_type].status == "completed"
        )

    def set_summary(self, summary: Summary) -> None:
        """Set the article summary."""
        self.summary = summary
        self.updated_at = datetime.utcnow()

    def has_summary(self) -> bool:
        """Check if article has a completed summary."""
        return self.summary is not None and self.summary.status == "completed"

    def mark_completed(self) -> None:
        """Mark article processing as completed."""
        self.status = ArticleStatus.COMPLETED
        self.updated_at = datetime.utcnow()

    def mark_failed(self, error: Optional[str] = None) -> None:
        """Mark article processing as failed."""
        self.status = ArticleStatus.FAILED
        self.updated_at = datetime.utcnow()
        if error and self.metadata:
            self.metadata.error = error

    @classmethod
    def from_firestore(cls, doc_id: str, data: Dict[str, Any]) -> "Article":
        """Create Article from Firestore document."""
        return cls(
            id=doc_id,
            url=data["url"],
            title=data.get("title"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            status=ArticleStatus(data.get("status", "pending")),
            archives={
                k: Archive.from_dict(v) for k, v in data.get("archives", {}).items()
            },
            summary=Summary.from_dict(data["summary"])
            if "summary" in data
            else None,
            metadata=Metadata.from_dict(data["metadata"])
            if "metadata" in data
            else None,
        )

    def to_firestore(self) -> Dict[str, Any]:
        """Convert Article to Firestore document."""
        doc = {
            "url": self.url,
            "status": self.status.value,
            "updated_at": self.updated_at or datetime.utcnow(),
        }
        if self.title:
            doc["title"] = self.title
        if self.created_at:
            doc["created_at"] = self.created_at
        if self.archives:
            doc["archives"] = {k: v.to_dict() for k, v in self.archives.items()}
        if self.summary:
            doc["summary"] = self.summary.to_dict()
        if self.metadata:
            doc["metadata"] = self.metadata.to_dict()
        return doc
