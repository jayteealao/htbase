"""
Monolith Archiver.

Archives web pages using the Monolith CLI tool.
"""

from __future__ import annotations

import logging
import os

from shared.models import ArchiveResult

from app.archivers.base import BaseArchiver

logger = logging.getLogger(__name__)


class MonolithArchiver(BaseArchiver):
    """Archive pages using Monolith CLI."""

    name = "monolith"
    output_extension = "html"

    def archive(self, *, url: str, item_id: str, output_path) -> ArchiveResult:
        """Archive URL using Monolith to provided output_path."""
        from pathlib import Path

        output_path = Path(output_path)

        logger.info(
            f"Archiving {item_id} {url}",
            extra={"item_id": item_id, "archiver": "monolith"},
        )

        # Get binary path from environment
        monolith_bin = os.getenv("MONOLITH_BIN", "/usr/local/bin/monolith")
        monolith_flags = os.getenv("MONOLITH_FLAGS", "")

        # Build command as list (safe from command injection)
        cmd = [monolith_bin, url, "-o", str(output_path)]

        # Add optional flags if present
        if monolith_flags:
            # Use shlex.split to properly handle quoted strings
            import shlex
            cmd.extend(shlex.split(monolith_flags))

        # Execute command
        result = self.command_runner.execute(
            command=cmd,
            timeout=300.0,
            archiver=self.name,
        )

        if result.timed_out:
            return ArchiveResult(success=False, exit_code=None, saved_path=None)

        return self.create_result(path=output_path, exit_code=result.exit_code)
