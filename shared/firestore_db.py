"""
Firestore data access layer for HTBase.

DEPRECATED: This module is maintained for backward compatibility only.
Please use `from shared.firestore import ...` instead.

This file now re-exports all functions from the new modular structure:
- shared.firestore.articles - Article CRUD operations
- shared.firestore.artifacts - Artifact management
- shared.firestore.metadata - Metadata operations
- shared.firestore.summaries - Summary operations
- shared.firestore.entities - Entity operations
- shared.firestore.tags - Tag operations
- shared.firestore.pocket - Pocket integration

All existing imports will continue to work unchanged:
    from shared.firestore_db import create_article  # ✅ Still works
    from shared.firestore import create_article      # ✅ Preferred
"""

# Re-export all functions from the new modular structure
from shared.firestore import (
    # Articles
    create_article,
    get_article,
    article_exists,
    update_article,
    delete_article,
    query_by_url,
    list_articles,
    # Artifacts
    update_artifact,
    get_artifact,
    get_artifacts_by_status,
    # Metadata
    update_metadata,
    # Summaries
    create_summary,
    get_summary,
    # Entities
    add_entities,
    get_entities,
    # Tags
    add_tags,
    get_tags,
    # Pocket
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
