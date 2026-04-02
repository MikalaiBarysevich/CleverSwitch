import logging
import platform
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

_USAGE_TO_REPORT_ID = {
    HIDPP_USAGE_SHORT: REPORT_SHORT,
    HIDPP_USAGE_LONG: REPORT_LONG,
    HIDPP_BT_USAGE_LONG: REPORT_LONG,
}


class HidGateway(Thread, Subscriber):
    def __init__(self, device_info: HidDeviceInfo, event_listener: EventListener) -> None:
        super().__init__(daemon=True)
        self._device_info = device_info
        self._connected: bool = False
        self._ever_connected: bool = False
        self._transport: HIDTransport | None = None
        self._event_listener: EventListener = event_listener

    def run(self):
        while True:
            if self._connected:
                try:
                    hid_event = self._transport.read()
                    self._event_listener.listen(hid_event)
                    log.debug(
                        f"Received HID event from pid={hex(self._device_info.pid)}: {hid_event.hex()}",
                    )
                except TransportError:
                    log.debug(f"Device disconnected pid={hex(self._device_info.pid)}")
                    self._set_connected(False)
            else:
                self._try_connect()

    def _try_connect(self):
        this_device_collection = enumerate_hid_devices(product_id=self._device_info.pid)
        if len(this_device_collection) == 0:
            time.sleep(1)
            return

        for device in this_device_collection[self._device_info.pid]:
            if device.usage_page == self._device_info.usage_page and device.usage == self._device_info.usage:
                if device.path != self._device_info.path:
                    self._device_info.path = device.path
                    self._transport.close()
                    self._transport = None
                break

        try:
            if self._transport is None:
                self._transport = HIDTransport(self._device_info.connection_type, self._device_info.path)
            else:
                self._transport.try_reopen()
            self._set_connected(True)
        except OSError as e:
            log.debug(f"Failed to connect to HID device pid={hex(self._device_info.pid)}: {e}")

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
            if not self._ever_connected:
                while not self._connected:
                    time.sleep(0.5)
            else:
                log.debug("Dropping write to pid=%s: device disconnected", hex(self._device_info.pid))
                return

        if _IS_WINDOWS:
            expected = _USAGE_TO_REPORT_ID.get(self._device_info.usage)
            if expected is None or event.hid_message[0] != expected:
                return

        log.debug("hid gateway notified")
        self._write(event.hid_message)

    def _write(self, msg: bytes) -> None:
        if not self._connected or self._transport is None:
            log.debug(f"Cannot write to pid={hex(self._device_info.pid)}: disconnected")
            return
        log.debug(f"Writing to pid={hex(self._device_info.pid)}: {msg.hex()}")
        try:
            self._do_write(msg)
        except TransportError:
            log.debug(f"Write failed for pid={hex(self._device_info.pid)}, marking disconnected")
            self._connected = False

    def _do_write(self, msg: bytes) -> None:
        self._transport.write(msg)

    def close(self):
        if self._transport is None:
            return
        self._transport.close()
