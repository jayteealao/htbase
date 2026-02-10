"""
PDF Archiver.

Archives web pages as PDF using Chromium headless.
"""

from __future__ import annotations

import logging
import os
import shlex

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

        # Build command
        url_q = shlex.quote(url)
        out_q = shlex.quote(str(out_path))

        cmd = (
            f"{chromium_bin} "
            f"--headless "
            f"--disable-gpu "
            f"--no-sandbox "
            f"--disable-software-rasterizer "
            f"--disable-dev-shm-usage "
            f"--user-data-dir={shlex.quote(str(user_data_dir))} "
            f"--print-to-pdf={out_q} "
            f"--no-margins "
            f"--run-all-compositor-stages-before-draw "
            f"--virtual-time-budget=10000 "
            f"{url_q}"
        )

        # Execute command
        result = self.command_runner.execute(
            command=cmd,
            timeout=120.0,
            archiver=self.name,
        )

        if result.timed_out:
            return ArchiveResult(success=False, exit_code=None, saved_path=None)

        return self.create_result(path=out_path, exit_code=result.exit_code)
