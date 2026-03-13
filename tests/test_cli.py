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
    assert mock_basic.call_args[1]["level"] == logging.DEBUG


# ── main() ────────────────────────────────────────────────────────────────────


def test_main_exits_with_code_1_and_prints_error_on_config_error(mocker, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cleverswitch"])
    mocker.patch("cleverswitch.cli.cfg_module.load", side_effect=ConfigError("bad log_level"))
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "bad log_level" in capsys.readouterr().err


def test_main_calls_dry_run_and_returns_when_dry_run_flag_is_set(mocker, monkeypatch, default_cfg):
    monkeypatch.setattr(sys, "argv", ["cleverswitch", "--dry-run"])
    mocker.patch("cleverswitch.cli.cfg_module.load", return_value=default_cfg)
    mocker.patch("cleverswitch.cli._setup_logging")
    mocker.patch("cleverswitch.cli.platform_setup.check")
    mock_dry_run = mocker.patch("cleverswitch.cli._dry_run")

    main()

    mock_dry_run.assert_called_once()


def test_main_does_not_start_discovery_thread_in_dry_run_mode(mocker, monkeypatch, default_cfg):
    monkeypatch.setattr(sys, "argv", ["cleverswitch", "--dry-run"])
    mocker.patch("cleverswitch.cli.cfg_module.load", return_value=default_cfg)
    mocker.patch("cleverswitch.cli._setup_logging")
    mocker.patch("cleverswitch.cli.platform_setup.check")
    mocker.patch("cleverswitch.cli._dry_run")
    mock_thread = mocker.patch("cleverswitch.cli.threading.Thread")

    main()

    mock_thread.assert_not_called()


def test_main_starts_discovery_thread_in_normal_mode(mocker, monkeypatch, default_cfg):
    monkeypatch.setattr(sys, "argv", ["cleverswitch"])
    mocker.patch("cleverswitch.cli.cfg_module.load", return_value=default_cfg)
    mocker.patch("cleverswitch.cli._setup_logging")
    mocker.patch("cleverswitch.cli.platform_setup.check")
    mock_thread_cls = mocker.patch("cleverswitch.cli.threading.Thread")
    mock_thread = mock_thread_cls.return_value

    main()

    mock_thread.start.assert_called_once()
    mock_thread.join.assert_called_once()


# ── _dry_run() ────────────────────────────────────────────────────────────────


def test_dry_run_logs_found_receivers(mocker, caplog):
    from cleverswitch.hidpp.transport import HidDeviceInfo

    devices = [
        HidDeviceInfo(path=b"/dev/hidraw0", vid=0x046D, pid=0xC548, usage_page=0xFF00, usage=1, connection_type="receiver"),
    ]
    mocker.patch("cleverswitch.cli.enumerate_hid_devices", return_value=devices)

    with caplog.at_level(logging.INFO, logger="cleverswitch.cli"):
        _dry_run()

    assert "0xC548" in caplog.text or "hidraw0" in caplog.text


def test_dry_run_logs_multiple_receivers(mocker, caplog):
    from cleverswitch.hidpp.transport import HidDeviceInfo

    devices = [
        HidDeviceInfo(path=b"/dev/hidraw0", vid=0x046D, pid=0xC548, usage_page=0xFF00, usage=1, connection_type="receiver"),
        HidDeviceInfo(path=b"/dev/hidraw1", vid=0x046D, pid=0xC52B, usage_page=0xFF00, usage=1, connection_type="receiver"),
    ]
    mocker.patch("cleverswitch.cli.enumerate_hid_devices", return_value=devices)

    with caplog.at_level(logging.INFO, logger="cleverswitch.cli"):
        _dry_run()

    assert caplog.text.count("Found receiver") == 2


def test_dry_run_logs_no_devices_message_when_list_is_empty(mocker, caplog):
    mocker.patch("cleverswitch.cli.enumerate_hid_devices", return_value=[])

    with caplog.at_level(logging.INFO, logger="cleverswitch.cli"):
        _dry_run()

    assert "No Logitech receivers found" in caplog.text
