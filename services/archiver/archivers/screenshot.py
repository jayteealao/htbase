from __future__ import annotations

import logging
from pathlib import Path
import shlex
from typing import Optional

from .base import BaseArchiver
from core.chromium_utils import ChromiumArchiverMixin, ChromiumCommandBuilder
from core.config import AppSettings
from core.command_runner import CommandRunner
from core.utils import sanitize_filename
from models import ArchiveResult
from storage.file_storage import FileStorageProvider
from storage.database_storage import DatabaseStorageProvider

logger = logging.getLogger(__name__)


class ScreenshotArchiver(BaseArchiver, ChromiumArchiverMixin):
    name = "screenshot"
    output_extension = "png"

    def __init__(
        self,
        command_runner: CommandRunner,
        settings: AppSettings,
        file_storage_providers: Optional[list[FileStorageProvider]] = None,
        db_storage: Optional[DatabaseStorageProvider] = None
    ):
        super().__init__(settings, file_storage_providers, db_storage)
        self.command_runner = command_runner
        self.chromium_builder = ChromiumCommandBuilder(settings)

        # Default viewport to attempt near-full-page captures for common pages
        self.viewport_width = 1920
        # Height large enough for many pages; CLI screenshot doesn't truly do full-page
        self.viewport_height = 8000

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        out_dir, out_path = self.get_output_path(item_id)

        logger.info(f"Archiving {url}", extra={"item_id": item_id, "archiver": "screenshot"})

        # Setup Chromium (create user data dir and clean locks)
        self.setup_chromium()

        # Build Chromium command using builder
        chromium_args = self.chromium_builder.build_screenshot_args(
            url,
            out_path,
            viewport_width=self.viewport_width,
            viewport_height=self.viewport_height,
        )
        cmd = " ".join(shlex.quote(arg) for arg in chromium_args)

        # Execute command (archived_url_id context should be set by caller if needed)
        result = self.command_runner.execute(
            command=cmd,
            timeout=30.0,
            archived_url_id=None,  # Could be passed from caller
            archiver=self.name,
        )

        if result.timed_out:
            self.cleanup_after_timeout()
            return ArchiveResult(success=False, exit_code=result.exit_code, saved_path=None)

        # Clean up Chromium singleton locks after archiving
        self.cleanup_chromium()

        return self.create_result(path=out_path, exit_code=result.exit_code)
