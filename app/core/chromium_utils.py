"""Utilities for working with Chromium across archivers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from core.utils import cleanup_chromium_singleton_locks

if TYPE_CHECKING:
    from core.config import AppSettings


class ChromiumCommandBuilder:
    """Builder for constructing Chromium command arguments."""

    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.user_data_dir = settings.resolved_chromium_user_data_dir

    def build_base_args(self, *, incognito: bool = False) -> List[str]:
        """Build common base arguments for all Chromium invocations.

        Args:
            incognito: Whether to add --incognito flag

        Returns:
            List of base Chromium arguments
        """
        args = [
            self.settings.chromium_bin,
            "--headless=new",
            f"--user-data-dir={self.user_data_dir}",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            "--disable-features=NetworkService,NetworkServiceInProcess",
        ]

        # Add profile directory if configured
        profile_dir = getattr(self.settings, "chromium_profile_directory", "")
        if profile_dir and str(profile_dir).strip():
            args.append(f"--profile-directory={profile_dir}")

        if incognito:
            args.append("--incognito")

        return args

    def build_dump_dom_args(self, url: str) -> List[str]:
        """Build arguments for DOM dumping (used by ReadabilityArchiver).

        Args:
            url: URL to dump DOM from

        Returns:
            Complete argument list for Chromium DOM dump
        """
        return self.build_base_args() + [
            "--dump-dom",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=9000",
            "--hide-scrollbars",
            url,
        ]

    def build_screenshot_args(
        self,
        url: str,
        output_path: Path,
        viewport_width: int = 1920,
        viewport_height: int = 8000,
    ) -> List[str]:
        """Build arguments for taking screenshots.

        Args:
            url: URL to screenshot
            output_path: Path to save screenshot
            viewport_width: Viewport width in pixels
            viewport_height: Viewport height in pixels

        Returns:
            Complete argument list for Chromium screenshot
        """
        return self.build_base_args() + [
            f"--screenshot={output_path}",
            f"--window-size={viewport_width},{viewport_height}",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=9000",
            "--hide-scrollbars",
            "--remote-debugging-address=0.0.0.0",
            "--remote-debugging-port=9222",
            url,
        ]

    def build_pdf_args(self, url: str, output_path: Path) -> List[str]:
        """Build arguments for PDF generation.

        Args:
            url: URL to convert to PDF
            output_path: Path to save PDF

        Returns:
            Complete argument list for Chromium PDF generation
        """
        return self.build_base_args() + [
            f"--print-to-pdf={output_path}",
            "--print-to-pdf-no-header",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=9000",
            url,
        ]

    def build_dump_dom_for_monolith(self, url: str, incognito: bool = True) -> List[str]:
        """Build arguments for DOM dumping to pipe to monolith.

        Args:
            url: URL to dump DOM from
            incognito: Whether to use incognito mode

        Returns:
            Complete argument list for Chromium DOM dump for monolith
        """
        return self.build_base_args(incognito=incognito) + [
            "--window-size=1920,1080",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=9000",
            "--dump-dom",
            url,
        ]


class ChromiumArchiverMixin:
    """Mixin providing common Chromium setup/cleanup functionality for archivers.

    Classes using this mixin must have:
    - self.settings: AppSettings
    - self.ht_runner: HTRunner (optional, only needed for cleanup_after_timeout)
    """

    def setup_chromium(self) -> None:
        """Prepare Chromium user data directory and clean singleton locks."""
        user_data_dir = self.settings.resolved_chromium_user_data_dir
        user_data_dir.mkdir(parents=True, exist_ok=True)
        cleanup_chromium_singleton_locks(user_data_dir)

    def cleanup_chromium(self) -> None:
        """Clean up Chromium singleton locks after execution."""
        cleanup_chromium_singleton_locks(self.settings.resolved_chromium_user_data_dir)

    def cleanup_after_timeout(self) -> None:
        """Standard timeout cleanup for Chromium archivers.

        Interrupts the running shell and kills any stray Chromium processes.
        Requires self.ht_runner to be set.
        """
        if not hasattr(self, "ht_runner"):
            return

        self.ht_runner.interrupt()
        cleanup_cmd = (
            "pkill -f 'chromium' >/dev/null 2>&1 || true; "
            "pkill -f 'chrome' >/dev/null 2>&1 || true; "
            "echo __CLEANUP__:0"
        )
        self.ht_runner.send_input(cleanup_cmd + "\r")
        self.ht_runner.wait_for_done_marker("__CLEANUP__", timeout=15.0)
