"""Thread-safe command runner with full observability and replay capabilities."""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of a command execution with full context."""
    execution_id: int
    command: str
    exit_code: Optional[int]
    timed_out: bool
    duration_seconds: float
    stdout_lines: list[str]
    stderr_lines: list[str]
    combined_output: list[str]

    @property
    def success(self) -> bool:
        """Command succeeded if it completed with exit code 0."""
        return self.exit_code == 0 and not self.timed_out


class CommandRunner:
    """
    Thread-safe command runner that logs all execution details to database.

    Features:
    - Thread-safe execution via lock
    - Stores all stdin/stdout/stderr to database with timestamps
    - Optional debug logging to console
    - Replay functionality to review past executions
    - Proper timeout handling with cleanup
    - Links executions to archiving context
    """

    def __init__(self, debug: bool = False):
        """
        Initialize CommandRunner.

        Args:
            debug: If True, log all stdin/stdout/stderr to console at DEBUG level
        """
        self.lock = threading.Lock()
        self.debug = debug

    def _kill_process_tree(self, proc: subprocess.Popen, execution_id: int, is_windows: bool) -> None:
        """
        Kill the entire process tree to ensure all child processes are terminated.

        Args:
            proc: The subprocess.Popen object to kill
            execution_id: ID for logging context
            is_windows: Whether running on Windows
        """
        try:
            if is_windows:
                # Windows: Use taskkill to kill process tree
                # proc.kill() only kills the shell, not children
                import subprocess as sp
                sp.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=sp.DEVNULL,
                    stderr=sp.DEVNULL,
                    timeout=5,
                )
                logger.debug(f"Killed process tree on Windows (execution_id={execution_id}, pid={proc.pid})")
            else:
                # Unix: Kill the entire process group
                # Use negative PID to kill process group
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    logger.debug(f"Killed process group on Unix (execution_id={execution_id}, pgid={os.getpgid(proc.pid)})")
                except ProcessLookupError:
                    # Process already died
                    logger.debug(f"Process group already terminated (execution_id={execution_id})")
                except Exception as e:
                    # Fallback to killing just the process
                    logger.warning(f"Failed to kill process group, falling back to proc.kill() (execution_id={execution_id}): {e}")
                    proc.kill()
        except Exception as e:
            logger.error(f"Failed to kill process tree (execution_id={execution_id}): {e}", exc_info=True)
            # Last resort: try regular kill
            try:
                proc.kill()
            except Exception:
                pass

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
        Execute a shell command with full observability.

        Args:
            command: Shell command to execute
            timeout: Timeout in seconds
            cwd: Working directory for command
            env: Environment variables
            archived_url_id: Optional FK to archived_urls table for context
            archiver: Optional archiver name for context

        Returns:
            CommandResult with execution details and output

        Raises:
            RuntimeError: If database operations fail
        """
        with self.lock:
            return self._execute_locked(
                command=command,
                timeout=timeout,
                cwd=cwd,
                env=env,
                archived_url_id=archived_url_id,
                archiver=archiver,
            )

    def _execute_locked(
        self,
        command: str,
        timeout: float,
        cwd: Optional[Path],
        env: Optional[dict[str, str]],
        archived_url_id: Optional[int],
        archiver: Optional[str],
    ) -> CommandResult:
        """Internal locked execution implementation."""
        from common.db import CommandExecutionRepository

        start_time = datetime.now(timezone.utc)

        # Create execution record in database
        cmd_repo = CommandExecutionRepository()
        execution_id = cmd_repo.create_execution(
            command=command,
            start_time=start_time,
            timeout=timeout,
            archived_url_id=archived_url_id,
            archiver=archiver,
        )

        logger.info(
            f"Executing command (execution_id={execution_id})",
            extra={
                "execution_id": execution_id,
                "command": command,
                "timeout": timeout,
                "archived_url_id": archived_url_id,
                "archiver": archiver,
            }
        )

        # Log command to database as stdin
        cmd_repo.append_output_line(
            execution_id=execution_id,
            stream="stdin",
            line=command,
            timestamp=start_time,
            line_number=1,
        )

        if self.debug:
            logger.debug(f"[stdin] {command}")

        # Execute command
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        combined_output: list[str] = []
        exit_code: Optional[int] = None
        timed_out = False

        try:
            # On Windows, use CREATE_NEW_PROCESS_GROUP; on Unix, use process groups
            # This ensures we can kill the entire process tree on timeout
            is_windows = sys.platform == "win32"

            if is_windows:
                # Windows: CREATE_NEW_PROCESS_GROUP allows us to terminate the whole tree
                proc = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=cwd,
                    env=env,
                    bufsize=1,  # Line buffered
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            else:
                # Unix: Use process group to kill entire tree
                proc = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=cwd,
                    env=env,
                    bufsize=1,  # Line buffered
                    preexec_fn=os.setsid,  # Create new process group
                )

            # Read output in real-time
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                # Kill the entire process tree
                self._kill_process_tree(proc, execution_id, is_windows)
                stdout, stderr = proc.communicate()
                timed_out = True
                exit_code = -1  # Set explicit timeout exit code
                logger.warning(
                    f"Command timed out after {timeout}s (execution_id={execution_id})",
                    extra={"execution_id": execution_id, "command": command, "timeout": timeout}
                )

            # Process stdout
            if stdout:
                for line_num, line in enumerate(stdout.splitlines(), start=1):
                    timestamp = datetime.now(timezone.utc)
                    stdout_lines.append(line)
                    combined_output.append(f"[stdout] {line}")

                    cmd_repo.append_output_line(
                        execution_id=execution_id,
                        stream="stdout",
                        line=line,
                        timestamp=timestamp,
                        line_number=line_num,
                    )

                    if self.debug:
                        logger.debug(f"[stdout] {line}")

            # Process stderr
            if stderr:
                for line_num, line in enumerate(stderr.splitlines(), start=1):
                    timestamp = datetime.now(timezone.utc)
                    stderr_lines.append(line)
                    combined_output.append(f"[stderr] {line}")

                    cmd_repo.append_output_line(
                        execution_id=execution_id,
                        stream="stderr",
                        line=line,
                        timestamp=timestamp,
                        line_number=line_num,
                    )

                    if self.debug:
                        logger.debug(f"[stderr] {line}")

        except Exception as e:
            logger.error(
                f"Command execution failed with exception (execution_id={execution_id}): {e}",
                extra={"execution_id": execution_id, "command": command, "error": str(e)},
                exc_info=True,
            )
            # Log error to database
            timestamp = datetime.now(timezone.utc)
            error_msg = f"Exception: {type(e).__name__}: {e}"
            stderr_lines.append(error_msg)
            combined_output.append(f"[stderr] {error_msg}")

            cmd_repo.append_output_line(
                execution_id=execution_id,
                stream="stderr",
                line=error_msg,
                timestamp=timestamp,
            )

        # Finalize execution record
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        cmd_repo.finalize_execution(
            execution_id=execution_id,
            end_time=end_time,
            exit_code=exit_code,
            timed_out=timed_out,
        )

        logger.info(
            f"Command completed (execution_id={execution_id})",
            extra={
                "execution_id": execution_id,
                "command": command,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "duration_seconds": duration,
            }
        )

        return CommandResult(
            execution_id=execution_id,
            command=command,
            exit_code=exit_code,
            timed_out=timed_out,
            duration_seconds=duration,
            stdout_lines=stdout_lines,
            stderr_lines=stderr_lines,
            combined_output=combined_output,
        )

    def replay(self, execution_id: int) -> CommandResult:
        """
        Replay a past command execution from database logs.

        This reconstructs the full execution context without re-running the command.
        Useful for debugging and reviewing what happened during an archiving run.

        Args:
            execution_id: ID of the command execution to replay

        Returns:
            CommandResult reconstructed from database logs

        Raises:
            ValueError: If execution_id not found
        """
        from common.db import CommandExecutionRepository

        cmd_repo = CommandExecutionRepository()
        execution = cmd_repo.get_by_id(execution_id)
        if not execution:
            raise ValueError(f"Command execution {execution_id} not found")

        output_lines = cmd_repo.get_output_lines(execution_id)

        # Reconstruct output lists
        stdout_lines = [line.line for line in output_lines if line.stream == "stdout"]
        stderr_lines = [line.line for line in output_lines if line.stream == "stderr"]
        combined_output = [
            f"[{line.stream}] {line.line}"
            for line in output_lines
            if line.stream in ("stdout", "stderr")
        ]

        duration = 0.0
        if execution.start_time and execution.end_time:
            duration = (execution.end_time - execution.start_time).total_seconds()

        return CommandResult(
            execution_id=execution.id,
            command=execution.command,
            exit_code=execution.exit_code,
            timed_out=execution.timed_out or False,
            duration_seconds=duration,
            stdout_lines=stdout_lines,
            stderr_lines=stderr_lines,
            combined_output=combined_output,
        )
