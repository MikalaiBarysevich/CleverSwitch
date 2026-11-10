import sys
import time
from logging.handlers import RotatingFileHandler

ROLLOVER_RETRY_DELAY = 60.0


class SafeRotatingFileHandler(RotatingFileHandler):
    """Keeps appending to the current file when rollover's rename fails (on Windows a viewer or
    antivirus can hold the file open), and retries the rollover only after ROLLOVER_RETRY_DELAY."""

    def __init__(self, *args, clock=time.monotonic, **kwargs):
        super().__init__(*args, **kwargs)
        self._clock = clock
        self._retry_at = 0.0
        self._warned = False

    def shouldRollover(self, record) -> bool:
        if self._clock() < self._retry_at:
            return False
        return bool(super().shouldRollover(record))

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except OSError as e:
            self._retry_at = self._clock() + ROLLOVER_RETRY_DELAY
            if not self._warned:
                self._warned = True
                print(f"CleverSwitch: log rollover failed, appending to current file: {e}", file=sys.stderr)
            if self.stream is None:
                self.stream = self._open()
