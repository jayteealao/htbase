from __future__ import annotations

from pathlib import Path
import shlex

from archivers.base import BaseArchiver
from core.chromium_utils import ChromiumArchiverMixin, ChromiumCommandBuilder
from core.config import AppSettings
from core.ht_runner import HTRunner
from core.utils import sanitize_filename
from models import ArchiveResult


class ScreenshotArchiver(BaseArchiver, ChromiumArchiverMixin):
    name = "screenshot"

    def __init__(self, ht_runner: HTRunner, settings: AppSettings):
        super().__init__(settings)
        self.ht_runner = ht_runner
        self.chromium_builder = ChromiumCommandBuilder(settings)

        # Default viewport to attempt near-full-page captures for common pages
        self.viewport_width = 1920
        # Height large enough for many pages; CLI screenshot doesn't truly do full-page
        self.viewport_height = 8000

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        safe_item = sanitize_filename(item_id)
        out_dir = Path(self.settings.data_dir) / safe_item / self.name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "output.png"

        print(f"ScreenshotArchiver: archiving {url} as {item_id}")

        # Setup Chromium (create user data dir and clean locks)
        self.setup_chromium()

        # Build Chromium command using builder
        chromium_args = self.chromium_builder.build_screenshot_args(
            url,
            out_path,
            viewport_width=self.viewport_width,
            viewport_height=self.viewport_height,
        )
        cmd = " ".join(shlex.quote(arg) for arg in chromium_args) + "; echo __DONE__:$?"

        with self.ht_runner.lock:
            self.ht_runner.send_input(cmd + "\r")
            code = self.ht_runner.wait_for_done_marker("__DONE__", timeout=300.0)
            if code is None:
                self.cleanup_after_timeout()
                return ArchiveResult(success=False, exit_code=None, saved_path=None)

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
