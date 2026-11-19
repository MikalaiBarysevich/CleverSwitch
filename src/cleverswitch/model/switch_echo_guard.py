import threading
import time
from collections.abc import Callable

ECHO_WINDOW_S = 2.0


class SwitchEchoGuard:
    """Remembers software-initiated switches so a device's own x1814 announcement of one is not
    taken as a new Easy-Switch press. Whether devices announce a switch they were told to make is
    unconfirmed; the guard only drops an announcement of the same target shortly after we sent it.

    The window cuts both ways: a genuine press to that same host inside it is dropped too, along with
    the switch burst it would have triggered. That is tolerable because every device was just told to
    go to that host, so the only thing lost is a redundant repair; a press to any other host passes
    immediately, because only the target we sent is recorded.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic, window_s: float = ECHO_WINDOW_S):
        self._clock = clock
        self._window_s = window_s
        self._lock = threading.Lock()
        self._recent: dict[int, float] = {}

    def record(self, target_host: int) -> None:
        with self._lock:
            self._recent[target_host] = self._clock()

    def is_echo(self, target_host: int) -> bool:
        with self._lock:
            sent_at = self._recent.get(target_host)
        return sent_at is not None and self._clock() - sent_at <= self._window_s
