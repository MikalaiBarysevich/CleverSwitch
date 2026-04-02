"""Unit tests for registry/logi_device_registry.py."""

from __future__ import annotations

from cleverswitch.hidpp.constants import BOLT_PID
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry


def _make_device(wpid=0x407B, slot=1, role="keyboard"):
    return LogiDevice(wpid=wpid, pid=BOLT_PID, slot=slot, role=role, available_features={})


def test_register_and_all_entries():
    registry = LogiDeviceRegistry()
    device = _make_device()
    registry.register(0x407B, device)
    assert registry.all_entries() == [device]


def test_unregister():
    registry = LogiDeviceRegistry()
    device = _make_device()
    registry.register(0x407B, device)
    registry.unregister(0x407B)
    assert registry.all_entries() == []


def test_unregister_nonexistent_key():
    registry = LogiDeviceRegistry()
    registry.unregister(0x9999)  # must not raise


def test_get_by_wpid_found():
    registry = LogiDeviceRegistry()
    device = _make_device()
    registry.register(0x407B, device)
    assert registry.get_by_wpid(0x407B) is device


def test_get_by_wpid_not_found():
    registry = LogiDeviceRegistry()
    assert registry.get_by_wpid(0x9999) is None


def test_register_overwrites_existing():
    registry = LogiDeviceRegistry()
    device1 = _make_device(role="keyboard")
    device2 = _make_device(role="mouse")
    registry.register(0x407B, device1)
    registry.register(0x407B, device2)
    assert registry.get_by_wpid(0x407B).role == "mouse"
    assert len(registry.all_entries()) == 1
