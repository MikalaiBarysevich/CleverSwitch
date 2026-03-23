"""Unit tests for discovery.py — background device discovery loop."""

from __future__ import annotations

import threading

from cleverswitch.config import default_config
from cleverswitch.discovery import BTDeviceCache, discover
from cleverswitch.hidpp.constants import BOLT_PID
from cleverswitch.hidpp.transport import HidDeviceInfo
from cleverswitch.model import CachedBTDevice

_CFG = default_config()


def _receiver_device(path=b"/dev/hidraw0"):
    return HidDeviceInfo(
        path=path, vid=0x046D, pid=BOLT_PID, usage_page=0xFF00, usage=0x0002, connection_type="receiver"
    )


def _bt_device(path=b"/dev/hidraw1", pid=0xB023):
    return HidDeviceInfo(path=path, vid=0x046D, pid=pid, usage_page=0xFF43, usage=0x0202, connection_type="bluetooth")


def test_discover_returns_immediately_when_shutdown_is_already_set(mocker):
    mocker.patch("cleverswitch.discovery.enumerate_hid_devices", return_value=[])
    shutdown = threading.Event()
    shutdown.set()
    discover(_CFG, shutdown)  # must return without hanging


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

    discover(_CFG, shutdown)

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

    discover(_CFG, shutdown)

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

    discover(_CFG, shutdown)

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

    discover(_CFG, shutdown)

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

    discover(_CFG, shutdown)

    # First listener was dead, so a second was created
    assert call_count[0] == 2
    listeners[0].stop.assert_called_once()


def test_discover_passes_bt_cache_to_bt_listener(mocker):
    """discover() creates one BTDeviceCache and passes it to every BTListener."""
    device = _bt_device()
    mocker.patch("cleverswitch.discovery.enumerate_hid_devices", return_value=[device])

    mock_listener = mocker.MagicMock()
    mocker.patch("cleverswitch.discovery.ReceiverListener")
    mock_bt_cls = mocker.patch("cleverswitch.discovery.BTListener", return_value=mock_listener)

    shutdown = threading.Event()

    def fake_wait(timeout):
        shutdown.set()

    shutdown.wait = fake_wait

    discover(_CFG, shutdown)

    call_kwargs = mock_bt_cls.call_args[1]
    assert "bt_cache" in call_kwargs
    assert isinstance(call_kwargs["bt_cache"], BTDeviceCache)


# ── BTDeviceCache ─────────────────────────────────────────────────────────────


def _make_cached_entry(pid=0xB023) -> CachedBTDevice:
    return CachedBTDevice(
        pid=pid,
        role="keyboard",
        name="MX Keys",
        change_host_feat_idx=3,
        divert_feat_idx=5,
        hosts_info_feat_idx=None,
    )


def test_bt_device_cache_get_returns_none_when_empty():
    cache = BTDeviceCache()
    assert cache.get(0xB023) is None


def test_bt_device_cache_put_then_get_returns_entry():
    cache = BTDeviceCache()
    entry = _make_cached_entry(pid=0xB023)
    cache.put(entry)
    assert cache.get(0xB023) is entry


def test_bt_device_cache_get_returns_none_for_unknown_pid():
    cache = BTDeviceCache()
    entry = _make_cached_entry(pid=0xB023)
    cache.put(entry)
    assert cache.get(0xB024) is None


def test_bt_device_cache_put_overwrites_existing_entry():
    cache = BTDeviceCache()
    first = _make_cached_entry(pid=0xB023)
    cache.put(first)
    second = CachedBTDevice(
        pid=0xB023, role="mouse", name="MX Anywhere", change_host_feat_idx=4, divert_feat_idx=None, hosts_info_feat_idx=None
    )
    cache.put(second)
    assert cache.get(0xB023) is second
