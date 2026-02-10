"""
Monolith Archiver.

Archives web pages using the Monolith CLI tool.
"""

from __future__ import annotations

import logging
import os
import shlex

from shared.models import ArchiveResult

from app.archivers.base import BaseArchiver

logger = logging.getLogger(__name__)


class MonolithArchiver(BaseArchiver):
    """Archive pages using Monolith CLI."""

    name = "monolith"
    output_extension = "html"

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        """Archive URL using Monolith."""
        out_dir, out_path = self.get_output_path(item_id)

        logger.info(
            f"Archiving {item_id} {url}",
            extra={"item_id": item_id, "archiver": "monolith"},
        )

        # Get binary path from environment
        monolith_bin = os.getenv("MONOLITH_BIN", "/usr/local/bin/monolith")
        monolith_flags = os.getenv("MONOLITH_FLAGS", "")

        # Build command
        url_q = shlex.quote(url)
        out_q = shlex.quote(str(out_path))

        cmd = f"{monolith_bin} {url_q} -o {out_q}"
        if monolith_flags:
            cmd += f" {monolith_flags}"

        # Execute command
        result = self.command_runner.execute(
            command=cmd,
            timeout=300.0,
            archiver=self.name,
        )

        if result.timed_out:
            return ArchiveResult(success=False, exit_code=None, saved_path=None)

        return self.create_result(path=out_path, exit_code=result.exit_code)
