"""
Shared database module for HTBase microservices.

Provides SQLAlchemy models, Pydantic schemas, session management,
and repository classes for database operations.
"""

from shared.db.session import (
    get_engine,
    get_session,
    get_sessionmaker,
    init_db,
)
from shared.db.models import (
    Base,
    ArchivedUrl,
    ArchiveArtifact,
    UrlMetadata,
    ArticleSummary,
    ArticleEntity,
    ArticleTag,
    CommandExecution,
    CommandOutputLine,
)
from shared.db.schemas import (
    ArtifactStatus,
    ArtifactSchema,
    ArchivedUrlSchema,
    UrlMetadataSchema,
    ArticleSummarySchema,
    ArticleTagSchema,
    ArticleEntitySchema,
)

__all__ = [
    # Session management
    "get_engine",
    "get_session",
    "get_sessionmaker",
    "init_db",
    # SQLAlchemy models
    "Base",
    "ArchivedUrl",
    "ArchiveArtifact",
    "UrlMetadata",
    "ArticleSummary",
    "ArticleEntity",
    "ArticleTag",
    "CommandExecution",
    "CommandOutputLine",
    # Pydantic schemas
    "ArtifactStatus",
    "ArtifactSchema",
    "ArchivedUrlSchema",
    "UrlMetadataSchema",
    "ArticleSummarySchema",
    "ArticleTagSchema",
    "ArticleEntitySchema",
]
