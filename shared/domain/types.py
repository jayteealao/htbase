"""Type definitions for Firestore document structures.

Provides TypedDict definitions for all Firestore documents to enable:
- Type checking with mypy
- IDE autocomplete for dict access
- Self-documenting data structures
- Safer dict manipulation

Use these types for dict-based code during migration to domain models.
Eventually, prefer domain models (Article, Archive, Summary) over dicts.
"""

from typing import TypedDict, Optional, Dict, Any, List
from datetime import datetime


class ArchiveDict(TypedDict, total=False):
    """Firestore structure for archive artifacts.

    Fields:
        archive_type: Type of archive (screenshot, pdf, singlefile, etc.)
        status: Archive status (pending, processing, completed, failed)
        gcs_path: GCS path to archived file (if completed)
        created_at: Timestamp when archive was created/completed
        error: Error message (if failed)
        metadata: Additional archiver-specific metadata
    """
    archive_type: str
    status: str
    gcs_path: Optional[str]
    created_at: Optional[datetime]
    error: Optional[str]
    metadata: Optional[Dict[str, Any]]


class SummaryDict(TypedDict, total=False):
    """Firestore structure for article summaries.

    Fields:
        text: Summary text content
        status: Summary status (pending, processing, completed, failed)
        created_at: Timestamp when summary was created
        model: LLM model used for summarization
        tokens_used: Number of tokens consumed
        error: Error message (if failed)
        entities: Extracted named entities
        tags: Generated tags/categories
    """
    text: str
    status: str
    created_at: Optional[datetime]
    model: Optional[str]
    tokens_used: Optional[int]
    error: Optional[str]
    entities: List[Dict[str, Any]]
    tags: List[str]


class MetadataDict(TypedDict, total=False):
    """Firestore structure for article metadata.

    Fields:
        author: Article author/byline
        published_date: Original publication date
        word_count: Article word count
        language: Detected language code
        error: Error message if metadata extraction failed
    """
    author: Optional[str]
    published_date: Optional[datetime]
    word_count: Optional[int]
    language: Optional[str]
    error: Optional[str]


class ArticleDict(TypedDict, total=False):
    """Firestore structure for article documents.

    Fields:
        url: Canonical article URL
        title: Article title
        created_at: When article was first created
        updated_at: Last update timestamp
        status: Article processing status (pending, processing, completed, failed)
        archives: Map of archive_type -> ArchiveDict
        summary: Article summary (SummaryDict)
        metadata: Extracted metadata (MetadataDict)
    """
    url: str
    title: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    status: str
    archives: Dict[str, ArchiveDict]
    summary: SummaryDict
    metadata: MetadataDict


class ArtifactDict(TypedDict, total=False):
    """Firestore structure for artifact tracking documents.

    Note: This is deprecated in favor of inline archives in ArticleDict.
    Kept for backward compatibility.

    Fields:
        article_id: Reference to article document
        artifact_type: Type of artifact (matches archive_type)
        status: Artifact status
        gcs_path: GCS path to artifact file
        created_at: Creation timestamp
        error: Error message if failed
    """
    article_id: str
    artifact_type: str
    status: str
    gcs_path: Optional[str]
    created_at: Optional[datetime]
    error: Optional[str]
