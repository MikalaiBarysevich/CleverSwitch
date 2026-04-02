"""Unit tests for platform-specific prerequisite checks."""

from __future__ import annotations

import logging

import cleverswitch.setup.platform_setup as ps
from cleverswitch.setup.platform_setup import _check_linux, _check_macos, check

# ── check() dispatch ──────────────────────────────────────────────────────────


def test_check_calls_check_linux_on_linux(mocker):
    mocker.patch.object(ps, "_SYSTEM", "Linux")
    mock = mocker.patch("cleverswitch.setup.platform_setup._check_linux")
    check()
    mock.assert_called_once()


def test_check_calls_check_macos_on_darwin(mocker):
    mocker.patch.object(ps, "_SYSTEM", "Darwin")
    mock = mocker.patch("cleverswitch.setup.platform_setup._check_macos")
    check()
    mock.assert_called_once()


def test_check_does_not_call_platform_helpers_on_windows(mocker):
    mocker.patch.object(ps, "_SYSTEM", "Windows")
    linux_mock = mocker.patch("cleverswitch.setup.platform_setup._check_linux")
    mac_mock = mocker.patch("cleverswitch.setup.platform_setup._check_macos")
    check()
    linux_mock.assert_not_called()
    mac_mock.assert_not_called()


# ── _check_linux() ────────────────────────────────────────────────────────────


def test_check_linux_does_not_warn_when_udev_rule_is_found_in_first_dir(mocker, caplog):
    mocker.patch("cleverswitch.setup.platform_setup.os.path.exists", return_value=True)
    with caplog.at_level(logging.WARNING, logger="cleverswitch.setup.platform_setup"):
        _check_linux()
    assert "udev rule not found" not in caplog.text


def test_check_linux_logs_warning_when_udev_rule_is_absent_from_all_dirs(mocker, caplog):
    mocker.patch("cleverswitch.setup.platform_setup.os.path.exists", return_value=False)
    with caplog.at_level(logging.WARNING, logger="cleverswitch.setup.platform_setup"):
        _check_linux()
    assert "udev rule not found" in caplog.text


def test_check_linux_warning_includes_copy_command(mocker, caplog):
    mocker.patch("cleverswitch.setup.platform_setup.os.path.exists", return_value=False)
    with caplog.at_level(logging.WARNING, logger="cleverswitch.setup.platform_setup"):
        _check_linux()
    assert "sudo cp" in caplog.text


# ── _check_macos() ────────────────────────────────────────────────────────────


def test_check_macos_logs_info_about_input_monitoring(caplog):
    with caplog.at_level(logging.INFO, logger="cleverswitch.setup.platform_setup"):
        _check_macos()
    assert "Input Monitoring" in caplog.text
