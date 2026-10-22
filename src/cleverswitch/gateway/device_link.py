import logging
import threading

from ..event.link_channel_changed_event import CHANNEL_GATT, LinkChannelChangedEvent
from ..event.transport_connected_event import TransportConnectedEvent
from ..event.transport_disconnected_event import TransportDisconnectedEvent
from ..event.write_event import WriteEvent
from ..gateway.gatt_channel import GattChannel
from ..gateway.hid_channel import HidChannel
from ..gateway.write_router import WriteRouter
from ..listener.event_listener import EventListener
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)


class DeviceLink(Subscriber):
    """Everything CleverSwitch holds open for one HID product id.

    Owns the device's HID collection channels, the optional macOS GATT channel and their shared
    EventListener, and is the only write-topic subscriber for that pid.

    The device is present while every HID collection is open. Only changes in presence are
    emitted, so a device with several collections connects and disconnects once. The GATT
    channel runs while the device is present; its own up/down is published as a
    LinkChannelChangedEvent and never affects presence.

    Writes go over GATT while it is subscribed (responses then come back on the GATT notify
    channel), otherwise to the HID collection the WriteRouter selects.
    """

    def __init__(
        self,
        pid: int,
        connection_type: str,
        topics: Topics,
        listener: EventListener,
        router: WriteRouter,
    ) -> None:
        self._pid = pid
        self._connection_type = connection_type
        self._listener = listener
        self._router = router
        self._hid_channels: list[HidChannel] = []
        self._gatt: GattChannel | None = None
        self._present = False
        self._lock = threading.Lock()
        topics.write.subscribe(self)

    def attach(self, hid_channels: list[HidChannel], gatt: GattChannel | None = None) -> None:
        self._hid_channels = hid_channels
        self._gatt = gatt

    # Runs on an HID channel's reader thread, so it must never block.
    def on_hid_state_changed(self) -> None:
        with self._lock:
            present = bool(self._hid_channels) and all(hid_channel.connected for hid_channel in self._hid_channels)
            if present == self._present:
                return
            self._present = present
            if present:
                self._listener.emit(
                    TransportConnectedEvent(slot=0, pid=self._pid, connection_type=self._connection_type)
                )
            else:
                self._listener.emit(TransportDisconnectedEvent(slot=0, pid=self._pid))
            if self._gatt is not None:
                if present:
                    self._gatt.activate()
                else:
                    self._gatt.deactivate()

    def on_gatt_state(self, up: bool) -> None:
        self._listener.emit(LinkChannelChangedEvent(slot=0, pid=self._pid, channel=CHANNEL_GATT, up=up))

    def notify(self, event) -> None:
        if not isinstance(event, WriteEvent) or event.pid != self._pid:
            return
        msg = event.hid_message
        if self._gatt is not None and self._gatt.write(msg):
            return
        hid_channel = self._router.select(msg, self._hid_channels)
        if hid_channel is None:
            log.debug(f"No collection accepts report 0x{msg[0]:02X} for pid=0x{self._pid:04X}")
            return
        hid_channel.submit(msg)

    def start(self) -> None:
        if self._gatt is not None:
            self._gatt.start()
        for hid_channel in self._hid_channels:
            hid_channel.start()
        self._listener.start()

    def close(self) -> None:
        if self._gatt is not None:
            self._gatt.close()
        for hid_channel in self._hid_channels:
            hid_channel.close()
