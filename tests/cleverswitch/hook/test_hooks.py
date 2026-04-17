"""Unit tests for external hook script execution."""

from __future__ import annotations

import logging
import subprocess

from cleverswitch.model.config.hook_entry import HookEntry
from cleverswitch.model.config.hooks_config import HooksConfig
from cleverswitch.hook.hooks import _run, fire, fire_connect, fire_disconnect, fire_switch

# ── fire() ────────────────────────────────────────────────────────────────────


def test_fire_submits_one_task_per_hook(mocker):
    mock_submit = mocker.patch("cleverswitch.hook.hooks._executor.submit")
    hooks = (HookEntry(path="/a.sh"), HookEntry(path="/b.sh"))
    fire(hooks, {"CLEVERSWITCH_DEVICE": "keyboard"})
    assert mock_submit.call_count == 2


def test_fire_does_nothing_for_empty_hooks_tuple(mocker):
    mock_submit = mocker.patch("cleverswitch.hook.hooks._executor.submit")
    fire((), {"CLEVERSWITCH_DEVICE": "keyboard"})
    mock_submit.assert_not_called()


def test_fire_skips_mouse_events_by_default(mocker):
    mock_submit = mocker.patch("cleverswitch.hook.hooks._executor.submit")
    hooks = (HookEntry(path="/a.sh"),)
    fire(hooks, {"CLEVERSWITCH_DEVICE": "mouse"})
    mock_submit.assert_not_called()


def test_fire_allows_mouse_events_when_fire_for_all_devices_is_true(mocker):
    mock_submit = mocker.patch("cleverswitch.hook.hooks._executor.submit")
    hooks = (HookEntry(path="/a.sh"),)
    fire(hooks, {"CLEVERSWITCH_DEVICE": "mouse"}, fire_for_all_devices=True)
    assert mock_submit.call_count == 1


# ── fire_switch / fire_connect / fire_disconnect ──────────────────────────────


def test_fire_switch_calls_fire_with_on_switch_hooks_and_correct_env(mocker):
    mock_fire = mocker.patch("cleverswitch.hook.hooks.fire")
    hooks_cfg = HooksConfig(on_switch=(HookEntry(path="/hook.sh"),))
    fire_switch(hooks_cfg, device_name="MX Keys", role="keyboard", target_host=1)
    mock_fire.assert_called_once_with(
        hooks_cfg.on_switch,
        {
            "CLEVERSWITCH_EVENT": "switch",
            "CLEVERSWITCH_DEVICE": "keyboard",
            "CLEVERSWITCH_DEVICE_NAME": "MX Keys",
            "CLEVERSWITCH_TARGET_HOST": "2",  # converted to 1-based
        },
        fire_for_all_devices=False,
    )


def test_fire_connect_calls_fire_with_on_connect_hooks_and_correct_env(mocker):
    mock_fire = mocker.patch("cleverswitch.hook.hooks.fire")
    hooks_cfg = HooksConfig(on_connect=(HookEntry(path="/hook.sh"),))
    fire_connect(hooks_cfg, device_name="MX Master 3", role="mouse")
    mock_fire.assert_called_once_with(
        hooks_cfg.on_connect,
        {
            "CLEVERSWITCH_EVENT": "connect",
            "CLEVERSWITCH_DEVICE": "mouse",
            "CLEVERSWITCH_DEVICE_NAME": "MX Master 3",
        },
        fire_for_all_devices=False,
    )


def test_fire_disconnect_calls_fire_with_on_disconnect_hooks_and_correct_env(mocker):
    mock_fire = mocker.patch("cleverswitch.hook.hooks.fire")
    hooks_cfg = HooksConfig(on_disconnect=(HookEntry(path="/hook.sh"),))
    fire_disconnect(hooks_cfg, device_name="MX Keys", role="keyboard")
    mock_fire.assert_called_once_with(
        hooks_cfg.on_disconnect,
        {
            "CLEVERSWITCH_EVENT": "disconnect",
            "CLEVERSWITCH_DEVICE": "keyboard",
            "CLEVERSWITCH_DEVICE_NAME": "MX Keys",
        },
        fire_for_all_devices=False,
    )


# ── _run() ────────────────────────────────────────────────────────────────────


def test_run_executes_command_via_shell_when_path_is_not_a_file(mocker):
    mocker.patch("cleverswitch.hook.hooks.os.path.exists", return_value=False)
    mock_result = mocker.MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_run = mocker.patch("cleverswitch.hook.hooks.subprocess.run", return_value=mock_result)

    _run(HookEntry(path="echo hello"), {})

    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0] == "echo hello"  # string, not list
    assert kwargs["shell"] is True


def test_run_executes_script_without_shell_when_file_exists(mocker, tmp_path):
    script = tmp_path / "hook.sh"
    script.touch()
    mock_result = mocker.MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_run = mocker.patch("cleverswitch.hook.hooks.subprocess.run", return_value=mock_result)

    _run(HookEntry(path=str(script)), {})

    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0] == [str(script)]  # list, not string
    assert kwargs.get("shell", False) is False


def test_run_passes_hook_timeout_to_subprocess(mocker, tmp_path):
    script = tmp_path / "hook.sh"
    script.touch()
    mock_result = mocker.MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_run = mocker.patch("cleverswitch.hook.hooks.subprocess.run", return_value=mock_result)

    _run(HookEntry(path=str(script), timeout=15), {})

    _, call_kwargs = mock_run.call_args
    assert call_kwargs["timeout"] == 15


def test_run_logs_warning_on_nonzero_exit_code(mocker, tmp_path, caplog):
    script = tmp_path / "hook.sh"
    script.touch()
    mock_result = mocker.MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "something went wrong"
    mocker.patch("cleverswitch.hook.hooks.subprocess.run", return_value=mock_result)

    with caplog.at_level(logging.WARNING, logger="cleverswitch.hook.hooks"):
        _run(HookEntry(path=str(script)), {})

    assert "exited with code 1" in caplog.text


def test_run_logs_warning_on_timeout(mocker, tmp_path, caplog):
    script = tmp_path / "hook.sh"
    script.touch()
    mocker.patch(
        "cleverswitch.hook.hooks.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=str(script), timeout=5),
    )

    with caplog.at_level(logging.WARNING, logger="cleverswitch.hook.hooks"):
        _run(HookEntry(path=str(script), timeout=5), {})

    assert "timed out" in caplog.text


def test_run_kills_process_on_timeout(mocker, tmp_path):
    script = tmp_path / "hook.sh"
    script.touch()
    mock_process = mocker.MagicMock()
    exc = subprocess.TimeoutExpired(cmd=str(script), timeout=5)
    exc.process = mock_process
    mocker.patch("cleverswitch.hook.hooks.subprocess.run", side_effect=exc)

    _run(HookEntry(path=str(script), timeout=5), {})

    mock_process.kill.assert_called_once()
    mock_process.communicate.assert_called_once()


def test_run_logs_warning_on_unexpected_exception(mocker, tmp_path, caplog):
    script = tmp_path / "hook.sh"
    script.touch()
    mocker.patch("cleverswitch.hook.hooks.subprocess.run", side_effect=PermissionError("denied"))

    with caplog.at_level(logging.WARNING, logger="cleverswitch.hook.hooks"):
        _run(HookEntry(path=str(script)), {})

    assert "failed" in caplog.text


def test_run_logs_warning_when_script_path_does_not_exist(caplog):
    hook = HookEntry(path="/definitely/does/not/exist.sh")
    with caplog.at_level(logging.WARNING, logger="cleverswitch.hook.hooks"):
        _run(hook, {})
    assert "not found" in caplog.text


def test_run_does_not_call_subprocess_when_script_path_is_missing(mocker):
    mocker.patch("cleverswitch.hook.hooks.os.path.exists", return_value=False)
    mock_run = mocker.patch("cleverswitch.hook.hooks.subprocess.run")
    _run(HookEntry(path="/missing/script.sh"), {})
    mock_run.assert_not_called()


def test_run_command_logs_warning_on_nonzero_exit_code(mocker, caplog):
    mocker.patch("cleverswitch.hook.hooks.os.path.exists", return_value=False)
    mock_result = mocker.MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "command failed"
    mocker.patch("cleverswitch.hook.hooks.subprocess.run", return_value=mock_result)

    with caplog.at_level(logging.WARNING, logger="cleverswitch.hook.hooks"):
        _run(HookEntry(path="bad-command"), {})

    assert "exited with code 1" in caplog.text


def test_run_command_logs_warning_on_timeout(mocker, caplog):
    mocker.patch("cleverswitch.hook.hooks.os.path.exists", return_value=False)
    exc = subprocess.TimeoutExpired(cmd="slow-command", timeout=5)
    exc.process = mocker.MagicMock()
    mocker.patch("cleverswitch.hook.hooks.subprocess.run", side_effect=exc)

    with caplog.at_level(logging.WARNING, logger="cleverswitch.hook.hooks"):
        _run(HookEntry(path="slow-command", timeout=5), {})

    assert "timed out" in caplog.text
    exc.process.kill.assert_called_once()


def test_run_command_logs_warning_on_unexpected_exception(mocker, caplog):
    mocker.patch("cleverswitch.hook.hooks.os.path.exists", return_value=False)
    mocker.patch("cleverswitch.hook.hooks.subprocess.run", side_effect=OSError("exec failed"))

    with caplog.at_level(logging.WARNING, logger="cleverswitch.hook.hooks"):
        _run(HookEntry(path="broken-command"), {})

    assert "failed" in caplog.text
