"""
Archivers module for Archive Worker.

Provides archiver implementations for different archive formats.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from typing import Dict, Any

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../.."))

from shared.config import get_settings

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


def get_archiver(name: str) -> BaseArchiver:
    """
    Get archiver instance by name.

    Args:
        name: Archiver name (singlefile, monolith, readability, pdf, screenshot)

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

    return archiver_class(settings=settings, command_runner=command_runner)


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
