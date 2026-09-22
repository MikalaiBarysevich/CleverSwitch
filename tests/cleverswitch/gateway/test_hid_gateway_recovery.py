from unittest.mock import MagicMock

from cleverswitch.gateway.hid_gateway import HidGateway
from cleverswitch.hidpp.transport import HidDeviceInfo
from cleverswitch.listener.event_listener import EventListener


def _device_info():
    return HidDeviceInfo(
        path=b"/dev/hidraw0", vid=0x046D, pid=0xB380, usage_page=0xFF00, usage=0x0002, connection_type="bluetooth"
    )


def test_read_timeout_keeps_an_healthy_idle_gateway_connected(mocker):
    gateway = HidGateway(_device_info(), MagicMock(spec=EventListener))
    gateway._transport = MagicMock()
    gateway._transport.read.return_value = None
    gateway._connected = True
    gateway._stop_event = MagicMock()
    gateway._stop_event.is_set.side_effect = [False, True]
    set_connected = mocker.patch.object(gateway, "_set_connected")
    gateway.run()

    gateway._transport.read.assert_called_once()
    set_connected.assert_not_called()
