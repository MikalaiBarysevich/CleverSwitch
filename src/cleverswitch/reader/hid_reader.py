import time
from threading import Thread

from ..errors import TransportError
from ..hidpp.transport import HidDeviceInfo, enumerate_hid_devices, HIDTransport

import logging

from ..listener.event_listener import EventListener

log = logging.getLogger(__name__)

class HidReader(Thread):

    def __init__(self, device_info: HidDeviceInfo, event_listener: EventListener) -> None:
        super().__init__(daemon=True)
        self._device_info = device_info
        self._connected: bool = False
        self._transport: HIDTransport | None = None
        self._event_listener: EventListener = event_listener

    def run(self):
        while True:
            if self._connected:
                try:
                    hid_event = self._transport.read()
                    self._event_listener.listen(hid_event)
                    log.debug(f"HID event from pid={hex(self._device_info.pid)}: {hid_event.hex()}", )
                except TransportError :
                    log.debug("Device disconnected")
                    self._connected = False
            else:
                self._try_connect()

    def _try_connect(self):
        this_device = enumerate_hid_devices(product_id=self._device_info.pid)
        if len(this_device) == 0:
            time.sleep(1)
            return

        try:
            if self._transport is None:
                self._transport = HIDTransport(self._device_info.connection_type, self._device_info.pid)
            else:
                self._transport.try_reopen()

            self._connected = True
        except OSError as e:
            log.debug(f"Failed to connect to HID device: {e}")

    def close(self):
        if self._transport is not None:
            self._transport.close()

