"""
Archivers module for Archive Worker.

Provides archiver implementations for different archive formats.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from typing import Dict, Any, List, Optional

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../.."))

from shared.config import get_settings
from shared.storage.file_storage import FileStorageProvider
from shared.storage.database_storage import DatabaseStorageProvider

from app.archivers.base import BaseArchiver
from app.archivers.singlefile import SingleFileArchiver
from app.archivers.monolith import MonolithArchiver
from app.archivers.readability import ReadabilityArchiver
from app.archivers.pdf import PDFArchiver
from app.archivers.screenshot import ScreenshotArchiver


@lru_cache
def get_command_runner():
    """Get cached command runner instance."""
    from app.archivers.command_runner import CommandRunner

    settings = get_settings()
    return CommandRunner(data_dir=settings.data_dir)


@lru_cache
def get_storage_providers() -> List[FileStorageProvider]:
    """Get configured file storage providers."""
    settings = get_settings()
    providers = []

    # Add GCS provider if configured
    if settings.storage_backend == "gcs" and settings.gcs.is_configured():
        try:
            from shared.storage.gcs_file_storage import GCSFileStorage
            providers.append(GCSFileStorage(
                bucket_name=settings.gcs.bucket,
                project_id=settings.gcs.project_id,
            ))
        except Exception:
            pass

    return providers


@lru_cache
def get_database_storage() -> Optional[DatabaseStorageProvider]:
    """Get configured database storage provider."""
    settings = get_settings()

    # Configure Firestore if available
    if settings.firestore.is_configured():
        try:
            from shared.storage.firestore_storage import FirestoreStorage
            return FirestoreStorage(project_id=settings.firestore.project_id)
        except Exception:
            pass

    return None


def get_archiver(name: str, with_storage: bool = True) -> BaseArchiver:
    """
    Get archiver instance by name.

    Args:
        name: Archiver name (singlefile, monolith, readability, pdf, screenshot)
        with_storage: Include storage providers for cloud uploads

    Returns:
        Archiver instance

    Raises:
        ValueError: If archiver name is unknown
    """
    settings = get_settings()
    command_runner = get_command_runner()

    archivers: Dict[str, type] = {
        "singlefile": SingleFileArchiver,
        "monolith": MonolithArchiver,
        "readability": ReadabilityArchiver,
        "pdf": PDFArchiver,
        "screenshot": ScreenshotArchiver,
    }

    archiver_class = archivers.get(name)
    if not archiver_class:
        raise ValueError(f"Unknown archiver: {name}. Available: {list(archivers.keys())}")

    # Get storage providers if requested
    file_providers = get_storage_providers() if with_storage else []
    db_storage = get_database_storage() if with_storage else None

    return archiver_class(
        settings=settings,
        command_runner=command_runner,
        file_storage_providers=file_providers,
        db_storage=db_storage,
    )


def get_all_archivers() -> Dict[str, BaseArchiver]:
    """Get all archiver instances."""
    return {
        name: get_archiver(name)
        for name in ["singlefile", "monolith", "readability", "pdf", "screenshot"]
    }


__all__ = [
    "BaseArchiver",
    "SingleFileArchiver",
    "MonolithArchiver",
    "ReadabilityArchiver",
    "PDFArchiver",
    "ScreenshotArchiver",
    "get_archiver",
    "get_all_archivers",
]
