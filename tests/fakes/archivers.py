"""
Fake archivers for testing various scenarios.

Extends the existing DummyArchiver pattern with additional failure modes.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from archivers.base import BaseArchiver, ArchiveResult
from core.utils import sanitize_filename
from core.config import get_settings


class FailingArchiver(BaseArchiver):
    """
    Archiver that always fails with configurable exit code.

    Use for testing error handling and failure scenarios.

    Usage:
        archiver = FailingArchiver(settings, exit_code=1, error_message="Command failed")
        result = archiver.archive(url="https://example.com", item_id="test")
        assert not result.success
        assert result.exit_code == 1
    """

    name = "failing"

    def __init__(self, settings, exit_code: int = 1, error_message: str = "Configured to fail"):
        """
        Initialize failing archiver.

        Args:
            settings: Application settings
            exit_code: Exit code to return (non-zero for failure)
            error_message: Error message to include in result
        """
        super().__init__(settings)
        self._exit_code = exit_code
        self._error_message = error_message

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        """Always fail with configured exit code."""
        # Don't create output file for failures
        return ArchiveResult(
            success=False,
            exit_code=self._exit_code,
            saved_path=None,
            combined_output=[self._error_message]
        )


class TimeoutArchiver(BaseArchiver):
    """
    Archiver that simulates timeout by sleeping.

    Use for testing timeout handling and cleanup.

    Usage:
        archiver = TimeoutArchiver(settings, sleep_seconds=10)
        # Test timeout handling with shorter timeout
        result = archiver.archive(url="https://example.com", item_id="test")
    """

    name = "timeout"

    def __init__(self, settings, sleep_seconds: float = 5.0):
        """
        Initialize timeout archiver.

        Args:
            settings: Application settings
            sleep_seconds: How long to sleep before returning
        """
        super().__init__(settings)
        self._sleep_seconds = sleep_seconds

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        """Sleep to simulate timeout, then fail."""
        time.sleep(self._sleep_seconds)

        return ArchiveResult(
            success=False,
            exit_code=124,  # Standard timeout exit code
            saved_path=None,
            combined_output=["Operation timed out"]
        )


class SlowArchiver(BaseArchiver):
    """
    Archiver that succeeds but takes a long time.

    Use for testing concurrency and task queue behavior.

    Usage:
        archiver = SlowArchiver(settings, sleep_seconds=2.0)
        result = archiver.archive(url="https://example.com", item_id="test")
        # Takes 2 seconds but succeeds
        assert result.success
    """

    name = "slow"

    def __init__(self, settings, sleep_seconds: float = 2.0):
        """
        Initialize slow archiver.

        Args:
            settings: Application settings
            sleep_seconds: How long to sleep before returning success
        """
        super().__init__(settings)
        self._sleep_seconds = sleep_seconds

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        """Sleep to simulate slow operation, then succeed."""
        # Create output file like DummyArchiver
        safe_item = sanitize_filename(item_id)
        out_dir = Path(self.settings.data_dir) / safe_item / self.name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "output.html"

        # Simulate slow operation
        time.sleep(self._sleep_seconds)

        # Write output
        out_path.write_text(
            f"<html><body>Slow archiver saved (after {self._sleep_seconds}s): {url}</body></html>",
            encoding="utf-8"
        )

        return ArchiveResult(
            success=True,
            exit_code=0,
            saved_path=str(out_path),
            combined_output=[f"Completed after {self._sleep_seconds} seconds"]
        )


class IntermittentArchiver(BaseArchiver):
    """
    Archiver that succeeds on Nth try.

    Use for testing retry logic.

    Usage:
        archiver = IntermittentArchiver(settings, fail_count=2)
        # First call fails
        result1 = archiver.archive(url="https://example.com", item_id="test")
        assert not result1.success

        # Second call fails
        result2 = archiver.archive(url="https://example.com", item_id="test")
        assert not result2.success

        # Third call succeeds
        result3 = archiver.archive(url="https://example.com", item_id="test")
        assert result3.success
    """

    name = "intermittent"

    def __init__(self, settings, fail_count: int = 1):
        """
        Initialize intermittent archiver.

        Args:
            settings: Application settings
            fail_count: Number of times to fail before succeeding
        """
        super().__init__(settings)
        self._fail_count = fail_count
        self._attempt_count = 0

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        """Fail N times, then succeed."""
        self._attempt_count += 1

        if self._attempt_count <= self._fail_count:
            return ArchiveResult(
                success=False,
                exit_code=1,
                saved_path=None,
                combined_output=[f"Attempt {self._attempt_count} failed (configured to fail {self._fail_count} times)"]
            )

        # Succeed after N failures
        safe_item = sanitize_filename(item_id)
        out_dir = Path(self.settings.data_dir) / safe_item / self.name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "output.html"
        out_path.write_text(
            f"<html><body>Succeeded on attempt {self._attempt_count}: {url}</body></html>",
            encoding="utf-8"
        )

        return ArchiveResult(
            success=True,
            exit_code=0,
            saved_path=str(out_path),
            combined_output=[f"Succeeded on attempt {self._attempt_count}"]
        )

    def reset(self):
        """Reset attempt counter (useful for test cleanup)."""
        self._attempt_count = 0


class ConfigurableArchiver(BaseArchiver):
    """
    Archiver with fully configurable behavior.

    Use for flexible test scenarios where you need fine control.

    Usage:
        archiver = ConfigurableArchiver(settings)

        # Configure to succeed
        archiver.configure(success=True, exit_code=0, output_content="<html>test</html>")
        result = archiver.archive(url="https://example.com", item_id="test")
        assert result.success

        # Reconfigure to fail
        archiver.configure(success=False, exit_code=1)
        result = archiver.archive(url="https://example.com", item_id="test")
        assert not result.success
    """

    name = "configurable"

    def __init__(self, settings):
        """Initialize configurable archiver."""
        super().__init__(settings)
        self._configured_success = True
        self._configured_exit_code = 0
        self._configured_output_content: Optional[str] = None
        self._configured_combined_output: list[str] = []

    def configure(
        self,
        success: bool = True,
        exit_code: int = 0,
        output_content: Optional[str] = None,
        combined_output: Optional[list[str]] = None
    ):
        """
        Configure archiver behavior.

        Args:
            success: Whether to succeed
            exit_code: Exit code to return
            output_content: Content to write to output file (if success=True)
            combined_output: Combined output lines
        """
        self._configured_success = success
        self._configured_exit_code = exit_code
        self._configured_output_content = output_content
        self._configured_combined_output = combined_output or []

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        """Return configured result."""
        if self._configured_success:
            # Create output file
            safe_item = sanitize_filename(item_id)
            out_dir = Path(self.settings.data_dir) / safe_item / self.name
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / "output.html"

            content = self._configured_output_content or f"<html><body>Configured: {url}</body></html>"
            out_path.write_text(content, encoding="utf-8")

            return ArchiveResult(
                success=True,
                exit_code=self._configured_exit_code,
                saved_path=str(out_path),
                combined_output=self._configured_combined_output or ["Success"]
            )
        else:
            return ArchiveResult(
                success=False,
                exit_code=self._configured_exit_code,
                saved_path=None,
                combined_output=self._configured_combined_output or ["Configured to fail"]
            )


class DummyArchiver(BaseArchiver):
    """
    Simple successful archiver for basic testing.

    Always succeeds and creates a minimal HTML file.
    Use for tests that just need a working archiver without specific behavior.

    Usage:
        archiver = DummyArchiver(settings)
        result = archiver.archive(url="https://example.com", item_id="test")
        assert result.success
    """

    name = "monolith"

    def archive(self, *, url: str, item_id: str) -> ArchiveResult:
        """Create dummy HTML file and return success."""
        safe_item = sanitize_filename(item_id)
        out_dir = Path(self.settings.data_dir) / safe_item / self.name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "output.html"
        out_path.write_text(f"<html><body>Dummy saved: {url}</body></html>", encoding="utf-8")
        return ArchiveResult(success=True, exit_code=0, saved_path=str(out_path))
