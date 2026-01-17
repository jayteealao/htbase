"""
Summary operations for Firestore.

Provides functions for managing AI-generated article summaries.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from google.cloud import firestore

from shared.firestore_client import get_articles_collection
from shared.firestore.articles import get_article

logger = logging.getLogger(__name__)


def create_summary(
    item_id: str,
    summary_text: str,
    bullet_points: Optional[List[str]] = None,
    lede: Optional[str] = None,
    model_name: Optional[str] = None,
) -> None:
    """Create/update AI-generated summary.

    Args:
        item_id: Article identifier
        summary_text: Main summary text
        bullet_points: List of bullet points
        lede: Summary lede/intro
        model_name: LLM model name (e.g., 'claude-3-sonnet')
    """
    collection = get_articles_collection()
    doc_ref = collection.document(item_id)

    summary_data = {
        "text": summary_text,
        "bulletPoints": bullet_points or [],
        "lede": lede,
        "modelName": model_name,
        "createdAt": firestore.SERVER_TIMESTAMP,
    }

    doc_ref.update({
        "summary": summary_data,
        "updated_at": firestore.SERVER_TIMESTAMP,
    })

    logger.info(f"Created summary for: {item_id}")


def get_summary(item_id: str) -> Optional[Dict[str, Any]]:
    """Get summary for article.

    Args:
        item_id: Article identifier

    Returns:
        Summary data dictionary or None if not found
    """
    article = get_article(item_id)
    if not article:
        return None

    return article.get("summary") if article.get("summary") else None
