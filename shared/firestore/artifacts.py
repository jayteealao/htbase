"""
Artifact operations for Firestore.

Provides functions for managing archive artifacts within article documents.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from google.cloud import firestore

from shared.infrastructure.firestore import get_articles_collection
from shared.firestore.articles import get_article

logger = logging.getLogger(__name__)


def update_artifact(
    item_id: str,
    archiver: str,
    status: str,
    gcs_path: Optional[str] = None,
    gcs_bucket: Optional[str] = None,
    file_size: Optional[int] = None,
    exit_code: Optional[int] = None,
) -> None:
    """Update artifact status in archives map.

    Args:
        item_id: Article identifier
        archiver: Archiver name (singlefile, monolith, pdf, etc.)
        status: Artifact status (pending, in_progress, success, failed, skipped)
        gcs_path: GCS object path
        gcs_bucket: GCS bucket name
        file_size: File size in bytes
        exit_code: Command exit code
    """
    collection = get_articles_collection()
    doc_ref = collection.document(item_id)

    artifact_data = {
        "status": status,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }

    if gcs_path is not None:
        artifact_data["gcs_path"] = gcs_path
    if gcs_bucket is not None:
        artifact_data["gcs_bucket"] = gcs_bucket
    if file_size is not None:
        artifact_data["file_size"] = file_size
    if exit_code is not None:
        artifact_data["exit_code"] = exit_code

    # Update nested map using dot notation
    doc_ref.update({
        f"archives.{archiver}": artifact_data,
        "updated_at": firestore.SERVER_TIMESTAMP,
    })

    logger.info(f"Updated artifact: {item_id}/{archiver} -> {status}")


def get_artifact(item_id: str, archiver: str) -> Optional[Dict[str, Any]]:
    """Get artifact data for specific archiver.

    Args:
        item_id: Article identifier
        archiver: Archiver name

    Returns:
        Artifact data dictionary or None if not found
    """
    article = get_article(item_id)
    if not article:
        return None

    archives = article.get("archives", {})
    return archives.get(archiver)


def get_artifacts_by_status(
    status: str,
    archiver: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Query articles by artifact status.

    Note: Firestore doesn't support nested map queries efficiently.
    This fetches documents and filters in-memory.
    For production use, consider restructuring as subcollection.

    Args:
        status: Artifact status to filter by
        archiver: Optional archiver name to filter by
        limit: Maximum number of results

    Returns:
        List of results with article + artifact info
    """
    collection = get_articles_collection()
    docs = collection.limit(limit * 2).stream()  # Over-fetch for filtering

    results = []
    for doc in docs:
        data = doc.to_dict()
        archives = data.get("archives", {})

        for arch_name, arch_data in archives.items():
            if archiver and arch_name != archiver:
                continue
            if arch_data.get("status") == status:
                results.append({
                    "item_id": data["item_id"],
                    "url": data["url"],
                    "archiver": arch_name,
                    "artifact": arch_data,
                    "article": data,  # Full article for context
                })

                if len(results) >= limit:
                    return results

    return results
