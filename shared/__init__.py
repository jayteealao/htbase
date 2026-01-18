"""HTBase Shared Package - Clean architecture with domain models.

Provides reusable components for all HTBase microservices:
- domain: Rich domain models (Article, Archive, Summary, Metadata)
- infrastructure: Infrastructure services (Firestore, Celery, Storage)
- database: Repository pattern for data access
- web: Web utilities (auth, rate limiting, dependencies)
- config: Service-specific configuration
- models: API request/response models
- summarization: Summary generation components
"""

# Infrastructure
from shared.infrastructure.celery import celery_app
from shared.infrastructure.firestore import get_firestore_client

# Domain models
from shared.domain import Article, Archive, Summary, Metadata, ArticleStatus

# Database repositories
from shared.database.repositories import ArticleRepository, ArtifactRepository

# Legacy status models
from shared.status import TaskStatus, TaskResult

__all__ = [
    # Infrastructure
    "celery_app",
    "get_firestore_client",
    # Domain
    "Article",
    "Archive",
    "Summary",
    "Metadata",
    "ArticleStatus",
    # Database
    "ArticleRepository",
    "ArtifactRepository",
    # Legacy
    "TaskStatus",
    "TaskResult",
]
