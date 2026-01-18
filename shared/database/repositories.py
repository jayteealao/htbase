"""
Repository pattern implementations for Firestore.

Repositories encapsulate data access logic and provide a clean interface
that can be mocked in tests or swapped with different implementations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from google.cloud import firestore
from google.cloud.firestore import Client, CollectionReference
from google.cloud.firestore_v1.base_query import FieldFilter

# Import domain models for rich domain support
try:
    from shared.domain import Article, Archive, Summary, Metadata
    DOMAIN_MODELS_AVAILABLE = True
except ImportError:
    DOMAIN_MODELS_AVAILABLE = False


class FirestoreClientProtocol(Protocol):
    """Protocol defining Firestore client interface."""

    def collection(self, name: str) -> CollectionReference:
        """Get collection reference."""
        ...


class ArticleRepository:
    """Repository for article data access.

    Encapsulates all Firestore operations for articles, making them
    easily mockable for testing.
    """

    def __init__(
        self,
        firestore_client: FirestoreClientProtocol,
        collection_name: str = "articles"
    ):
        """Initialize repository.

        Args:
            firestore_client: Firestore client instance
            collection_name: Name of the articles collection
        """
        self.client = firestore_client
        self.collection_name = collection_name

    def _collection(self) -> CollectionReference:
        """Get collection reference."""
        return self.client.collection(self.collection_name)

    def create(
        self,
        item_id: str,
        url: str,
        title: Optional[str] = None,
        byline: Optional[str] = None,
        excerpt: Optional[str] = None,
        pocket_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create article document.

        Args:
            item_id: Unique article identifier (used as document ID)
            url: Canonical URL
            title: Article title
            byline: Author/byline
            excerpt: Article excerpt/description
            pocket_data: Optional Pocket integration data

        Returns:
            Created article data dictionary
        """
        collection = self._collection()
        doc_ref = collection.document(item_id)

        article_data = {
            "item_id": item_id,
            "url": url,
            "title": title,
            "byline": byline,
            "excerpt": excerpt,
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "archives": {},
            "metadata": {},
            "pocket": pocket_data or {},
            "summary": {},
            "entities": [],
            "tags": [],
        }

        doc_ref.set(article_data)
        return article_data

    def get(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get article by ID.

        Args:
            item_id: Article identifier

        Returns:
            Article data dictionary or None if not found
        """
        collection = self._collection()
        doc = collection.document(item_id).get()

        if not doc.exists:
            return None

        return doc.to_dict()

    def exists(self, item_id: str) -> bool:
        """Check if article exists.

        Args:
            item_id: Article identifier

        Returns:
            True if article exists, False otherwise
        """
        collection = self._collection()
        doc = collection.document(item_id).get()
        return doc.exists

    def update(
        self,
        item_id: str,
        title: Optional[str] = None,
        byline: Optional[str] = None,
        excerpt: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Update article metadata.

        Args:
            item_id: Article identifier
            title: New title (if provided)
            byline: New byline (if provided)
            excerpt: New excerpt (if provided)
            **kwargs: Additional fields to update
        """
        collection = self._collection()
        doc_ref = collection.document(item_id)

        updates = {"updated_at": firestore.SERVER_TIMESTAMP}

        if title is not None:
            updates["title"] = title
        if byline is not None:
            updates["byline"] = byline
        if excerpt is not None:
            updates["excerpt"] = excerpt

        updates.update(kwargs)

        doc_ref.update(updates)

    def delete(self, item_id: str) -> bool:
        """Delete article document.

        Args:
            item_id: Article identifier

        Returns:
            True if deleted, False if not found
        """
        collection = self._collection()
        doc_ref = collection.document(item_id)

        if not doc_ref.get().exists:
            return False

        doc_ref.delete()
        return True

    def query_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Find article by URL.

        Args:
            url: URL to search for

        Returns:
            Article data dictionary or None if not found
        """
        collection = self._collection()
        query = collection.where(filter=FieldFilter("url", "==", url)).limit(1)

        for doc in query.stream():
            return doc.to_dict()

        return None

    def list(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at",
        descending: bool = True,
    ) -> List[Dict[str, Any]]:
        """List articles with pagination.

        Args:
            limit: Maximum number of articles to return
            offset: Number of articles to skip
            order_by: Field to order by
            descending: Sort descending if True, ascending if False

        Returns:
            List of article data dictionaries
        """
        collection = self._collection()

        direction = (
            firestore.Query.DESCENDING if descending else firestore.Query.ASCENDING
        )
        query = collection.order_by(order_by, direction=direction)

        # Note: Firestore doesn't have efficient OFFSET
        docs = query.limit(limit + offset).stream()

        articles = []
        for i, doc in enumerate(docs):
            if i >= offset:
                articles.append(doc.to_dict())

        return articles

    # Domain model methods (requires shared.domain package)

    def get_article(self, item_id: str) -> Optional["Article"]:
        """Get article as domain model.

        Args:
            item_id: Article identifier

        Returns:
            Article domain object or None if not found

        Requires:
            shared.domain package must be available
        """
        if not DOMAIN_MODELS_AVAILABLE:
            raise ImportError(
                "Domain models not available. Install shared.domain package."
            )

        data = self.get(item_id)
        if not data:
            return None

        return Article.from_firestore(item_id, data)

    def create_article(self, article: "Article") -> Dict[str, Any]:
        """Create article from domain model.

        Args:
            article: Article domain object

        Returns:
            Created article data dictionary

        Requires:
            shared.domain package must be available
        """
        if not DOMAIN_MODELS_AVAILABLE:
            raise ImportError(
                "Domain models not available. Install shared.domain package."
            )

        collection = self._collection()
        doc_ref = collection.document(article.id)

        article_data = article.to_firestore()
        doc_ref.set(article_data)

        return article_data

    def update_article(self, article: "Article") -> None:
        """Update article from domain model.

        Args:
            article: Article domain object with updated fields

        Requires:
            shared.domain package must be available
        """
        if not DOMAIN_MODELS_AVAILABLE:
            raise ImportError(
                "Domain models not available. Install shared.domain package."
            )

        collection = self._collection()
        doc_ref = collection.document(article.id)

        article_data = article.to_firestore()
        doc_ref.update(article_data)


class ArtifactRepository:
    """Repository for artifact data access within articles."""

    def __init__(
        self,
        firestore_client: FirestoreClientProtocol,
        collection_name: str = "articles"
    ):
        """Initialize repository.

        Args:
            firestore_client: Firestore client instance
            collection_name: Name of the articles collection
        """
        self.client = firestore_client
        self.collection_name = collection_name

    def _collection(self) -> CollectionReference:
        """Get collection reference."""
        return self.client.collection(self.collection_name)

    def update(
        self,
        item_id: str,
        archiver: str,
        status: str,
        gcs_path: Optional[str] = None,
        gcs_bucket: Optional[str] = None,
        file_size: Optional[int] = None,
        exit_code: Optional[int] = None,
    ) -> None:
        """Update artifact status.

        Args:
            item_id: Article identifier
            archiver: Archiver name
            status: New status
            gcs_path: GCS path (if successful)
            gcs_bucket: GCS bucket (if successful)
            file_size: File size in bytes (if successful)
            exit_code: Exit code from archiver
        """
        collection = self._collection()
        doc_ref = collection.document(item_id)

        updates = {
            f"archives.{archiver}.status": status,
            f"archives.{archiver}.updated_at": firestore.SERVER_TIMESTAMP,
        }

        if gcs_path is not None:
            updates[f"archives.{archiver}.gcs_path"] = gcs_path
        if gcs_bucket is not None:
            updates[f"archives.{archiver}.gcs_bucket"] = gcs_bucket
        if file_size is not None:
            updates[f"archives.{archiver}.file_size"] = file_size
        if exit_code is not None:
            updates[f"archives.{archiver}.exit_code"] = exit_code

        doc_ref.update(updates)

    def get(self, item_id: str, archiver: str) -> Optional[Dict[str, Any]]:
        """Get specific artifact.

        Args:
            item_id: Article identifier
            archiver: Archiver name

        Returns:
            Artifact data or None if not found
        """
        collection = self._collection()
        doc = collection.document(item_id).get()

        if not doc.exists:
            return None

        data = doc.to_dict()
        archives = data.get("archives", {})
        return archives.get(archiver)
