"""
Command Runner for executing CLI commands.

Provides a safe way to execute shell commands with timeout support.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of a command execution."""

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_seconds: float = 0.0


class CommandRunner:
    """Execute shell commands with timeout and logging."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def execute(
        self,
        command: str,
        timeout: float = 300.0,
        cwd: Path | None = None,
        archived_url_id: int | None = None,
        archiver: str | None = None,
    ) -> CommandResult:
        """
        Execute a shell command.

        Args:
            command: Shell command to execute
            timeout: Timeout in seconds
            cwd: Working directory
            archived_url_id: Optional archived URL ID for logging
            archiver: Optional archiver name for logging

        Returns:
            CommandResult with exit code, output, and timing
        """
        start_time = datetime.utcnow()

        logger.debug(
            "Executing command",
            extra={
                "command": command[:200],
                "timeout": timeout,
                "archiver": archiver,
            },
        )

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )

            duration = (datetime.utcnow() - start_time).total_seconds()

            logger.debug(
                "Command completed",
                extra={
                    "exit_code": result.returncode,
                    "duration": duration,
                    "archiver": archiver,
                },
            )

            return CommandResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                timed_out=False,
                duration_seconds=duration,
            )

        except subprocess.TimeoutExpired:
            duration = (datetime.utcnow() - start_time).total_seconds()

            logger.warning(
                "Command timed out",
                extra={
                    "timeout": timeout,
                    "duration": duration,
                    "archiver": archiver,
                },
            )

            return CommandResult(
                exit_code=None,
                stdout="",
                stderr="Command timed out",
                timed_out=True,
                duration_seconds=duration,
            )

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()

            logger.error(
                f"Command execution failed: {e}",
                exc_info=True,
                extra={
                    "archiver": archiver,
                },
            )

            return CommandResult(
                exit_code=1,
                stdout="",
                stderr=str(e),
                timed_out=False,
                duration_seconds=duration,
            )
