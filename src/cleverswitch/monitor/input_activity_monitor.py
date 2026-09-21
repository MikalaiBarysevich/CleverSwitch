"""Per-role user-activity timestamps, read from the standard keyboard/mouse input collections.

Exists for PeerHostFollowSubscriber's activity gating: a genuine Easy-Switch departure
follows recent user input on the departing device, while an idle power-save link drop
follows silence by definition. The report *content* is never inspected or stored — each
report only refreshes a monotonic timestamp keyed by (pid, role).

This is deliberately not a Topic publisher: a mouse in motion produces 50+ reports per
second, which would flood hid_event with traffic no other subscriber cares about. Like
LogiDeviceRegistry and DeviceCache, the monitor is injected shared state queried on demand.

One reader thread per open collection blocks on HIDTransport.read(timeout) and dies on
TransportError (receiver unplugged). A manager thread re-enumerates every few seconds and
opens any collection it is not already reading — so a re-plugged receiver resumes being
monitored without any coupling to the gateway lifecycle. Collections that cannot be opened
are skipped and retried on the next sweep (on Windows the OS denies opening keyboard/mouse
top-level collections entirely — the monitor then simply never has data, and the gating
falls back to relaying like before, see PeerHostFollowSubscriber).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from ..errors.errors import TransportError
from ..hidpp.transport import HIDTransport, InputCollectionInfo, enumerate_input_collections

log = logging.getLogger(__name__)

_ENUMERATE_INTERVAL_S = 5.0
_READ_TIMEOUT_MS = 1000


class InputActivityMonitor:
    """Tracks the monotonic timestamp of the last input report per (pid, role)."""

    def __init__(
        self,
        shutdown: threading.Event,
        enumerate_fn: Callable[[], list[InputCollectionInfo]] = enumerate_input_collections,
        transport_factory: Callable[[bytes], HIDTransport] = lambda path: HIDTransport("input", path),
    ):
        self._shutdown = shutdown
        self._enumerate = enumerate_fn
        self._transport_factory = transport_factory
        self._last: dict[tuple[int, str], float] = {}
        # Paths with a live reader thread; readers discard their entry on exit so the
        # manager reopens the collection on its next sweep.
        self._active_paths: set[bytes] = set()
        self._lock = threading.Lock()

    def start(self) -> None:
        manager = threading.Thread(target=self._manage, name="input-activity-manager", daemon=True)
        manager.start()

    def last_activity(self, pid: int, role: str) -> float | None:
        """Monotonic timestamp of the last input report for this (pid, role), or None."""
        return self._last.get((pid, role))

    def _manage(self) -> None:
        while not self._shutdown.is_set():
            try:
                collections = self._enumerate()
            except Exception as error:
                log.debug(f"Input collection enumeration failed: {error}")
                collections = []
            for collection in collections:
                with self._lock:
                    if collection.path in self._active_paths:
                        continue
                    self._active_paths.add(collection.path)
                reader = threading.Thread(
                    target=self._read_loop,
                    args=(collection,),
                    name=f"input-activity-{collection.role}",
                    daemon=True,
                )
                reader.start()
            self._shutdown.wait(_ENUMERATE_INTERVAL_S)

    def _read_loop(self, collection: InputCollectionInfo) -> None:
        try:
            transport = self._transport_factory(collection.path)
        except OSError as error:
            log.debug(f"Cannot open input collection {collection.role} pid=0x{collection.pid:04X}: {error}")
            with self._lock:
                self._active_paths.discard(collection.path)
            return
        log.debug(f"Monitoring input activity: {collection.role} pid=0x{collection.pid:04X}")
        key = (collection.pid, collection.role)
        try:
            while not self._shutdown.is_set():
                data = transport.read(timeout=_READ_TIMEOUT_MS)
                if data:
                    self._last[key] = time.monotonic()
        except TransportError:
            log.debug(f"Input collection gone: {collection.role} pid=0x{collection.pid:04X}")
        finally:
            transport.close()
            with self._lock:
                self._active_paths.discard(collection.path)
