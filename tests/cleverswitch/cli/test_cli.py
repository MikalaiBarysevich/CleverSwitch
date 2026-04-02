"""Unit tests for the CLI entry point."""

from __future__ import annotations

import logging
import sys

import pytest

from cleverswitch.cli.cli_module import _parse_args, _setup_logging, main


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


def test_parse_args_enables_verbose_extra_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cleverswitch", "-vv"])
    args = _parse_args()
    assert args.verbose_extra is True


# ── _setup_logging() ──────────────────────────────────────────────────────────


def test_setup_logging_uses_info_level_when_not_verbose(mocker):
    mock_basic = mocker.patch("cleverswitch.cli.cli_module.logging.basicConfig")
    _setup_logging(verbose=False)
    assert mock_basic.call_args[1]["level"] == logging.INFO


def test_setup_logging_overrides_to_debug_when_verbose_is_true(mocker):
    mock_basic = mocker.patch("cleverswitch.cli.cli_module.logging.basicConfig")
    _setup_logging(verbose=True)
    assert mock_basic.call_args[1]["level"] == logging.DEBUG


# ── main() ────────────────────────────────────────────────────────────────────


def test_main_starts_discovery_thread_in_normal_mode(mocker, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cleverswitch"])
    mock_context = mocker.MagicMock()
    mocker.patch("cleverswitch.cli.cli_module.setup_context", return_value=mock_context)
    mocker.patch("cleverswitch.cli.cli_module._setup_logging")
    mock_thread_cls = mocker.patch("cleverswitch.cli.cli_module.threading.Thread")
    mock_thread = mock_thread_cls.return_value

    main()

    mock_thread.start.assert_called_once()
    mock_thread.join.assert_called_once()


def test_main_exits_with_code_1_on_clever_switch_error(mocker, monkeypatch):
    from cleverswitch.errors.errors import CleverSwitchError

    monkeypatch.setattr(sys, "argv", ["cleverswitch"])
    mock_context = mocker.MagicMock()
    mocker.patch("cleverswitch.cli.cli_module.setup_context", return_value=mock_context)
    mocker.patch("cleverswitch.cli.cli_module._setup_logging")
    mock_thread_cls = mocker.patch("cleverswitch.cli.cli_module.threading.Thread")
    mock_thread_cls.return_value.start.side_effect = CleverSwitchError("boom")

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
