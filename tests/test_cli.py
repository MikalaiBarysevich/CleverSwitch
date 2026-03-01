"""Unit tests for the CLI entry point."""

from __future__ import annotations

import logging
import sys

import pytest

from cleverswitch.cli import _dry_run, _parse_args, _setup_logging, main
from cleverswitch.errors import CleverSwitchError, ConfigError


# ── _parse_args() ─────────────────────────────────────────────────────────────


def test_parse_args_defaults_when_no_arguments_given(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cleverswitch"])
    args = _parse_args()
    assert args.config is None
    assert args.verbose is False
    assert args.dry_run is False


def test_parse_args_captures_config_file_path(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cleverswitch", "-c", "/etc/cleverswitch.yaml"])
    args = _parse_args()
    assert args.config == "/etc/cleverswitch.yaml"


def test_parse_args_captures_long_form_config_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cleverswitch", "--config", "/etc/cs.yaml"])
    args = _parse_args()
    assert args.config == "/etc/cs.yaml"


def test_parse_args_enables_verbose_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cleverswitch", "-v"])
    args = _parse_args()
    assert args.verbose is True


def test_parse_args_enables_dry_run_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cleverswitch", "--dry-run"])
    args = _parse_args()
    assert args.dry_run is True


# ── _setup_logging() ──────────────────────────────────────────────────────────


def test_setup_logging_uses_provided_level_when_not_verbose(mocker):
    mock_basic = mocker.patch("cleverswitch.cli.logging.basicConfig")
    _setup_logging("WARNING", verbose=False)
    assert mock_basic.call_args[1]["level"] == logging.WARNING


def test_setup_logging_overrides_to_debug_when_verbose_is_true(mocker):
    mock_basic = mocker.patch("cleverswitch.cli.logging.basicConfig")
    _setup_logging("INFO", verbose=True)
    # verbose flag forces DEBUG regardless of the provided level
    assert mock_basic.call_args[1]["level"] == logging.DEBUG


# ── main() ────────────────────────────────────────────────────────────────────


def test_main_exits_with_code_1_and_prints_error_on_config_error(mocker, monkeypatch, capsys):
    # Arrange
    monkeypatch.setattr(sys, "argv", ["cleverswitch"])
    mocker.patch("cleverswitch.cli.cfg_module.load", side_effect=ConfigError("bad log_level"))
    # Act / Assert
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "bad log_level" in capsys.readouterr().err


def test_main_calls_dry_run_and_returns_when_dry_run_flag_is_set(mocker, monkeypatch):
    # Arrange
    monkeypatch.setattr(sys, "argv", ["cleverswitch", "--dry-run"])
    mocker.patch("cleverswitch.cli._setup_logging")
    mocker.patch("cleverswitch.cli.platform_setup.check")
    mock_dry_run = mocker.patch("cleverswitch.cli._dry_run")
    # Act
    main()
    # Assert: _dry_run was called with the loaded config; monitor.run was not
    mock_dry_run.assert_called_once()


def test_main_does_not_call_monitor_run_in_dry_run_mode(mocker, monkeypatch, default_cfg):
    monkeypatch.setattr(sys, "argv", ["cleverswitch", "--dry-run"])
    mocker.patch("cleverswitch.cli.cfg_module.load", return_value=default_cfg)
    mocker.patch("cleverswitch.cli._setup_logging")
    mocker.patch("cleverswitch.cli.platform_setup.check")
    mocker.patch("cleverswitch.cli._dry_run")
    mock_run = mocker.patch("cleverswitch.cli.run")

    main()

    mock_run.assert_not_called()


def test_main_calls_run_in_normal_mode(mocker, monkeypatch, default_cfg):
    monkeypatch.setattr(sys, "argv", ["cleverswitch"])
    mocker.patch("cleverswitch.cli.cfg_module.load", return_value=default_cfg)
    mocker.patch("cleverswitch.cli._setup_logging")
    mocker.patch("cleverswitch.cli.platform_setup.check")
    mock_run = mocker.patch("cleverswitch.cli.run")

    main()

    mock_run.assert_called_once()


def test_main_exits_with_code_1_on_clever_switch_error_from_run(mocker, monkeypatch, default_cfg):
    monkeypatch.setattr(sys, "argv", ["cleverswitch"])
    mocker.patch("cleverswitch.cli.cfg_module.load", return_value=default_cfg)
    mocker.patch("cleverswitch.cli._setup_logging")
    mocker.patch("cleverswitch.cli.platform_setup.check")
    mocker.patch("cleverswitch.cli.run", side_effect=CleverSwitchError("fatal"))

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


# ── _dry_run() ────────────────────────────────────────────────────────────────


def test_dry_run_logs_device_info_when_discovery_succeeds(mocker, make_fake_transport, caplog):
    from cleverswitch.discovery import DeviceContext, Setup

    t = make_fake_transport()
    kbd = DeviceContext(
        transport=t, devnumber=1, change_host_feat_idx=2,
        divert_feat_idx=None, long_msg=False,
        role="keyboard", name="MX Keys", wpid=0x408A,
    )
    mouse = DeviceContext(
        transport=t, devnumber=2, change_host_feat_idx=3,
        divert_feat_idx=None, long_msg=False,
        role="mouse", name="MX Master 3", wpid=0x4082,
    )
    setup = Setup(devices=[kbd, mouse])
    mocker.patch("cleverswitch.discovery.discover", return_value=setup)

    with caplog.at_level(logging.INFO, logger="cleverswitch.cli"):
        _dry_run()

    assert "MX Keys" in caplog.text
    assert "MX Master 3" in caplog.text


def test_dry_run_closes_transports_after_logging(mocker, make_fake_transport):
    from cleverswitch.discovery import DeviceContext, Setup

    t = make_fake_transport()
    kbd = DeviceContext(
        transport=t, devnumber=1, change_host_feat_idx=2,
        divert_feat_idx=None, long_msg=False,
        role="keyboard", name="MX Keys", wpid=0x408A,
    )
    mouse = DeviceContext(
        transport=t, devnumber=2, change_host_feat_idx=3,
        divert_feat_idx=None, long_msg=False,
        role="mouse", name="MX Master 3", wpid=0x4082,
    )
    setup = Setup(devices=[kbd, mouse])
    mocker.patch("cleverswitch.discovery.discover", return_value=setup)

    _dry_run()

    assert t.closed


def test_dry_run_exits_with_code_1_when_discovery_fails(mocker):
    mocker.patch("cleverswitch.discovery.discover", side_effect=CleverSwitchError("no device"))

    with pytest.raises(SystemExit) as exc:
        _dry_run()
    assert exc.value.code == 1
