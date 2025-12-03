from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
import shlex

from archivers.base import BaseArchiver
from core.chromium_utils import ChromiumArchiverMixin, ChromiumCommandBuilder
from core.config import AppSettings
from core.command_runner import CommandRunner
from models import ArchiveResult
from core.utils import sanitize_filename
from ..storage.file_storage import FileStorageProvider
from ..storage.database_storage import DatabaseStorageProvider

logger = logging.getLogger(__name__)


class MonolithArchiver(BaseArchiver, ChromiumArchiverMixin):
    name = "monolith"

    def __init__(
        self,
        command_runner: CommandRunner,
        settings: AppSettings,
        file_storage: Optional[FileStorageProvider] = None,
        db_storage: Optional[DatabaseStorageProvider] = None
    ):
        super().__init__(settings, file_storage, db_storage)
        self.command_runner = command_runner
        self.use_chromium = settings.chromium.enabled
        self.chromium_builder = ChromiumCommandBuilder(settings)

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        logger.info(f"Archiving {url}", extra={"item_id": item_id, "archiver": "monolith"})
        out_dir, out_path = self.get_output_path(item_id)


        # Setup Chromium if needed
        if self.use_chromium:
            self.setup_chromium()

        # Parse and safely quote any extra monolith flags from config
        url_q = shlex.quote(url)
        out_q = shlex.quote(str(out_path))

        extra_flags = self.settings.monolith_flags.strip()
        if extra_flags:
            try:
                tokens = shlex.split(extra_flags)
            except ValueError:
                tokens = [extra_flags]
            extra_q = " ".join(shlex.quote(t) for t in tokens)
        else:
            extra_q = ""

        mono_cmd = f"{self.settings.monolith_bin}"
        if extra_q:
            mono_cmd += f" {extra_q}"

        if self.use_chromium:
            # Build Chromium command for DOM dumping
            chromium_args = self.chromium_builder.build_dump_dom_for_monolith(url, incognito=True)
            chromium_cmd = " ".join(shlex.quote(arg) for arg in chromium_args)

            # Pipe Chromium output to monolith
            cmd = f"{chromium_cmd} | {mono_cmd} - -I -b {url_q} -o {out_q}"
        else:
            # Call monolith directly on the URL
            cmd = f"{mono_cmd} {url_q} -o {out_q}"

        # Execute command (archived_url_id context should be set by caller if needed)
        result = self.command_runner.execute(
            command=cmd,
            timeout=300.0,
            archived_url_id=None,  # Could be passed from caller
            archiver=self.name,
        )

        if result.timed_out:
            self.cleanup_after_timeout()
            return ArchiveResult(success=False, exit_code=result.exit_code, saved_path=None)

        # Clean up Chromium singleton locks after archiving (if using Chromium)
        if self.use_chromium:
            self.cleanup_chromium()

        return self.create_result(path=out_path, exit_code=result.exit_code)
