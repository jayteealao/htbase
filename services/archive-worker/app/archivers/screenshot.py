"""
Screenshot Archiver.

Archives web pages as screenshots using Chromium headless.
"""

from __future__ import annotations

import logging
import os

from shared.models import ArchiveResult

from app.archivers.base import BaseArchiver

logger = logging.getLogger(__name__)


class ScreenshotArchiver(BaseArchiver):
    """Archive pages as screenshots using Chromium."""

    name = "screenshot"
    output_extension = "png"

    def archive(self, *, url: str, item_id: str, output_path) -> ArchiveResult:
        """Archive URL as screenshot to provided output_path."""
        from pathlib import Path

        output_path = Path(output_path)

        logger.info(
            f"Taking screenshot of {item_id} {url}",
            extra={"item_id": item_id, "archiver": "screenshot"},
        )

        # Get binary path from environment
        chromium_bin = os.getenv("CHROMIUM_BIN", "/usr/bin/chromium")
        user_data_dir = self.settings.data_dir / "chromium-user-data"
        user_data_dir.mkdir(parents=True, exist_ok=True)

        # Get window size from environment
        window_width = os.getenv("SCREENSHOT_WIDTH", "1920")
        window_height = os.getenv("SCREENSHOT_HEIGHT", "1080")

        # Build command as list (safe from command injection)
        cmd = [
            chromium_bin,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-software-rasterizer",
            "--disable-dev-shm-usage",
            f"--user-data-dir={user_data_dir}",
            f"--screenshot={output_path}",
            f"--window-size={window_width},{window_height}",
            "--hide-scrollbars",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=10000",
            url,
        ]

        # Execute command
        result = self.command_runner.execute(
            command=cmd,
            timeout=60.0,
            archiver=self.name,
        )

        if result.timed_out:
            return ArchiveResult(success=False, exit_code=None, saved_path=None)

        return self.create_result(path=output_path, exit_code=result.exit_code)
