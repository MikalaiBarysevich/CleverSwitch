"""Unit tests for gateway/hid_gateway.py and gateway/hid_gateway_bt.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.write_event import WriteEvent
from cleverswitch.gateway.hid_gateway import HidGateway
from cleverswitch.gateway.hid_gateway_bt import HidGatewayBT
from cleverswitch.hidpp.constants import BOLT_PID, REPORT_LONG
from cleverswitch.hidpp.transport import HidDeviceInfo
from cleverswitch.listener.event_listener import EventListener


def _device_info(pid=BOLT_PID, connection_type="receiver"):
    return HidDeviceInfo(
        path=b"/dev/hidraw0", vid=0x046D, pid=pid, usage_page=0xFF00, usage=0x0002, connection_type=connection_type
    )


def _bt_device_info(pid=0xB023):
    return HidDeviceInfo(
        path=b"/dev/hidraw1", vid=0x046D, pid=pid, usage_page=0xFF43, usage=0x0202, connection_type="bluetooth"
    )


# ── HidGateway.notify ────────────────────────────────────────────────────────


def test_notify_ignores_non_write_event():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    gw.notify("not a WriteEvent")  # must not raise


def test_notify_ignores_wrong_pid():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(pid=BOLT_PID), event_listener)
    event = WriteEvent(slot=1, pid=0x9999, hid_message=b"\x11" + bytes(19))
    gw.notify(event)  # must not raise (different pid)


def test_notify_drops_write_when_disconnected_and_was_previously_connected():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    gw._connected = False
    gw._ever_connected = True
    mock_transport = MagicMock()
    gw._transport = mock_transport

    event = WriteEvent(slot=1, pid=BOLT_PID, hid_message=b"\x11" + bytes(19))
    gw.notify(event)

    mock_transport.write.assert_not_called()


def test_notify_writes_when_connected():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    gw._connected = True
    gw._ever_connected = True
    mock_transport = MagicMock()
    gw._transport = mock_transport

    msg = bytes([REPORT_LONG]) + bytes(19)
    event = WriteEvent(slot=1, pid=BOLT_PID, hid_message=msg)
    gw.notify(event)

    mock_transport.write.assert_called_once_with(msg)


# ── HidGateway.close ─────────────────────────────────────────────────────────


def test_close_closes_transport():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    mock_transport = MagicMock()
    gw._transport = mock_transport

    gw.close()

    mock_transport.close.assert_called_once()


def test_close_noop_when_no_transport():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGateway(_device_info(), event_listener)
    gw._transport = None
    gw.close()  # must not raise


# ── HidGatewayBT._do_write ──────────────────────────────────────────────────


def test_bt_gateway_uses_write_output_report():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGatewayBT(_bt_device_info(), event_listener)
    mock_transport = MagicMock()
    gw._transport = mock_transport
    gw._connected = True

    msg = bytes([REPORT_LONG]) + bytes(19)
    gw._do_write(msg)

    mock_transport.write_output_report.assert_called_once_with(msg)


# ── HidGatewayBT._set_connected ─────────────────────────────────────────────


def test_bt_gateway_set_connected_synthesizes_connection_event():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGatewayBT(_bt_device_info(pid=0xB023), event_listener)

    gw._set_connected(True)

    event_listener.listen.assert_called_once()
    raw = event_listener.listen.call_args[0][0]
    assert raw[0] == 0x10  # REPORT_SHORT
    assert raw[1] == 0xFF  # slot
    assert raw[2] == 0x41  # Device Connection
    assert (raw[4] & 0x40) == 0  # connected (bit 6 clear)


def test_bt_gateway_set_connected_false_synthesizes_disconnection():
    event_listener = MagicMock(spec=EventListener)
    gw = HidGatewayBT(_bt_device_info(pid=0xB023), event_listener)

    gw._set_connected(False)

    raw = event_listener.listen.call_args[0][0]
    assert (raw[4] & 0x40) == 0x40  # disconnected (bit 6 set)
