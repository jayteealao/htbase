"""
Firestore to PostgreSQL converter.

Converts Firestore document structure to PostgreSQL model instances.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from shared.db.models import (
    ArchivedUrl,
    ArchiveArtifact,
    UrlMetadata,
    ArticleSummary,
    ArticleEntity,
    ArticleTag,
)

logger = logging.getLogger(__name__)


class FirestoreToPostgresConverter:
    """
    Converts Firestore documents to PostgreSQL models.

    Firestore Schema (from FirestoreStorage):
    - articles/{item_id}
        - url, title, byline, excerpt, created_at, updated_at
        - archives (map): {archiver_name: {status, gcs_path, gcs_bucket, ...}}
        - pocket (map): {itemId, resolvedId, wordCount, timeAdded, ...}
        - metadata (map): {textContent, wordCount}
        - summary (map): {text, bulletPoints, modelName, createdAt}
        - entities (array): [{type, value, confidence}]
        - tags (array): [{tag, source, confidence}]

    PostgreSQL Schema (from shared/db/models.py):
    - archived_urls: Main article table
    - url_metadata: Extracted content metadata
    - archive_artifact: Archive outputs per archiver
    - article_summaries: AI-generated summaries
    - article_entities: Named entities
    - article_tags: Tags/categories
    """

    @staticmethod
    def convert_document(doc_dict: Dict[str, Any]) -> tuple[
        Optional[ArchivedUrl],
        Optional[UrlMetadata],
        list[ArchiveArtifact],
        Optional[ArticleSummary],
        list[ArticleEntity],
        list[ArticleTag],
    ]:
        """
        Convert a Firestore document to PostgreSQL models.

        Args:
            doc_dict: Firestore document as dictionary

        Returns:
            Tuple of (archived_url, url_metadata, artifacts, summary, entities, tags)
            Any component can be None/empty if not present in source data
        """
        try:
            # Extract core fields
            item_id = doc_dict.get("item_id")
            url = doc_dict.get("url")

            if not url:
                logger.warning(f"Document missing URL, skipping: {item_id}")
                return None, None, [], None, [], []

            # Convert main article record
            archived_url = FirestoreToPostgresConverter._convert_archived_url(doc_dict)

            # Convert metadata
            url_metadata = FirestoreToPostgresConverter._convert_metadata(doc_dict)

            # Convert artifacts
            artifacts = FirestoreToPostgresConverter._convert_artifacts(doc_dict)

            # Convert summary
            summary = FirestoreToPostgresConverter._convert_summary(doc_dict)

            # Convert entities
            entities = FirestoreToPostgresConverter._convert_entities(doc_dict)

            # Convert tags
            tags = FirestoreToPostgresConverter._convert_tags(doc_dict)

            return archived_url, url_metadata, artifacts, summary, entities, tags

        except Exception as e:
            logger.error(f"Failed to convert document: {e}", exc_info=True)
            return None, None, [], None, [], []

    @staticmethod
    def _convert_archived_url(doc_dict: Dict[str, Any]) -> Optional[ArchivedUrl]:
        """Convert to ArchivedUrl model."""
        try:
            # Calculate total size from all artifacts
            total_size = 0
            archives = doc_dict.get("archives", {})
            for archiver_data in archives.values():
                file_size = archiver_data.get("file_size", 0)
                if file_size:
                    total_size += file_size

            created_at = doc_dict.get("created_at")
            if hasattr(created_at, "timestamp"):
                # Convert Firestore Timestamp to datetime
                created_at = datetime.fromtimestamp(created_at.timestamp())
            elif not isinstance(created_at, datetime):
                created_at = datetime.utcnow()

            return ArchivedUrl(
                item_id=doc_dict.get("item_id"),
                url=doc_dict.get("url"),
                name=doc_dict.get("title"),  # Map title to name
                created_at=created_at,
                total_size_bytes=total_size if total_size > 0 else None,
            )
        except Exception as e:
            logger.error(f"Failed to convert ArchivedUrl: {e}")
            return None

    @staticmethod
    def _convert_metadata(doc_dict: Dict[str, Any]) -> Optional[UrlMetadata]:
        """Convert to UrlMetadata model."""
        try:
            metadata_dict = doc_dict.get("metadata", {})

            # Extract metadata fields - map from Firestore camelCase to PostgreSQL snake_case
            title = doc_dict.get("title")
            byline = doc_dict.get("byline")
            excerpt = doc_dict.get("excerpt")
            text_content = metadata_dict.get("textContent")
            word_count = metadata_dict.get("wordCount")

            # Only create metadata if we have meaningful content
            if not any([title, byline, excerpt, text_content, word_count]):
                return None

            # Calculate reading time (assuming 200 words per minute)
            reading_time = None
            if word_count:
                reading_time = word_count / 200.0

            return UrlMetadata(
                source_url=doc_dict.get("url"),
                title=title,
                byline=byline,
                site_name=None,  # Not in Firestore schema
                description=excerpt,
                published=None,  # Not in Firestore schema
                language=None,  # Not in Firestore schema
                canonical_url=doc_dict.get("url"),
                top_image=None,  # Could extract from Pocket images
                favicon=None,  # Not in Firestore schema
                keywords=None,  # Not in Firestore schema
                text=text_content,
                word_count=word_count,
                reading_time_minutes=reading_time,
            )
        except Exception as e:
            logger.error(f"Failed to convert UrlMetadata: {e}")
            return None

    @staticmethod
    def _convert_artifacts(doc_dict: Dict[str, Any]) -> list[ArchiveArtifact]:
        """Convert to ArchiveArtifact models."""
        artifacts = []

        try:
            archives = doc_dict.get("archives", {})

            for archiver_name, archiver_data in archives.items():
                try:
                    # Map Firestore status to PostgreSQL status
                    status = archiver_data.get("status", "pending")
                    success = status == "completed"

                    created_at = archiver_data.get("created_at")
                    if hasattr(created_at, "timestamp"):
                        created_at = datetime.fromtimestamp(created_at.timestamp())
                    elif not isinstance(created_at, datetime):
                        created_at = None

                    updated_at = archiver_data.get("updated_at")
                    if hasattr(updated_at, "timestamp"):
                        updated_at = datetime.fromtimestamp(updated_at.timestamp())
                    elif not isinstance(updated_at, datetime):
                        updated_at = None

                    artifact = ArchiveArtifact(
                        archiver=archiver_name,
                        success=success,
                        exit_code=archiver_data.get("exit_code"),
                        saved_path=archiver_data.get("local_path"),
                        status=status,
                        task_id=None,  # Not tracked in Firestore
                        created_at=created_at,
                        updated_at=updated_at,
                        size_bytes=archiver_data.get("file_size"),
                        uploaded_to_storage=bool(archiver_data.get("gcs_path")),
                        storage_uploads=None,  # Could reconstruct from gcs_path/bucket
                        all_uploads_succeeded=bool(archiver_data.get("gcs_path")),
                        local_file_deleted=False,  # Unknown from Firestore
                        local_file_deleted_at=None,
                        gcs_path=archiver_data.get("gcs_path"),
                        gcs_bucket=archiver_data.get("gcs_bucket"),
                    )

                    artifacts.append(artifact)

                except Exception as e:
                    logger.error(f"Failed to convert artifact {archiver_name}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to convert artifacts: {e}")

        return artifacts

    @staticmethod
    def _convert_summary(doc_dict: Dict[str, Any]) -> Optional[ArticleSummary]:
        """Convert to ArticleSummary model."""
        try:
            summary_dict = doc_dict.get("summary")

            if not summary_dict:
                return None

            summary_text = summary_dict.get("text")
            if not summary_text:
                return None

            # Extract bullet points
            bullet_points = summary_dict.get("bulletPoints")

            created_at = summary_dict.get("createdAt")
            if hasattr(created_at, "timestamp"):
                created_at = datetime.fromtimestamp(created_at.timestamp())
            elif not isinstance(created_at, datetime):
                created_at = None

            return ArticleSummary(
                summary_type="default",
                summary_text=summary_text,
                lede=None,  # Not in Firestore schema
                bullet_points=bullet_points,
                model_name=summary_dict.get("modelName"),
                created_at=created_at,
            )
        except Exception as e:
            logger.error(f"Failed to convert ArticleSummary: {e}")
            return None

    @staticmethod
    def _convert_entities(doc_dict: Dict[str, Any]) -> list[ArticleEntity]:
        """Convert to ArticleEntity models."""
        entities = []

        try:
            entities_list = doc_dict.get("entities", [])

            for entity_dict in entities_list:
                try:
                    entity = ArticleEntity(
                        entity=entity_dict.get("value", ""),
                        entity_type=entity_dict.get("type"),
                        alias=None,  # Not in Firestore schema
                        reason=None,  # Not in Firestore schema
                        confidence=entity_dict.get("confidence"),
                        validated=False,  # Default
                    )

                    entities.append(entity)

                except Exception as e:
                    logger.error(f"Failed to convert entity: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to convert entities: {e}")

        return entities

    @staticmethod
    def _convert_tags(doc_dict: Dict[str, Any]) -> list[ArticleTag]:
        """Convert to ArticleTag models."""
        tags = []

        try:
            tags_list = doc_dict.get("tags", [])

            for tag_dict in tags_list:
                try:
                    tag = ArticleTag(
                        tag=tag_dict.get("tag", ""),
                        source=tag_dict.get("source", "llm"),
                        confidence=tag_dict.get("confidence"),
                        reason=None,  # Not in Firestore schema
                    )

                    tags.append(tag)

                except Exception as e:
                    logger.error(f"Failed to convert tag: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to convert tags: {e}")

        return tags
