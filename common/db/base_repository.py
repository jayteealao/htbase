"""Base repository with generic CRUD operations.

Provides reusable query patterns and session management for all repositories.
Follows the Repository Pattern with generic type support.
"""

from pathlib import Path
from typing import Generic, List, Optional, Sequence, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from .session import get_session

# Generic type for ORM models
ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    """Base repository providing common CRUD operations.

    Subclasses should set the model_class attribute to their ORM model.

    Example:
        class ArticleRepository(BaseRepository[ArchiveArtifact]):
            model_class = ArchiveArtifact
    """

    model_class: Type[ModelT]

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize repository with optional database path.

        Args:
            db_path: Path to database file. If None, uses default from settings.
        """
        self.db_path = db_path

    def _get_session(self):
        """Get a database session context manager."""
        return get_session(self.db_path)

    def get_by_id(self, id: int) -> Optional[ModelT]:
        """Get a record by its primary key ID.

        Args:
            id: Primary key value

        Returns:
            Model instance or None if not found
        """
        with self._get_session() as session:
            return session.get(self.model_class, id)

    def get_all(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> List[ModelT]:
        """Get all records with optional pagination.

        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip

        Returns:
            List of model instances
        """
        with self._get_session() as session:
            stmt = select(self.model_class)
            if limit is not None:
                stmt = stmt.limit(limit)
            if offset > 0:
                stmt = stmt.offset(offset)
            return list(session.execute(stmt).scalars().all())

    def get_by_ids(self, ids: Sequence[int]) -> List[ModelT]:
        """Get multiple records by their IDs.

        Args:
            ids: Sequence of primary key values

        Returns:
            List of model instances (may be fewer than requested if some don't exist)
        """
        if not ids:
            return []
        with self._get_session() as session:
            stmt = select(self.model_class).where(
                self.model_class.id.in_(ids)  # type: ignore[attr-defined]
            )
            return list(session.execute(stmt).scalars().all())

    def create(self, **kwargs) -> ModelT:
        """Create a new record.

        Args:
            **kwargs: Field values for the new record

        Returns:
            Created model instance with ID populated
        """
        with self._get_session() as session:
            instance = self.model_class(**kwargs)  # type: ignore[call-arg]
            session.add(instance)
            session.flush()
            session.refresh(instance)
            return instance

    def update(self, id: int, **kwargs) -> Optional[ModelT]:
        """Update an existing record.

        Args:
            id: Primary key of record to update
            **kwargs: Fields to update

        Returns:
            Updated model instance or None if not found
        """
        with self._get_session() as session:
            instance = session.get(self.model_class, id)
            if instance is None:
                return None
            for key, value in kwargs.items():
                setattr(instance, key, value)
            session.flush()
            session.refresh(instance)
            return instance

    def delete(self, id: int) -> bool:
        """Delete a record by ID.

        Args:
            id: Primary key of record to delete

        Returns:
            True if deleted, False if not found
        """
        with self._get_session() as session:
            instance = session.get(self.model_class, id)
            if instance is None:
                return False
            session.delete(instance)
            session.flush()
            return True

    def delete_many(self, ids: Sequence[int]) -> int:
        """Delete multiple records by ID.

        Args:
            ids: Sequence of primary keys to delete

        Returns:
            Number of records deleted
        """
        if not ids:
            return 0
        with self._get_session() as session:
            count = 0
            for id in ids:
                instance = session.get(self.model_class, id)
                if instance is not None:
                    session.delete(instance)
                    count += 1
            session.flush()
            return count

    def exists(self, id: int) -> bool:
        """Check if a record exists.

        Args:
            id: Primary key to check

        Returns:
            True if record exists, False otherwise
        """
        with self._get_session() as session:
            return session.get(self.model_class, id) is not None

    def count(self) -> int:
        """Count total records.

        Returns:
            Total number of records
        """
        with self._get_session() as session:
            stmt = select(self.model_class)
            return len(list(session.execute(stmt).scalars().all()))

    # Session-aware methods for transaction composition

    def _get_by_id_session(self, session: Session, id: int) -> Optional[ModelT]:
        """Get by ID within an existing session."""
        return session.get(self.model_class, id)

    def _create_session(self, session: Session, **kwargs) -> ModelT:
        """Create within an existing session."""
        instance = self.model_class(**kwargs)  # type: ignore[call-arg]
        session.add(instance)
        session.flush()
        return instance

    def _update_session(
        self, session: Session, id: int, **kwargs
    ) -> Optional[ModelT]:
        """Update within an existing session."""
        instance = session.get(self.model_class, id)
        if instance is None:
            return None
        for key, value in kwargs.items():
            setattr(instance, key, value)
        session.flush()
        return instance
