import json
import queue
import re
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO, Union


class HTRunner:
    def __init__(self, ht_bin: str, listen_addr: str, log_path: Optional[Union[str, Path]] = None):
        self.ht_bin = ht_bin
        self.listen_addr = listen_addr
        self.proc: Optional[subprocess.Popen] = None
        self.stdout_thread: Optional[threading.Thread] = None
        self.events = queue.Queue()  # raw JSON lines from ht stdout
        self.lock = threading.Lock()  # serialize shell commands
        self.running = threading.Event()
        # Logging
        self.log_path: Optional[Path] = Path(log_path) if log_path else None
        self._log_fp: Optional[TextIO] = None
        self._log_lock = threading.Lock()

    def _log(self, kind: str, text: str):
        if not self._log_fp:
            return
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        line = f"[{ts}] {kind}: {text}\n"
        with self._log_lock:
            try:
                self._log_fp.write(line)
                self._log_fp.flush()
            except Exception:
                pass

    def start(self):
        if self.proc is not None:
            return
        # Use /bin/sh as the wrapped program to ensure presence on slim images
        cmd = [
            self.ht_bin,
            "--listen",
            self.listen_addr,
            "--subscribe",
            "init,output,resize,snapshot",
            "sh",
        ]
        # Prepare logger
        if self.log_path is not None:
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                # Open in append mode
                self._log_fp = open(self.log_path, "a", encoding="utf-8")
                self._log(
                    "START",
                    "ht proc starting with cmd="
                    + json.dumps(cmd, ensure_ascii=False),
                )
            except Exception:
                self._log_fp = None
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.running.set()
        self.stdout_thread = threading.Thread(target=self._reader, daemon=True)
        self.stdout_thread.start()

    def _reader(self):
        assert self.proc is not None and self.proc.stdout is not None
        for line in self.proc.stdout:
            # push raw line to queue for any waiter
            try:
                raw = line.rstrip("\n")
                # Log raw stdout JSON line
                self._log("STDOUT", raw)
                self.events.put_nowait(raw)
            except queue.Full:
                pass

    def send_input(self, payload: str):
        if self.proc is None or self.proc.stdin is None:
            raise RuntimeError("ht process not started")
        msg = json.dumps({"type": "input", "payload": payload}) + "\n"
        # Log exact JSON input line and a human-friendly payload
        self._log("STDIN.json", msg.rstrip("\n"))
        self._log("STDIN.payload", payload.replace("\r", "\\r"))
        self.proc.stdin.write(msg)
        self.proc.stdin.flush()

    def interrupt(self):
        """Send a CTRL+C (SIGINT) to the wrapped shell."""
        try:
            self.send_input("\u0003")
        except Exception:
            pass

    def wait_for_done_marker(self, marker: str, timeout: float = 120.0) -> Optional[int]:
        deadline = time.time() + timeout
        pattern = re.compile(re.escape(marker) + r":(?P<code>\d+)")
        while time.time() < deadline:
            try:
                line = self.events.get(timeout=0.25)
            except queue.Empty:
                continue
            # ht emits JSON event lines; look for output events and scan seq
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            if evt.get("type") == "output":
                seq = evt.get("data", {}).get("seq", "")
                m = pattern.search(seq)
                if m:
                    return int(m.group("code"))
        return None

    def execute_command(
        self,
        cmd: str,
        marker: str = "__DONE__",
        timeout: float = 300.0,
        cleanup_on_timeout: Optional[Callable[[], None]] = None,
    ) -> Optional[int]:
        """Execute a shell command and wait for completion marker.

        Args:
            cmd: Shell command to execute (without the trailing marker)
            marker: Completion marker to wait for (default: "__DONE__")
            timeout: Timeout in seconds (default: 300.0)
            cleanup_on_timeout: Optional callback to run if command times out

        Returns:
            Exit code as integer, or None if timed out
        """
        with self.lock:
            self.send_input(cmd + "\r")
            code = self.wait_for_done_marker(marker, timeout=timeout)
            if code is None and cleanup_on_timeout:
                cleanup_on_timeout()
            return code

    def stop(self, timeout: float = 5.0):
        """Gracefully stop the ht process and reader thread.

        Idempotent and safe to call multiple times.
        """
        proc = self.proc
        if proc is None:
            return
        # Prevent concurrent writes while shutting down
        with self.lock:
            # Close stdin to signal EOF to ht
            try:
                if proc.stdin and not proc.stdin.closed:
                    proc.stdin.close()
            except Exception:
                pass
            # Send SIGTERM
            try:
                proc.terminate()
            except Exception:
                pass
        # Wait for clean exit
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                proc.wait(timeout=2.0)
            except Exception:
                pass

        self.running.clear()
        if self.stdout_thread and self.stdout_thread.is_alive():
            try:
                self.stdout_thread.join(timeout=1.0)
            except Exception:
                pass
        self.stdout_thread = None
        # Log stop
        try:
            rc = proc.returncode
        except Exception:
            rc = None
        self._log("STOP", f"ht proc stopped rc={rc}")
        # Close log file if open
        if self._log_fp:
            try:
                self._log_fp.flush()
                self._log_fp.close()
            except Exception:
                pass
            finally:
                self._log_fp = None
        self.proc = None
