"""Unit tests for device discovery logic.

Pure helpers (_role_for_wpid, _role_for_btid, Setup.unique_transports) are
tested without any mocking.  The higher-level discover() function is tested
by patching the hardware-access layer (find_*_transports, protocol calls).
"""

from __future__ import annotations

import pytest

from cleverswitch.discovery import (
    DeviceContext,
    Setup,
    _role_for_btid,
    _role_for_wpid,
    discover,
)
from cleverswitch.errors import DeviceNotFound
from cleverswitch.hidpp.constants import (
    MX_KEYS_BTID,
    MX_KEYS_WPID,
    MX_MASTER_3_BTID,
    MX_MASTER_3_WPID,
)


# ── _role_for_wpid ────────────────────────────────────────────────────────────


def test_role_for_wpid_identifies_keyboard_by_wpid(default_cfg):
    assert _role_for_wpid(MX_KEYS_WPID, default_cfg) == "keyboard"


def test_role_for_wpid_identifies_mouse_by_wpid(default_cfg):
    assert _role_for_wpid(MX_MASTER_3_WPID, default_cfg) == "mouse"


def test_role_for_wpid_returns_none_for_unknown_wpid(default_cfg):
    assert _role_for_wpid(0xFFFF, default_cfg) is None


# ── _role_for_btid ────────────────────────────────────────────────────────────


def test_role_for_btid_identifies_keyboard_by_btid(default_cfg):
    assert _role_for_btid(MX_KEYS_BTID, default_cfg) == "keyboard"


def test_role_for_btid_identifies_mouse_by_btid(default_cfg):
    assert _role_for_btid(MX_MASTER_3_BTID, default_cfg) == "mouse"


def test_role_for_btid_returns_none_for_unknown_btid(default_cfg):
    assert _role_for_btid(0xFFFF, default_cfg) is None


# ── Setup.unique_transports ───────────────────────────────────────────────────


def _make_ctx(transport, role: str) -> DeviceContext:
    """Build a minimal DeviceContext pointing at the given transport."""
    return DeviceContext(
        transport=transport,
        devnumber=1,
        change_host_feat_idx=1,
        divert_feat_idx=None,
        long_msg=False,
        role=role,
        name=role,
        wpid=None,
    )


def test_unique_transports_deduplicates_when_both_devices_share_a_receiver(fake_transport):
    # Arrange: both devices are on the same physical receiver
    setup = Setup(
        keyboard=_make_ctx(fake_transport, "keyboard"),
        mouse=_make_ctx(fake_transport, "mouse"),
    )
    # Act
    result = setup.unique_transports()
    # Assert: only one transport returned
    assert result == [fake_transport]


def test_unique_transports_returns_all_transports_when_devices_are_on_different_receivers(
    make_fake_transport,
):
    # Arrange: keyboard on receiver A, mouse on receiver B
    transport_a = make_fake_transport(kind="bolt")
    transport_b = make_fake_transport(kind="unifying")
    setup = Setup(
        keyboard=_make_ctx(transport_a, "keyboard"),
        mouse=_make_ctx(transport_b, "mouse"),
    )
    # Act
    result = setup.unique_transports()
    # Assert
    assert len(result) == 2
    assert transport_a in result
    assert transport_b in result


# ── discover ──────────────────────────────────────────────────────────────────


def test_discover_raises_device_not_found_when_no_receivers_or_bt_devices(mocker, default_cfg):
    # Arrange: no hardware present
    mocker.patch("cleverswitch.discovery.find_receiver_transports", return_value=[])
    mocker.patch("cleverswitch.discovery.find_bluetooth_transports", return_value=[])
    # Act / Assert
    with pytest.raises(DeviceNotFound):
        discover(default_cfg)


def test_discover_returns_setup_when_both_devices_found_via_receiver(mocker, default_cfg, make_fake_transport):
    # Arrange: one receiver contains keyboard in slot 1, mouse in slot 2
    transport = make_fake_transport(kind="bolt")
    mocker.patch("cleverswitch.discovery.find_receiver_transports", return_value=[transport])
    mocker.patch("cleverswitch.discovery.find_bluetooth_transports", return_value=[])

    def _fake_read_wpid(t, slot, kind):
        return {1: MX_KEYS_WPID, 2: MX_MASTER_3_WPID}.get(slot)

    mocker.patch("cleverswitch.discovery.read_pairing_wpid", side_effect=_fake_read_wpid)
    # resolve_feature_index is called twice for keyboard (CHANGE_HOST + REPROG_CONTROLS),
    # once for mouse (CHANGE_HOST only); return index 1 for all
    mocker.patch("cleverswitch.discovery.resolve_feature_index", return_value=1)
    mocker.patch("cleverswitch.discovery.get_change_host_info", return_value=(3, 0))

    # Act
    setup = discover(default_cfg)

    # Assert
    assert setup.keyboard.role == "keyboard"
    assert setup.keyboard.name == "MX Keys"
    assert setup.mouse.role == "mouse"
    assert setup.mouse.name == "MX Master 3"


def test_discover_raises_device_not_found_when_only_keyboard_is_present(mocker, default_cfg, make_fake_transport):
    # Arrange: receiver only has keyboard; mouse is absent
    transport = make_fake_transport(kind="bolt")
    mocker.patch("cleverswitch.discovery.find_receiver_transports", return_value=[transport])
    mocker.patch("cleverswitch.discovery.find_bluetooth_transports", return_value=[])

    def _fake_read_wpid(t, slot, kind):
        return MX_KEYS_WPID if slot == 1 else None

    mocker.patch("cleverswitch.discovery.read_pairing_wpid", side_effect=_fake_read_wpid)
    mocker.patch("cleverswitch.discovery.resolve_feature_index", return_value=1)
    mocker.patch("cleverswitch.discovery.get_change_host_info", return_value=(3, 0))

    # Act / Assert
    with pytest.raises(DeviceNotFound):
        discover(default_cfg)


def test_discover_falls_back_to_bluetooth_when_receiver_scan_finds_nothing(
    mocker, default_cfg, make_fake_transport
):
    # Arrange: no receiver; mouse on Bluetooth, keyboard also on Bluetooth
    bt_transport = make_fake_transport(kind="bluetooth")
    mocker.patch("cleverswitch.discovery.find_receiver_transports", return_value=[])
    mocker.patch(
        "cleverswitch.discovery.find_bluetooth_transports",
        return_value=[
            (make_fake_transport(kind="bluetooth"), MX_KEYS_BTID),
            (make_fake_transport(kind="bluetooth"), MX_MASTER_3_BTID),
        ],
    )
    mocker.patch("cleverswitch.discovery.resolve_feature_index", return_value=1)
    mocker.patch("cleverswitch.discovery.get_change_host_info", return_value=(3, 0))

    # Act
    setup = discover(default_cfg)

    # Assert
    assert setup.keyboard.role == "keyboard"
    assert setup.mouse.role == "mouse"
