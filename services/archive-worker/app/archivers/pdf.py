"""
PDF Archiver.

Archives web pages as PDF using Chromium headless.
"""

from __future__ import annotations

import logging
import os

from shared.models import ArchiveResult

from app.archivers.base import BaseArchiver

logger = logging.getLogger(__name__)


class PDFArchiver(BaseArchiver):
    """Archive pages as PDF using Chromium."""

    name = "pdf"
    output_extension = "pdf"

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        """Archive URL as PDF."""
        out_dir, out_path = self.get_output_path(item_id)

        logger.info(
            f"Creating PDF of {item_id} {url}",
            extra={"item_id": item_id, "archiver": "pdf"},
        )

        # Get binary path from environment
        chromium_bin = os.getenv("CHROMIUM_BIN", "/usr/bin/chromium")
        user_data_dir = self.settings.data_dir / "chromium-user-data"
        user_data_dir.mkdir(parents=True, exist_ok=True)

        # Build command as list (safe from command injection)
        cmd = [
            chromium_bin,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-software-rasterizer",
            "--disable-dev-shm-usage",
            f"--user-data-dir={user_data_dir}",
            f"--print-to-pdf={out_path}",
            "--no-margins",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=10000",
            url,
        ]

        # Execute command
        result = self.command_runner.execute(
            command=cmd,
            timeout=120.0,
            archiver=self.name,
        )

        if result.timed_out:
            return ArchiveResult(success=False, exit_code=None, saved_path=None)

        return self.create_result(path=out_path, exit_code=result.exit_code)
