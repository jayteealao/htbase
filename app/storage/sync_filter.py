"""
Data Filtering for Firestore Sync

This module determines what data gets synchronized to Firestore
from PostgreSQL. Firestore is a mobile-optimized read replica that
contains only articles and pocket data (not full analytics).
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from .database_storage import (
    ArticleRecord,
    ArticleMetadata,
    ArchiveArtifact,
    PocketData,
    ArchiveStatus
)


class SyncFilter:
    """
    Filter that determines what data gets synced to Firestore.

    Firestore Sync Rules:
    - ✅ Include: item_id, url, title, byline, excerpt, created_at, pocket_data
    - ✅ Include: Basic archive status per archiver (status, gcs_path, file_size)
    - ❌ Exclude: Summaries, entities, tags, full artifact history, analytics

    Purpose:
    - Firestore optimized for mobile real-time sync
    - PostgreSQL handles analytics, search, full history
    """

    # Fields that sync to Firestore
    ALLOWED_METADATA_FIELDS = {
        'item_id', 'url', 'title', 'byline', 'excerpt',
        'word_count', 'created_at', 'updated_at'
    }

    # Fields that stay PostgreSQL-only
    POSTGRES_ONLY_FIELDS = {
        'text_content',  # Too large for Firestore
    }

    # Archive artifact fields to sync
    ALLOWED_ARTIFACT_FIELDS = {
        'status', 'gcs_path', 'gcs_bucket', 'file_size',
        'created_at', 'updated_at'
    }

    # Artifact fields to exclude
    EXCLUDED_ARTIFACT_FIELDS = {
        'local_path',  # Not relevant for mobile
        'exit_code',   # Internal detail
        'error_message',  # Internal detail (could include later for debugging)
    }

    def filter_for_firestore(self, article: ArticleRecord) -> Dict[str, Any]:
        """
        Extract Firestore-relevant data from ArticleRecord.

        Returns denormalized structure optimized for Firestore:
        {
            'item_id': '...',
            'url': '...',
            'title': '...',
            'metadata': {...},  # Filtered article metadata
            'pocket': {...} if present,
            'archives': {
                'monolith': {'status': 'success', 'gcs_path': '...'},
                'pdf': {'status': 'pending'}
            }
        }

        Args:
            article: Complete ArticleRecord from PostgreSQL

        Returns:
            Filtered dict suitable for Firestore document
        """
        result = {}

        # Filter metadata
        metadata = self._filter_metadata(article.metadata)
        result.update(metadata)

        # Add pocket data if present
        if article.pocket:
            result['pocket'] = self._filter_pocket_data(article.pocket)

        # Filter and denormalize archives
        if article.archives:
            result['archives'] = self._filter_archives(article.archives)

        return result

    def _filter_metadata(self, metadata: ArticleMetadata) -> Dict[str, Any]:
        """
        Filter article metadata to Firestore-allowed fields.

        Args:
            metadata: ArticleMetadata instance

        Returns:
            Filtered metadata dict
        """
        result = {}

        for field in self.ALLOWED_METADATA_FIELDS:
            value = getattr(metadata, field, None)
            if value is not None:
                # Convert datetime to ISO string for JSON serialization
                if isinstance(value, datetime):
                    result[field] = value.isoformat()
                else:
                    result[field] = value

        return result

    def _filter_pocket_data(self, pocket: PocketData) -> Dict[str, Any]:
        """
        Convert PocketData to Firestore-compatible dict.

        Args:
            pocket: PocketData instance

        Returns:
            Pocket data dict
        """
        return {
            'item_id': pocket.item_id,
            'resolved_id': pocket.resolved_id,
            'word_count': pocket.word_count,
            'time_added': pocket.time_added.isoformat() if pocket.time_added else None,
            'time_read': pocket.time_read.isoformat() if pocket.time_read else None,
            'favorite': pocket.favorite,
            'status': pocket.status,
            'images': pocket.images or [],
            'authors': pocket.authors or [],
        }

    def _filter_archives(self, artifacts: List[ArchiveArtifact]) -> Dict[str, Dict[str, Any]]:
        """
        Convert archive artifacts list to denormalized Firestore map.

        Firestore stores archives as nested map keyed by archiver name:
        {
            'monolith': {'status': 'success', 'gcs_path': '...'},
            'pdf': {'status': 'pending'}
        }

        This is different from PostgreSQL which stores separate rows per artifact.

        Args:
            artifacts: List of ArchiveArtifact instances

        Returns:
            Denormalized archives map
        """
        archives_map = {}

        for artifact in artifacts:
            archiver_name = artifact.archiver

            # Build filtered artifact data
            artifact_data = {
                'status': artifact.status.value if isinstance(artifact.status, ArchiveStatus) else artifact.status
            }

            # Add optional fields if present
            if artifact.gcs_path:
                artifact_data['gcs_path'] = artifact.gcs_path
            if artifact.gcs_bucket:
                artifact_data['gcs_bucket'] = artifact.gcs_bucket
            if artifact.file_size:
                artifact_data['file_size'] = artifact.file_size
            if artifact.updated_at:
                artifact_data['updated_at'] = artifact.updated_at.isoformat()
            if artifact.created_at:
                artifact_data['created_at'] = artifact.created_at.isoformat()

            archives_map[archiver_name] = artifact_data

        return archives_map

    def filter_artifact_for_firestore(
        self,
        archiver: str,
        status: ArchiveStatus,
        gcs_path: Optional[str] = None,
        gcs_bucket: Optional[str] = None,
        file_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Filter a single archive artifact for Firestore update.

        Used when updating individual artifact status without full ArticleRecord.

        Args:
            archiver: Archiver name
            status: Archive status
            gcs_path: Optional GCS path
            gcs_bucket: Optional GCS bucket
            file_size: Optional file size

        Returns:
            Filtered artifact data for Firestore
        """
        artifact_data = {
            'status': status.value if isinstance(status, ArchiveStatus) else status,
            'updated_at': datetime.utcnow().isoformat(),
        }

        if gcs_path:
            artifact_data['gcs_path'] = gcs_path
        if gcs_bucket:
            artifact_data['gcs_bucket'] = gcs_bucket
        if file_size:
            artifact_data['file_size'] = file_size

        return artifact_data

    def should_sync_to_firestore(self, data_type: str) -> bool:
        """
        Determine if a specific data type should sync to Firestore.

        Args:
            data_type: Type of data ('article', 'summary', 'entity', 'tag')

        Returns:
            True if should sync to Firestore
        """
        # Only articles and pocket data sync to Firestore
        # Summaries, entities, tags stay PostgreSQL-only
        return data_type in {'article', 'pocket', 'artifact'}
