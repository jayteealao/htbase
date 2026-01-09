"""
Validation tasks - verify data integrity between Firestore and PostgreSQL.

These tasks help ensure the migration completed successfully and data
is consistent between both databases.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from firebase_admin import firestore
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from shared.celery_config import celery_app
from shared.config import get_settings

logger = logging.getLogger(__name__)


def get_firestore_client():
    """Get Firestore client instance."""
    return firestore.client()


def get_postgres_session() -> Session:
    """Get PostgreSQL session."""
    settings = get_settings()
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
    )
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


@celery_app.task(name="services.sync_worker.tasks.compare_counts")
def compare_counts(collection: str = "articles") -> Dict[str, Any]:
    """
    Compare document counts between Firestore and PostgreSQL.

    Args:
        collection: Firestore collection to compare

    Returns:
        Dictionary with count comparison results
    """
    logger.info(f"Comparing counts for collection: {collection}")

    firestore_db = get_firestore_client()
    postgres_session = get_postgres_session()

    try:
        # Count Firestore documents
        firestore_count = 0
        try:
            # Get all documents and count them
            # Note: Firestore count() aggregation is more efficient but requires newer SDK
            docs = firestore_db.collection(collection).stream()
            firestore_count = sum(1 for _ in docs)
        except Exception as e:
            logger.error(f"Failed to count Firestore documents: {e}")
            firestore_count = -1

        # Count PostgreSQL records
        postgres_count = 0
        try:
            result = postgres_session.execute(
                text("SELECT COUNT(*) FROM archived_urls")
            )
            postgres_count = result.scalar()
        except Exception as e:
            logger.error(f"Failed to count PostgreSQL records: {e}")
            postgres_count = -1

        # Calculate difference
        difference = firestore_count - postgres_count if firestore_count >= 0 and postgres_count >= 0 else None
        match = firestore_count == postgres_count if difference is not None else False

        result = {
            "firestore_count": firestore_count,
            "postgres_count": postgres_count,
            "difference": difference,
            "match": match,
            "status": "success" if match else "mismatch",
        }

        logger.info(
            f"Count comparison: Firestore={firestore_count}, "
            f"PostgreSQL={postgres_count}, Match={match}"
        )

        return result

    finally:
        postgres_session.close()


@celery_app.task(name="services.sync_worker.tasks.validate_sync")
def validate_migration(
    collection: str = "articles",
    sample_size: int = 100,
) -> Dict[str, Any]:
    """
    Validate migration by sampling records and checking data integrity.

    Args:
        collection: Firestore collection to validate
        sample_size: Number of random records to validate

    Returns:
        Dictionary with validation results
    """
    logger.info(
        f"Validating migration: collection={collection}, sample_size={sample_size}"
    )

    firestore_db = get_firestore_client()
    postgres_session = get_postgres_session()

    try:
        # Get count comparison first
        counts = compare_counts(collection)

        # Sample random PostgreSQL records
        result = postgres_session.execute(
            text(
                """
                SELECT item_id, url, created_at
                FROM archived_urls
                ORDER BY RANDOM()
                LIMIT :limit
                """
            ),
            {"limit": sample_size},
        )

        sampled_records = result.fetchall()

        if not sampled_records:
            return {
                "status": "error",
                "message": "No records found in PostgreSQL",
                "counts": counts,
            }

        # Validate each sampled record
        validation_errors: List[Dict[str, Any]] = []
        validated_count = 0

        for record in sampled_records:
            item_id, url, created_at = record

            try:
                # Check if document exists in Firestore
                if item_id:
                    firestore_doc = (
                        firestore_db.collection(collection).document(item_id).get()
                    )

                    if not firestore_doc.exists:
                        validation_errors.append(
                            {
                                "item_id": item_id,
                                "url": url,
                                "error": "Document not found in Firestore",
                            }
                        )
                        continue

                    # Validate URL matches
                    firestore_data = firestore_doc.to_dict()
                    firestore_url = firestore_data.get("url")

                    if firestore_url != url:
                        validation_errors.append(
                            {
                                "item_id": item_id,
                                "error": "URL mismatch",
                                "postgres_url": url,
                                "firestore_url": firestore_url,
                            }
                        )
                        continue

                validated_count += 1

            except Exception as e:
                logger.error(f"Validation error for {item_id}: {e}")
                validation_errors.append(
                    {
                        "item_id": item_id,
                        "url": url,
                        "error": f"Validation exception: {str(e)}",
                    }
                )

        # Calculate validation rate
        validation_rate = (
            validated_count / len(sampled_records) if sampled_records else 0
        )

        result = {
            "status": "success" if validation_rate > 0.95 else "warning",
            "counts": counts,
            "sample_size": len(sampled_records),
            "validated_count": validated_count,
            "error_count": len(validation_errors),
            "validation_rate": validation_rate,
            "errors": validation_errors[:10],  # Return first 10 errors
        }

        logger.info(
            f"Validation complete: validated={validated_count}/{len(sampled_records)}, "
            f"errors={len(validation_errors)}, rate={validation_rate:.2%}"
        )

        return result

    finally:
        postgres_session.close()


@celery_app.task(name="services.sync_worker.tasks.find_missing_records")
def find_missing_records(
    collection: str = "articles",
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Find records that exist in Firestore but not in PostgreSQL.

    Args:
        collection: Firestore collection to check
        limit: Maximum number of missing records to return

    Returns:
        Dictionary with missing records
    """
    logger.info(f"Finding missing records: collection={collection}, limit={limit}")

    firestore_db = get_firestore_client()
    postgres_session = get_postgres_session()

    try:
        # Get all PostgreSQL URLs (for comparison)
        result = postgres_session.execute(text("SELECT url FROM archived_urls"))
        postgres_urls = {row[0] for row in result.fetchall()}

        logger.info(f"Found {len(postgres_urls)} URLs in PostgreSQL")

        # Stream Firestore documents and find missing ones
        missing_records: List[Dict[str, Any]] = []
        checked_count = 0

        docs = firestore_db.collection(collection).stream()

        for doc in docs:
            checked_count += 1

            if len(missing_records) >= limit:
                break

            try:
                doc_dict = doc.to_dict()
                url = doc_dict.get("url")

                if url and url not in postgres_urls:
                    missing_records.append(
                        {
                            "item_id": doc.id,
                            "url": url,
                            "title": doc_dict.get("title"),
                            "created_at": str(doc_dict.get("created_at")),
                        }
                    )

            except Exception as e:
                logger.error(f"Error checking document {doc.id}: {e}")

        result = {
            "status": "success",
            "checked_count": checked_count,
            "missing_count": len(missing_records),
            "missing_records": missing_records,
        }

        logger.info(
            f"Found {len(missing_records)} missing records out of {checked_count} checked"
        )

        return result

    finally:
        postgres_session.close()


@celery_app.task(name="services.sync_worker.tasks.get_sync_stats")
def get_migration_stats() -> Dict[str, Any]:
    """
    Get comprehensive migration statistics.

    Returns:
        Dictionary with migration statistics
    """
    logger.info("Getting migration statistics")

    postgres_session = get_postgres_session()

    try:
        # Get migration progress
        result = postgres_session.execute(
            text(
                """
                SELECT id, collection, last_document_id, documents_migrated,
                       started_at, updated_at, completed_at, status
                FROM migration_progress
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
        )
        progress_row = result.fetchone()

        if not progress_row:
            return {
                "status": "not_started",
                "message": "No migration progress found",
            }

        progress = {
            "id": progress_row[0],
            "collection": progress_row[1],
            "last_document_id": progress_row[2],
            "documents_migrated": progress_row[3],
            "started_at": str(progress_row[4]),
            "updated_at": str(progress_row[5]) if progress_row[5] else None,
            "completed_at": str(progress_row[6]) if progress_row[6] else None,
            "status": progress_row[7],
        }

        # Calculate duration
        if progress_row[6]:  # completed_at
            duration = (progress_row[6] - progress_row[4]).total_seconds()
        elif progress_row[5]:  # updated_at
            from datetime import datetime

            duration = (datetime.utcnow() - progress_row[4]).total_seconds()
        else:
            duration = 0

        # Get PostgreSQL counts by type
        result = postgres_session.execute(
            text(
                """
                SELECT
                    COUNT(*) as archived_urls,
                    (SELECT COUNT(*) FROM url_metadata) as url_metadata,
                    (SELECT COUNT(*) FROM archive_artifact) as archive_artifacts,
                    (SELECT COUNT(*) FROM article_summaries) as article_summaries,
                    (SELECT COUNT(*) FROM article_entities) as article_entities,
                    (SELECT COUNT(*) FROM article_tags) as article_tags
                FROM archived_urls
                """
            )
        )
        counts_row = result.fetchone()

        counts = {
            "archived_urls": counts_row[0],
            "url_metadata": counts_row[1],
            "archive_artifacts": counts_row[2],
            "article_summaries": counts_row[3],
            "article_entities": counts_row[4],
            "article_tags": counts_row[5],
        }

        return {
            "status": "success",
            "progress": progress,
            "duration_seconds": duration,
            "counts": counts,
        }

    finally:
        postgres_session.close()
