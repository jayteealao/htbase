"""
Firestore Database Storage Implementation

Stores article metadata and related data in Google Cloud Firestore.
Optimized for real-time sync with mobile clients.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from google.cloud import firestore
from google.api_core.exceptions import NotFound

from .database_storage import (
    DatabaseStorageProvider,
    ArticleMetadata,
    ArchiveArtifact,
    PocketData,
    ArticleSummary,
    ArticleEntity,
    ArticleTag,
    ArticleRecord,
    ArchiveStatus
)


class FirestoreStorage(DatabaseStorageProvider):
    """
    Firestore database implementation.

    Structure:
    - articles/{item_id}
        - url, title, byline, excerpt, etc.
        - archives (map):
            - {archiver_name}:
                - status, gcs_path, gcs_bucket, etc.
        - pocket (map):
            - itemId, resolvedId, wordCount, etc.
            - images (array)
            - authors (array)
        - metadata (map):
            - textContent, wordCount, etc.
        - summary (map):
            - text, createdAt
        - entities (array)
        - tags (array)
    """

    def __init__(self, project_id: str):
        """
        Initialize Firestore storage.

        Args:
            project_id: GCP project ID
        """
        self.client = firestore.Client(project=project_id)
        self.articles_ref = self.client.collection("articles")

    # ==================== Article Operations ====================

    def create_article(self, metadata: ArticleMetadata) -> bool:
        """Create a new article record."""
        try:
            doc_ref = self.articles_ref.document(metadata.item_id)

            doc_data = {
                "item_id": metadata.item_id,
                "url": metadata.url,
                "title": metadata.title,
                "byline": metadata.byline,
                "excerpt": metadata.excerpt,
                "created_at": metadata.created_at or firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "archives": {},
                "metadata": {}
            }

            if metadata.text_content or metadata.word_count:
                doc_data["metadata"] = {
                    "textContent": metadata.text_content,
                    "wordCount": metadata.word_count
                }

            doc_ref.set(doc_data)
            return True

        except Exception:
            return False

    def get_article(self, item_id: str) -> Optional[ArticleRecord]:
        """Get complete article record by item_id."""
        try:
            doc_ref = self.articles_ref.document(item_id)
            doc = doc_ref.get()

            if not doc.exists:
                return None

            data = doc.to_dict()
            return self._doc_to_article_record(data)

        except Exception:
            return None

    def get_article_by_url(self, url: str) -> Optional[ArticleRecord]:
        """Get article record by URL."""
        try:
            # Query by URL (not as efficient as item_id lookup)
            query = self.articles_ref.where("url", "==", url).limit(1)
            docs = list(query.stream())

            if not docs:
                return None

            data = docs[0].to_dict()
            return self._doc_to_article_record(data)

        except Exception:
            return None

    def update_article_metadata(self, item_id: str, metadata: Dict[str, Any]) -> bool:
        """Update article metadata fields."""
        try:
            doc_ref = self.articles_ref.document(item_id)

            # Add updated_at timestamp
            metadata["updated_at"] = firestore.SERVER_TIMESTAMP

            doc_ref.update(metadata)
            return True

        except NotFound:
            return False
        except Exception:
            return False

    def delete_article(self, item_id: str) -> bool:
        """Delete article and all related data."""
        try:
            doc_ref = self.articles_ref.document(item_id)
            doc_ref.delete()
            return True

        except Exception:
            return False

    def list_articles(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ArticleRecord]:
        """List articles with optional filtering."""
        try:
            query = self.articles_ref

            # Apply filters
            if filters:
                for field, value in filters.items():
                    query = query.where(field, "==", value)

            # Apply offset
            if offset:
                # Firestore doesn't have native offset, use startAfter with cursor
                # For simplicity, we'll fetch and skip (not efficient for large offsets)
                pass

            # Apply limit
            if limit:
                query = query.limit(limit)

            docs = query.stream()
            articles = []

            skip_count = offset or 0
            for doc in docs:
                if skip_count > 0:
                    skip_count -= 1
                    continue

                data = doc.to_dict()
                article = self._doc_to_article_record(data)
                if article:
                    articles.append(article)

            return articles

        except Exception:
            return []

    # ==================== Archive Artifact Operations ====================

    def create_artifact(self, artifact: ArchiveArtifact) -> bool:
        """Create or update archive artifact."""
        try:
            doc_ref = self.articles_ref.document(artifact.item_id)

            artifact_data = {
                "status": artifact.status.value,
                "gcs_path": artifact.gcs_path,
                "gcs_bucket": artifact.gcs_bucket,
                "local_path": artifact.local_path,
                "file_size": artifact.file_size,
                "exit_code": artifact.exit_code,
                "error_message": artifact.error_message,
                "created_at": artifact.created_at or firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            }

            # Update nested archives map
            doc_ref.update({
                f"archives.{artifact.archiver}": artifact_data,
                "updated_at": firestore.SERVER_TIMESTAMP
            })

            return True

        except NotFound:
            # Document doesn't exist, create it first
            doc_ref.set({
                "item_id": artifact.item_id,
                "archives": {
                    artifact.archiver: artifact_data
                },
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            return True

        except Exception:
            return False

    def get_artifacts(self, item_id: str) -> List[ArchiveArtifact]:
        """Get all artifacts for an article."""
        try:
            doc_ref = self.articles_ref.document(item_id)
            doc = doc_ref.get()

            if not doc.exists:
                return []

            data = doc.to_dict()
            archives = data.get("archives", {})

            artifacts = []
            for archiver, archive_data in archives.items():
                artifact = self._dict_to_artifact(item_id, archiver, archive_data)
                if artifact:
                    artifacts.append(artifact)

            return artifacts

        except Exception:
            return []

    def get_artifact(self, item_id: str, archiver: str) -> Optional[ArchiveArtifact]:
        """Get specific artifact by archiver name."""
        try:
            doc_ref = self.articles_ref.document(item_id)
            doc = doc_ref.get()

            if not doc.exists:
                return None

            data = doc.to_dict()
            archives = data.get("archives", {})
            archive_data = archives.get(archiver)

            if not archive_data:
                return None

            return self._dict_to_artifact(item_id, archiver, archive_data)

        except Exception:
            return None

    def update_artifact_status(
        self,
        item_id: str,
        archiver: str,
        status: ArchiveStatus,
        **kwargs
    ) -> bool:
        """Update artifact status and related fields. Creates document if it doesn't exist."""
        try:
            doc_ref = self.articles_ref.document(item_id)

            update_data = {
                f"archives.{archiver}.status": status.value,
                f"archives.{archiver}.updated_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            }

            # Add any additional fields
            for key, value in kwargs.items():
                update_data[f"archives.{archiver}.{key}"] = value

            # Use set with merge=True to create document if it doesn't exist
            doc_ref.set(update_data, merge=True)
            return True

        except Exception:
            return False

    # ==================== Pocket Data Operations ====================

    def create_pocket_data(self, pocket: PocketData) -> bool:
        """Create or update Pocket metadata."""
        try:
            doc_ref = self.articles_ref.document(pocket.item_id)

            pocket_data = {
                "itemId": pocket.item_id,
                "resolvedId": pocket.resolved_id,
                "wordCount": pocket.word_count,
                "timeAdded": pocket.time_added,
                "timeRead": pocket.time_read,
                "favorite": pocket.favorite,
                "status": pocket.status,
                "images": pocket.images or [],
                "authors": pocket.authors or []
            }

            doc_ref.update({
                "pocket": pocket_data,
                "updated_at": firestore.SERVER_TIMESTAMP
            })

            return True

        except NotFound:
            # Document doesn't exist, create it
            doc_ref.set({
                "item_id": pocket.item_id,
                "pocket": pocket_data,
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            return True

        except Exception:
            return False

    def get_pocket_data(self, item_id: str) -> Optional[PocketData]:
        """Get Pocket metadata for an article."""
        try:
            doc_ref = self.articles_ref.document(item_id)
            doc = doc_ref.get()

            if not doc.exists:
                return None

            data = doc.to_dict()
            pocket_data = data.get("pocket")

            if not pocket_data:
                return None

            return PocketData(
                item_id=pocket_data.get("itemId", item_id),
                resolved_id=pocket_data.get("resolvedId"),
                word_count=pocket_data.get("wordCount"),
                time_added=pocket_data.get("timeAdded"),
                time_read=pocket_data.get("timeRead"),
                favorite=pocket_data.get("favorite", False),
                status=pocket_data.get("status"),
                images=pocket_data.get("images"),
                authors=pocket_data.get("authors")
            )

        except Exception:
            return None

    # ==================== AI Content Operations ====================

    def create_summary(self, summary: ArticleSummary) -> bool:
        """Store article summary."""
        try:
            doc_ref = self.articles_ref.document(summary.item_id)

            summary_data = {
                "text": summary.summary,
                "createdAt": summary.created_at or firestore.SERVER_TIMESTAMP
            }

            doc_ref.update({
                "summary": summary_data,
                "updated_at": firestore.SERVER_TIMESTAMP
            })

            return True

        except Exception:
            return False

    def get_summary(self, item_id: str) -> Optional[ArticleSummary]:
        """Get article summary."""
        try:
            doc_ref = self.articles_ref.document(item_id)
            doc = doc_ref.get()

            if not doc.exists:
                return None

            data = doc.to_dict()
            summary_data = data.get("summary")

            if not summary_data:
                return None

            return ArticleSummary(
                item_id=item_id,
                summary=summary_data.get("text", ""),
                created_at=summary_data.get("createdAt")
            )

        except Exception:
            return None

    def create_entities(self, entities: List[ArticleEntity]) -> bool:
        """Store extracted entities (batch)."""
        if not entities:
            return True

        try:
            item_id = entities[0].item_id
            doc_ref = self.articles_ref.document(item_id)

            entities_data = [
                {
                    "type": entity.entity_type,
                    "value": entity.entity_value,
                    "confidence": entity.confidence
                }
                for entity in entities
            ]

            doc_ref.update({
                "entities": entities_data,
                "updated_at": firestore.SERVER_TIMESTAMP
            })

            return True

        except Exception:
            return False

    def get_entities(self, item_id: str) -> List[ArticleEntity]:
        """Get all entities for an article."""
        try:
            doc_ref = self.articles_ref.document(item_id)
            doc = doc_ref.get()

            if not doc.exists:
                return []

            data = doc.to_dict()
            entities_data = data.get("entities", [])

            entities = [
                ArticleEntity(
                    item_id=item_id,
                    entity_type=e.get("type", ""),
                    entity_value=e.get("value", ""),
                    confidence=e.get("confidence")
                )
                for e in entities_data
            ]

            return entities

        except Exception:
            return []

    def create_tags(self, tags: List[ArticleTag]) -> bool:
        """Store article tags (batch)."""
        if not tags:
            return True

        try:
            item_id = tags[0].item_id
            doc_ref = self.articles_ref.document(item_id)

            tags_data = [
                {
                    "tag": tag.tag,
                    "confidence": tag.confidence
                }
                for tag in tags
            ]

            doc_ref.update({
                "tags": tags_data,
                "updated_at": firestore.SERVER_TIMESTAMP
            })

            return True

        except Exception:
            return False

    def get_tags(self, item_id: str) -> List[ArticleTag]:
        """Get all tags for an article."""
        try:
            doc_ref = self.articles_ref.document(item_id)
            doc = doc_ref.get()

            if not doc.exists:
                return []

            data = doc.to_dict()
            tags_data = data.get("tags", [])

            tags = [
                ArticleTag(
                    item_id=item_id,
                    tag=t.get("tag", ""),
                    confidence=t.get("confidence")
                )
                for t in tags_data
            ]

            return tags

        except Exception:
            return []

    # ==================== Batch Operations ====================

    def batch_create_articles(self, articles: List[ArticleMetadata]) -> int:
        """Create multiple articles in batch."""
        batch = self.client.batch()
        count = 0

        try:
            for metadata in articles:
                doc_ref = self.articles_ref.document(metadata.item_id)

                doc_data = {
                    "item_id": metadata.item_id,
                    "url": metadata.url,
                    "title": metadata.title,
                    "byline": metadata.byline,
                    "excerpt": metadata.excerpt,
                    "created_at": metadata.created_at or firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "archives": {},
                    "metadata": {}
                }

                if metadata.text_content or metadata.word_count:
                    doc_data["metadata"] = {
                        "textContent": metadata.text_content,
                        "wordCount": metadata.word_count
                    }

                batch.set(doc_ref, doc_data)
                count += 1

                # Firestore batch limit is 500 operations
                if count % 500 == 0:
                    batch.commit()
                    batch = self.client.batch()

            # Commit remaining
            if count % 500 != 0:
                batch.commit()

            return count

        except Exception:
            return count

    def batch_update_artifacts(self, artifacts: List[ArchiveArtifact]) -> int:
        """Update multiple artifacts in batch."""
        batch = self.client.batch()
        count = 0

        try:
            for artifact in artifacts:
                doc_ref = self.articles_ref.document(artifact.item_id)

                artifact_data = {
                    "status": artifact.status.value,
                    "gcs_path": artifact.gcs_path,
                    "gcs_bucket": artifact.gcs_bucket,
                    "local_path": artifact.local_path,
                    "file_size": artifact.file_size,
                    "exit_code": artifact.exit_code,
                    "error_message": artifact.error_message,
                    "updated_at": firestore.SERVER_TIMESTAMP
                }

                batch.update(doc_ref, {
                    f"archives.{artifact.archiver}": artifact_data,
                    "updated_at": firestore.SERVER_TIMESTAMP
                })
                count += 1

                # Firestore batch limit
                if count % 500 == 0:
                    batch.commit()
                    batch = self.client.batch()

            # Commit remaining
            if count % 500 != 0:
                batch.commit()

            return count

        except Exception:
            return count

    # ==================== Query Operations ====================

    def count_articles(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count articles matching filters."""
        try:
            query = self.articles_ref

            if filters:
                for field, value in filters.items():
                    query = query.where(field, "==", value)

            # Firestore doesn't have a direct count; must fetch all
            docs = list(query.stream())
            return len(docs)

        except Exception:
            return 0

    def search_articles(
        self,
        query: str,
        limit: Optional[int] = None
    ) -> List[ArticleRecord]:
        """
        Full-text search articles.

        Note: Firestore doesn't have native full-text search.
        This is a basic implementation that searches title and excerpt.
        For production, use Algolia, Elasticsearch, or Cloud Search.
        """
        try:
            # Basic search on title (case-sensitive prefix match)
            query_ref = self.articles_ref.where("title", ">=", query).where("title", "<=", query + "\uf8ff")

            if limit:
                query_ref = query_ref.limit(limit)

            docs = query_ref.stream()
            articles = []

            for doc in docs:
                data = doc.to_dict()
                article = self._doc_to_article_record(data)
                if article:
                    articles.append(article)

            return articles

        except Exception:
            return []

    # ==================== Provider Info ====================

    @property
    def provider_name(self) -> str:
        """Provider name."""
        return "firestore"

    @property
    def supports_transactions(self) -> bool:
        """Supports ACID transactions."""
        return True

    @property
    def supports_full_text_search(self) -> bool:
        """Does not support native full-text search."""
        return False

    # ==================== Helper Methods ====================

    def _doc_to_article_record(self, data: Dict[str, Any]) -> Optional[ArticleRecord]:
        """Convert Firestore document to ArticleRecord."""
        try:
            # Extract metadata
            metadata_data = data.get("metadata", {})
            metadata = ArticleMetadata(
                item_id=data.get("item_id", ""),
                url=data.get("url", ""),
                title=data.get("title"),
                byline=data.get("byline"),
                excerpt=data.get("excerpt"),
                text_content=metadata_data.get("textContent"),
                word_count=metadata_data.get("wordCount"),
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at")
            )

            # Extract archives
            archives_data = data.get("archives", {})
            archives = [
                self._dict_to_artifact(metadata.item_id, archiver, archive_data)
                for archiver, archive_data in archives_data.items()
            ]
            archives = [a for a in archives if a is not None]

            # Extract Pocket data
            pocket = None
            pocket_data = data.get("pocket")
            if pocket_data:
                pocket = PocketData(
                    item_id=pocket_data.get("itemId", metadata.item_id),
                    resolved_id=pocket_data.get("resolvedId"),
                    word_count=pocket_data.get("wordCount"),
                    time_added=pocket_data.get("timeAdded"),
                    time_read=pocket_data.get("timeRead"),
                    favorite=pocket_data.get("favorite", False),
                    status=pocket_data.get("status"),
                    images=pocket_data.get("images"),
                    authors=pocket_data.get("authors")
                )

            # Extract summary
            summary = None
            summary_data = data.get("summary")
            if summary_data:
                summary = ArticleSummary(
                    item_id=metadata.item_id,
                    summary=summary_data.get("text", ""),
                    created_at=summary_data.get("createdAt")
                )

            # Extract entities
            entities = []
            entities_data = data.get("entities", [])
            for e in entities_data:
                entities.append(ArticleEntity(
                    item_id=metadata.item_id,
                    entity_type=e.get("type", ""),
                    entity_value=e.get("value", ""),
                    confidence=e.get("confidence")
                ))

            # Extract tags
            tags = []
            tags_data = data.get("tags", [])
            for t in tags_data:
                tags.append(ArticleTag(
                    item_id=metadata.item_id,
                    tag=t.get("tag", ""),
                    confidence=t.get("confidence")
                ))

            return ArticleRecord(
                metadata=metadata,
                archives=archives,
                pocket=pocket,
                summary=summary,
                entities=entities or None,
                tags=tags or None
            )

        except Exception:
            return None

    def _dict_to_artifact(
        self,
        item_id: str,
        archiver: str,
        data: Dict[str, Any]
    ) -> Optional[ArchiveArtifact]:
        """Convert dictionary to ArchiveArtifact."""
        try:
            status_str = data.get("status", "pending")
            status = ArchiveStatus(status_str)

            return ArchiveArtifact(
                item_id=item_id,
                archiver=archiver,
                status=status,
                gcs_path=data.get("gcs_path"),
                gcs_bucket=data.get("gcs_bucket"),
                local_path=data.get("local_path"),
                file_size=data.get("file_size"),
                exit_code=data.get("exit_code"),
                error_message=data.get("error_message"),
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at")
            )

        except Exception:
            return None
