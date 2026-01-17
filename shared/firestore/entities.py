"""
Entity operations for Firestore.

Provides functions for managing named entities (people, organizations, locations) in articles.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from google.cloud import firestore

from shared.firestore_client import get_articles_collection
from shared.firestore.articles import get_article

logger = logging.getLogger(__name__)


def add_entities(item_id: str, entities: List[Dict[str, Any]]) -> None:
    """Add named entities to article.

    Args:
        item_id: Article identifier
        entities: List of entity dictionaries with keys:
            - entity: str (entity text)
            - entity_type: str (PERSON, ORG, LOC, etc.)
            - confidence: float (0-1)
    """
    collection = get_articles_collection()
    doc_ref = collection.document(item_id)

    # Convert snake_case to camelCase for Firestore
    firestore_entities = [
        {
            "type": e.get("entity_type"),
            "value": e.get("entity"),
            "confidence": e.get("confidence"),
        }
        for e in entities
    ]

    doc_ref.update({
        "entities": firestore.ArrayUnion(firestore_entities),
        "updated_at": firestore.SERVER_TIMESTAMP,
    })

    logger.info(f"Added {len(entities)} entities to: {item_id}")


def get_entities(item_id: str) -> List[Dict[str, Any]]:
    """Get entities for article.

    Args:
        item_id: Article identifier

    Returns:
        List of entity dictionaries
    """
    article = get_article(item_id)
    if not article:
        return []

    return article.get("entities", [])
