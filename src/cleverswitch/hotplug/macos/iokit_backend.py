import logging
import threading
from collections.abc import Callable

from ...errors.errors import HotplugError
from ...event.hid_node_added_event import HidNodeAddedEvent
from ...event.hid_node_removed_event import HidNodeRemovedEvent
from ...hidpp.constants import LOGITECH_VENDOR_ID
from ...topic.topics import Topics
from ..backend import HotplugBackend
from .iokit import DeviceCallback, IOKit

log = logging.getLogger(__name__)

_RUN_SLICE = 1.0
_START_TIMEOUT = 5.0
_STOP_JOIN_TIMEOUT = 2.0


class IOKitHotplugBackend(HotplugBackend):
    def __init__(self, topics: Topics, iokit_factory: Callable[[], IOKit] = IOKit) -> None:
        self._topics = topics
        self._iokit_factory = iokit_factory
        self._iokit: IOKit | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopping = threading.Event()
        self._lock = threading.Lock()
        self._run_loop: int | None = None
        self._error: Exception | None = None
        self._match_callback = DeviceCallback(lambda _ctx, _result, _sender, device: self._publish(True, device))
        self._remove_callback = DeviceCallback(lambda _ctx, _result, _sender, device: self._publish(False, device))

    def start(self) -> None:
        thread = threading.Thread(target=self._run, name="hotplug-iokit", daemon=True)
        self._thread = thread
        thread.start()
        if not self._ready.wait(_START_TIMEOUT):
            raise HotplugError("IOKit device notifications did not start in time")
        if self._error is not None:
            self._thread = None
            raise HotplugError(f"Cannot listen for IOKit device events: {self._error}") from self._error
        log.info("Listening for device hotplug events from IOKit")

    def stop(self) -> None:
        thread, self._thread = self._thread, None
        if thread is None:
            return
        self._stopping.set()
        with self._lock:
            if self._run_loop is not None:
                self._iokit.stop(self._run_loop)
        thread.join(timeout=_STOP_JOIN_TIMEOUT)

    # The run loop belongs to this thread: it is created here, runs here, and is released here.
    # stop() may only touch it under _lock while _run_loop is set, so never after it is gone.
    def _run(self) -> None:
        try:
            iokit = self._iokit_factory()
            self._iokit = iokit
            manager = iokit.create_manager(LOGITECH_VENDOR_ID, self._match_callback, self._remove_callback)
        except Exception as e:
            self._error = e
            self._ready.set()
            return
        with self._lock:
            self._run_loop = iokit.current_run_loop()
        self._ready.set()
        try:
            while not self._stopping.is_set():
                iokit.run(_RUN_SLICE)
        finally:
            with self._lock:
                self._run_loop = None
            iokit.release_manager(manager)

    def _publish(self, added: bool, device: int) -> None:
        try:
            pid = self._iokit.product_id(device)
        except Exception:
            log.exception("Cannot read the product id of an IOKit HID device")
            return
        if pid is None:
            return
        event_type = HidNodeAddedEvent if added else HidNodeRemovedEvent
        self._topics.hotplug.publish(event_type(slot=0, pid=pid))
