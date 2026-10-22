import logging

from ..gateway import gatt_channel
from ..gateway.device_link import DeviceLink
from ..gateway.gatt_channel import GattChannel
from ..gateway.hid_gateway import HidGateway
from ..gateway.write_router import ReportIdWriteRouter, WriteRouter
from ..hidpp.transport import HidDeviceInfo
from ..listener.event_listener import EventListener
from ..topic.topics import Topics
from ..util.util import get_system

log = logging.getLogger(__name__)


def create_link(pid: int, collections: list[HidDeviceInfo], topics: Topics) -> DeviceLink:
    connection_type = collections[0].connection_type
    is_bluetooth = connection_type != "receiver"
    listener = EventListener(collections[0], topics)
    router = ReportIdWriteRouter() if get_system() == "Windows" else WriteRouter()
    link = DeviceLink(pid, connection_type, topics, listener, router)
    gateways = [
        HidGateway(collection, listener, link.on_hid_state_changed, use_output_report=is_bluetooth)
        for collection in collections
    ]
    link.attach(gateways, _create_gatt(pid, is_bluetooth, listener, link))
    return link


# HID++ reporting follows the channel that armed it, and on macOS peer apps arm over GATT, so a
# Bluetooth device there is read over GATT as well as HID.
def _create_gatt(pid: int, is_bluetooth: bool, listener: EventListener, link: DeviceLink) -> GattChannel | None:
    if not is_bluetooth or get_system() != "Darwin":
        return None
    if not gatt_channel._BLE_OK:
        log.warning(f"bleak unavailable — pid=0x{pid:04X} BLE notify path disabled")
        return None
    return GattChannel(pid, listener.listen, link.on_gatt_state)
