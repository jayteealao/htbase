from __future__ import annotations

import json
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


class SingleFileCLIArchiver(BaseArchiver, ChromiumArchiverMixin):
    # Folder name to write under each item_id
    name = "singlefile"

    def __init__(self, command_runner: CommandRunner, settings: AppSettings):
        super().__init__(settings)
        self.command_runner = command_runner
        self.chromium_builder = ChromiumCommandBuilder(settings)

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        out_dir, out_path = self.get_output_path(item_id)

        logger.info(f"Archiving {item_id} {url}", extra={"item_id": item_id, "archiver": "singlefile"})

        # Setup Chromium (create user data dir and clean locks)
        self.setup_chromium()

        # Compose command to run via command runner
        url_q = shlex.quote(url)
        out_q = shlex.quote(str(out_path))
        user_data_dir = self.settings.resolved_chromium_user_data_dir

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
                # Extract existing args JSON (handle both quoted and unquoted JSON)
                try:
                    existing_args_json = token.split("=", 1)[1]
                    # Remove any surrounding quotes that might have survived shlex
                    existing_args_json = existing_args_json.strip("'\"")
                    browser_args = json.loads(existing_args_json)
                    if not isinstance(browser_args, list):
                        browser_args = []
                except (json.JSONDecodeError, IndexError, ValueError) as e:
                    logger.warning(f"Failed to parse existing browser-args: {e}")
                    browser_args = []
                break

        # Add user-data-dir if not already present
        # Using default profile (no --profile-directory) to share login state across all archiving runs
        user_data_arg = f"--user-data-dir={str(user_data_dir)}"
        if not any(arg.startswith("--user-data-dir=") for arg in browser_args):
            browser_args.append(user_data_arg)

        # Add critical flags to prevent exit code 21 (profile lock conflicts)
        critical_flags = [
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=LockProfileCookieDatabase",
        ]
        for flag in critical_flags:
            if flag not in browser_args and not any(arg.startswith(flag.split("=")[0]) for arg in browser_args):
                browser_args.append(flag)

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
            command=sf_cmd,
            timeout=300.0,
            archived_url_id=archived_url_id,
            archiver=self.name,
        )

        if result.timed_out:
            return ArchiveResult(success=False, exit_code=result.exit_code, saved_path=None)

        success = result.exit_code == 0 and out_path.exists() and out_path.stat().st_size > 0

        # Clean up Chromium singleton locks after archiving
        self.cleanup_chromium()

        return ArchiveResult(
            success=success,
            exit_code=result.exit_code,
            saved_path=str(out_path) if success else None,
        )

