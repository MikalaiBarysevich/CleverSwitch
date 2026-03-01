"""Unit tests for monitor helper functions.
#
Covers the stateless helpers and the event-loop entry points
with mocked transport and shutdown controls.
"""
#
from __future__ import annotations
#
import logging
import struct
import threading
#
import pytest
#
from cleverswitch.discovery import DeviceContext, Setup
from cleverswitch.errors import DeviceNotFound
from cleverswitch.hidpp.constants import HOST_SWITCH_CIDS, REPORT_LONG
from cleverswitch.monitor import (
    _close_setup,
    _divert_all_es_keys,
    _fire_startup_hooks,
    _log_retry,
    _monitor_loop,
    _role_for_devnumber,
    _switch,
    run,
)
#
#
# ── Fixtures ──────────────────────────────────────────────────────────────────
#
#
def _make_ctx(transport, role: str, devnumber: int, divert_feat_idx=None) -> DeviceContext:
    return DeviceContext(
        transport=transport,
        devnumber=devnumber,
        change_host_feat_idx=1,
        divert_feat_idx=divert_feat_idx,
        long_msg=False,
        role=role,
        name=role,
        wpid=None,
    )
#
#
def _host_change_raw(devnumber: int, feat_idx: int, cid_byte: int) -> bytes:
    """Build a 20-byte REPORT_LONG HostChangeEvent packet."""
    payload = bytes([feat_idx, 0x00, 0x00, cid_byte]) + bytes(14)
    return struct.pack("!BB18s", REPORT_LONG, devnumber, payload)
#
#
@pytest.fixture
def setup(fake_transport):
    return Setup(
        keyboard=_make_ctx(fake_transport, "keyboard", devnumber=1),
        mouse=_make_ctx(fake_transport, "mouse", devnumber=2),
    )
#
#
# ── _role_for_devnumber() ─────────────────────────────────────────────────────
#
#
def test_role_for_devnumber_returns_keyboard_for_keyboard_device_number(setup):
    assert _role_for_devnumber(1, setup) == "keyboard"
#
#
def test_role_for_devnumber_returns_mouse_for_mouse_device_number(setup):
    assert _role_for_devnumber(2, setup) == "mouse"
#
#
def test_role_for_devnumber_returns_none_for_unknown_device_number(setup):
    assert _role_for_devnumber(99, setup) is None
#
#
def test_role_for_devnumber_distinguishes_between_keyboard_and_mouse_when_they_share_transport(
    make_fake_transport,
):
    # Both devices on the same receiver → devnumber is the only differentiator
    shared_transport = make_fake_transport()
    setup = Setup(
        keyboard=_make_ctx(shared_transport, "keyboard", devnumber=3),
        mouse=_make_ctx(shared_transport, "mouse", devnumber=5),
    )
    assert _role_for_devnumber(3, setup) == "keyboard"
    assert _role_for_devnumber(5, setup) == "mouse"
    assert _role_for_devnumber(1, setup) is None
#
#
# ── _fire_startup_hooks() ─────────────────────────────────────────────────────
#
#
def test_fire_startup_hooks_calls_fire_connect_for_both_devices(mocker, setup, default_cfg):
    mock_fire = mocker.patch("cleverswitch.monitor.hook_runner.fire_connect")
    _fire_startup_hooks(setup, default_cfg)
    assert mock_fire.call_count == 2
#
#
def test_fire_startup_hooks_passes_device_name_and_role(mocker, setup, default_cfg):
    calls = []
    mocker.patch("cleverswitch.monitor.hook_runner.fire_connect", side_effect=lambda cfg, name, role: calls.append((name, role)))
    _fire_startup_hooks(setup, default_cfg)
    names_and_roles = {(name, role) for name, role in calls}
    assert ("keyboard", "keyboard") in names_and_roles
    assert ("mouse", "mouse") in names_and_roles
#
#
# ── _log_retry() ──────────────────────────────────────────────────────────────
#
#
def test_log_retry_emits_warning_with_retry_interval(caplog):
    with caplog.at_level(logging.WARNING, logger="cleverswitch.monitor"):
        _log_retry(DeviceNotFound("keyboard"), 5)
    assert "retrying in 5s" in caplog.text
#
#
# ── _divert_all_es_keys() ─────────────────────────────────────────────────────
#
#
def test_divert_all_es_keys_calls_set_cid_divert_for_each_host_switch_cid(mocker, setup):
    mock_divert = mocker.patch("cleverswitch.monitor.set_cid_divert")
    _divert_all_es_keys(setup.keyboard)
    assert mock_divert.call_count == len(HOST_SWITCH_CIDS)
#
#
def test_divert_all_es_keys_sets_diverted_true(mocker, setup):
    calls = []
    mocker.patch("cleverswitch.monitor.set_cid_divert", side_effect=lambda *a, **kw: calls.append(a))
    _divert_all_es_keys(setup.keyboard)
    # Fifth positional arg is diverted=True
    assert all(args[4] is True for args in calls)
#
#
# ── _switch() ─────────────────────────────────────────────────────────────────
#
#
def test_switch_calls_send_change_host_with_correct_target_host(mocker, setup):
    mock_send = mocker.patch("cleverswitch.monitor.send_change_host")
    _switch(setup.keyboard, target_host=2)
    mock_send.assert_called_once_with(
        setup.keyboard.transport,
        setup.keyboard.devnumber,
        setup.keyboard.change_host_feat_idx,
        2,
        long=setup.keyboard.long_msg,
    )
#
#
# ── _close_setup() ────────────────────────────────────────────────────────────
#
#
def test_close_setup_closes_all_unique_transports(mocker, make_fake_transport):
    mocker.patch("cleverswitch.monitor.set_cid_divert")
    t1, t2 = make_fake_transport(), make_fake_transport()
    kbd = _make_ctx(t1, "keyboard", devnumber=1)
    mouse = _make_ctx(t2, "mouse", devnumber=2)
    setup = Setup(keyboard=kbd, mouse=mouse)
    _close_setup(setup)
    assert t1.closed and t2.closed
#
#
def test_close_setup_calls_set_cid_divert_for_each_diverted_cid(mocker, make_fake_transport):
    mock_divert = mocker.patch("cleverswitch.monitor.set_cid_divert")
    t = make_fake_transport()
    kbd = _make_ctx(t, "keyboard", devnumber=1)
    kbd.reprog_feat_idx = 3
    kbd.diverted_cids = [0x00D1, 0x00D2]
    mouse = _make_ctx(t, "mouse", devnumber=2)
    setup = Setup(keyboard=kbd, mouse=mouse)
    _close_setup(setup)
    assert mock_divert.call_count == 2
#
#
def test_close_setup_handles_exception_during_undivert(mocker, make_fake_transport):
    mocker.patch("cleverswitch.monitor.set_cid_divert", side_effect=OSError("gone"))
    t = make_fake_transport()
    kbd = _make_ctx(t, "keyboard", devnumber=1)
    kbd.reprog_feat_idx = 3
    kbd.diverted_cids = [0x00D1]
    mouse = _make_ctx(t, "mouse", devnumber=2)
    setup = Setup(keyboard=kbd, mouse=mouse)
    # Should not raise; exception is caught internally
    _close_setup(setup)
    assert t.closed
#
#
# ── _monitor_loop() ───────────────────────────────────────────────────────────
#
#
def test_monitor_loop_exits_when_shutdown_is_set_on_second_check(mocker, make_fake_transport, default_cfg):
    # Arrange: shutdown returns False once (enter loop), then True (exit)
    t = make_fake_transport()
    kbd = _make_ctx(t, "keyboard", devnumber=1, divert_feat_idx=5)
    mouse = _make_ctx(t, "mouse", devnumber=2, divert_feat_idx=5)
    setup = Setup(keyboard=kbd, mouse=mouse)
#
    mocker.patch("cleverswitch.monitor._divert_all_es_keys")
    shutdown = threading.Event()
    is_set_calls = [0]
#
    def controlled_is_set():
        is_set_calls[0] += 1
        return is_set_calls[0] > 1  # False on first call, True on second
#
    mocker.patch.object(shutdown, "is_set", side_effect=controlled_is_set)
    _monitor_loop(setup, default_cfg, shutdown)
    assert is_set_calls[0] == 2
#
#
def test_monitor_loop_dispatches_host_change_event_to_both_devices(mocker, make_fake_transport, default_cfg):
    # Arrange: transport returns a valid HostChangeEvent then nothing
    feat_idx = 5
    cid_byte = 0xD1  # maps to host 0 in HOST_SWITCH_CIDS
    t = make_fake_transport()
    kbd = _make_ctx(t, "keyboard", devnumber=1, divert_feat_idx=feat_idx)
    mouse = _make_ctx(t, "mouse", devnumber=2, divert_feat_idx=feat_idx)
    setup = Setup(keyboard=kbd, mouse=mouse)
#
    raw = _host_change_raw(devnumber=1, feat_idx=feat_idx, cid_byte=cid_byte)
    t._responses.append(raw)
#
    mock_switch = mocker.patch("cleverswitch.monitor._switch")
    mocker.patch("cleverswitch.monitor._divert_all_es_keys")
#
    shutdown = threading.Event()
    call_count = [0]
#
    def controlled_is_set():
        call_count[0] += 1
        return call_count[0] > 1
#
    mocker.patch.object(shutdown, "is_set", side_effect=controlled_is_set)
    _monitor_loop(setup, default_cfg, shutdown)
#
    # _switch called once for keyboard and once for mouse
    assert mock_switch.call_count == 2
#
#
# ── run() ─────────────────────────────────────────────────────────────────────
#
#
def test_run_exits_immediately_when_shutdown_is_already_set(mocker, default_cfg):
    mock_discover = mocker.patch("cleverswitch.monitor.discover")
    shutdown = threading.Event()
    shutdown.set()
    run(default_cfg, shutdown)
    mock_discover.assert_not_called()
#
#
def test_run_stops_after_max_retries_on_device_not_found(mocker, make_fake_transport):
    from cleverswitch.config import Config, DeviceConfig, HooksConfig, ReceiverConfig, Settings
    from cleverswitch.hidpp.constants import MX_KEYS_BTID, MX_KEYS_WPID, MX_MASTER_3_BTID, MX_MASTER_3_WPID
#
    cfg = Config(
        receiver=ReceiverConfig(),
        keyboard=DeviceConfig(name="K", wpid=MX_KEYS_WPID, btid=MX_KEYS_BTID),
        mouse=DeviceConfig(name="M", wpid=MX_MASTER_3_WPID, btid=MX_MASTER_3_BTID),
        hooks=HooksConfig(),
        settings=Settings(max_retries=1, retry_interval_s=0),
    )
    mocker.patch("cleverswitch.monitor.discover", side_effect=DeviceNotFound("keyboard"))
    shutdown = threading.Event()
    mocker.patch.object(shutdown, "wait")  # instant wait
    run(cfg, shutdown)
    # Function must return (not loop infinitely) after 1 failed attempt
#
#
def test_run_reconnects_after_transport_error(mocker, make_fake_transport, default_cfg):
    # First discover succeeds; _monitor_loop raises TransportError; second discover raises
    # DeviceNotFound to exit after reconnect attempt.
    t = make_fake_transport()
    kbd = _make_ctx(t, "keyboard", devnumber=1)
    mouse = _make_ctx(t, "mouse", devnumber=2)
    fake_setup = Setup(keyboard=kbd, mouse=mouse)
#
    from cleverswitch.config import Config, DeviceConfig, HooksConfig, ReceiverConfig, Settings
    from cleverswitch.errors import TransportError
    from cleverswitch.hidpp.constants import MX_KEYS_BTID, MX_KEYS_WPID, MX_MASTER_3_BTID, MX_MASTER_3_WPID
#
    cfg = Config(
        receiver=ReceiverConfig(),
        keyboard=DeviceConfig(name="K", wpid=MX_KEYS_WPID, btid=MX_KEYS_BTID),
        mouse=DeviceConfig(name="M", wpid=MX_MASTER_3_WPID, btid=MX_MASTER_3_BTID),
        hooks=HooksConfig(),
        settings=Settings(max_retries=1, retry_interval_s=0),
    )
#
    discover_calls = [0]
#
    def fake_discover(c):
        discover_calls[0] += 1
        if discover_calls[0] == 1:
            return fake_setup
        raise DeviceNotFound("keyboard")
#
    mocker.patch("cleverswitch.monitor.discover", side_effect=fake_discover)
    mocker.patch("cleverswitch.monitor._fire_startup_hooks")
    mocker.patch("cleverswitch.monitor._monitor_loop", side_effect=TransportError("disconnected"))
    mocker.patch("cleverswitch.monitor._close_setup")
    shutdown = threading.Event()
    mocker.patch.object(shutdown, "wait")
    run(cfg, shutdown)
    assert discover_calls[0] == 2
