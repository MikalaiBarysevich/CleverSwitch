import threading

from ..model.logi_device import LogiDevice


class LogiDeviceRegistry:
    """Thread-safe registry of all known products across all connection types."""

    def __init__(self):
        self._lock = threading.Lock()
        self._products: dict[int, LogiDevice] = {}

    def register(self, wpid: int, entry: LogiDevice) -> None:
        with self._lock:
            self._products[wpid] = entry

    def unregister(self, wpid: int) -> None:
        with self._lock:
            self._products.pop(wpid, None)

    def all_entries(self) -> list[LogiDevice]:
        with self._lock:
            return list(self._products.values())

    def get_by_wpid(self, wpid: int) -> LogiDevice | None:
        with self._lock:
            return self._products.get(wpid, None)
