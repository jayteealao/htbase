import json
import queue
import re
import subprocess
import threading
import time
from typing import Optional


class HTRunner:
    def __init__(self, ht_bin: str, listen_addr: str):
        self.ht_bin = ht_bin
        self.listen_addr = listen_addr
        self.proc: Optional[subprocess.Popen] = None
        self.stdout_thread: Optional[threading.Thread] = None
        self.events = queue.Queue()  # raw JSON lines from ht stdout
        self.lock = threading.Lock()  # serialize shell commands
        self.running = threading.Event()

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
                self.events.put_nowait(line.rstrip("\n"))
            except queue.Full:
                pass

    def send_input(self, payload: str):
        if self.proc is None or self.proc.stdin is None:
            raise RuntimeError("ht process not started")
        msg = json.dumps({"type": "input", "payload": payload}) + "\n"
        self.proc.stdin.write(msg)
        self.proc.stdin.flush()

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
        self.proc = None
