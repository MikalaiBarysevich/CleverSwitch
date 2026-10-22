import logging
import time

from .gatt_channel import _BLE_OK, GattChannel
from .hid_gateway import HidGateway
from .hid_gateway_bt import HidGatewayBT

log = logging.getLogger(__name__)

# How long _set_connected(True) waits for the GATT subscription before firing the connect event
# anyway. Without a bound, a device whose notify path never comes up is never set up at all.
_BLE_SUBSCRIBE_GRACE = 5.0


class HidGatewayBLE(HidGatewayBT):
    """macOS-only subclass of HidGatewayBT that reads HID++ notifications from both transports.

    HID++ reporting is bound to the transport channel that armed it. CleverSwitch and peer apps
    (OpenLogi; reportedly Logi Options+) arm the same Easy-Switch CIDs via 0x1B04 setCidReporting,
    and the device reports a press only on the channel whose request landed last. CleverSwitch arms
    over the Logitech GATT characteristic, OpenLogi arms over HID, so reading either channel alone
    goes deaf whenever a peer armed more recently. run() therefore reads both.

    No deduplication is applied: channel affinity means a message is delivered on exactly one
    channel, so a press cannot arrive twice.
    """

    def __init__(self, device_info, event_listener) -> None:
        super().__init__(device_info, event_listener)
        self._gatt = GattChannel(
            device_info.pid,
            event_listener.listen,
            self._connected_signal,
            lambda: self._set_connected(False),
            self._stop,
        )

    def _set_connected(self, state: bool) -> None:
        if not state:
            self._gatt.subscribed.clear()
            super()._set_connected(False)
            return
        # Set _connected first so the BLE thread can proceed with subscribe.
        # Bypass HidGatewayBT to defer the connect event until BLE is ready.
        HidGateway._set_connected(self, True)
        if not _BLE_OK:
            self._emit_state(True)
            return
        deadline = time.monotonic() + _BLE_SUBSCRIBE_GRACE
        while not self._stop.is_set():
            if self._gatt.subscribed.wait(timeout=1.0):
                break
            if time.monotonic() >= deadline:
                log.debug(
                    f"BLE notify not up for pid=0x{self._device_info.pid:04X} after "
                    f"{_BLE_SUBSCRIBE_GRACE:.0f}s — continuing on the HID read path"
                )
                break
        else:
            return
        # A BLE drop during the wait has already emitted the disconnect; don't follow it with a connect.
        if self._connected:
            self._emit_state(True)

    def run(self) -> None:
        if not _BLE_OK:
            log.warning(f"bleak unavailable — pid=0x{self._device_info.pid:04X} BLE notify path disabled")
        else:
            self._gatt.start()

        # Read the HID input reports as well as the GATT notify subscription — see the class
        # docstring for why neither channel alone is reliable. The inherited loop also owns the
        # transport handle and closes it on exit, as before.
        super().run()

    def _do_write(self, transport, msg: bytes) -> None:
        if not self._gatt.write(msg):
            super()._do_write(transport, msg)
