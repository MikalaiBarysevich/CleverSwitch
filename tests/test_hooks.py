"""Unit tests for external hook script execution."""

from __future__ import annotations

import logging
import subprocess

import pytest

from cleverswitch.config import HookEntry, HooksConfig
from cleverswitch.hooks import _run, fire, fire_connect, fire_disconnect, fire_switch


# ── fire() ────────────────────────────────────────────────────────────────────


def test_fire_submits_one_task_per_hook(mocker):
    # Arrange
    mock_submit = mocker.patch("cleverswitch.hooks._executor.submit")
    hooks = (HookEntry(path="/a.sh"), HookEntry(path="/b.sh"))
    # Act
    fire(hooks, {"KEY": "val"})
    # Assert
    assert mock_submit.call_count == 2


def test_fire_does_nothing_for_empty_hooks_tuple(mocker):
    mock_submit = mocker.patch("cleverswitch.hooks._executor.submit")
    fire((), {})
    mock_submit.assert_not_called()


# ── fire_switch / fire_connect / fire_disconnect ──────────────────────────────


def test_fire_switch_calls_fire_with_on_switch_hooks_and_correct_env(mocker):
    # Arrange
    mock_fire = mocker.patch("cleverswitch.hooks.fire")
    hooks_cfg = HooksConfig(on_switch=(HookEntry(path="/hook.sh"),))
    # Act
    fire_switch(hooks_cfg, device_name="MX Keys", role="keyboard", target_host=1, previous_host=0)
    # Assert
    mock_fire.assert_called_once_with(
        hooks_cfg.on_switch,
        {
            "CLEVERSWITCH_EVENT": "switch",
            "CLEVERSWITCH_DEVICE": "keyboard",
            "CLEVERSWITCH_DEVICE_NAME": "MX Keys",
            "CLEVERSWITCH_TARGET_HOST": "2",  # converted to 1-based
            "CLEVERSWITCH_PREVIOUS_HOST": "1",
        },
    )


def test_fire_connect_calls_fire_with_on_connect_hooks_and_correct_env(mocker):
    # Arrange
    mock_fire = mocker.patch("cleverswitch.hooks.fire")
    hooks_cfg = HooksConfig(on_connect=(HookEntry(path="/hook.sh"),))
    # Act
    fire_connect(hooks_cfg, device_name="MX Master 3", role="mouse")
    # Assert
    mock_fire.assert_called_once_with(
        hooks_cfg.on_connect,
        {
            "CLEVERSWITCH_EVENT": "connect",
            "CLEVERSWITCH_DEVICE": "mouse",
            "CLEVERSWITCH_DEVICE_NAME": "MX Master 3",
        },
    )


def test_fire_disconnect_calls_fire_with_on_disconnect_hooks_and_correct_env(mocker):
    # Arrange
    mock_fire = mocker.patch("cleverswitch.hooks.fire")
    hooks_cfg = HooksConfig(on_disconnect=(HookEntry(path="/hook.sh"),))
    # Act
    fire_disconnect(hooks_cfg, device_name="MX Keys", role="keyboard")
    # Assert
    mock_fire.assert_called_once_with(
        hooks_cfg.on_disconnect,
        {
            "CLEVERSWITCH_EVENT": "disconnect",
            "CLEVERSWITCH_DEVICE": "keyboard",
            "CLEVERSWITCH_DEVICE_NAME": "MX Keys",
        },
    )


# ── _run() ────────────────────────────────────────────────────────────────────


def test_run_logs_warning_when_script_does_not_exist(caplog):
    hook = HookEntry(path="/definitely/does/not/exist.sh")
    with caplog.at_level(logging.WARNING, logger="cleverswitch.hooks"):
        _run(hook, {})
    assert "not found" in caplog.text


def test_run_does_not_call_subprocess_when_script_is_missing(mocker):
    mocker.patch("cleverswitch.hooks.os.path.exists", return_value=False)
    mock_run = mocker.patch("cleverswitch.hooks.subprocess.run")
    _run(HookEntry(path="/missing.sh"), {})
    mock_run.assert_not_called()


def test_run_executes_script_when_it_exists(mocker, tmp_path):
    # Arrange: real file on disk so os.path.exists passes naturally
    script = tmp_path / "hook.sh"
    script.touch()
    mock_result = mocker.MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_run = mocker.patch("cleverswitch.hooks.subprocess.run", return_value=mock_result)
    # Act
    _run(HookEntry(path=str(script)), {"CLEVERSWITCH_EVENT": "switch"})
    # Assert
    mock_run.assert_called_once()
    _, call_kwargs = mock_run.call_args
    assert "CLEVERSWITCH_EVENT" in call_kwargs["env"]


def test_run_passes_hook_timeout_to_subprocess(mocker, tmp_path):
    script = tmp_path / "hook.sh"
    script.touch()
    mock_result = mocker.MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_run = mocker.patch("cleverswitch.hooks.subprocess.run", return_value=mock_result)

    _run(HookEntry(path=str(script), timeout=15), {})

    _, call_kwargs = mock_run.call_args
    assert call_kwargs["timeout"] == 15


def test_run_logs_warning_on_nonzero_exit_code(mocker, tmp_path, caplog):
    script = tmp_path / "hook.sh"
    script.touch()
    mock_result = mocker.MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "something went wrong"
    mocker.patch("cleverswitch.hooks.subprocess.run", return_value=mock_result)

    with caplog.at_level(logging.WARNING, logger="cleverswitch.hooks"):
        _run(HookEntry(path=str(script)), {})

    assert "exited with code 1" in caplog.text


def test_run_logs_warning_on_timeout(mocker, tmp_path, caplog):
    script = tmp_path / "hook.sh"
    script.touch()
    mocker.patch(
        "cleverswitch.hooks.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=str(script), timeout=5),
    )

    with caplog.at_level(logging.WARNING, logger="cleverswitch.hooks"):
        _run(HookEntry(path=str(script), timeout=5), {})

    assert "timed out" in caplog.text


def test_run_logs_warning_on_unexpected_exception(mocker, tmp_path, caplog):
    script = tmp_path / "hook.sh"
    script.touch()
    mocker.patch("cleverswitch.hooks.subprocess.run", side_effect=PermissionError("denied"))

    with caplog.at_level(logging.WARNING, logger="cleverswitch.hooks"):
        _run(HookEntry(path=str(script)), {})

    assert "failed" in caplog.text
