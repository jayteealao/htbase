"""
Pocket integration operations for Firestore.

Provides functions for managing Pocket integration data.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from google.cloud import firestore

from shared.infrastructure.firestore import get_articles_collection

logger = logging.getLogger(__name__)


def update_pocket_data(item_id: str, pocket_data: Dict[str, Any]) -> None:
    """Update Pocket integration data.

    Args:
        item_id: Article identifier
        pocket_data: Pocket data dictionary with camelCase keys
    """
    collection = get_articles_collection()
    doc_ref = collection.document(item_id)

    doc_ref.update({
        "pocket": pocket_data,
        "updated_at": firestore.SERVER_TIMESTAMP,
    })

    logger.info(f"Updated Pocket data for: {item_id}")
