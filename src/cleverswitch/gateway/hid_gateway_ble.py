import logging

from ..event.link_channel_changed_event import LinkChannelChangedEvent
from .gatt_channel import _BLE_OK, GattChannel
from .hid_gateway_bt import HidGatewayBT

log = logging.getLogger(__name__)


class HidGatewayBLE(HidGatewayBT):
    """macOS-only subclass of HidGatewayBT that reads HID++ notifications from both transports.

    HID++ reporting is bound to the transport channel that armed it. CleverSwitch and peer apps
    (OpenLogi; Logi Options+) arm the same Easy-Switch CIDs via 0x1B04 setCidReporting, and the
    device reports a press only on the channel whose request landed last. OpenLogi arms over HID;
    with Logi Options+ running, presses were seen only on GATT. Reading either channel alone goes
    deaf whenever a peer armed more recently, so run() reads both.

    No deduplication is applied: channel affinity means a message is delivered on exactly one
    channel, so a press cannot arrive twice.

    HID decides whether the device is present. The GATT channel runs while HID is up, and its own
    up/down is published as LinkChannelChangedEvent so reporting is re-armed onto whichever channel
    writes now prefer; it never marks the device disconnected.
    """

    def __init__(self, device_info, event_listener) -> None:
        super().__init__(device_info, event_listener)
        self._gatt = GattChannel(device_info.pid, event_listener.listen, self._on_gatt_state, self._stop)

    def _set_connected(self, state: bool) -> None:
        super()._set_connected(state)
        if state:
            self._gatt.activate()
        else:
            self._gatt.deactivate()

    def _on_gatt_state(self, up: bool) -> None:
        self._event_listener.emit(LinkChannelChangedEvent(slot=0, pid=self._device_info.pid, channel="gatt", up=up))

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
