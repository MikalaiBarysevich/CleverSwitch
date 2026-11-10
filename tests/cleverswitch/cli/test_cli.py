"""Unit tests for the CLI entry point."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from src.cleverswitch.cli.cli_module import _parse_args, main
from src.cleverswitch.errors.errors import CleverSwitchError, HotplugError

# ── _parse_args() ─────────────────────────────────────────────────────────────


def test_parse_args_defaults_when_no_arguments_given(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cleverswitch"])
    args = _parse_args()
    assert args.config is None
    assert args.verbose is False


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


def test_parse_args_enables_verbose_extra_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cleverswitch", "-vv"])
    args = _parse_args()
    assert args.verbose_extra is True


def test_parse_args_clear_cache_defaults_false(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cleverswitch"])
    args = _parse_args()
    assert args.clear_cache is False


def test_parse_args_enables_clear_cache_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cleverswitch", "--clear-cache"])
    args = _parse_args()
    assert args.clear_cache is True


# ── logging ───────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _logging(mocker):
    return (
        mocker.patch("src.cleverswitch.cli.cli_module.bootstrap_logging"),
        mocker.patch("src.cleverswitch.cli.cli_module.configure_logging"),
    )


def test_main_bootstraps_logging_with_verbose_flag(mocker, monkeypatch, _logging):
    monkeypatch.setattr(sys, "argv", ["cleverswitch", "-vv"])
    mocker.patch("src.cleverswitch.cli.cli_module.setup_context")
    mocker.patch("src.cleverswitch.cli.cli_module.discover")

    main()

    _logging[0].assert_called_once_with(True)


def test_main_bootstraps_logging_without_verbose(mocker, monkeypatch, _logging):
    monkeypatch.setattr(sys, "argv", ["cleverswitch"])
    mocker.patch("src.cleverswitch.cli.cli_module.setup_context")
    mocker.patch("src.cleverswitch.cli.cli_module.discover")

    main()

    _logging[0].assert_called_once_with(False)


def test_clear_cache_configures_console_only_logging(mocker, monkeypatch, _logging):
    monkeypatch.setattr(sys, "argv", ["cleverswitch", "--clear-cache"])
    mock_load = mocker.patch("src.cleverswitch.cli.cli_module.cfg_module.load")
    mocker.patch("src.cleverswitch.cli.cli_module.DeviceCache")

    main()

    _logging[1].assert_called_once_with(mock_load.return_value.logging, False, file_allowed=False)


def test_clear_cache_never_opens_the_log_file(mocker, monkeypatch, tmp_path):
    from src.cleverswitch.log import log_setup
    from src.cleverswitch.model.config.logging_config import LoggingConfig

    log_file = tmp_path / "logs" / "cleverswitch.log"
    monkeypatch.setattr(sys, "argv", ["cleverswitch", "--clear-cache"])
    mocker.patch("src.cleverswitch.cli.cli_module.configure_logging", side_effect=log_setup.configure_logging)
    mock_load = mocker.patch("src.cleverswitch.cli.cli_module.cfg_module.load")
    mock_load.return_value.logging = LoggingConfig(file_path=log_file)
    mocker.patch("src.cleverswitch.cli.cli_module.DeviceCache")
    root_handlers = list(logging.getLogger().handlers)

    try:
        main()
    finally:
        log_setup.stop_logging()
        log_setup._remove_console()
        for handler in list(logging.getLogger().handlers):
            if handler not in root_handlers:
                logging.getLogger().removeHandler(handler)

    assert not Path(log_file).exists()
    assert not log_file.parent.exists()


def test_clear_cache_config_error_logs_and_exits(mocker, monkeypatch, _logging):
    from src.cleverswitch.errors.errors import ConfigError

    monkeypatch.setattr(sys, "argv", ["cleverswitch", "--clear-cache"])
    mocker.patch("src.cleverswitch.cli.cli_module.cfg_module.load", side_effect=ConfigError("bad"))

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 1
    assert _logging[1].call_args.kwargs == {"file_allowed": False}


# ── main() ────────────────────────────────────────────────────────────────────


def test_main_starts_discovery_thread_in_normal_mode(mocker, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cleverswitch"])
    mock_context = mocker.MagicMock()
    mocker.patch("src.cleverswitch.cli.cli_module.setup_context", return_value=mock_context)
    mock_thread_cls = mocker.patch("src.cleverswitch.cli.cli_module.threading.Thread")
    mock_thread = mock_thread_cls.return_value

    main()

    mock_thread.start.assert_called_once()
    mock_thread.join.assert_called_once()


def test_main_clears_cache_and_exits_without_starting_daemon(mocker, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cleverswitch", "--clear-cache"])
    mock_load = mocker.patch("src.cleverswitch.cli.cli_module.cfg_module.load")
    mock_load.return_value.cache_path = "/tmp/some/device_cache.json"
    mock_cache_cls = mocker.patch("src.cleverswitch.cli.cli_module.DeviceCache")
    mock_setup = mocker.patch("src.cleverswitch.cli.cli_module.setup_context")
    mock_thread_cls = mocker.patch("src.cleverswitch.cli.cli_module.threading.Thread")

    main()

    mock_cache_cls.assert_called_once_with("/tmp/some/device_cache.json")
    mock_cache_cls.return_value.clear.assert_called_once()
    mock_setup.assert_not_called()
    mock_thread_cls.assert_not_called()


def test_main_exits_with_code_1_on_clever_switch_error(mocker, monkeypatch):

    monkeypatch.setattr(sys, "argv", ["cleverswitch"])
    mock_context = mocker.MagicMock()
    mocker.patch("src.cleverswitch.cli.cli_module.setup_context", return_value=mock_context)
    mock_thread_cls = mocker.patch("src.cleverswitch.cli.cli_module.threading.Thread")
    mock_thread_cls.return_value.start.side_effect = CleverSwitchError("boom")

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_main_exits_with_code_1_when_discovery_fails(mocker, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cleverswitch"])
    mocker.patch("src.cleverswitch.cli.cli_module.setup_context", return_value=mocker.MagicMock())
    mocker.patch("src.cleverswitch.cli.cli_module.discover", side_effect=HotplugError("no netlink"))

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_main_returns_normally_when_discovery_ends(mocker, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cleverswitch"])
    mocker.patch("src.cleverswitch.cli.cli_module.setup_context", return_value=mocker.MagicMock())
    discover = mocker.patch("src.cleverswitch.cli.cli_module.discover")

    main()

    discover.assert_called_once()
