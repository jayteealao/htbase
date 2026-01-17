"""
Tag operations for Firestore.

Provides functions for managing article tags.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from google.cloud import firestore

from shared.firestore_client import get_articles_collection
from shared.firestore.articles import get_article

logger = logging.getLogger(__name__)


def add_tags(item_id: str, tags: List[Dict[str, Any]]) -> None:
    """Add tags to article.

    Args:
        item_id: Article identifier
        tags: List of tag dictionaries with keys:
            - tag: str (tag value)
            - source: str (e.g., 'llm', 'user')
            - confidence: float (0-1)
    """
    collection = get_articles_collection()
    doc_ref = collection.document(item_id)

    firestore_tags = [
        {
            "tag": t.get("tag"),
            "source": t.get("source", "llm"),
            "confidence": t.get("confidence"),
        }
        for t in tags
    ]

    doc_ref.update({
        "tags": firestore.ArrayUnion(firestore_tags),
        "updated_at": firestore.SERVER_TIMESTAMP,
    })

    logger.info(f"Added {len(tags)} tags to: {item_id}")


def get_tags(item_id: str) -> List[Dict[str, Any]]:
    """Get tags for article.

    Args:
        item_id: Article identifier

    Returns:
        List of tag dictionaries
    """
    article = get_article(item_id)
    if not article:
        return []

    return article.get("tags", [])
