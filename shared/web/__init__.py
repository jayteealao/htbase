"""
Web framework integration utilities for HTBase.

This package contains FastAPI-specific code like dependency injection,
response helpers, and middleware.
"""

from shared.web.dependencies import (
    get_article_repository,
    get_artifact_repository,
    ArticleRepoType,
    ArtifactRepoType,
)

__all__ = [
    "get_article_repository",
    "get_artifact_repository",
    "ArticleRepoType",
    "ArtifactRepoType",
]
