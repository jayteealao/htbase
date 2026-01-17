"""
Firestore client singleton for HTBase services.

Provides cached Firestore client instance and collection references.
Replaces PostgreSQL session management with direct Firestore access.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

from google.cloud import firestore
from google.cloud.firestore import Client, CollectionReference

from shared.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_firestore_client() -> Client:
    """Get cached Firestore client instance.

    Returns:
        Firestore Client configured with project from settings

    Raises:
        ValueError: If Firestore is not properly configured
    """
    settings = get_settings()

    if not settings.firestore.is_configured():
        raise ValueError(
            "Firestore not configured. Set FIRESTORE_PROJECT_ID or GCS_PROJECT_ID "
            "environment variable."
        )

    logger.info(
        "Initializing Firestore client",
        extra={"project_id": settings.firestore.project_id},
    )

    # Credentials automatically loaded from GOOGLE_APPLICATION_CREDENTIALS env var
    return firestore.Client(project=settings.firestore.project_id)


def get_articles_collection() -> CollectionReference:
    """Get articles collection reference.

    Returns:
        CollectionReference for the articles collection
    """
    client = get_firestore_client()
    settings = get_settings()
    return client.collection(settings.firestore.collection_name)


def check_firestore_connection() -> bool:
    """Check if Firestore connection is working.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        client = get_firestore_client()
        # Try to access collections (lightweight operation)
        list(client.collections(max_results=1))
        return True
    except Exception as e:
        logger.error(f"Firestore connection check failed: {e}", exc_info=True)
        return False
