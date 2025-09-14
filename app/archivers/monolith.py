from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
import shlex

from archivers.base import BaseArchiver
from core.config import AppSettings
from core.ht_runner import HTRunner
from models import ArchiveResult
from core.utils import sanitize_filename


class MonolithArchiver(BaseArchiver):
    name = "monolith"

    def __init__(self, ht_runner: HTRunner, settings: AppSettings):
        super().__init__(settings)
        self.ht_runner = ht_runner
        self.use_chromium = settings.use_chromium

    def archive(self, *, url: str, item_id: str, out_name: Optional[str]) -> ArchiveResult:
        # Determine output filename
        if out_name:
            out_name = sanitize_filename(out_name)
            if not out_name.endswith(".html"):
                out_name += ".html"
        else:
            ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
            host = url.replace("http://", "").replace("https://", "").split("/")[0]
            out_name = sanitize_filename(f"{host}-{ts}.html")

        # Build output path: <DATA_DIR>/<item_id>/monolith/<file>
        safe_item = sanitize_filename(item_id)
        out_dir = Path(self.settings.data_dir) / safe_item / self.name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / out_name

        # Compose monolith command to run via ht
        url_q = shlex.quote(url)
        out_q = shlex.quote(str(out_path))
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
            return ArchiveResult(success=False, exit_code=None, saved_path=None)

        success = code == 0 and out_path.exists() and out_path.stat().st_size > 0
        return ArchiveResult(
            success=success,
            exit_code=code,
            saved_path=str(out_path) if success else None,
        )
