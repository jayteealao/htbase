from __future__ import annotations

import logging
from pathlib import Path
import shlex

from archivers.base import BaseArchiver
from core.chromium_utils import ChromiumArchiverMixin, ChromiumCommandBuilder
from core.config import AppSettings
from core.command_runner import CommandRunner
from core.utils import sanitize_filename
from models import ArchiveResult

logger = logging.getLogger(__name__)


class PDFArchiver(BaseArchiver, ChromiumArchiverMixin):
    name = "pdf"
    output_extension = "pdf"

    def __init__(self, command_runner: CommandRunner, settings: AppSettings):
        super().__init__(settings)
        self.command_runner = command_runner
        self.chromium_builder = ChromiumCommandBuilder(settings)

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        out_dir, out_path = self.get_output_path(item_id)

        logger.info(f"Archiving {url}", extra={"item_id": item_id, "archiver": "pdf"})

        # Setup Chromium (create user data dir and clean locks)
        self.setup_chromium()

        # Build Chromium command using builder
        chromium_args = self.chromium_builder.build_pdf_args(url, out_path)
        cmd = " ".join(shlex.quote(arg) for arg in chromium_args)

        # Get archived_url_id for context linking
        from db.session import get_session
        from db.repository import get_archived_url_by_url

        archived_url_id = None
        try:
            with get_session() as db:
                archived_url = get_archived_url_by_url(db, url=url)
                if archived_url:
                    archived_url_id = archived_url.id
        except Exception:
            pass

        result = self.command_runner.execute(
            command=cmd,
            timeout=300.0,
            archived_url_id=archived_url_id,
            archiver=self.name,
        )

        if result.timed_out:
            self.cleanup_after_timeout()
            return ArchiveResult(success=False, exit_code=result.exit_code, saved_path=None)

        # Clean up Chromium singleton locks after archiving
        self.cleanup_chromium()

        return self.create_result(path=out_path, exit_code=result.exit_code)
