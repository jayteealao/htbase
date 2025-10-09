"""DB package assembling models, session helpers, and repository functions.

New code should use repository classes from .repositories:
    from db.repositories import ArchiveArtifactRepository, ArchivedUrlRepository

Legacy module-level functions in .repository are deprecated.
"""

# Export new repository classes
from .repositories import (
    ArchivedUrlRepository,
    ArchiveArtifactRepository,
    UrlMetadataRepository,
    ArticleSummaryRepository,
    ArticleTagRepository,
    ArticleEntityRepository,
    CommandExecutionRepository,
)

# Export schemas
from .schemas import (
    ArtifactSchema,
    ArtifactStatus,
    ArchivedUrlSchema,
    UrlMetadataSchema,
    ArticleSummarySchema,
    ArticleTagSchema,
    ArticleEntitySchema,
    SizeStatsSchema,
)

# Export base for extensibility
from .base_repository import BaseRepository

__all__ = [
    # Repositories
    "ArchivedUrlRepository",
    "ArchiveArtifactRepository",
    "UrlMetadataRepository",
    "ArticleSummaryRepository",
    "ArticleTagRepository",
    "ArticleEntityRepository",
    "CommandExecutionRepository",
    # Schemas
    "ArtifactSchema",
    "ArtifactStatus",
    "ArchivedUrlSchema",
    "UrlMetadataSchema",
    "ArticleSummarySchema",
    "ArticleTagSchema",
    "ArticleEntitySchema",
    "SizeStatsSchema",
    # Base
    "BaseRepository",
]
