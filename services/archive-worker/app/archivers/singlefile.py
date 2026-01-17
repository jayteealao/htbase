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

        # Get binary paths from environment
        singlefile_bin = os.getenv("SINGLEFILE_BIN", "/usr/local/bin/single-file")
        chromium_bin = os.getenv("CHROMIUM_BIN", "/usr/bin/chromium")
        user_data_dir = self.settings.data_dir / "chromium-user-data"
        user_data_dir.mkdir(parents=True, exist_ok=True)

        # Clean up Chromium singleton locks
        self._cleanup_chromium_locks(user_data_dir)

        # Build browser args
        browser_args = [
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=LockProfileCookieDatabase",
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

        if result.timed_out:
            return ArchiveResult(success=False, exit_code=None, saved_path=None)

        # Clean up locks after archiving
        self._cleanup_chromium_locks(user_data_dir)

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
