"""Factory for creating and registering archivers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Type, Optional

if TYPE_CHECKING:
    from core.config import AppSettings
    from core.command_runner import CommandRunner
    from archivers.base import BaseArchiver
    from ..storage.file_storage import FileStorageProvider
    from ..storage.database_storage import DatabaseStorageProvider

logger = logging.getLogger(__name__)


class ArchiverFactory:
    """Factory for creating and registering archivers.

    Provides a centralized registry for archiver classes and handles
    their instantiation with proper dependency injection.
    """

    def __init__(
        self,
        settings: "AppSettings",
        command_runner: "CommandRunner",
        file_storage: Optional["FileStorageProvider"] = None,
        db_storage: Optional["DatabaseStorageProvider"] = None
    ):
        """Initialize the factory with required dependencies.

        Args:
            settings: Application settings
            command_runner: CommandRunner instance for command execution
            file_storage: Optional file storage provider (local, GCS, etc.)
            db_storage: Optional database storage provider (PostgreSQL, Firestore, etc.)
        """
        self.settings = settings
        self.command_runner = command_runner
        self.file_storage = file_storage
        self.db_storage = db_storage
        self._registry: Dict[str, Type["BaseArchiver"]] = {}

    def register(self, name: str, archiver_class: Type["BaseArchiver"]) -> None:
        """Register an archiver class.

        Args:
            name: Unique name for the archiver (e.g., "monolith", "pdf")
            archiver_class: The archiver class to register

        Raises:
            ValueError: If an archiver with this name is already registered
        """
        if name in self._registry:
            logger.warning(
                "Overwriting existing archiver registration",
                extra={"archiver_name": name, "class": archiver_class.__name__}
            )
        self._registry[name] = archiver_class
        logger.debug("Registered archiver", extra={"name": name, "class": archiver_class.__name__})

    def create(self, name: str) -> "BaseArchiver":
        """Create an archiver instance by name.

        Args:
            name: Name of the archiver to create

        Returns:
            Instantiated archiver

        Raises:
            ValueError: If no archiver with this name is registered
        """
        archiver_class = self._registry.get(name)
        if not archiver_class:
            raise ValueError(
                f"Unknown archiver: {name}. "
                f"Available archivers: {', '.join(self._registry.keys())}"
            )

        logger.debug(
            "Creating archiver instance",
            extra={
                "name": name,
                "has_file_storage": self.file_storage is not None,
                "has_db_storage": self.db_storage is not None
            }
        )
        return archiver_class(
            command_runner=self.command_runner,
            settings=self.settings,
            file_storage=self.file_storage,
            db_storage=self.db_storage
        )

    def create_all(self) -> Dict[str, "BaseArchiver"]:
        """Create instances of all registered archivers.

        Returns:
            Dictionary mapping archiver names to instances
        """
        logger.info(
            "Creating all registered archivers",
            extra={"archiver_count": len(self._registry)}
        )
        return {name: self.create(name) for name in self._registry}

    def list_registered(self) -> list[str]:
        """Get list of all registered archiver names.

        Returns:
            List of archiver names in registration order
        """
        return list(self._registry.keys())

    def is_registered(self, name: str) -> bool:
        """Check if an archiver is registered.

        Args:
            name: Archiver name to check

        Returns:
            True if registered, False otherwise
        """
        return name in self._registry
