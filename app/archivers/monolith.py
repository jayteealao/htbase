from __future__ import annotations

from pathlib import Path
import shlex

from archivers.base import BaseArchiver
from core.config import AppSettings
from core.ht_runner import HTRunner
from models import ArchiveResult
from core.utils import cleanup_chromium_singleton_locks, sanitize_filename


class MonolithArchiver(BaseArchiver):
    name = "monolith"

    def __init__(self, ht_runner: HTRunner, settings: AppSettings):
        super().__init__(settings)
        self.ht_runner = ht_runner
        self.use_chromium = settings.use_chromium

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        # Build output path: <DATA_DIR>/<item_id>/monolith/output.html
        print(f"MonolithArchiver: archiving {url} as {item_id}")
        safe_item = sanitize_filename(item_id)
        out_dir = Path(self.settings.data_dir) / safe_item / self.name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "output.html"


        # Compose monolith command to run via ht
        url_q = shlex.quote(url)
        out_q = shlex.quote(str(out_path))

        user_data_dir = self.settings.resolved_chromium_user_data_dir
        user_data_dir.mkdir(parents=True, exist_ok=True)

        # Clean up stale Chromium singleton locks before launching (if using Chromium)
        if self.use_chromium:
            cleanup_chromium_singleton_locks(user_data_dir)

        user_data_q = shlex.quote(str(user_data_dir))
        profile_raw = getattr(self.settings, "chromium_profile_directory", "")
        profile_name = str(profile_raw).strip() if profile_raw is not None else ""
        profile_flag = (
            f"--profile-directory={shlex.quote(profile_name)} " if profile_name else ""
        )
        # Parse and safely quote any extra monolith flags from config
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
            # Fresh Chromium dump piped directly into monolith (no raw reuse)
            chromium_cmd = (
                f"{self.settings.chromium_bin} --headless=new "
                f"--user-data-dir={user_data_q} "
                f"{profile_flag}"
                "--window-size=1920,1080 "
                "--run-all-compositor-stages-before-draw --virtual-time-budget=9000 "
                "--incognito --dump-dom "
                "--no-sandbox --disable-gpu --disable-software-rasterizer "
                "--disable-dev-shm-usage --disable-setuid-sandbox "
                "--disable-features=NetworkService,NetworkServiceInProcess"
            )
            cmd = (
                f"{chromium_cmd} {url_q} | {mono_cmd} - -I -b {url_q} -o {out_q}; "
                f"echo __DONE__:$?"
            )
        else:
            # Call monolith directly on the URL
            cmd = (
                f"{mono_cmd} {url_q} -o {out_q}; "
                f"echo __DONE__:$?"
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

        # Clean up Chromium singleton locks after archiving (if using Chromium)
        if self.use_chromium:
            cleanup_chromium_singleton_locks(user_data_dir)

        return ArchiveResult(
            success=success,
            exit_code=code,
            saved_path=str(out_path) if success else None,
        )

    def _cleanup_after_timeout(self) -> None:
        # Send SIGINT to the running shell and ensure stray Chromium processes exit.
        self.ht_runner.interrupt()
        cleanup_cmd = (
            "pkill -f 'chromium' >/dev/null 2>&1 || true; "
            "pkill -f 'chrome' >/dev/null 2>&1 || true; "
            "echo __CLEANUP__:0"
        )
        self.ht_runner.send_input(cleanup_cmd + "\r")
        # Best-effort wait; ignore result to avoid hanging indefinitely.
        self.ht_runner.wait_for_done_marker("__CLEANUP__", timeout=15.0)
