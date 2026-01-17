"""
Database layer for HTBase.

This package provides repository pattern implementations for Firestore access.
Repositories provide a clean abstraction for data access that can be easily mocked in tests.
"""

from shared.database.repositories import (
    ArticleRepository,
    ArtifactRepository,
)

__all__ = [
    "ArticleRepository",
    "ArtifactRepository",
]
