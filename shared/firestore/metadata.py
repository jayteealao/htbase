"""
Metadata operations for Firestore.

Provides functions for managing article metadata (word count, text content, etc.).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from google.cloud import firestore

from shared.infrastructure.firestore import get_articles_collection

logger = logging.getLogger(__name__)


def update_metadata(
    item_id: str,
    word_count: Optional[int] = None,
    text_content: Optional[str] = None,
    **kwargs,
) -> None:
    """Update article metadata.

    Args:
        item_id: Article identifier
        word_count: Word count
        text_content: Full text content (camelCase: textContent)
        **kwargs: Additional metadata fields
    """
    collection = get_articles_collection()
    doc_ref = collection.document(item_id)

    metadata = {}

    if word_count is not None:
        metadata["wordCount"] = word_count
    if text_content is not None:
        metadata["textContent"] = text_content

    metadata.update(kwargs)

    if metadata:
        doc_ref.update({
            "metadata": metadata,
            "updated_at": firestore.SERVER_TIMESTAMP,
        })
