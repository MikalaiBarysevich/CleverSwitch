"""Unit tests for discovery/link_factory.py."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from cleverswitch.discovery.link_factory import create_link
from cleverswitch.gateway.gatt_channel import GattChannel
from cleverswitch.gateway.write_router import ReportIdWriteRouter, WriteRouter
from cleverswitch.hidpp.constants import BOLT_PID, CONNECTION_BLUETOOTH, CONNECTION_RECEIVER
from cleverswitch.hidpp.transport import HidDeviceInfo
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics
from cleverswitch.util.util import SYSTEM_LINUX, SYSTEM_MACOS, SYSTEM_WINDOWS

BT_PID = 0xB023


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _receiver(usage=0x0002):
    return HidDeviceInfo(
        path=b"/dev/hidraw0",
        vid=0x046D,
        pid=BOLT_PID,
        usage_page=0xFF00,
        usage=usage,
        connection_type=CONNECTION_RECEIVER,
    )


def _bluetooth():
    return HidDeviceInfo(
        path=b"/dev/hidraw1",
        vid=0x046D,
        pid=BT_PID,
        usage_page=0xFF43,
        usage=0x0202,
        connection_type=CONNECTION_BLUETOOTH,
    )


def _system(mocker, name):
    mocker.patch("cleverswitch.discovery.link_factory.get_system", return_value=name)


def _ble_ok(mocker, ok):
    mocker.patch("cleverswitch.gateway.gatt_channel._BLE_OK", ok)


@pytest.mark.parametrize("system", [SYSTEM_LINUX, SYSTEM_MACOS, SYSTEM_WINDOWS])
def test_receiver_gets_one_hid_channel_per_collection_and_no_gatt(mocker, system):
    _system(mocker, system)
    link = create_link(BOLT_PID, [_receiver(0x0001), _receiver(0x0002)], _make_topics())
    assert len(link._hid_channels) == 2
    assert not any(g._use_output_report for g in link._hid_channels)
    assert link._gatt is None
    assert link._connection_type == CONNECTION_RECEIVER


def test_bluetooth_on_linux_writes_output_reports_without_gatt(mocker):
    _system(mocker, SYSTEM_LINUX)
    link = create_link(BT_PID, [_bluetooth()], _make_topics())
    assert [g._use_output_report for g in link._hid_channels] == [True]
    assert link._gatt is None
    assert link._connection_type == CONNECTION_BLUETOOTH


def test_bluetooth_on_darwin_adds_gatt_channel(mocker):
    _system(mocker, SYSTEM_MACOS)
    _ble_ok(mocker, True)
    link = create_link(BT_PID, [_bluetooth()], _make_topics())
    assert isinstance(link._gatt, GattChannel)
    assert link._gatt._pid == BT_PID
    assert link._gatt._on_report == link._listener.listen
    assert link._gatt._on_state == link.on_gatt_state


def test_bluetooth_on_darwin_without_bleak_is_hid_only(mocker, caplog):
    _system(mocker, SYSTEM_MACOS)
    _ble_ok(mocker, False)
    with caplog.at_level(logging.WARNING):
        link = create_link(BT_PID, [_bluetooth()], _make_topics())
    assert link._gatt is None
    assert any("BLE notify path disabled" in r.message for r in caplog.records)


def test_hid_channel_report_state_to_the_link(mocker):
    _system(mocker, SYSTEM_LINUX)
    link = create_link(BOLT_PID, [_receiver()], _make_topics())
    assert link._hid_channels[0]._on_state_changed == link.on_hid_state_changed


def test_windows_routes_by_report_id(mocker):
    _system(mocker, SYSTEM_WINDOWS)
    link = create_link(BOLT_PID, [_receiver()], _make_topics())
    assert isinstance(link._router, ReportIdWriteRouter)


@pytest.mark.parametrize("system", [SYSTEM_LINUX, SYSTEM_MACOS])
def test_other_platforms_use_default_router(mocker, system):
    _system(mocker, system)
    link = create_link(BOLT_PID, [_receiver()], _make_topics())
    assert type(link._router) is WriteRouter


def test_hid_channel_share_the_link_listener(mocker):
    _system(mocker, SYSTEM_WINDOWS)
    link = create_link(BOLT_PID, [_receiver(0x0001), _receiver(0x0002)], _make_topics())
    assert all(g._event_listener is link._listener for g in link._hid_channels)


def test_link_subscribes_to_write_topic(mocker):
    _system(mocker, SYSTEM_LINUX)
    topics = _make_topics()
    link = create_link(BOLT_PID, [_receiver()], topics)
    topics.write.subscribe.assert_called_once_with(link)
