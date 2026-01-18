"""Domain models for HTBase microservices.

Provides rich domain classes that encapsulate business logic:
- Article: Core article with business methods (has_archive, set_summary, mark_completed)
- Archive: Archive artifact with status tracking (mark_completed, mark_failed)
- Summary: Article summary with metadata (mark_completed, mark_failed)
- Metadata: Extracted article metadata
- ArticleStatus: Enum for article processing states
"""

from .models import (
    Article,
    Archive,
    Summary,
    Metadata,
    ArticleStatus,
)

__all__ = [
    "Article",
    "Archive",
    "Summary",
    "Metadata",
    "ArticleStatus",
]
