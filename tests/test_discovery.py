"""Unit tests for device discovery logic.

The higher-level discover() function is tested by patching the hardware-access
layer (find_*_transports, protocol calls).  Pure helpers
(_device_type_to_role, _query_device_info) are tested without mocking.
"""

from __future__ import annotations

import pytest

from cleverswitch.discovery import (
    DeviceContext,
    Setup,
    _device_type_to_role,
    _query_device_info,
    discover,
)
from cleverswitch.hidpp.constants import (
    DEVICE_TYPE_KEYBOARD,
    DEVICE_TYPE_MOUSE,
    DEVICE_TYPE_TRACKBALL,
    DEVICE_TYPE_TRACKPAD,
    FEATURE_CHANGE_HOST,
    FEATURE_DEVICE_TYPE_AND_NAME,
    FEATURE_REPROG_CONTROLS_V4,
)


# ── _device_type_to_role ──────────────────────────────────────────────────────


def test_device_type_to_role_keyboard():
    assert _device_type_to_role(DEVICE_TYPE_KEYBOARD) == "keyboard"


def test_device_type_to_role_mouse():
    assert _device_type_to_role(DEVICE_TYPE_MOUSE) == "mouse"


def test_device_type_to_role_trackball_is_mouse():
    assert _device_type_to_role(DEVICE_TYPE_TRACKBALL) == "mouse"


def test_device_type_to_role_trackpad_is_mouse():
    assert _device_type_to_role(DEVICE_TYPE_TRACKPAD) == "mouse"


def test_device_type_to_role_unknown_returns_none():
    assert _device_type_to_role(7) is None  # Receiver type — not keyboard or mouse


def test_device_type_to_role_none_returns_none():
    assert _device_type_to_role(None) is None


# ── _query_device_info ────────────────────────────────────────────────────────


def test_query_device_info_returns_role_and_name(mocker, fake_transport):
    mocker.patch("cleverswitch.discovery.resolve_feature_index", return_value=2)
    mocker.patch("cleverswitch.discovery.get_device_type", return_value=DEVICE_TYPE_KEYBOARD)
    mocker.patch("cleverswitch.discovery.get_device_name", return_value="MX Keys")
    result = _query_device_info(fake_transport, devnumber=1)
    assert result == ("keyboard", "MX Keys")


def test_query_device_info_falls_back_to_role_when_name_unavailable(mocker, fake_transport):
    mocker.patch("cleverswitch.discovery.resolve_feature_index", return_value=2)
    mocker.patch("cleverswitch.discovery.get_device_type", return_value=DEVICE_TYPE_MOUSE)
    mocker.patch("cleverswitch.discovery.get_device_name", return_value=None)
    result = _query_device_info(fake_transport, devnumber=2)
    assert result == ("mouse", "mouse")


def test_query_device_info_returns_none_when_feature_absent(mocker, fake_transport):
    mocker.patch("cleverswitch.discovery.resolve_feature_index", return_value=None)
    assert _query_device_info(fake_transport, devnumber=1) is None


def test_query_device_info_returns_none_for_unrecognised_device_type(mocker, fake_transport):
    mocker.patch("cleverswitch.discovery.resolve_feature_index", return_value=2)
    mocker.patch("cleverswitch.discovery.get_device_type", return_value=8)  # Headset
    mocker.patch("cleverswitch.discovery.get_device_name", return_value=None)
    assert _query_device_info(fake_transport, devnumber=1) is None


# ── discover ──────────────────────────────────────────────────────────────────


def _fake_resolve_features(t, devnumber, feature_code, long=False):
    return {
        FEATURE_DEVICE_TYPE_AND_NAME: 2,
        FEATURE_CHANGE_HOST: 3,
        FEATURE_REPROG_CONTROLS_V4: 4,
    }.get(feature_code)


def test_discover_returns_none_when_no_receivers_or_bt_devices(mocker):
    # Arrange: no hardware present
    mocker.patch("cleverswitch.discovery.find_receiver_transports", return_value=[])
    mocker.patch("cleverswitch.discovery.find_bluetooth_transports", return_value=[])
    # Act / Assert
    assert discover() is None


def test_discover_returns_setup_when_both_devices_found_via_receiver(mocker, make_fake_transport):
    # Arrange: one receiver contains keyboard in slot 1, mouse in slot 2
    transport = make_fake_transport(kind="bolt")
    mocker.patch("cleverswitch.discovery.find_receiver_transports", return_value=[transport])
    mocker.patch("cleverswitch.discovery.find_bluetooth_transports", return_value=[])

    def _fake_read_wpid(t, slot, kind):
        return {1: 0x1111, 2: 0x2222}.get(slot)

    mocker.patch("cleverswitch.discovery.read_pairing_wpid", side_effect=_fake_read_wpid)
    mocker.patch("cleverswitch.discovery.resolve_feature_index", side_effect=_fake_resolve_features)
    mocker.patch(
        "cleverswitch.discovery.get_device_type",
        side_effect=lambda t, devnumber, feat_idx, long=False: DEVICE_TYPE_KEYBOARD if devnumber == 1 else DEVICE_TYPE_MOUSE,
    )
    mocker.patch("cleverswitch.discovery.get_device_name", return_value=None)
    mocker.patch("cleverswitch.discovery.get_change_host_info", return_value=(3, 0))

    setup = discover()

    kbd = next(d for d in setup.devices if d.role == "keyboard")
    mouse = next(d for d in setup.devices if d.role == "mouse")
    assert kbd.name == "keyboard"
    assert mouse.name == "mouse"


def test_discover_stores_fetched_device_name_in_context(mocker, make_fake_transport):
    # Arrange: name query returns a real marketing name
    transport = make_fake_transport(kind="bolt")
    mocker.patch("cleverswitch.discovery.find_receiver_transports", return_value=[transport])
    mocker.patch("cleverswitch.discovery.find_bluetooth_transports", return_value=[])

    def _fake_read_wpid(t, slot, kind):
        return {1: 0x1111, 2: 0x2222}.get(slot)

    mocker.patch("cleverswitch.discovery.read_pairing_wpid", side_effect=_fake_read_wpid)
    mocker.patch("cleverswitch.discovery.resolve_feature_index", side_effect=_fake_resolve_features)
    mocker.patch(
        "cleverswitch.discovery.get_device_type",
        side_effect=lambda t, devnumber, feat_idx, long=False: DEVICE_TYPE_KEYBOARD if devnumber == 1 else DEVICE_TYPE_MOUSE,
    )
    mocker.patch(
        "cleverswitch.discovery.get_device_name",
        side_effect=lambda t, devnumber, feat_idx, long=False: "MX Keys" if devnumber == 1 else "MX Master 3",
    )
    mocker.patch("cleverswitch.discovery.get_change_host_info", return_value=(3, 0))

    setup = discover()

    kbd = next(d for d in setup.devices if d.role == "keyboard")
    mouse = next(d for d in setup.devices if d.role == "mouse")
    assert kbd.name == "MX Keys"
    assert mouse.name == "MX Master 3"


def test_discover_returns_none_when_only_keyboard_is_present(mocker, make_fake_transport):
    # Arrange: receiver only has keyboard; mouse is absent
    transport = make_fake_transport(kind="bolt")
    mocker.patch("cleverswitch.discovery.find_receiver_transports", return_value=[transport])
    mocker.patch("cleverswitch.discovery.find_bluetooth_transports", return_value=[])

    def _fake_read_wpid(t, slot, kind):
        return 0x1111 if slot == 1 else None

    mocker.patch("cleverswitch.discovery.read_pairing_wpid", side_effect=_fake_read_wpid)
    mocker.patch("cleverswitch.discovery.resolve_feature_index", side_effect=_fake_resolve_features)
    mocker.patch("cleverswitch.discovery.get_device_type", return_value=DEVICE_TYPE_KEYBOARD)
    mocker.patch("cleverswitch.discovery.get_device_name", return_value=None)
    mocker.patch("cleverswitch.discovery.get_change_host_info", return_value=(3, 0))

    assert discover() is None


def test_discover_falls_back_to_bluetooth_when_receiver_scan_finds_nothing(
    mocker, make_fake_transport
):
    # Arrange: no receiver; both devices on Bluetooth
    mocker.patch("cleverswitch.discovery.find_receiver_transports", return_value=[])
    mocker.patch(
        "cleverswitch.discovery.find_bluetooth_transports",
        return_value=[
            (make_fake_transport(kind="bluetooth"), 0xB999),
            (make_fake_transport(kind="bluetooth"), 0xB888),
        ],
    )
    mocker.patch("cleverswitch.discovery.resolve_feature_index", side_effect=_fake_resolve_features)

    call_count = {"n": 0}

    def _fake_device_type(t, devnumber, feat_idx, long=False):
        call_count["n"] += 1
        return DEVICE_TYPE_KEYBOARD if call_count["n"] == 1 else DEVICE_TYPE_MOUSE

    mocker.patch("cleverswitch.discovery.get_device_type", side_effect=_fake_device_type)
    mocker.patch("cleverswitch.discovery.get_device_name", return_value=None)
    mocker.patch("cleverswitch.discovery.get_change_host_info", return_value=(3, 0))

    setup = discover()

    roles = {d.role for d in setup.devices}
    assert "keyboard" in roles
    assert "mouse" in roles


def test_discover_auto_identifies_keyboard_and_mouse_via_device_type(mocker, make_fake_transport):
    # Arrange: receiver with two unknown wpids; device type reveals roles
    transport = make_fake_transport(kind="bolt")
    mocker.patch("cleverswitch.discovery.find_receiver_transports", return_value=[transport])
    mocker.patch("cleverswitch.discovery.find_bluetooth_transports", return_value=[])

    def _fake_read_wpid(t, slot, kind):
        return {1: 0x1111, 2: 0x2222}.get(slot)

    mocker.patch("cleverswitch.discovery.read_pairing_wpid", side_effect=_fake_read_wpid)
    mocker.patch("cleverswitch.discovery.resolve_feature_index", side_effect=_fake_resolve_features)
    mocker.patch(
        "cleverswitch.discovery.get_device_type",
        side_effect=lambda t, devnumber, feat_idx, long=False: DEVICE_TYPE_KEYBOARD if devnumber == 1 else DEVICE_TYPE_MOUSE,
    )
    mocker.patch("cleverswitch.discovery.get_device_name", return_value=None)
    mocker.patch("cleverswitch.discovery.get_change_host_info", return_value=(3, 0))

    setup = discover()

    kbd = next(d for d in setup.devices if d.role == "keyboard")
    mouse = next(d for d in setup.devices if d.role == "mouse")
    assert kbd.devnumber == 1
    assert mouse.devnumber == 2


def test_discover_auto_identifies_trackball_as_mouse(mocker, make_fake_transport):
    # Arrange: receiver with one keyboard and one trackball
    transport = make_fake_transport(kind="bolt")
    mocker.patch("cleverswitch.discovery.find_receiver_transports", return_value=[transport])
    mocker.patch("cleverswitch.discovery.find_bluetooth_transports", return_value=[])

    def _fake_read_wpid(t, slot, kind):
        return {1: 0xAAAA, 2: 0xBBBB}.get(slot)

    mocker.patch("cleverswitch.discovery.read_pairing_wpid", side_effect=_fake_read_wpid)
    mocker.patch("cleverswitch.discovery.resolve_feature_index", side_effect=_fake_resolve_features)
    mocker.patch(
        "cleverswitch.discovery.get_device_type",
        side_effect=lambda t, devnumber, feat_idx, long=False: DEVICE_TYPE_KEYBOARD if devnumber == 1 else DEVICE_TYPE_TRACKBALL,
    )
    mocker.patch("cleverswitch.discovery.get_device_name", return_value=None)
    mocker.patch("cleverswitch.discovery.get_change_host_info", return_value=(3, 0))

    setup = discover()

    roles = {d.role for d in setup.devices}
    assert "keyboard" in roles
    assert "mouse" in roles


def test_discover_auto_skips_device_with_unrecognised_type(mocker, make_fake_transport):
    # Arrange: slot 1 = headset (type 8), slot 2 = keyboard, slot 3 = mouse
    transport = make_fake_transport(kind="bolt")
    mocker.patch("cleverswitch.discovery.find_receiver_transports", return_value=[transport])
    mocker.patch("cleverswitch.discovery.find_bluetooth_transports", return_value=[])

    def _fake_read_wpid(t, slot, kind):
        return {1: 0xCCCC, 2: 0x1111, 3: 0x2222}.get(slot)

    mocker.patch("cleverswitch.discovery.read_pairing_wpid", side_effect=_fake_read_wpid)
    mocker.patch("cleverswitch.discovery.resolve_feature_index", side_effect=_fake_resolve_features)

    type_map = {1: 8, 2: DEVICE_TYPE_KEYBOARD, 3: DEVICE_TYPE_MOUSE}  # 8=Headset
    mocker.patch(
        "cleverswitch.discovery.get_device_type",
        side_effect=lambda t, devnumber, feat_idx, long=False: type_map.get(devnumber),
    )
    mocker.patch("cleverswitch.discovery.get_device_name", return_value=None)
    mocker.patch("cleverswitch.discovery.get_change_host_info", return_value=(3, 0))

    setup = discover()

    roles = {d.role for d in setup.devices}
    assert "keyboard" in roles
    assert "mouse" in roles


def test_discover_auto_returns_none_when_device_type_not_supported(mocker, make_fake_transport):
    # Arrange: wpid is unknown and x0005 feature is absent for all slots
    transport = make_fake_transport(kind="bolt")
    mocker.patch("cleverswitch.discovery.find_receiver_transports", return_value=[transport])
    mocker.patch("cleverswitch.discovery.find_bluetooth_transports", return_value=[])

    mocker.patch("cleverswitch.discovery.read_pairing_wpid", return_value=0x9999)
    # Neither DEVICE_TYPE_AND_NAME nor anything else resolves → None everywhere
    mocker.patch("cleverswitch.discovery.resolve_feature_index", return_value=None)

    assert discover() is None


def test_discover_auto_identifies_bt_devices_by_device_type(mocker, make_fake_transport):
    # Arrange: no receiver; BT devices identified only by device type
    mocker.patch("cleverswitch.discovery.find_receiver_transports", return_value=[])
    mocker.patch(
        "cleverswitch.discovery.find_bluetooth_transports",
        return_value=[
            (make_fake_transport(kind="bluetooth"), 0xB999),  # unknown btid
            (make_fake_transport(kind="bluetooth"), 0xB888),  # unknown btid
        ],
    )
    mocker.patch("cleverswitch.discovery.resolve_feature_index", side_effect=_fake_resolve_features)

    call_count = {"n": 0}

    def _fake_device_type(t, devnumber, feat_idx, long=False):
        call_count["n"] += 1
        return DEVICE_TYPE_KEYBOARD if call_count["n"] == 1 else DEVICE_TYPE_MOUSE

    mocker.patch("cleverswitch.discovery.get_device_type", side_effect=_fake_device_type)
    mocker.patch("cleverswitch.discovery.get_device_name", return_value=None)
    mocker.patch("cleverswitch.discovery.get_change_host_info", return_value=(3, 0))

    setup = discover()

    roles = {d.role for d in setup.devices}
    assert "keyboard" in roles
    assert "mouse" in roles
