from __future__ import annotations

from pathlib import Path
import shlex

from archivers.base import BaseArchiver
from core.chromium_utils import ChromiumArchiverMixin, ChromiumCommandBuilder
from core.config import AppSettings
from core.ht_runner import HTRunner
from models import ArchiveResult
from core.utils import sanitize_filename


class MonolithArchiver(BaseArchiver, ChromiumArchiverMixin):
    name = "monolith"

    def __init__(self, ht_runner: HTRunner, settings: AppSettings):
        super().__init__(settings)
        self.ht_runner = ht_runner
        self.use_chromium = settings.use_chromium
        self.chromium_builder = ChromiumCommandBuilder(settings)

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        # Build output path: <DATA_DIR>/<item_id>/monolith/output.html
        print(f"MonolithArchiver: archiving {url} as {item_id}")
        safe_item = sanitize_filename(item_id)
        out_dir = Path(self.settings.data_dir) / safe_item / self.name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "output.html"


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
            cmd = (
                f"{chromium_cmd} | {mono_cmd} - -I -b {url_q} -o {out_q}; "
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
                self.cleanup_after_timeout()
                return ArchiveResult(success=False, exit_code=None, saved_path=None)

        if code is None:
            return ArchiveResult(success=False, exit_code=None, saved_path=None)

        success = code == 0 and out_path.exists() and out_path.stat().st_size > 0

        # Clean up Chromium singleton locks after archiving (if using Chromium)
        if self.use_chromium:
            self.cleanup_chromium()

        return ArchiveResult(
            success=success,
            exit_code=code,
            saved_path=str(out_path) if success else None,
        )
