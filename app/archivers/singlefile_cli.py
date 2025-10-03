from __future__ import annotations

import json
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

        print(f"SingleFileCLIArchiver: archiving {url} as {item_id}")

        # Compose command to run via ht
        url_q = shlex.quote(url)
        out_q = shlex.quote(str(out_path))
        user_data_dir = self.settings.resolved_chromium_user_data_dir
        user_data_dir.mkdir(parents=True, exist_ok=True)
        profile_raw = getattr(self.settings, "chromium_profile_directory", "")
        profile_name = str(profile_raw).strip() if profile_raw is not None else ""
        chromium_bin = getattr(self.settings, "chromium_bin", "")
        chromium_bin = chromium_bin.strip() if isinstance(chromium_bin, str) else str(chromium_bin)

        # Parse and safely quote any extra flags from config
        extra_flags = self.settings.singlefile_flags.strip() if getattr(self.settings, "singlefile_flags", "") else ""
        if extra_flags:
            try:
                tokens = shlex.split(extra_flags)
            except ValueError:
                tokens = [extra_flags]
        else:
            tokens = []

        # Only add browser-executable-path if chromium_bin is set and not already in flags
        if chromium_bin and "--browser-executable-path" not in extra_flags:
            tokens.append(f"--browser-executable-path={chromium_bin}")

        # Build browser args array to pass via --browser-args
        # This allows us to pass --user-data-dir and --profile-directory to Chromium
        # to persist login state across archiving runs
        browser_args = []

        # Check if --browser-args already exists in the flags
        existing_browser_args_idx = None
        for idx, token in enumerate(tokens):
            if token.startswith("--browser-args="):
                existing_browser_args_idx = idx
                # Extract existing args JSON
                try:
                    existing_args_json = token.split("=", 1)[1]
                    browser_args = json.loads(existing_args_json)
                except (json.JSONDecodeError, IndexError):
                    browser_args = []
                break

        # Add user-data-dir if not already present
        user_data_arg = f"--user-data-dir={str(user_data_dir)}"
        if not any(arg.startswith("--user-data-dir=") for arg in browser_args):
            browser_args.append(user_data_arg)

        # Add profile-directory if profile_name is set and not already present
        if profile_name:
            profile_arg = f"--profile-directory={profile_name}"
            if not any(arg.startswith("--profile-directory=") for arg in browser_args):
                browser_args.append(profile_arg)

        # Update or add --browser-args token
        browser_args_json = json.dumps(browser_args)
        browser_args_token = f"--browser-args={browser_args_json}"

        if existing_browser_args_idx is not None:
            tokens[existing_browser_args_idx] = browser_args_token
        else:
            tokens.append(browser_args_token)

        extra_q = " ".join(shlex.quote(t) for t in tokens) if tokens else ""

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

