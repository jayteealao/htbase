"""
Backfill task - migrate data from Firestore to PostgreSQL.

This task implements resumable batch migration with progress tracking.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from celery import Task
from firebase_admin import credentials, firestore, initialize_app
from google.cloud.firestore_v1 import DocumentSnapshot
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from shared.celery_config import celery_app
from shared.config import get_settings
from shared.db.models import ArchivedUrl, Base

from ..converters.firestore_to_pg import FirestoreToPostgresConverter

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
settings = get_settings()

try:
    if settings.firestore.is_configured():
        # Initialize Firebase app for Firestore access
        # Uses GOOGLE_APPLICATION_CREDENTIALS environment variable
        initialize_app()
        logger.info("Firebase Admin SDK initialized")
    else:
        logger.warning("Firestore not configured, migration tasks will fail")
except Exception as e:
    logger.error(f"Failed to initialize Firebase Admin SDK: {e}")


def get_firestore_client():
    """Get Firestore client instance."""
    return firestore.client()


def get_postgres_session() -> Session:
    """Get PostgreSQL session."""
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
    )
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def get_or_create_migration_progress(
    session: Session, collection: str = "articles"
) -> Dict[str, Any]:
    """
    Get or create migration progress record.

    Args:
        session: Database session
        collection: Firestore collection name

    Returns:
        Dictionary with progress data
    """
    try:
        result = session.execute(
            text(
                """
                SELECT id, collection, last_document_id, documents_migrated,
                       started_at, updated_at, completed_at, status
                FROM migration_progress
                WHERE collection = :collection
                ORDER BY started_at DESC
                LIMIT 1
                """
            ),
            {"collection": collection},
        )
        row = result.fetchone()

        if row:
            return {
                "id": row[0],
                "collection": row[1],
                "last_document_id": row[2],
                "documents_migrated": row[3],
                "started_at": row[4],
                "updated_at": row[5],
                "completed_at": row[6],
                "status": row[7],
            }
        else:
            # Create new progress record
            result = session.execute(
                text(
                    """
                    INSERT INTO migration_progress
                    (collection, documents_migrated, started_at, status)
                    VALUES (:collection, 0, :started_at, 'running')
                    RETURNING id
                    """
                ),
                {"collection": collection, "started_at": datetime.utcnow()},
            )
            new_id = result.fetchone()[0]
            session.commit()

            return {
                "id": new_id,
                "collection": collection,
                "last_document_id": None,
                "documents_migrated": 0,
                "started_at": datetime.utcnow(),
                "updated_at": None,
                "completed_at": None,
                "status": "running",
            }

    except Exception as e:
        logger.error(f"Failed to get/create migration progress: {e}")
        session.rollback()
        raise


def update_migration_progress(
    session: Session,
    progress_id: int,
    last_doc_id: Optional[str] = None,
    documents_migrated: Optional[int] = None,
    status: Optional[str] = None,
    completed: bool = False,
) -> None:
    """
    Update migration progress.

    Args:
        session: Database session
        progress_id: Progress record ID
        last_doc_id: Last migrated document ID
        documents_migrated: Total documents migrated
        status: Migration status
        completed: Whether migration is completed
    """
    try:
        updates = ["updated_at = :updated_at"]
        params: Dict[str, Any] = {
            "progress_id": progress_id,
            "updated_at": datetime.utcnow(),
        }

        if last_doc_id is not None:
            updates.append("last_document_id = :last_doc_id")
            params["last_doc_id"] = last_doc_id

        if documents_migrated is not None:
            updates.append("documents_migrated = :documents_migrated")
            params["documents_migrated"] = documents_migrated

        if status is not None:
            updates.append("status = :status")
            params["status"] = status

        if completed:
            updates.append("completed_at = :completed_at")
            params["completed_at"] = datetime.utcnow()
            params["status"] = "completed"
            updates.append("status = :status")

        query = f"""
            UPDATE migration_progress
            SET {', '.join(updates)}
            WHERE id = :progress_id
        """

        session.execute(text(query), params)
        session.commit()

    except Exception as e:
        logger.error(f"Failed to update migration progress: {e}")
        session.rollback()
        raise


class BackfillTask(Task):
    """Custom Celery task with error handling and cleanup."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        logger.error(
            f"Backfill task {task_id} failed: {exc}",
            exc_info=einfo,
        )

        # Update progress status to failed
        try:
            session = get_postgres_session()
            try:
                # Get the latest progress record
                result = session.execute(
                    text(
                        """
                        SELECT id FROM migration_progress
                        WHERE collection = 'articles' AND status = 'running'
                        ORDER BY started_at DESC
                        LIMIT 1
                        """
                    )
                )
                row = result.fetchone()
                if row:
                    update_migration_progress(
                        session, row[0], status="failed"
                    )
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Failed to update progress on failure: {e}")


@celery_app.task(
    bind=True,
    base=BackfillTask,
    name="services.migration_worker.tasks.backfill_firestore_to_postgres",
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
)
def backfill_firestore_to_postgres(
    self,
    batch_size: int = 100,
    cursor: Optional[str] = None,
    collection: str = "articles",
) -> Dict[str, Any]:
    """
    Backfill Firestore documents to PostgreSQL.

    This task processes documents in batches and schedules itself to continue
    until all documents are migrated. Progress is tracked in the database
    for resumability.

    Args:
        batch_size: Number of documents to process per batch
        cursor: Firestore cursor to resume from (document ID)
        collection: Firestore collection to migrate

    Returns:
        Dictionary with migration results
    """
    logger.info(
        f"Starting backfill batch: batch_size={batch_size}, cursor={cursor}"
    )

    firestore_db = get_firestore_client()
    postgres_session = get_postgres_session()

    try:
        # Get or create progress tracking
        progress = get_or_create_migration_progress(postgres_session, collection)
        progress_id = progress["id"]

        # If we have a cursor from progress but not from args, use progress cursor
        if not cursor and progress["last_document_id"]:
            cursor = progress["last_document_id"]
            logger.info(f"Resuming from saved cursor: {cursor}")

        # Query Firestore in batches
        query = firestore_db.collection(collection).limit(batch_size)

        if cursor:
            # Get the cursor document to start after it
            cursor_doc = firestore_db.collection(collection).document(cursor).get()
            if cursor_doc.exists:
                query = query.start_after(cursor_doc)
                logger.info(f"Starting after document: {cursor}")
            else:
                logger.warning(f"Cursor document not found: {cursor}")

        docs = query.stream()

        migrated_count = 0
        error_count = 0
        last_doc_id = cursor

        converter = FirestoreToPostgresConverter()

        for doc in docs:
            try:
                # Convert Firestore document to PostgreSQL models
                doc_dict = doc.to_dict()
                doc_dict["item_id"] = doc.id  # Ensure item_id is set

                logger.debug(f"Migrating document: {doc.id}")

                (
                    archived_url,
                    url_metadata,
                    artifacts,
                    summary,
                    entities,
                    tags,
                ) = converter.convert_document(doc_dict)

                if not archived_url:
                    logger.warning(f"Skipping document {doc.id}: no archived_url")
                    error_count += 1
                    continue

                # Check if URL already exists in PostgreSQL
                existing = postgres_session.execute(
                    select(ArchivedUrl).where(ArchivedUrl.url == archived_url.url)
                ).scalar_one_or_none()

                if existing:
                    logger.debug(
                        f"Document {doc.id} already migrated (URL: {archived_url.url})"
                    )
                    last_doc_id = doc.id
                    continue

                # Insert into PostgreSQL
                postgres_session.add(archived_url)
                postgres_session.flush()  # Get the ID

                # Set foreign keys for related models
                if url_metadata:
                    url_metadata.archived_url_id = archived_url.id
                    postgres_session.add(url_metadata)

                for artifact in artifacts:
                    artifact.archived_url_id = archived_url.id
                    postgres_session.add(artifact)

                if summary:
                    summary.archived_url_id = archived_url.id
                    postgres_session.add(summary)

                for entity in entities:
                    entity.archived_url_id = archived_url.id
                    postgres_session.add(entity)

                for tag in tags:
                    tag.archived_url_id = archived_url.id
                    postgres_session.add(tag)

                postgres_session.commit()

                migrated_count += 1
                last_doc_id = doc.id

                logger.debug(f"Successfully migrated document: {doc.id}")

            except Exception as e:
                logger.error(f"Failed to migrate document {doc.id}: {e}", exc_info=True)
                postgres_session.rollback()
                error_count += 1
                continue

        # Update progress
        total_migrated = progress["documents_migrated"] + migrated_count
        update_migration_progress(
            postgres_session,
            progress_id,
            last_doc_id=last_doc_id,
            documents_migrated=total_migrated,
        )

        logger.info(
            f"Batch complete: migrated={migrated_count}, errors={error_count}, "
            f"total={total_migrated}, last_doc={last_doc_id}"
        )

        # Schedule next batch if we processed a full batch
        if migrated_count + error_count >= batch_size:
            logger.info("Scheduling next batch...")
            backfill_firestore_to_postgres.apply_async(
                kwargs={
                    "batch_size": batch_size,
                    "cursor": last_doc_id,
                    "collection": collection,
                },
                countdown=5,  # Wait 5 seconds before next batch
            )

            return {
                "status": "running",
                "migrated_count": migrated_count,
                "error_count": error_count,
                "total_migrated": total_migrated,
                "last_document_id": last_doc_id,
                "has_more": True,
            }
        else:
            # Migration complete
            logger.info("Migration complete!")
            update_migration_progress(
                postgres_session,
                progress_id,
                last_doc_id=last_doc_id,
                documents_migrated=total_migrated,
                completed=True,
            )

            return {
                "status": "completed",
                "migrated_count": migrated_count,
                "error_count": error_count,
                "total_migrated": total_migrated,
                "last_document_id": last_doc_id,
                "has_more": False,
            }

    except Exception as e:
        logger.error(f"Backfill task failed: {e}", exc_info=True)
        postgres_session.rollback()
        raise
    finally:
        postgres_session.close()


@celery_app.task(name="services.migration_worker.tasks.resume_backfill")
def resume_backfill(
    batch_size: int = 100,
    collection: str = "articles",
) -> Dict[str, Any]:
    """
    Resume backfill from last saved progress.

    Args:
        batch_size: Number of documents to process per batch
        collection: Firestore collection to migrate

    Returns:
        Dictionary with resume status
    """
    logger.info(f"Resuming backfill for collection: {collection}")

    postgres_session = get_postgres_session()

    try:
        progress = get_or_create_migration_progress(postgres_session, collection)

        if progress["status"] == "completed":
            logger.info("Migration already completed")
            return {
                "status": "completed",
                "message": "Migration already completed",
                "total_migrated": progress["documents_migrated"],
            }

        # Update status to running if it was paused or failed
        if progress["status"] in ["paused", "failed"]:
            update_migration_progress(
                postgres_session,
                progress["id"],
                status="running",
            )

        # Start/resume backfill
        cursor = progress["last_document_id"]
        logger.info(
            f"Resuming from cursor: {cursor}, "
            f"already migrated: {progress['documents_migrated']}"
        )

        # Schedule backfill task
        backfill_firestore_to_postgres.apply_async(
            kwargs={
                "batch_size": batch_size,
                "cursor": cursor,
                "collection": collection,
            }
        )

        return {
            "status": "resumed",
            "message": f"Migration resumed from {cursor}",
            "documents_migrated": progress["documents_migrated"],
            "last_document_id": cursor,
        }

    finally:
        postgres_session.close()
