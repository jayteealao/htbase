from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
import shlex

from archivers.base import BaseArchiver
from core.config import AppSettings
from core.ht_runner import HTRunner
from core.utils import sanitize_filename
from models import ArchiveResult


class PDFArchiver(BaseArchiver):
    name = "pdf"

    def __init__(self, ht_runner: HTRunner, settings: AppSettings):
        super().__init__(settings)
        self.ht_runner = ht_runner

    def archive(self, *, url: str, item_id: str, out_name: Optional[str]) -> ArchiveResult:
        # Determine output filename
        if out_name:
            out_name = sanitize_filename(out_name)
            if not out_name.endswith(".pdf"):
                out_name += ".pdf"
        else:
            out_name = "output.pdf"

        safe_item = sanitize_filename(item_id)
        out_dir = Path(self.settings.data_dir) / safe_item / self.name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / out_name

        url_q = shlex.quote(url)
        out_q = shlex.quote(str(out_path))

        # Compose Chromium headless PDF print command
        cmd = (
            f"{self.settings.chromium_bin} --headless=new "
            f"--print-to-pdf={out_q} --print-to-pdf-no-header "
            "--run-all-compositor-stages-before-draw --virtual-time-budget=9000 "
            "--no-sandbox --disable-gpu --disable-software-rasterizer "
            "--disable-dev-shm-usage --disable-setuid-sandbox "
            "--disable-features=NetworkService,NetworkServiceInProcess "
            f"{url_q}; echo __DONE__:$?"
        )

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
