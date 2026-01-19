"""
SingleFile CLI Archiver.

Archives web pages using the SingleFile CLI tool.
"""

from __future__ import annotations

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

        # Ensure output file doesn't exist - single-file renames output if file exists
        if output_path.exists():
            output_path.unlink()

        logger.info(
            f"Archiving {item_id} {url}",
            extra={"item_id": item_id, "archiver": "singlefile"},
        )

        # Use wrapper script to work around Python subprocess issues
        # The wrapper automatically includes --browser-executable-path
        singlefile_bin = os.getenv("SINGLEFILE_BIN", "/usr/local/bin/single-file-wrapper")

        # Build command as list (safe from command injection)
        cmd = [
            singlefile_bin,
            url,
            str(output_path),
        ]

        # Execute command
        result = self.command_runner.execute(
            command=cmd,
            timeout=300.0,
            archiver=self.name,
        )

        # Debug: Check file immediately after command
        if output_path.exists():
            size = output_path.stat().st_size
            logger.info(
                f"SingleFile output file: size={size}, exit_code={result.exit_code}",
                extra={"item_id": item_id, "path": str(output_path), "size": size}
            )
        else:
            logger.warning(
                f"SingleFile output file does not exist: {output_path}",
                extra={"item_id": item_id}
            )

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
