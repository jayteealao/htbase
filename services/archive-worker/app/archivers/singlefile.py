"""
SingleFile CLI Archiver.

Archives web pages using the SingleFile CLI tool.
"""

from __future__ import annotations

import json
import logging
import os

from shared.models import ArchiveResult

from app.archivers.base import BaseArchiver

logger = logging.getLogger(__name__)


class SingleFileArchiver(BaseArchiver):
    """Archive pages using SingleFile CLI."""

    name = "singlefile"
    output_extension = "html"

    def archive(self, *, url: str, item_id: str, output_path) -> ArchiveResult:
        """Archive URL using SingleFile to provided output_path."""
        from pathlib import Path

        output_path = Path(output_path)

        logger.info(
            f"Archiving {item_id} {url}",
            extra={"item_id": item_id, "archiver": "singlefile"},
        )

        import tempfile

        # Get binary paths from environment
        singlefile_bin = os.getenv("SINGLEFILE_BIN", "/usr/local/bin/single-file")
        chromium_bin = os.getenv("CHROMIUM_BIN", "/usr/bin/chromium")
        # Use unique temp dir to avoid SingletonLock conflicts
        user_data_dir = Path(tempfile.mkdtemp(prefix="chrome-singlefile-"))

        # Build browser args - keep it minimal to avoid JSON parsing issues
        # Only include essential flags for Docker
        browser_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]
        browser_args_json = json.dumps(browser_args)

        # Build command as list (safe from command injection)
        cmd = [
            singlefile_bin,
            url,
            str(output_path),
            f"--browser-executable-path={chromium_bin}",
            f"--browser-args={browser_args_json}",
        ]

        # Execute command
        result = self.command_runner.execute(
            command=cmd,
            timeout=300.0,
            archiver=self.name,
        )

        # Clean up temp Chrome user data directory
        import shutil
        try:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass

        if result.timed_out:
            return ArchiveResult(success=False, exit_code=None, saved_path=None)

        return self.create_result(path=output_path, exit_code=result.exit_code)

    def _cleanup_chromium_locks(self, user_data_dir):
        """Remove Chromium singleton lock files."""
        import glob
        from pathlib import Path

        if not user_data_dir.exists():
            return

        for lock_file in glob.glob(str(user_data_dir / "Singleton*")):
            try:
                Path(lock_file).unlink(missing_ok=True)
            except (OSError, PermissionError):
                pass
