import logging
import threading
import time
from collections.abc import Callable
from threading import Thread

from ..errors.errors import TransportError
from ..hidpp.constants import CONNECTION_BLUETOOTH
from ..hidpp.transport import HidDeviceInfo, HIDTransport
from ..listener.event_listener import EventListener
from ..util.util import SYSTEM_MACOS, get_system

log = logging.getLogger(__name__)

# How long a write may wait for a channel that has never connected yet. Measured once from
# construction, so a collection that never connects can only ever park the write topic's drain
# thread for this window. Aligned with RESPONSE_TIMEOUT in subscriber/task/info_task.py.
_FIRST_CONNECT_GRACE = 2.0

# Waits between attempts to open a node the OS reports present. After the last one the channel
# waits for the next attach().
_OPEN_RETRY_DELAYS = (1.0, 2.0, 4.0, 8.0, 16.0)

# How long close() waits for the reader thread to tear down its own handle. Must comfortably
# exceed HIDTransport._READ_POLL_MS.
_CLOSE_JOIN_TIMEOUT = 2.0


class HidChannel(Thread):
    """Reader thread for one HID collection. Its owner says which node path to use with attach() and
    detach(); every connection change is reported through `on_state_changed`, and the owning
    DeviceLink decides what that means for the device."""

    def __init__(
        self,
        device_info: HidDeviceInfo,
        event_listener: EventListener,
        on_state_changed: Callable[[], None],
    ) -> None:
        super().__init__(daemon=True)
        self._device_info = device_info
        self._on_state_changed = on_state_changed
        self._use_output_report = device_info.connection_type == CONNECTION_BLUETOOTH
        self._connected_signal = threading.Event()
        self._ever_connected: bool = False
        self._grace_deadline = time.monotonic() + _FIRST_CONNECT_GRACE
        self._stop = threading.Event()
        self._wake = threading.Event()
        # Set by a failed write on the write-drain thread; the reader thread acts on it, so only the
        # reader ever changes connection state.
        self._reopen_requested = threading.Event()
        self._transport: HIDTransport | None = None
        self._event_listener: EventListener = event_listener

        self._command_lock = threading.Lock()
        self._desired_path: bytes | None = None
        self._generation = 0

        self._open_path: bytes | None = None
        self._open_generation = -1
        self._dead_generation = -1
        self._failing_generation = -1
        self._open_failures = 0

    @property
    def device_info(self) -> HidDeviceInfo:
        return self._device_info

    @property
    def connected(self) -> bool:
        return self._connected_signal.is_set()

    @property
    def _connected(self) -> bool:
        return self._connected_signal.is_set()

    @_connected.setter
    def _connected(self, state: bool) -> None:
        if state:
            self._connected_signal.set()
        else:
            self._connected_signal.clear()

    # Any thread. Every call is a fresh report that the node is present, so a path given up on after
    # a failure is tried again.
    def attach(self, path: bytes) -> None:
        with self._command_lock:
            self._desired_path = path
            self._generation += 1
        self._wake.set()

    def detach(self) -> None:
        with self._command_lock:
            self._desired_path = None
        self._wake.set()

    def run(self):
        # The reader owns its handle end to end: hid_close's CancelIo only cancels I/O issued by
        # the calling thread, so closing from anywhere else can leave the kernel writing into
        # freed heap. close() sets _stop and joins instead of touching the transport.
        try:
            while not self._stop.is_set():
                self._step()
        finally:
            self._close_transport()

    def _step(self) -> None:
        with self._command_lock:
            desired, generation = self._desired_path, self._generation

        if self._connected:
            if desired != self._open_path:
                self._drop()
            elif self._reopen_requested.is_set():
                self._reopen_after_write_failure()
            else:
                self._read_once()
            return

        if desired is None or generation == self._dead_generation:
            self._sleep(None)
            return
        self._try_open(desired, generation)

    def _read_once(self) -> None:
        try:
            hid_event = self._transport.read()
        except TransportError:
            if self._stop.is_set():
                return
            log.debug(f"Device disconnected pid=0x{self._device_info.pid:04X}")
            self._lost()
            return
        if hid_event is None:
            return
        self._event_listener.listen(hid_event)
        log.debug(f"Received HID event from pid=0x{self._device_info.pid:04X}: {hid_event.hex()}")

    def _try_open(self, path: bytes, generation: int) -> None:
        if generation != self._failing_generation:
            self._failing_generation = generation
            self._open_failures = 0
        self._close_transport()
        self._transport = None
        try:
            self._transport = HIDTransport(self._device_info.connection_type, path)
        except OSError as e:
            self._on_open_failure(generation, e)
            return
        self._open_path = path
        self._open_generation = generation
        self._open_failures = 0
        self._set_connected(True)

    def _on_open_failure(self, generation: int, error: OSError) -> None:
        if self._open_failures < len(_OPEN_RETRY_DELAYS):
            delay = _OPEN_RETRY_DELAYS[self._open_failures]
            self._open_failures += 1
            log.debug(f"Failed to open HID device pid=0x{self._device_info.pid:04X}: {error}; retrying in {delay}s")
            self._sleep(delay)
            return
        self._dead_generation = generation
        hint = " (check the Input Monitoring permission)" if get_system() == SYSTEM_MACOS else ""
        log.warning(
            f"Cannot open HID device pid=0x{self._device_info.pid:04X}: {error}{hint}; waiting for it to be reconnected"
        )

    # A failure on the open handle. If the OS has reported the node since it was opened, that report
    # may be the device coming back, so the open is retried; otherwise the channel waits for one.
    def _lost(self) -> None:
        with self._command_lock:
            generation = self._generation
        if generation == self._open_generation:
            self._dead_generation = generation
        self._drop()

    def _drop(self) -> None:
        self._close_transport()
        self._transport = None
        self._open_path = None
        self._set_connected(False)

    # A failed write alone doesn't mean the device left: on Windows a BT device can still be listed
    # right after a host switch and fail writes, and reporting that as a disconnect made the link
    # flap. The handle is reopened quietly; only a failed reopen, or a failed read, reports it gone.
    def _reopen_after_write_failure(self) -> None:
        self._reopen_requested.clear()
        try:
            self._transport.try_reopen()
            log.debug(f"Write failed for pid=0x{self._device_info.pid:04X}, handle reopened")
        except OSError as e:
            log.debug(f"Write failed for pid=0x{self._device_info.pid:04X} and reopen failed: {e}")
            self._lost()

    def _sleep(self, timeout: float | None) -> None:
        self._wake.wait(timeout)
        self._wake.clear()

    def _close_transport(self) -> None:
        transport = self._transport
        if transport is not None:
            transport.close()

    def _set_connected(self, state: bool) -> None:
        self._reopen_requested.clear()
        self._connected = state
        if not self._ever_connected:
            self._ever_connected = state
        self._on_state_changed()

    # Runs on the owning DeviceLink's write-topic drain thread.
    def submit(self, msg: bytes) -> None:
        if not self._connected:
            grace = max(0.0, self._grace_deadline - time.monotonic())
            if self._ever_connected or not self._connected_signal.wait(grace):
                log.debug(f"Dropping write to pid=0x{self._device_info.pid:04X}: device disconnected")
                return

        self._write(msg)

    def _write(self, msg: bytes) -> None:
        # Snapshot the transport: the reader can null it between this check and the write, and the
        # resulting AttributeError is not a TransportError, so it would kill this thread.
        transport = self._transport
        if not self._connected or self._reopen_requested.is_set() or transport is None:
            log.debug(f"Cannot write to pid=0x{self._device_info.pid:04X}: disconnected")
            return
        log.debug(f"Writing to pid=0x{self._device_info.pid:04X}: {msg.hex()}")
        try:
            if self._use_output_report:
                transport.write_output_report(msg)
            else:
                transport.write(msg)
        except TransportError:
            log.debug(f"Write failed for pid=0x{self._device_info.pid:04X}, requesting reconnect")
            self._reopen_requested.set()

    def close(self):
        self._stop.set()
        self._wake.set()
        if threading.current_thread() is self:
            return  # run()'s finally closes the handle on the way out
        if self.is_alive():
            self.join(timeout=_CLOSE_JOIN_TIMEOUT)
            if not self.is_alive():
                return
            log.warning(
                f"HID channel pid=0x{self._device_info.pid:04X} did not stop in time; closing handle externally"
            )
        self._close_transport()
