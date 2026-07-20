"""A spinner for the waits that can't be made shorter.

arXiv takes up to 20s, Gemini a few seconds before its first token. Without
something moving, both look like a hang. Use as a context manager:

    with Spinner("searching arXiv"):
        hits = paper.search(q)

Silent when stdout isn't a terminal, so piped output and logs stay clean.
"""
import sys
import threading
import time

FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
DIM, RESET = "\033[2m", "\033[0m"


class Spinner:
    def __init__(self, text, stream=None):
        self.text = text
        self.stream = stream or sys.stdout
        self.live = self.stream.isatty()
        self._stop = threading.Event()
        self._thread = None

    def _spin(self):
        i = 0
        start = time.time()
        while not self._stop.is_set():
            # after a few seconds show elapsed time, so a slow call reads as
            # slow rather than stuck
            waited = time.time() - start
            clock = f" {waited:.0f}s" if waited > 3 else ""
            self.stream.write(f"\r{DIM}  {FRAMES[i % len(FRAMES)]} {self.text}{clock}…{RESET}")
            self.stream.flush()
            i += 1
            self._stop.wait(0.08)

    def start(self):
        if self.live and self._thread is None:
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def stop(self):
        """Idempotent — safe to call from a token callback and again on exit."""
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=1)
        self._thread = None
        self.stream.write("\r\033[2K")   # clear the whole line
        self.stream.flush()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False
