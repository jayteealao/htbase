"""
Rollback tasks - revert migration if needed.

These tasks help clean up PostgreSQL data if the migration needs to be
rolled back or restarted.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from shared.celery_config import celery_app
from shared.config import get_settings

logger = logging.getLogger(__name__)


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


@celery_app.task(name="services.sync_worker.tasks.rollback_sync")
def rollback_migration(
    confirm: bool = False,
    collection: str = "articles",
) -> Dict[str, Any]:
    """
    Rollback migration by deleting all migrated data from PostgreSQL.

    WARNING: This is a destructive operation. Use with caution.

    Args:
        confirm: Must be True to execute (safety check)
        collection: Collection that was migrated

    Returns:
        Dictionary with rollback results
    """
    if not confirm:
        return {
            "status": "error",
            "message": "Rollback not confirmed. Set confirm=True to proceed.",
        }

    logger.warning(f"Starting migration rollback for collection: {collection}")

    postgres_session = get_postgres_session()

    try:
        # Get counts before deletion
        result = postgres_session.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(*) FROM archived_urls) as archived_urls,
                    (SELECT COUNT(*) FROM url_metadata) as url_metadata,
                    (SELECT COUNT(*) FROM archive_artifact) as archive_artifacts,
                    (SELECT COUNT(*) FROM article_summaries) as article_summaries,
                    (SELECT COUNT(*) FROM article_entities) as article_entities,
                    (SELECT COUNT(*) FROM article_tags) as article_tags
                """
            )
        )
        before_counts = result.fetchone()

        # Delete all migrated data (CASCADE will handle related records)
        logger.warning("Deleting all archived URLs and related data...")

        postgres_session.execute(text("DELETE FROM archived_urls"))
        postgres_session.commit()

        logger.info("All migrated data deleted")

        # Update migration progress status
        postgres_session.execute(
            text(
                """
                UPDATE migration_progress
                SET status = 'rolled_back',
                    updated_at = NOW()
                WHERE collection = :collection
                  AND status != 'rolled_back'
                """
            ),
            {"collection": collection},
        )
        postgres_session.commit()

        # Get counts after deletion
        result = postgres_session.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(*) FROM archived_urls) as archived_urls,
                    (SELECT COUNT(*) FROM url_metadata) as url_metadata,
                    (SELECT COUNT(*) FROM archive_artifact) as archive_artifacts,
                    (SELECT COUNT(*) FROM article_summaries) as article_summaries,
                    (SELECT COUNT(*) FROM article_entities) as article_entities,
                    (SELECT COUNT(*) FROM article_tags) as article_tags
                """
            )
        )
        after_counts = result.fetchone()

        return {
            "status": "success",
            "message": "Migration rolled back successfully",
            "deleted_counts": {
                "archived_urls": before_counts[0] - after_counts[0],
                "url_metadata": before_counts[1] - after_counts[1],
                "archive_artifacts": before_counts[2] - after_counts[2],
                "article_summaries": before_counts[3] - after_counts[3],
                "article_entities": before_counts[4] - after_counts[4],
                "article_tags": before_counts[5] - after_counts[5],
            },
        }

    except Exception as e:
        logger.error(f"Rollback failed: {e}", exc_info=True)
        postgres_session.rollback()
        raise
    finally:
        postgres_session.close()


@celery_app.task(name="services.sync_worker.tasks.delete_synced_data")
def delete_migrated_data(
    batch_size: int = 1000,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Delete migrated data in batches (safer than full rollback).

    Args:
        batch_size: Number of records to delete per batch
        dry_run: If True, only count records without deleting

    Returns:
        Dictionary with deletion results
    """
    logger.info(
        f"Delete migrated data: batch_size={batch_size}, dry_run={dry_run}"
    )

    postgres_session = get_postgres_session()

    try:
        # Count records
        result = postgres_session.execute(
            text("SELECT COUNT(*) FROM archived_urls")
        )
        total_count = result.scalar()

        if dry_run:
            return {
                "status": "dry_run",
                "message": f"Would delete {total_count} records",
                "total_count": total_count,
            }

        # Delete in batches
        deleted_count = 0

        while True:
            # Delete batch
            result = postgres_session.execute(
                text(
                    """
                    DELETE FROM archived_urls
                    WHERE id IN (
                        SELECT id FROM archived_urls
                        ORDER BY id
                        LIMIT :batch_size
                    )
                    """
                ),
                {"batch_size": batch_size},
            )

            batch_deleted = result.rowcount
            deleted_count += batch_deleted

            postgres_session.commit()

            logger.info(f"Deleted batch: {batch_deleted} records")

            if batch_deleted == 0:
                break

            if batch_deleted < batch_size:
                # Last batch
                break

        return {
            "status": "success",
            "message": f"Deleted {deleted_count} records",
            "deleted_count": deleted_count,
            "total_count": total_count,
        }

    except Exception as e:
        logger.error(f"Deletion failed: {e}", exc_info=True)
        postgres_session.rollback()
        raise
    finally:
        postgres_session.close()


@celery_app.task(name="services.sync_worker.tasks.pause_sync")
def pause_migration(collection: str = "articles") -> Dict[str, Any]:
    """
    Pause ongoing migration.

    Args:
        collection: Collection being migrated

    Returns:
        Dictionary with pause status
    """
    logger.info(f"Pausing migration for collection: {collection}")

    postgres_session = get_postgres_session()

    try:
        result = postgres_session.execute(
            text(
                """
                UPDATE migration_progress
                SET status = 'paused',
                    updated_at = NOW()
                WHERE collection = :collection
                  AND status = 'running'
                RETURNING id, documents_migrated
                """
            ),
            {"collection": collection},
        )

        row = result.fetchone()

        if not row:
            return {
                "status": "error",
                "message": "No running migration found to pause",
            }

        postgres_session.commit()

        return {
            "status": "success",
            "message": "Migration paused",
            "progress_id": row[0],
            "documents_migrated": row[1],
        }

    finally:
        postgres_session.close()


@celery_app.task(name="services.sync_worker.tasks.reset_sync_progress")
def reset_migration_progress(
    collection: str = "articles",
    confirm: bool = False,
) -> Dict[str, Any]:
    """
    Reset migration progress to start over.

    Args:
        collection: Collection to reset
        confirm: Must be True to execute (safety check)

    Returns:
        Dictionary with reset status
    """
    if not confirm:
        return {
            "status": "error",
            "message": "Reset not confirmed. Set confirm=True to proceed.",
        }

    logger.warning(f"Resetting migration progress for collection: {collection}")

    postgres_session = get_postgres_session()

    try:
        # Delete existing progress records
        postgres_session.execute(
            text(
                """
                DELETE FROM migration_progress
                WHERE collection = :collection
                """
            ),
            {"collection": collection},
        )

        postgres_session.commit()

        return {
            "status": "success",
            "message": f"Migration progress reset for collection: {collection}",
        }

    finally:
        postgres_session.close()
