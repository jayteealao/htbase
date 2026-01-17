"""
Firestore data access layer for HTBase.

Provides functions for CRUD operations on Firestore articles collection.
Organized into focused modules by concern.

This module re-exports all functions from submodules for convenience.
All Firestore operations should import from `shared.firestore`.

Document Structure:
    articles/{item_id}:
        - item_id: str (document ID)
        - url: str (canonical URL)
        - title: Optional[str]
        - byline: Optional[str]
        - excerpt: Optional[str]
        - created_at: Timestamp
        - updated_at: Timestamp
        - archives: Map[str, Map] (keyed by archiver name)
        - metadata: Map (word count, etc.)
        - pocket: Map (Pocket integration data)
        - summary: Map (AI-generated summary)
        - entities: Array[Map] (named entities)
        - tags: Array[Map] (article tags)
"""

# Article operations
from shared.firestore.articles import (
    create_article,
    get_article,
    article_exists,
    update_article,
    delete_article,
    query_by_url,
    list_articles,
)

# Artifact operations
from shared.firestore.artifacts import (
    update_artifact,
    get_artifact,
    get_artifacts_by_status,
)

# Metadata operations
from shared.firestore.metadata import (
    update_metadata,
)

# Summary operations
from shared.firestore.summaries import (
    create_summary,
    get_summary,
)

# Entity operations
from shared.firestore.entities import (
    add_entities,
    get_entities,
)

# Tag operations
from shared.firestore.tags import (
    add_tags,
    get_tags,
)

# Pocket integration
from shared.firestore.pocket import (
    update_pocket_data,
)

__all__ = [
    # Articles
    "create_article",
    "get_article",
    "article_exists",
    "update_article",
    "delete_article",
    "query_by_url",
    "list_articles",
    # Artifacts
    "update_artifact",
    "get_artifact",
    "get_artifacts_by_status",
    # Metadata
    "update_metadata",
    # Summaries
    "create_summary",
    "get_summary",
    # Entities
    "add_entities",
    "get_entities",
    # Tags
    "add_tags",
    "get_tags",
    # Pocket
    "update_pocket_data",
]
