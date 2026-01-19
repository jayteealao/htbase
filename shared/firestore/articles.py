"""
Article CRUD operations for Firestore.

Provides functions for creating, reading, updating, deleting, and querying articles.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from shared.infrastructure.firestore import get_articles_collection

logger = logging.getLogger(__name__)


def create_article(
    item_id: str,
    url: str,
    title: Optional[str] = None,
    byline: Optional[str] = None,
    excerpt: Optional[str] = None,
    pocket_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create article document in Firestore.

    Args:
        item_id: Unique article identifier (used as document ID)
        url: Canonical URL
        title: Article title
        byline: Author/byline
        excerpt: Article excerpt/description
        pocket_data: Optional Pocket integration data

    Returns:
        Created article data dictionary
    """
    collection = get_articles_collection()
    doc_ref = collection.document(item_id)

    article_data = {
        "item_id": item_id,
        "url": url,
        "title": title,
        "byline": byline,
        "excerpt": excerpt,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
        "archives": {},  # Empty map, populated by archivers
        "metadata": {},  # Word count, etc.
        "pocket": pocket_data or {},  # Pocket integration data
        "summary": {},  # AI summary
        "entities": [],  # Named entities
        "tags": [],  # Article tags
    }

    doc_ref.set(article_data)
    logger.info(f"Created article: {item_id}")

    return article_data


def get_article(item_id: str) -> Optional[Dict[str, Any]]:
    """Get article by item_id.

    Args:
        item_id: Article identifier (document ID)

    Returns:
        Article data dictionary or None if not found
    """
    collection = get_articles_collection()
    doc = collection.document(item_id).get()

    if not doc.exists:
        return None

    return doc.to_dict()


def article_exists(item_id: str) -> bool:
    """Check if article exists.

    Args:
        item_id: Article identifier

    Returns:
        True if article exists, False otherwise
    """
    collection = get_articles_collection()
    doc = collection.document(item_id).get()
    return doc.exists


def update_article(
    item_id: str,
    title: Optional[str] = None,
    byline: Optional[str] = None,
    excerpt: Optional[str] = None,
    **kwargs,
) -> None:
    """Update article metadata.

    Args:
        item_id: Article identifier
        title: New title (if provided)
        byline: New byline (if provided)
        excerpt: New excerpt (if provided)
        **kwargs: Additional fields to update
    """
    collection = get_articles_collection()
    doc_ref = collection.document(item_id)

    updates = {"updated_at": firestore.SERVER_TIMESTAMP}

    if title is not None:
        updates["title"] = title
    if byline is not None:
        updates["byline"] = byline
    if excerpt is not None:
        updates["excerpt"] = excerpt

    updates.update(kwargs)

    doc_ref.update(updates)
    logger.info(f"Updated article: {item_id}")


def delete_article(item_id: str) -> bool:
    """Delete article document.

    Args:
        item_id: Article identifier

    Returns:
        True if deleted, False if not found
    """
    collection = get_articles_collection()
    doc_ref = collection.document(item_id)

    if not doc_ref.get().exists:
        return False

    doc_ref.delete()
    logger.info(f"Deleted article: {item_id}")
    return True


def query_by_url(url: str) -> Optional[Dict[str, Any]]:
    """Find article by URL.

    Note: This requires a composite index on 'url' field.

    Args:
        url: URL to search for

    Returns:
        Article data dictionary or None if not found
    """
    collection = get_articles_collection()
    query = collection.where(filter=FieldFilter("url", "==", url)).limit(1)

    for doc in query.stream():
        return doc.to_dict()

    return None


def list_articles(
    limit: int = 100,
    offset: int = 0,
    order_by: str = "created_at",
    descending: bool = True,
) -> List[Dict[str, Any]]:
    """List articles with pagination.

    Args:
        limit: Maximum number of articles to return
        offset: Number of articles to skip (less efficient in Firestore)
        order_by: Field to order by
        descending: Sort descending if True, ascending if False

    Returns:
        List of article data dictionaries
    """
    collection = get_articles_collection()

    direction = (
        firestore.Query.DESCENDING if descending else firestore.Query.ASCENDING
    )
    query = collection.order_by(order_by, direction=direction)

    # Note: Firestore doesn't have efficient OFFSET
    # For better performance, use cursor-based pagination in production
    docs = query.limit(limit + offset).stream()

    articles = []
    for i, doc in enumerate(docs):
        if i >= offset:
            articles.append(doc.to_dict())

    return articles
