"""
Fake command runner for testing.

FakeCommandRunner avoids subprocess execution, allowing fast, deterministic tests.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.command_runner import CommandResult

logger = logging.getLogger(__name__)


@dataclass
class CommandInvocation:
    """Record of a command invocation for test assertions."""
    command: str
    timeout: float
    cwd: Optional[Path]
    env: Optional[dict[str, str]]
    archived_url_id: Optional[int]
    archiver: Optional[str]


@dataclass
class ConfiguredResult:
    """Pre-configured result for matching commands."""
    pattern: str  # Regex pattern to match command
    exit_code: int = 0
    stdout_lines: list[str] = field(default_factory=list)
    stderr_lines: list[str] = field(default_factory=list)
    timed_out: bool = False
    duration_seconds: float = 0.1


class FakeCommandRunner:
    """
    Fake command runner that returns pre-configured results.

    Avoids subprocess execution for fast, deterministic tests.

    Features:
    - Returns pre-configured results based on command patterns
    - Records all command invocations for assertions
    - Configurable success/failure scenarios
    - No actual subprocess execution

    Usage:
        runner = FakeCommandRunner()

        # Configure result for monolith commands
        runner.configure_result(
            "monolith",
            exit_code=0,
            stdout_lines=["<html>...</html>"]
        )

        # Execute command
        result = runner.execute("monolith --output test.html https://example.com")

        # Assert execution
        assert result.success
        assert len(runner.invocations) == 1
    """

    def __init__(self, debug: bool = False):
        """
        Initialize fake command runner.

        Args:
            debug: If True, log command executions (for debugging tests)
        """
        self.debug = debug
        self.invocations: list[CommandInvocation] = []
        self._configured_results: list[ConfiguredResult] = []
        self._default_result = ConfiguredResult(
            pattern=".*",  # Matches everything
            exit_code=0,
            stdout_lines=["Fake command output"],
            stderr_lines=[],
            timed_out=False,
            duration_seconds=0.1
        )
        self._next_execution_id = 1

    def configure_result(
        self,
        pattern: str,
        exit_code: int = 0,
        stdout_lines: Optional[list[str]] = None,
        stderr_lines: Optional[list[str]] = None,
        timed_out: bool = False,
        duration_seconds: float = 0.1
    ):
        """
        Configure a result for commands matching a pattern.

        Args:
            pattern: Regex pattern to match command strings
            exit_code: Exit code to return (0 = success)
            stdout_lines: Lines to return in stdout
            stderr_lines: Lines to return in stderr
            timed_out: Whether command should appear timed out
            duration_seconds: Fake duration

        Example:
            # Configure monolith to succeed
            runner.configure_result("monolith", exit_code=0)

            # Configure singlefile to fail
            runner.configure_result("singlefile", exit_code=1, stderr_lines=["Error"])

            # Configure chromium to timeout
            runner.configure_result("chromium", timed_out=True)
        """
        self._configured_results.append(
            ConfiguredResult(
                pattern=pattern,
                exit_code=exit_code,
                stdout_lines=stdout_lines or [],
                stderr_lines=stderr_lines or [],
                timed_out=timed_out,
                duration_seconds=duration_seconds
            )
        )

    def execute(
        self,
        command: str,
        timeout: float = 300.0,
        cwd: Optional[Path] = None,
        env: Optional[dict[str, str]] = None,
        archived_url_id: Optional[int] = None,
        archiver: Optional[str] = None,
    ) -> CommandResult:
        """
        Execute fake command (returns pre-configured result).

        Args:
            command: Command string (not actually executed)
            timeout: Timeout (ignored, for interface compatibility)
            cwd: Working directory (ignored)
            env: Environment (ignored)
            archived_url_id: Context (recorded but not used)
            archiver: Context (recorded but not used)

        Returns:
            CommandResult with pre-configured data
        """
        # Record invocation
        invocation = CommandInvocation(
            command=command,
            timeout=timeout,
            cwd=cwd,
            env=env,
            archived_url_id=archived_url_id,
            archiver=archiver
        )
        self.invocations.append(invocation)

        if self.debug:
            logger.debug(f"FakeCommandRunner executing: {command}")

        # Find matching configured result
        configured = self._find_matching_result(command)

        # Create CommandResult
        execution_id = self._next_execution_id
        self._next_execution_id += 1

        combined_output = []
        for line in configured.stdout_lines:
            combined_output.append(f"[stdout] {line}")
        for line in configured.stderr_lines:
            combined_output.append(f"[stderr] {line}")

        result = CommandResult(
            execution_id=execution_id,
            command=command,
            exit_code=None if configured.timed_out else configured.exit_code,
            timed_out=configured.timed_out,
            duration_seconds=configured.duration_seconds,
            stdout_lines=configured.stdout_lines,
            stderr_lines=configured.stderr_lines,
            combined_output=combined_output
        )

        if self.debug:
            logger.debug(
                f"FakeCommandRunner result: exit_code={result.exit_code}, "
                f"timed_out={result.timed_out}, success={result.success}"
            )

        return result

    def _find_matching_result(self, command: str) -> ConfiguredResult:
        """
        Find the first configured result matching the command.

        Checks configured results in order, returns first match.

        Args:
            command: Command string to match

        Returns:
            ConfiguredResult (default if no match)
        """
        for configured in self._configured_results:
            if re.search(configured.pattern, command):
                return configured

        # No match, return default
        return self._default_result

    # Helper methods for testing

    def clear(self):
        """Clear invocation history."""
        self.invocations.clear()

    def clear_configurations(self):
        """Clear all configured results."""
        self._configured_results.clear()

    def reset(self):
        """Reset to initial state."""
        self.clear()
        self.clear_configurations()
        self._next_execution_id = 1

    def get_invocation_count(self) -> int:
        """Get number of command invocations."""
        return len(self.invocations)

    def was_command_executed(self, pattern: str) -> bool:
        """Check if any command matching pattern was executed."""
        return any(
            re.search(pattern, inv.command)
            for inv in self.invocations
        )

    def get_invocations_matching(self, pattern: str) -> list[CommandInvocation]:
        """Get all invocations matching a pattern."""
        return [
            inv for inv in self.invocations
            if re.search(pattern, inv.command)
        ]

    def get_last_invocation(self) -> Optional[CommandInvocation]:
        """Get the last command invocation."""
        return self.invocations[-1] if self.invocations else None
