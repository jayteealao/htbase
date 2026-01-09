"""
Storage Worker Celery Tasks.

Defines Celery tasks for file storage operations.
"""

from __future__ import annotations

import gzip
import logging
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from celery import Task
from shared.celery_config import celery_app, configure_for_worker
from shared.config import get_settings, configure_logging
from shared.db import get_session, ArchiveArtifact, ArchivedUrl

# Configure for storage worker
configure_for_worker("storage")

logger = logging.getLogger(__name__)


class StorageTask(Task):
    """Base class for storage tasks."""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True
    max_retries = 5

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        logger.error(
            f"Storage task failed: {exc}",
            exc_info=True,
            extra={"task_id": task_id, "kwargs": kwargs},
        )


@celery_app.task(base=StorageTask, bind=True, name="services.storage_worker.tasks.upload_to_gcs")
def upload_to_gcs(
    self,
    item_id: str,
    archiver: str,
    artifact_id: int,
    local_path: str,
) -> dict:
    """
    Upload archive artifact to Google Cloud Storage.

    Args:
        item_id: Item identifier
        archiver: Archiver name
        artifact_id: Database ID of artifact
        local_path: Local file path to upload

    Returns:
        Upload result dictionary
    """
    logger.info(
        "Starting GCS upload",
        extra={
            "task_id": self.request.id,
            "item_id": item_id,
            "archiver": archiver,
            "local_path": local_path,
        },
    )

    settings = get_settings()
    path = Path(local_path)

    if not path.exists():
        logger.error(f"Local file not found: {local_path}")
        return {"success": False, "error": "file_not_found"}

    try:
        from google.cloud import storage

        # Initialize GCS client
        client = storage.Client(project=settings.gcs.project_id)
        bucket = client.bucket(settings.gcs.bucket)

        # Determine destination path
        file_ext = path.suffix
        gcs_path = f"archives/{item_id}/{archiver}/output{file_ext}"

        # Compress if not already compressed
        if file_ext not in [".gz", ".zip", ".br"]:
            compressed_path = path.with_suffix(path.suffix + ".gz")
            _compress_file(path, compressed_path)
            upload_path = compressed_path
            gcs_path = f"archives/{item_id}/{archiver}/output{file_ext}.gz"
        else:
            upload_path = path
            compressed_path = None

        # Upload to GCS
        blob = bucket.blob(gcs_path)
        blob.upload_from_filename(str(upload_path))

        # Get file sizes
        original_size = path.stat().st_size
        stored_size = upload_path.stat().st_size
        compression_ratio = stored_size / original_size if original_size > 0 else 1.0

        # Clean up compressed file
        if compressed_path and compressed_path.exists():
            compressed_path.unlink()

        # Update database
        _update_artifact_storage(
            artifact_id=artifact_id,
            gcs_path=gcs_path,
            gcs_bucket=settings.gcs.bucket,
            stored_size=stored_size,
            compression_ratio=compression_ratio,
        )

        logger.info(
            "GCS upload completed",
            extra={
                "item_id": item_id,
                "gcs_path": gcs_path,
                "original_size": original_size,
                "stored_size": stored_size,
            },
        )

        return {
            "success": True,
            "gcs_path": gcs_path,
            "gcs_bucket": settings.gcs.bucket,
            "original_size": original_size,
            "stored_size": stored_size,
            "compression_ratio": compression_ratio,
        }

    except Exception as e:
        logger.error(f"GCS upload failed: {e}", exc_info=True)
        raise


@celery_app.task(base=StorageTask, bind=True, name="services.storage_worker.tasks.upload_artifacts")
def upload_artifacts(
    self,
    item_id: str,
    archived_url_id: int,
) -> dict:
    """
    Upload all successful artifacts for an item to storage.

    Args:
        item_id: Item identifier
        archived_url_id: Database ID of archived URL

    Returns:
        Upload results for all artifacts
    """
    logger.info(
        "Starting artifact uploads",
        extra={
            "task_id": self.request.id,
            "item_id": item_id,
            "archived_url_id": archived_url_id,
        },
    )

    # Get all successful artifacts
    with get_session() as session:
        artifacts = (
            session.query(ArchiveArtifact)
            .filter(
                ArchiveArtifact.archived_url_id == archived_url_id,
                ArchiveArtifact.success == True,
                ArchiveArtifact.uploaded_to_storage == False,
            )
            .all()
        )

        results = []
        for artifact in artifacts:
            if artifact.saved_path:
                try:
                    result = upload_to_gcs.delay(
                        item_id=item_id,
                        archiver=artifact.archiver,
                        artifact_id=artifact.id,
                        local_path=artifact.saved_path,
                    )
                    results.append({
                        "archiver": artifact.archiver,
                        "task_id": result.id,
                        "status": "queued",
                    })
                except Exception as e:
                    results.append({
                        "archiver": artifact.archiver,
                        "status": "error",
                        "error": str(e),
                    })

    return {
        "item_id": item_id,
        "uploads_queued": len(results),
        "results": results,
    }


@celery_app.task(base=StorageTask, bind=True, name="services.storage_worker.tasks.download_from_gcs")
def download_from_gcs(
    self,
    gcs_path: str,
    local_path: str,
    decompress: bool = True,
) -> dict:
    """
    Download file from Google Cloud Storage.

    Args:
        gcs_path: Path in GCS bucket
        local_path: Local destination path
        decompress: Whether to decompress .gz files

    Returns:
        Download result dictionary
    """
    logger.info(
        "Starting GCS download",
        extra={
            "task_id": self.request.id,
            "gcs_path": gcs_path,
            "local_path": local_path,
        },
    )

    settings = get_settings()

    try:
        from google.cloud import storage

        client = storage.Client(project=settings.gcs.project_id)
        bucket = client.bucket(settings.gcs.bucket)
        blob = bucket.blob(gcs_path)

        # Ensure directory exists
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)

        # Download file
        if decompress and gcs_path.endswith(".gz"):
            # Download to temp and decompress
            temp_path = local_path + ".gz"
            blob.download_to_filename(temp_path)
            _decompress_file(Path(temp_path), Path(local_path))
            Path(temp_path).unlink()
        else:
            blob.download_to_filename(local_path)

        logger.info(
            "GCS download completed",
            extra={"gcs_path": gcs_path, "local_path": local_path},
        )

        return {
            "success": True,
            "local_path": local_path,
        }

    except Exception as e:
        logger.error(f"GCS download failed: {e}", exc_info=True)
        raise


@celery_app.task(base=StorageTask, bind=True, name="services.storage_worker.tasks.cleanup_local_files")
def cleanup_local_files(
    self,
    artifact_id: int,
    local_path: str,
) -> dict:
    """
    Clean up local files after successful cloud upload.

    Args:
        artifact_id: Database ID of artifact
        local_path: Local file path to delete

    Returns:
        Cleanup result dictionary
    """
    logger.info(
        "Starting local cleanup",
        extra={
            "task_id": self.request.id,
            "artifact_id": artifact_id,
            "local_path": local_path,
        },
    )

    path = Path(local_path)

    if not path.exists():
        return {"success": True, "reason": "already_deleted"}

    try:
        # Delete the file
        path.unlink()

        # Try to remove empty parent directories
        parent = path.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

        # Update database
        with get_session() as session:
            artifact = session.query(ArchiveArtifact).get(artifact_id)
            if artifact:
                artifact.local_file_deleted = True
                artifact.local_file_deleted_at = datetime.utcnow()

        logger.info(
            "Local cleanup completed",
            extra={"artifact_id": artifact_id, "local_path": local_path},
        )

        return {"success": True, "deleted_path": local_path}

    except Exception as e:
        logger.error(f"Local cleanup failed: {e}", exc_info=True)
        raise


@celery_app.task(bind=True, name="services.storage_worker.tasks.cleanup_expired_files")
def cleanup_expired_files(self) -> dict:
    """
    Periodic task to clean up expired local files.

    Finds artifacts where cloud upload succeeded and retention period expired.
    """
    logger.info("Starting expired file cleanup")

    settings = get_settings()
    cutoff = datetime.utcnow() - timedelta(hours=settings.local_workspace_retention_hours)

    with get_session() as session:
        artifacts = (
            session.query(ArchiveArtifact)
            .filter(
                ArchiveArtifact.success == True,
                ArchiveArtifact.all_uploads_succeeded == True,
                ArchiveArtifact.local_file_deleted == False,
                ArchiveArtifact.created_at < cutoff,
            )
            .limit(100)
            .all()
        )

        cleaned = 0
        errors = 0

        for artifact in artifacts:
            if artifact.saved_path:
                try:
                    path = Path(artifact.saved_path)
                    if path.exists():
                        path.unlink()
                        cleaned += 1

                    artifact.local_file_deleted = True
                    artifact.local_file_deleted_at = datetime.utcnow()
                except Exception as e:
                    logger.error(f"Failed to delete {artifact.saved_path}: {e}")
                    errors += 1

    logger.info(
        "Expired file cleanup completed",
        extra={"cleaned": cleaned, "errors": errors},
    )

    return {"cleaned": cleaned, "errors": errors}


@celery_app.task(bind=True, name="services.storage_worker.tasks.retry_failed_uploads")
def retry_failed_uploads(self) -> dict:
    """
    Periodic task to retry failed storage uploads.
    """
    logger.info("Starting failed upload retry")

    with get_session() as session:
        from shared.db import ArchivedUrl

        artifacts = (
            session.query(ArchiveArtifact, ArchivedUrl)
            .join(ArchivedUrl)
            .filter(
                ArchiveArtifact.success == True,
                ArchiveArtifact.uploaded_to_storage == False,
                ArchiveArtifact.saved_path.isnot(None),
            )
            .limit(50)
            .all()
        )

        queued = 0
        for artifact, archived_url in artifacts:
            if artifact.saved_path and Path(artifact.saved_path).exists():
                upload_to_gcs.delay(
                    item_id=archived_url.item_id,
                    archiver=artifact.archiver,
                    artifact_id=artifact.id,
                    local_path=artifact.saved_path,
                )
                queued += 1

    logger.info(
        "Failed upload retry completed",
        extra={"queued": queued},
    )

    return {"queued": queued}


def _compress_file(source: Path, dest: Path) -> None:
    """Compress a file using gzip."""
    with open(source, "rb") as f_in:
        with gzip.open(dest, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)


def _decompress_file(source: Path, dest: Path) -> None:
    """Decompress a gzip file."""
    with gzip.open(source, "rb") as f_in:
        with open(dest, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)


def _update_artifact_storage(
    artifact_id: int,
    gcs_path: str,
    gcs_bucket: str,
    stored_size: int,
    compression_ratio: float,
) -> None:
    """Update artifact with storage information."""
    with get_session() as session:
        artifact = session.query(ArchiveArtifact).get(artifact_id)
        if artifact:
            artifact.gcs_path = gcs_path
            artifact.gcs_bucket = gcs_bucket
            artifact.uploaded_to_storage = True
            artifact.all_uploads_succeeded = True
            artifact.storage_uploads = [
                {
                    "provider": "gcs",
                    "path": gcs_path,
                    "bucket": gcs_bucket,
                    "size": stored_size,
                    "compression_ratio": compression_ratio,
                    "uploaded_at": datetime.utcnow().isoformat(),
                }
            ]
            artifact.updated_at = datetime.utcnow()


@celery_app.task(bind=True, name="services.storage_worker.tasks.reconcile_dual_database")
def reconcile_dual_database(self) -> dict:
    """
    Reconcile PostgreSQL and Firestore data consistency.

    Detects and fixes drift between PostgreSQL (source of truth) and Firestore
    (mobile replica) by finding records that have never been synced or are stale.

    This task implements eventual consistency pattern for dual-database writes.
    """
    logger.info("Starting dual database reconciliation")

    try:
        from shared.storage.postgres_storage import PostgresStorage
        from shared.storage.firestore_storage import FirestoreStorage
        from shared.storage.database_storage import ArticleMetadata, ArchiveArtifact as ArtifactModel

        postgres = PostgresStorage()
        firestore = FirestoreStorage()

        articles_synced = 0
        articles_failed = 0
        artifacts_synced = 0
        artifacts_failed = 0

        # Find articles that have never been synced or were updated after last sync
        with get_session() as session:
            # Get articles that need sync (never synced or updated_at > last_synced)
            unsynced_articles = (
                session.query(ArchivedUrl)
                .filter(
                    (ArchivedUrl.last_synced_to_firestore.is_(None)) |
                    (ArchivedUrl.created_at > ArchivedUrl.last_synced_to_firestore)
                )
                .limit(50)  # Process in batches to avoid overwhelming Firestore
                .all()
            )

            logger.info(f"Found {len(unsynced_articles)} articles to reconcile")

            # Sync each article to Firestore
            for au in unsynced_articles:
                try:
                    # Get full article record from PostgreSQL
                    article_record = postgres.get_article(au.item_id)
                    if not article_record:
                        logger.warning(f"Article {au.item_id} not found in PostgreSQL")
                        continue

                    # Convert to ArticleMetadata for Firestore
                    metadata = ArticleMetadata(
                        url=article_record.url,
                        item_id=article_record.item_id,
                        title=article_record.title,
                        byline=article_record.byline,
                        text_content=article_record.text_content,
                        word_count=article_record.word_count,
                        excerpt=article_record.excerpt
                    )

                    # Write to Firestore
                    success = firestore.create_article(metadata)
                    if success:
                        # Update sync timestamp
                        au.last_synced_to_firestore = datetime.utcnow()
                        session.commit()
                        articles_synced += 1
                        logger.debug(f"Synced article {au.item_id} to Firestore")
                    else:
                        articles_failed += 1
                        logger.warning(f"Failed to sync article {au.item_id}")

                except Exception as e:
                    articles_failed += 1
                    logger.error(
                        f"Error syncing article {au.item_id}: {e}",
                        exc_info=True
                    )

        # Find artifacts that need sync
        with get_session() as session:
            unsynced_artifacts = (
                session.query(ArchiveArtifact, ArchivedUrl)
                .join(ArchivedUrl)
                .filter(
                    (ArchiveArtifact.last_synced_to_firestore.is_(None)) |
                    (ArchiveArtifact.updated_at > ArchiveArtifact.last_synced_to_firestore),
                    ArchiveArtifact.success == True  # Only sync successful artifacts
                )
                .limit(50)
                .all()
            )

            logger.info(f"Found {len(unsynced_artifacts)} artifacts to reconcile")

            # Sync each artifact to Firestore
            for artifact, au in unsynced_artifacts:
                try:
                    # Convert to Firestore artifact model
                    artifact_model = ArtifactModel(
                        item_id=au.item_id,
                        archiver=artifact.archiver,
                        status=artifact.status,
                        gcs_path=artifact.gcs_path,
                        gcs_bucket=artifact.gcs_bucket,
                        file_size=artifact.size_bytes,
                        created_at=artifact.created_at
                    )

                    # Write to Firestore
                    success = firestore.create_artifact(artifact_model)
                    if success:
                        # Update sync timestamp
                        artifact.last_synced_to_firestore = datetime.utcnow()
                        session.commit()
                        artifacts_synced += 1
                        logger.debug(
                            f"Synced artifact {au.item_id}/{artifact.archiver} to Firestore"
                        )
                    else:
                        artifacts_failed += 1
                        logger.warning(
                            f"Failed to sync artifact {au.item_id}/{artifact.archiver}"
                        )

                except Exception as e:
                    artifacts_failed += 1
                    logger.error(
                        f"Error syncing artifact {au.item_id}/{artifact.archiver}: {e}",
                        exc_info=True
                    )

        result = {
            "articles_synced": articles_synced,
            "articles_failed": articles_failed,
            "artifacts_synced": artifacts_synced,
            "artifacts_failed": artifacts_failed,
            "total_synced": articles_synced + artifacts_synced,
            "total_failed": articles_failed + artifacts_failed,
        }

        logger.info(
            "Dual database reconciliation completed",
            extra=result
        )

        return result

    except Exception as e:
        logger.error(f"Reconciliation task failed: {e}", exc_info=True)
        raise


@celery_app.task(bind=True, name="services.storage_worker.tasks.detect_sync_drift")
def detect_sync_drift(self) -> dict:
    """
    Detect and report on sync drift between PostgreSQL and Firestore.

    Returns metrics about unsynced records and sync lag for monitoring/alerting.
    """
    logger.info("Starting sync drift detection")

    try:
        with get_session() as session:
            # Count articles never synced
            never_synced_articles = (
                session.query(ArchivedUrl)
                .filter(ArchivedUrl.last_synced_to_firestore.is_(None))
                .count()
            )

            # Count articles with sync lag > 10 minutes
            cutoff = datetime.utcnow() - timedelta(minutes=10)
            stale_articles = (
                session.query(ArchivedUrl)
                .filter(
                    ArchivedUrl.last_synced_to_firestore.isnot(None),
                    ArchivedUrl.created_at > ArchivedUrl.last_synced_to_firestore,
                    ArchivedUrl.created_at < cutoff
                )
                .count()
            )

            # Count artifacts never synced
            never_synced_artifacts = (
                session.query(ArchiveArtifact)
                .filter(
                    ArchiveArtifact.last_synced_to_firestore.is_(None),
                    ArchiveArtifact.success == True
                )
                .count()
            )

            # Count artifacts with sync lag > 10 minutes
            stale_artifacts = (
                session.query(ArchiveArtifact)
                .filter(
                    ArchiveArtifact.last_synced_to_firestore.isnot(None),
                    ArchiveArtifact.updated_at > ArchiveArtifact.last_synced_to_firestore,
                    ArchiveArtifact.updated_at < cutoff,
                    ArchiveArtifact.success == True
                )
                .count()
            )

            metrics = {
                "never_synced_articles": never_synced_articles,
                "stale_articles": stale_articles,
                "never_synced_artifacts": never_synced_artifacts,
                "stale_artifacts": stale_artifacts,
                "total_drift": (
                    never_synced_articles + stale_articles +
                    never_synced_artifacts + stale_artifacts
                ),
                "drift_detected": (
                    never_synced_articles + stale_articles +
                    never_synced_artifacts + stale_artifacts
                ) > 0,
                "checked_at": datetime.utcnow().isoformat()
            }

            # Log warning if significant drift detected
            if metrics["total_drift"] > 10:
                logger.warning(
                    f"Significant sync drift detected: {metrics['total_drift']} records",
                    extra=metrics
                )
            else:
                logger.info(
                    f"Sync drift check completed: {metrics['total_drift']} records out of sync",
                    extra=metrics
                )

            return metrics

    except Exception as e:
        logger.error(f"Drift detection failed: {e}", exc_info=True)
        raise
