import logging

from ..gateway import gatt_channel
from ..gateway.device_link import DeviceLink
from ..gateway.gatt_channel import GattChannel
from ..gateway.hid_channel import HidChannel
from ..gateway.write_router import ReportIdWriteRouter, WriteRouter
from ..hidpp.constants import (
    CONNECTION_BLUETOOTH,
    CONNECTION_RECEIVER,
    HIDPP_RECEIVER_USAGE_PAGE,
    HIDPP_USAGE_LONG,
    HIDPP_USAGE_SHORT,
)
from ..hidpp.transport import HidDeviceInfo
from ..listener.event_listener import EventListener
from ..topic.topics import Topics
from ..util.util import SYSTEM_MACOS, SYSTEM_WINDOWS, get_system

log = logging.getLogger(__name__)

# Windows splits a receiver's short and long HID++ reports into two collections that arrive as
# separate hotplug events, so presence must wait until both have been listed.
_WINDOWS_RECEIVER_COLLECTIONS = frozenset(
    {(HIDPP_RECEIVER_USAGE_PAGE, HIDPP_USAGE_SHORT), (HIDPP_RECEIVER_USAGE_PAGE, HIDPP_USAGE_LONG)}
)


def create_link(pid: int, collections: list[HidDeviceInfo], topics: Topics) -> DeviceLink:
    connection_type = collections[0].connection_type
    listener = EventListener(collections[0], topics)
    windows = get_system() == SYSTEM_WINDOWS
    router = ReportIdWriteRouter() if windows else WriteRouter()
    required = _WINDOWS_RECEIVER_COLLECTIONS if windows and connection_type == CONNECTION_RECEIVER else frozenset()
    link = DeviceLink(pid, connection_type, topics, listener, router, required)
    link.attach(
        lambda collection: HidChannel(collection, listener, link.on_hid_state_changed),
        _create_gatt(pid, connection_type, listener, link),
    )
    link.update(collections)
    return link


# HID++ reporting follows the channel that armed it, and on macOS peer apps arm over GATT, so a
# Bluetooth device there is read over GATT as well as HID.
def _create_gatt(pid: int, connection_type: str, listener: EventListener, link: DeviceLink) -> GattChannel | None:
    if connection_type != CONNECTION_BLUETOOTH or get_system() != SYSTEM_MACOS:
        return None
    if not gatt_channel._BLE_OK:
        log.warning(f"bleak unavailable — pid=0x{pid:04X} BLE notify path disabled")
        return None
    return GattChannel(pid, listener.listen, link.on_gatt_state)
