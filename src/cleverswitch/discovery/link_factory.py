from ..gateway.device_link import DeviceLink
from ..gateway.hid_gateway import HidGateway
from ..gateway.hid_gateway_ble import HidGatewayBLE
from ..gateway.hid_gateway_bt import HidGatewayBT
from ..gateway.hid_gateway_receiver import HidGatewayReceiver
from ..gateway.write_router import ReportIdWriteRouter, WriteRouter
from ..hidpp.transport import HidDeviceInfo
from ..listener.event_listener import EventListener
from ..topic.topics import Topics
from ..util.util import get_system

# TEMPORARY: macOS HID-only test with GATT disabled. Remove after hardware testing.
_GATT_ENABLED = False


def create_link(pid: int, collections: list[HidDeviceInfo], topics: Topics) -> DeviceLink:
    listener = EventListener(collections[0], topics)
    gateways = [_create_gateway(collection, listener) for collection in collections]
    router = ReportIdWriteRouter() if get_system() == "Windows" else WriteRouter()
    return DeviceLink(pid, topics, listener, gateways, router)


def _create_gateway(collection: HidDeviceInfo, listener: EventListener) -> HidGateway:
    if collection.connection_type == "receiver":
        return HidGatewayReceiver(collection, listener)
    if get_system() == "Darwin" and _GATT_ENABLED:
        return HidGatewayBLE(collection, listener)
    return HidGatewayBT(collection, listener)
