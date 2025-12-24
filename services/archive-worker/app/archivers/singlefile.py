"""
SingleFile CLI Archiver.

Archives web pages using the SingleFile CLI tool.
"""

from __future__ import annotations

import json
import logging
import os
import shlex

from shared.models import ArchiveResult

from app.archivers.base import BaseArchiver

logger = logging.getLogger(__name__)


class SingleFileArchiver(BaseArchiver):
    """Archive pages using SingleFile CLI."""

    name = "singlefile"
    output_extension = "html"

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        """Archive URL using SingleFile."""
        out_dir, out_path = self.get_output_path(item_id)

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

        # Build command
        url_q = shlex.quote(url)
        out_q = shlex.quote(str(out_path))

        # Build browser args
        browser_args = [
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=LockProfileCookieDatabase",
        ]
        browser_args_json = json.dumps(browser_args)

        cmd = (
            f"{singlefile_bin} {url_q} {out_q} "
            f"--browser-executable-path={chromium_bin} "
            f"--browser-args={shlex.quote(browser_args_json)}"
        )

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

        return self.create_result(path=out_path, exit_code=result.exit_code)

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
