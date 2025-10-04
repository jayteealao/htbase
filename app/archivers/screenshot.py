from __future__ import annotations

from pathlib import Path
import shlex

from archivers.base import BaseArchiver
from core.config import AppSettings
from core.ht_runner import HTRunner
from core.utils import cleanup_chromium_singleton_locks, sanitize_filename
from models import ArchiveResult


class ScreenshotArchiver(BaseArchiver):
    name = "screenshot"

    def __init__(self, ht_runner: HTRunner, settings: AppSettings):
        super().__init__(settings)
        self.ht_runner = ht_runner

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

        url_q = shlex.quote(url)
        out_q = shlex.quote(str(out_path))
        user_data_dir = self.settings.resolved_chromium_user_data_dir
        user_data_dir.mkdir(parents=True, exist_ok=True)

        # Clean up stale Chromium singleton locks before launching
        cleanup_chromium_singleton_locks(user_data_dir)

        user_data_q = shlex.quote(str(user_data_dir))
        profile_raw = getattr(self.settings, "chromium_profile_directory", "")
        profile_name = str(profile_raw).strip() if profile_raw is not None else ""
        profile_flag = (
            f"--profile-directory={shlex.quote(profile_name)} " if profile_name else ""
        )

        # Compose Chromium headless screenshot command
        # Note: Chromium's --screenshot captures the viewport only; we use a tall viewport
        # and compositor/virtual-time flags to improve render completeness.
        cmd = (
            f"{self.settings.chromium_bin} --headless=new "
            f"--user-data-dir={user_data_q} "
            f"{profile_flag}"
            f"--screenshot={out_q} --window-size={self.viewport_width},{self.viewport_height} "
            "--run-all-compositor-stages-before-draw --virtual-time-budget=9000 "
            "--hide-scrollbars --no-sandbox --disable-gpu --disable-software-rasterizer "
            "--disable-dev-shm-usage --disable-setuid-sandbox "
            "--disable-features=NetworkService,NetworkServiceInProcess "
            f"--remote-debugging-address=0.0.0.0 "
            f"--remote-debugging-port=9222 "
            
            f"{url_q}; echo __DONE__:$?"
        )

        with self.ht_runner.lock:
            self.ht_runner.send_input(cmd + "\r")
            code = self.ht_runner.wait_for_done_marker("__DONE__", timeout=300.0)
            if code is None:
                self._cleanup_after_timeout()
                return ArchiveResult(success=False, exit_code=None, saved_path=None)

        if code is None:
            return ArchiveResult(success=False, exit_code=None, saved_path=None)

        success = code == 0 and out_path.exists() and out_path.stat().st_size > 0

        # Clean up Chromium singleton locks after archiving
        cleanup_chromium_singleton_locks(user_data_dir)

        return ArchiveResult(
            success=success,
            exit_code=code,
            saved_path=str(out_path) if success else None,
        )

    def _cleanup_after_timeout(self) -> None:
        self.ht_runner.interrupt()
        cleanup_cmd = (
            "pkill -f 'chromium' >/dev/null 2>&1 || true; "
            "pkill -f 'chrome' >/dev/null 2>&1 || true; "
            "echo __CLEANUP__:0"
        )
        self.ht_runner.send_input(cleanup_cmd + "\r")
        self.ht_runner.wait_for_done_marker("__CLEANUP__", timeout=15.0)
