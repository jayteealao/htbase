from __future__ import annotations

from pathlib import Path
import shlex

from archivers.base import BaseArchiver
from core.config import AppSettings
from core.ht_runner import HTRunner
from core.utils import sanitize_filename
from models import ArchiveResult


class SingleFileCLIArchiver(BaseArchiver):
    # Folder name to write under each item_id
    name = "singlefile"

    def __init__(self, ht_runner: HTRunner, settings: AppSettings):
        super().__init__(settings)
        self.ht_runner = ht_runner

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        # Output path is fixed to output.html in <DATA_DIR>/<item_id>/singlefile/
        safe_item = sanitize_filename(item_id)
        out_dir = Path(self.settings.data_dir) / safe_item / self.name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "output.html"

        # Compose command to run via ht
        url_q = shlex.quote(url)
        out_q = shlex.quote(str(out_path))
        # Parse and safely quote any extra flags from config
        extra_flags = self.settings.singlefile_flags.strip() if getattr(self.settings, "singlefile_flags", "") else ""
        if extra_flags:
            try:
                tokens = shlex.split(extra_flags)
            except ValueError:
                tokens = [extra_flags]
            extra_q = " ".join(shlex.quote(t) for t in tokens)
        else:
            extra_q = ""

        sf_cmd = f"{self.settings.singlefile_bin} {url_q} {out_q}"
        if extra_q:
            sf_cmd += f" {extra_q}"
        cmd = f"{sf_cmd}; echo __DONE__:$?"

        with self.ht_runner.lock:
            self.ht_runner.send_input(cmd + "\r")
            code = self.ht_runner.wait_for_done_marker("__DONE__", timeout=300.0)

        if code is None:
            return ArchiveResult(success=False, exit_code=None, saved_path=None)

        success = code == 0 and out_path.exists() and out_path.stat().st_size > 0
        return ArchiveResult(
            success=success,
            exit_code=code,
            saved_path=str(out_path) if success else None,
        )

