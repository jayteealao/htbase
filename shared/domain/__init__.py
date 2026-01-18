"""Domain models for HTBase microservices.

Provides rich domain classes that encapsulate business logic:
- Article: Core article with business methods (has_archive, set_summary, mark_completed)
- Archive: Archive artifact with status tracking (mark_completed, mark_failed)
- Summary: Article summary with metadata (mark_completed, mark_failed)
- Metadata: Extracted article metadata
- ArticleStatus: Enum for article processing states

Also provides TypedDict definitions for Firestore documents:
- ArticleDict, ArchiveDict, SummaryDict, MetadataDict, ArtifactDict
"""

from .models import (
    Article,
    Archive,
    Summary,
    Metadata,
    ArticleStatus,
)

from .types import (
    ArticleDict,
    ArchiveDict,
    SummaryDict,
    MetadataDict,
    ArtifactDict,
)

__all__ = [
    # Domain models
    "Article",
    "Archive",
    "Summary",
    "Metadata",
    "ArticleStatus",
    # TypedDict definitions
    "ArticleDict",
    "ArchiveDict",
    "SummaryDict",
    "MetadataDict",
    "ArtifactDict",
]
