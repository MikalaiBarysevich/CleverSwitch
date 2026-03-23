import time
from threading import Thread

from ..errors import TransportError
from ..event.write_event import WriteEvent
from ..hidpp.transport import HidDeviceInfo, enumerate_hid_devices, HIDTransport

import logging

from ..listener.event_listener import EventListener
from ..subscriber.subscriber import Subscriber

log = logging.getLogger(__name__)

class HidGateway(Thread, Subscriber):

    def __init__(self, device_info: HidDeviceInfo, event_listener: EventListener, send_event_on_connection: bool = False) -> None:
        super().__init__(daemon=True)
        self._send_event_on_connection = send_event_on_connection
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
                    log.debug(f"Received HID event from pid={hex(self._device_info.pid)}: {hid_event.hex()}", )
                except TransportError :
                    log.debug(f"Device disconnected pid={hex(self._device_info.pid)}")
                    self._connected = False
                    if self._send_event_on_connection:
                        self._event_listener.listen(self._create_connection_event())
            else:
                self._try_connect()

    def _try_connect(self):
        this_device = enumerate_hid_devices(product_id=self._device_info.pid)
        if len(this_device) == 0:
            time.sleep(1)
            return

        try:
            if self._transport is None:
                self._transport = HIDTransport(self._device_info.connection_type, self._device_info.path)
            else:
                self._transport.try_reopen()
            self._connected = True
            self._ever_connected = True
            if self._send_event_on_connection:
                self._event_listener.listen(self._create_connection_event())
        except OSError as e:
            log.debug(f"Failed to connect to HID device pid={hex(self._device_info.pid)}: {e}")

    def _create_connection_event(self) -> bytes:
        pid = self._device_info.pid
        # Synthesize a HID++ 1.0 Device Connection short report (0x41)
        # Layout: [report_id, slot, 0x41, 0x00, r1, wpid_lo, wpid_hi]
        # r1: bits[3:0]=device_type (unknown=0), bit[6]: 0=connected, 1=disconnected
        r1 = 0x00 if self._connected else 0x40
        wpid_lo = pid & 0xFF
        wpid_hi = (pid >> 8) & 0xFF
        return bytes([0x10, 0xFF, 0x41, 0x00, r1, wpid_lo, wpid_hi])

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

        log.debug("hid gateway notified")
        self._write(event.hid_message)

    def _write(self, msg: bytes) -> None:
        if not self._connected or self._transport is None:
            log.debug(f"Cannot write to pid={hex(self._device_info.pid)}: disconnected")
            return
        log.debug(f"Writing to pid={hex(self._device_info.pid)}: {msg.hex()}")
        self._transport.write(msg)

    def close(self):
        if self._transport is None:
            return
        self._transport.close()
