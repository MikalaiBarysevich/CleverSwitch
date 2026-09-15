from unittest.mock import MagicMock

from cleverswitch.gateway.hid_gateway import HidGateway, _IDLE_REOPEN_SECONDS, _READ_TIMEOUT_MS
from cleverswitch.hidpp.transport import HidDeviceInfo
from cleverswitch.listener.event_listener import EventListener


def _device_info():
    return HidDeviceInfo(
        path=b"/dev/hidraw0", vid=0x046D, pid=0xB380, usage_page=0xFF00, usage=0x0002, connection_type="bluetooth"
    )


def test_idle_gateway_reopens_instead_of_waiting_forever(mocker):
    gateway = HidGateway(_device_info(), MagicMock(spec=EventListener))
    gateway._transport = MagicMock()
    gateway._transport.read.return_value = None
    gateway._connected = True
    gateway._last_hid_activity = 0.0

    mocker.patch("cleverswitch.gateway.hid_gateway.time.monotonic", return_value=_IDLE_REOPEN_SECONDS + 1)

    def disconnect(state):
        assert state is False
        gateway._stop_event.set()

    set_connected = mocker.patch.object(gateway, "_set_connected", side_effect=disconnect)
    gateway.run()

    gateway._transport.read.assert_called_once_with(timeout=_READ_TIMEOUT_MS)
    set_connected.assert_called_once_with(False)
