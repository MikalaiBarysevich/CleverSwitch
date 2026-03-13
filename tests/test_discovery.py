"""Unit tests for discovery.py — background device discovery loop."""

from __future__ import annotations

import threading

import pytest

from cleverswitch.discovery import discover
from cleverswitch.hidpp.constants import BOLT_PID
from cleverswitch.hidpp.transport import HidDeviceInfo


def _receiver_device(path=b"/dev/hidraw0"):
    return HidDeviceInfo(path=path, vid=0x046D, pid=BOLT_PID, usage_page=0xFF00, usage=0x0002, connection_type="receiver")


def _bt_device(path=b"/dev/hidraw1", pid=0xB023):
    return HidDeviceInfo(path=path, vid=0x046D, pid=pid, usage_page=0xFF43, usage=0x0202, connection_type="bluetooth")


def test_discover_returns_immediately_when_shutdown_is_already_set(mocker):
    mocker.patch("cleverswitch.discovery.enumerate_hid_devices", return_value=[])
    shutdown = threading.Event()
    shutdown.set()
    discover(shutdown)  # must return without hanging


def test_discover_creates_receiver_listener_for_receiver_device(mocker):
    device = _receiver_device()

    mocker.patch("cleverswitch.discovery.enumerate_hid_devices", return_value=[device])

    mock_listener = mocker.MagicMock()
    mock_listener_cls = mocker.patch("cleverswitch.discovery.ReceiverListener", return_value=mock_listener)
    mocker.patch("cleverswitch.discovery.BTListener")

    shutdown = threading.Event()

    def fake_wait(timeout):
        shutdown.set()

    shutdown.wait = fake_wait

    discover(shutdown)

    mock_listener_cls.assert_called_once()
    assert mock_listener_cls.call_args[0][0] is device
    mock_listener.start.assert_called_once()


def test_discover_creates_bt_listener_for_bluetooth_device(mocker):
    device = _bt_device()

    mocker.patch("cleverswitch.discovery.enumerate_hid_devices", return_value=[device])

    mock_listener = mocker.MagicMock()
    mocker.patch("cleverswitch.discovery.ReceiverListener")
    mock_bt_cls = mocker.patch("cleverswitch.discovery.BTListener", return_value=mock_listener)

    shutdown = threading.Event()

    def fake_wait(timeout):
        shutdown.set()

    shutdown.wait = fake_wait

    discover(shutdown)

    mock_bt_cls.assert_called_once()
    assert mock_bt_cls.call_args[0][0] is device
    mock_listener.start.assert_called_once()


def test_discover_does_not_create_duplicate_listeners_for_same_device(mocker):
    device = _receiver_device()

    mocker.patch("cleverswitch.discovery.enumerate_hid_devices", return_value=[device])

    mock_listener = mocker.MagicMock()
    mock_listener_cls = mocker.patch("cleverswitch.discovery.ReceiverListener", return_value=mock_listener)
    mocker.patch("cleverswitch.discovery.BTListener")

    shutdown = threading.Event()
    wait_count = [0]

    def fake_wait(timeout):
        wait_count[0] += 1
        if wait_count[0] >= 2:
            shutdown.set()

    shutdown.wait = fake_wait

    discover(shutdown)

    assert mock_listener_cls.call_count == 1


def test_discover_joins_listeners_on_shutdown(mocker):
    device = _receiver_device()
    mocker.patch("cleverswitch.discovery.enumerate_hid_devices", return_value=[device])

    mock_listener = mocker.MagicMock()
    mocker.patch("cleverswitch.discovery.ReceiverListener", return_value=mock_listener)
    mocker.patch("cleverswitch.discovery.BTListener")

    shutdown = threading.Event()

    def fake_wait(timeout):
        shutdown.set()

    shutdown.wait = fake_wait

    discover(shutdown)

    mock_listener.join.assert_called_once()


def test_discover_removes_dead_listener_and_recreates(mocker):
    device = _receiver_device()

    mocker.patch("cleverswitch.discovery.enumerate_hid_devices", return_value=[device])

    call_count = [0]
    listeners = []

    def make_listener(*args, **kwargs):
        call_count[0] += 1
        mock = mocker.MagicMock()
        # First listener is dead on second iteration
        mock.is_alive.return_value = call_count[0] > 1
        listeners.append(mock)
        return mock

    mocker.patch("cleverswitch.discovery.ReceiverListener", side_effect=make_listener)
    mocker.patch("cleverswitch.discovery.BTListener")

    shutdown = threading.Event()
    wait_count = [0]

    def fake_wait(timeout):
        wait_count[0] += 1
        if wait_count[0] >= 3:
            shutdown.set()

    shutdown.wait = fake_wait

    discover(shutdown)

    # First listener was dead, so a second was created
    assert call_count[0] == 2
    listeners[0].stop.assert_called_once()
