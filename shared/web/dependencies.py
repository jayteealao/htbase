"""
FastAPI dependency injection providers.

These functions provide request-scoped dependencies that can be injected
into route handlers using FastAPI's Depends() mechanism.
"""

from typing import Annotated

from fastapi import Depends

from shared.database.repositories import ArticleRepository, ArtifactRepository
from shared.firestore_client import get_firestore_client


def get_article_repository() -> ArticleRepository:
    """Get article repository for request.

    This is a FastAPI dependency that provides an ArticleRepository
    instance for each request. In tests, this can be overridden with
    a mock repository.

    Returns:
        ArticleRepository instance
    """
    client = get_firestore_client()
    return ArticleRepository(client)


def get_artifact_repository() -> ArtifactRepository:
    """Get artifact repository for request.

    This is a FastAPI dependency that provides an ArtifactRepository
    instance for each request. In tests, this can be overridden with
    a mock repository.

    Returns:
        ArtifactRepository instance
    """
    client = get_firestore_client()
    return ArtifactRepository(client)


# Type aliases for clean dependency injection in route signatures
ArticleRepoType = Annotated[ArticleRepository, Depends(get_article_repository)]
ArtifactRepoType = Annotated[ArtifactRepository, Depends(get_artifact_repository)]
