import logging
import platform
import threading
import time
from threading import Thread

from ..errors.errors import TransportError
from ..event.write_event import WriteEvent
from ..hidpp.constants import HIDPP_BT_USAGE_LONG, HIDPP_USAGE_LONG, HIDPP_USAGE_SHORT, REPORT_LONG, REPORT_SHORT
from ..hidpp.transport import HidDeviceInfo, HIDTransport, enumerate_hid_devices
from ..listener.event_listener import EventListener
from ..subscriber.subscriber import Subscriber

log = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"

# How long a write may wait for a gateway that has never connected yet. Measured once from
# construction, so a collection that never connects can only ever park the write topic's drain
# thread for this window. Aligned with RESPONSE_TIMEOUT in subscriber/task/info_task.py.
_FIRST_CONNECT_GRACE = 2.0

# Reconnect backoff. A device parked on another host used to make every disconnected gateway
# re-enumerate once per second forever (issue #108 logged ~894 sweeps over 94 minutes).
_RECONNECT_BACKOFF_MIN = 1.0
_RECONNECT_BACKOFF_MAX = 30.0

# How long close() waits for the reader thread to tear down its own handle. Must comfortably
# exceed HIDTransport._READ_POLL_MS.
_CLOSE_JOIN_TIMEOUT = 2.0

_USAGE_TO_REPORT_ID = {
    HIDPP_USAGE_SHORT: REPORT_SHORT,
    HIDPP_USAGE_LONG: REPORT_LONG,
    HIDPP_BT_USAGE_LONG: REPORT_LONG,
}


class HidGateway(Thread, Subscriber):
    def __init__(self, device_info: HidDeviceInfo, event_listener: EventListener) -> None:
        super().__init__(daemon=True)
        self._device_info = device_info
        self._connected_signal = threading.Event()
        self._ever_connected: bool = False
        self._grace_deadline = time.monotonic() + _FIRST_CONNECT_GRACE
        self._stop = threading.Event()
        self._transport: HIDTransport | None = None
        self._event_listener: EventListener = event_listener
        self._backoff: float = _RECONNECT_BACKOFF_MIN

    @property
    def _connected(self) -> bool:
        return self._connected_signal.is_set()

    @_connected.setter
    def _connected(self, state: bool) -> None:
        if state:
            self._connected_signal.set()
        else:
            self._connected_signal.clear()

    def run(self):
        # The reader owns its handle end to end: hid_close's CancelIo only cancels I/O issued by
        # the calling thread, so closing from anywhere else can leave the kernel writing into
        # freed heap. close() sets _stop and joins instead of touching the transport.
        try:
            while not self._stop.is_set():
                if self._connected:
                    try:
                        hid_event = self._transport.read()
                        if hid_event is None:
                            continue
                        self._event_listener.listen(hid_event)
                        log.debug(
                            f"Received HID event from pid=0x{self._device_info.pid:04X}: {hid_event.hex()}",
                        )
                    except TransportError:
                        if self._stop.is_set():
                            break
                        log.debug(f"Device disconnected pid=0x{self._device_info.pid:04X}")
                        self._set_connected(False)
                else:
                    self._try_connect()
        finally:
            self._close_transport()

    def _try_connect(self):
        this_device_collection = enumerate_hid_devices(product_id=self._device_info.pid)
        if len(this_device_collection) == 0:
            self._backoff_wait()
            return

        for device in this_device_collection[self._device_info.pid]:
            if device.usage_page == self._device_info.usage_page and device.usage == self._device_info.usage:
                if device.path != self._device_info.path:
                    self._device_info.path = device.path
                    self._close_transport()
                    self._transport = None
                break

        try:
            if self._transport is None:
                self._transport = HIDTransport(self._device_info.connection_type, self._device_info.path)
            else:
                self._transport.try_reopen()
            self._set_connected(True)
            self._backoff = _RECONNECT_BACKOFF_MIN
        except OSError as e:
            log.debug(f"Failed to connect to HID device pid=0x{self._device_info.pid:04X}: {e}")
            self._backoff_wait()

    def _backoff_wait(self) -> None:
        self._stop.wait(self._backoff)
        self._backoff = min(self._backoff * 2, _RECONNECT_BACKOFF_MAX)

    def _close_transport(self) -> None:
        transport = self._transport
        if transport is not None:
            transport.close()

    def _set_connected(self, state: bool) -> None:
        self._connected = state
        if not self._ever_connected:
            self._ever_connected = state

    def notify(self, event) -> None:
        if not isinstance(event, WriteEvent):
            return

        if event.pid != self._device_info.pid:
            return

        if not self._connected:
            grace = max(0.0, self._grace_deadline - time.monotonic())
            if self._ever_connected or not self._connected_signal.wait(grace):
                log.debug(f"Dropping write to pid=0x{self._device_info.pid:04X}: device disconnected")
                return

        if _IS_WINDOWS:
            expected = _USAGE_TO_REPORT_ID.get(self._device_info.usage)
            if expected is None or event.hid_message[0] != expected:
                return

        self._write(event.hid_message)

    def _write(self, msg: bytes) -> None:
        # Snapshot the transport: _try_connect can null it between this check and the write,
        # and the resulting AttributeError is not a TransportError, so it would kill this thread.
        transport = self._transport
        if not self._connected or transport is None:
            log.debug(f"Cannot write to pid=0x{self._device_info.pid:04X}: disconnected")
            return
        log.debug(f"Writing to pid=0x{self._device_info.pid:04X}: {msg.hex()}")
        try:
            self._do_write(transport, msg)
        except TransportError:
            log.debug(f"Write failed for pid=0x{self._device_info.pid:04X}, marking disconnected")
            self._connected = False

    def _do_write(self, transport: HIDTransport, msg: bytes) -> None:
        transport.write(msg)

    def close(self):
        self._stop.set()
        if threading.current_thread() is self:
            return  # run()'s finally closes the handle on the way out
        if self.is_alive():
            self.join(timeout=_CLOSE_JOIN_TIMEOUT)
            if not self.is_alive():
                return
            log.warning(f"Gateway pid=0x{self._device_info.pid:04X} did not stop in time; closing handle externally")
        self._close_transport()
