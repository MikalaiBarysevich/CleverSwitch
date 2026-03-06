"""Unit tests for discovery.py — background device discovery loop."""

from __future__ import annotations

import threading

import pytest

from cleverswitch.discovery import discover
from cleverswitch.hidpp.constants import BOLT_PID
from cleverswitch.hidpp.transport import HidDeviceInfo


def test_discover_returns_immediately_when_shutdown_is_already_set(mocker):
    mocker.patch("cleverswitch.discovery.enumerate_hid_devices", return_value=[])
    shutdown = threading.Event()
    shutdown.set()
    discover(shutdown)  # must return without hanging


def test_discover_creates_listener_for_each_new_device(mocker):
    device = HidDeviceInfo(path=b"/dev/hidraw0", vid=0x046D, pid=BOLT_PID, usage_page=0xFF00, usage=1)

    enumerate_calls = [0]

    def fake_enumerate():
        enumerate_calls[0] += 1
        return [device]

    mocker.patch("cleverswitch.discovery.enumerate_hid_devices", side_effect=fake_enumerate)

    mock_listener = mocker.MagicMock()
    mock_listener_cls = mocker.patch("cleverswitch.discovery.PathListener", return_value=mock_listener)

    shutdown = threading.Event()

    def fake_wait(timeout):
        shutdown.set()

    shutdown.wait = fake_wait

    discover(shutdown)

    mock_listener_cls.assert_called_once_with(device, shutdown)
    mock_listener.start.assert_called_once()


def test_discover_does_not_create_duplicate_listeners_for_same_device(mocker):
    device = HidDeviceInfo(path=b"/dev/hidraw0", vid=0x046D, pid=BOLT_PID, usage_page=0xFF00, usage=1)

    call_count = [0]

    def fake_enumerate():
        call_count[0] += 1
        return [device]

    mocker.patch("cleverswitch.discovery.enumerate_hid_devices", side_effect=fake_enumerate)

    mock_listener = mocker.MagicMock()
    mock_listener_cls = mocker.patch("cleverswitch.discovery.PathListener", return_value=mock_listener)

    shutdown = threading.Event()
    wait_count = [0]

    def fake_wait(timeout):
        wait_count[0] += 1
        if wait_count[0] >= 2:
            shutdown.set()

    shutdown.wait = fake_wait

    discover(shutdown)

    # Even though enumerate ran twice, the listener is created only once
    assert mock_listener_cls.call_count == 1


def test_discover_joins_listeners_on_shutdown(mocker):
    device = HidDeviceInfo(path=b"/dev/hidraw0", vid=0x046D, pid=BOLT_PID, usage_page=0xFF00, usage=1)
    mocker.patch("cleverswitch.discovery.enumerate_hid_devices", return_value=[device])

    mock_listener = mocker.MagicMock()
    mocker.patch("cleverswitch.discovery.PathListener", return_value=mock_listener)

    shutdown = threading.Event()

    def fake_wait(timeout):
        shutdown.set()

    shutdown.wait = fake_wait

    discover(shutdown)

    mock_listener.join.assert_called_once()
