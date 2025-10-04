from __future__ import annotations

import logging
from pathlib import Path
import shlex

from archivers.base import BaseArchiver
from core.chromium_utils import ChromiumArchiverMixin, ChromiumCommandBuilder
from core.config import AppSettings
from core.ht_runner import HTRunner
from core.utils import sanitize_filename
from models import ArchiveResult

logger = logging.getLogger(__name__)


class PDFArchiver(BaseArchiver, ChromiumArchiverMixin):
    name = "pdf"
    output_extension = "pdf"

    def __init__(self, ht_runner: HTRunner, settings: AppSettings):
        super().__init__(settings)
        self.ht_runner = ht_runner
        self.chromium_builder = ChromiumCommandBuilder(settings)

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        out_dir, out_path = self.get_output_path(item_id)

        logger.info(f"Archiving {url}", extra={"item_id": item_id, "archiver": "pdf"})

        # Setup Chromium (create user data dir and clean locks)
        self.setup_chromium()

        # Build Chromium command using builder
        chromium_args = self.chromium_builder.build_pdf_args(url, out_path)
        cmd = " ".join(shlex.quote(arg) for arg in chromium_args) + "; echo __DONE__:$?"

        code = self.ht_runner.execute_command(
            cmd,
            timeout=300.0,
            cleanup_on_timeout=self.cleanup_after_timeout,
        )

        if code is None:
            return ArchiveResult(success=False, exit_code=None, saved_path=None)

        success = code == 0 and out_path.exists() and out_path.stat().st_size > 0

        # Clean up Chromium singleton locks after archiving
        self.cleanup_chromium()

        return ArchiveResult(
            success=success,
            exit_code=code,
            saved_path=str(out_path) if success else None,
        )
