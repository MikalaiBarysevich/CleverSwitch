"""Unit tests for external hook script execution."""

from __future__ import annotations

import logging
import subprocess

from cleverswitch.hook.hooks import _run, fire, fire_connect, fire_disconnect, fire_switch
from cleverswitch.model.config.hook_entry import HookEntry
from cleverswitch.model.config.hook_type import HookType
from cleverswitch.model.config.hooks_config import HooksConfig

# ── builders ──────────────────────────────────────────────────────────────────


def _script(
    path: str, *, timeout: int = 5, name: str = "hook", types=(HookType.SWITCH,), fire_for_all_devices=None
) -> HookEntry:
    return HookEntry(
        name=name, types=frozenset(types), path=path, timeout=timeout, fire_for_all_devices=fire_for_all_devices
    )


def _command(
    command: str, *, timeout: int = 5, name: str = "hook", types=(HookType.SWITCH,), fire_for_all_devices=None
) -> HookEntry:
    return HookEntry(
        name=name, types=frozenset(types), command=command, timeout=timeout, fire_for_all_devices=fire_for_all_devices
    )


# ── fire() ────────────────────────────────────────────────────────────────────


def test_fire_submits_one_task_per_hook(mocker):
    mock_submit = mocker.patch("cleverswitch.hook.hooks._executor.submit")
    hooks = (_script("/a.sh"), _script("/b.sh"))
    fire(hooks, {"CLEVERSWITCH_DEVICE": "keyboard"})
    assert mock_submit.call_count == 2


def test_fire_does_nothing_for_empty_hooks_tuple(mocker):
    mock_submit = mocker.patch("cleverswitch.hook.hooks._executor.submit")
    fire((), {"CLEVERSWITCH_DEVICE": "keyboard"})
    mock_submit.assert_not_called()


def test_fire_skips_mouse_events_by_default(mocker):
    mock_submit = mocker.patch("cleverswitch.hook.hooks._executor.submit")
    hooks = (_script("/a.sh"),)
    fire(hooks, {"CLEVERSWITCH_DEVICE": "mouse"})
    mock_submit.assert_not_called()


def test_fire_allows_mouse_events_when_fire_for_all_devices_is_true(mocker):
    mock_submit = mocker.patch("cleverswitch.hook.hooks._executor.submit")
    hooks = (_script("/a.sh"),)
    fire(hooks, {"CLEVERSWITCH_DEVICE": "mouse"}, fire_for_all_devices=True)
    assert mock_submit.call_count == 1


def test_fire_per_hook_override_true_fires_mouse_when_global_false(mocker):
    mock_submit = mocker.patch("cleverswitch.hook.hooks._executor.submit")
    hooks = (_script("/a.sh", fire_for_all_devices=True),)
    fire(hooks, {"CLEVERSWITCH_DEVICE": "mouse"}, fire_for_all_devices=False)
    assert mock_submit.call_count == 1


def test_fire_per_hook_override_false_stays_keyboard_only_when_global_true(mocker):
    mock_submit = mocker.patch("cleverswitch.hook.hooks._executor.submit")
    hooks = (_script("/a.sh", fire_for_all_devices=False),)
    fire(hooks, {"CLEVERSWITCH_DEVICE": "mouse"}, fire_for_all_devices=True)
    mock_submit.assert_not_called()


def test_fire_per_hook_none_inherits_global_true_for_mouse(mocker):
    mock_submit = mocker.patch("cleverswitch.hook.hooks._executor.submit")
    hooks = (_script("/a.sh", fire_for_all_devices=None),)
    fire(hooks, {"CLEVERSWITCH_DEVICE": "mouse"}, fire_for_all_devices=True)
    assert mock_submit.call_count == 1


def test_fire_mixed_overrides_submits_only_hooks_passing_their_own_gate(mocker):
    mock_submit = mocker.patch("cleverswitch.hook.hooks._executor.submit")
    widen = _script("/widen.sh", name="widen", fire_for_all_devices=True)
    inherit = _script("/inherit.sh", name="inherit", fire_for_all_devices=None)
    narrow = _script("/narrow.sh", name="narrow", fire_for_all_devices=False)
    fire((widen, inherit, narrow), {"CLEVERSWITCH_DEVICE": "mouse"}, fire_for_all_devices=False)
    submitted = [call.args[1].name for call in mock_submit.call_args_list]
    assert submitted == ["widen"]


# ── fire_switch / fire_connect / fire_disconnect ──────────────────────────────


def test_fire_switch_selects_switch_hooks_and_sets_env(mocker):
    mock_fire = mocker.patch("cleverswitch.hook.hooks.fire")
    switch_hook = _script("/hook.sh", name="s", types=(HookType.SWITCH,))
    connect_hook = _script("/other.sh", name="c", types=(HookType.CONNECT,))
    hooks_cfg = HooksConfig(hooks={"s": switch_hook, "c": connect_hook})
    fire_switch(hooks_cfg, device_name="MX Keys", role="keyboard", target_host=1)
    mock_fire.assert_called_once_with(
        (switch_hook,),
        {
            "CLEVERSWITCH_EVENT": "switch",
            "CLEVERSWITCH_DEVICE": "keyboard",
            "CLEVERSWITCH_DEVICE_NAME": "MX Keys",
            "CLEVERSWITCH_TARGET_HOST": "2",  # converted to 1-based
        },
        fire_for_all_devices=False,
    )


def test_fire_connect_selects_connect_hooks_and_sets_env(mocker):
    mock_fire = mocker.patch("cleverswitch.hook.hooks.fire")
    connect_hook = _script("/hook.sh", name="c", types=(HookType.CONNECT,))
    hooks_cfg = HooksConfig(hooks={"c": connect_hook})
    fire_connect(hooks_cfg, device_name="MX Master 3", role="mouse")
    mock_fire.assert_called_once_with(
        (connect_hook,),
        {
            "CLEVERSWITCH_EVENT": "connect",
            "CLEVERSWITCH_DEVICE": "mouse",
            "CLEVERSWITCH_DEVICE_NAME": "MX Master 3",
        },
        fire_for_all_devices=False,
    )


def test_fire_disconnect_selects_disconnect_hooks_and_sets_env(mocker):
    mock_fire = mocker.patch("cleverswitch.hook.hooks.fire")
    disconnect_hook = _script("/hook.sh", name="d", types=(HookType.DISCONNECT,))
    hooks_cfg = HooksConfig(hooks={"d": disconnect_hook})
    fire_disconnect(hooks_cfg, device_name="MX Keys", role="keyboard")
    mock_fire.assert_called_once_with(
        (disconnect_hook,),
        {
            "CLEVERSWITCH_EVENT": "disconnect",
            "CLEVERSWITCH_DEVICE": "keyboard",
            "CLEVERSWITCH_DEVICE_NAME": "MX Keys",
        },
        fire_for_all_devices=False,
    )


def test_fire_selects_hook_registered_for_multiple_types(mocker):
    mock_fire = mocker.patch("cleverswitch.hook.hooks.fire")
    multi = _script("/hook.sh", name="m", types=(HookType.CONNECT, HookType.DISCONNECT))
    hooks_cfg = HooksConfig(hooks={"m": multi})
    fire_connect(hooks_cfg, device_name="MX Keys", role="keyboard")
    fire_disconnect(hooks_cfg, device_name="MX Keys", role="keyboard")
    assert [call.args[0] for call in mock_fire.call_args_list] == [(multi,), (multi,)]


# ── _run() ────────────────────────────────────────────────────────────────────


def test_run_executes_command_via_shell(mocker):
    mock_result = mocker.MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_run = mocker.patch("cleverswitch.hook.hooks.subprocess.run", return_value=mock_result)

    _run(_command("echo hello"), {})

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

    _run(_script(str(script)), {})

    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0] == [str(script)]  # list, not string
    assert kwargs.get("shell", False) is False


def test_run_expands_tilde_in_script_path(mocker, tmp_path):
    script = tmp_path / "hook.sh"
    script.touch()
    mocker.patch("cleverswitch.hook.hooks.os.path.expanduser", return_value=str(script))
    mock_result = mocker.MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_run = mocker.patch("cleverswitch.hook.hooks.subprocess.run", return_value=mock_result)

    _run(_script("~/hook.sh"), {})

    args, _ = mock_run.call_args
    assert args[0] == [str(script)]


def test_run_passes_hook_timeout_to_subprocess(mocker, tmp_path):
    script = tmp_path / "hook.sh"
    script.touch()
    mock_result = mocker.MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_run = mocker.patch("cleverswitch.hook.hooks.subprocess.run", return_value=mock_result)

    _run(_script(str(script), timeout=15), {})

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
        _run(_script(str(script)), {})

    assert "exited with code 1" in caplog.text


def test_run_logs_warning_on_timeout(mocker, tmp_path, caplog):
    script = tmp_path / "hook.sh"
    script.touch()
    mocker.patch(
        "cleverswitch.hook.hooks.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=str(script), timeout=5),
    )

    with caplog.at_level(logging.WARNING, logger="cleverswitch.hook.hooks"):
        _run(_script(str(script), timeout=5), {})

    assert "timed out" in caplog.text


def test_run_kills_process_on_timeout(mocker, tmp_path):
    script = tmp_path / "hook.sh"
    script.touch()
    mock_process = mocker.MagicMock()
    exc = subprocess.TimeoutExpired(cmd=str(script), timeout=5)
    exc.process = mock_process
    mocker.patch("cleverswitch.hook.hooks.subprocess.run", side_effect=exc)

    _run(_script(str(script), timeout=5), {})

    mock_process.kill.assert_called_once()
    mock_process.communicate.assert_called_once()


def test_run_logs_warning_on_unexpected_exception(mocker, tmp_path, caplog):
    script = tmp_path / "hook.sh"
    script.touch()
    mocker.patch("cleverswitch.hook.hooks.subprocess.run", side_effect=PermissionError("denied"))

    with caplog.at_level(logging.WARNING, logger="cleverswitch.hook.hooks"):
        _run(_script(str(script)), {})

    assert "failed" in caplog.text


def test_run_logs_warning_when_script_path_does_not_exist(caplog):
    with caplog.at_level(logging.WARNING, logger="cleverswitch.hook.hooks"):
        _run(_script("/definitely/does/not/exist.sh"), {})
    assert "not found" in caplog.text


def test_run_does_not_call_subprocess_when_script_path_is_missing(mocker):
    mock_run = mocker.patch("cleverswitch.hook.hooks.subprocess.run")
    _run(_script("/missing/script.sh"), {})
    mock_run.assert_not_called()


def test_run_command_logs_warning_on_nonzero_exit_code(mocker, caplog):
    mock_result = mocker.MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "command failed"
    mocker.patch("cleverswitch.hook.hooks.subprocess.run", return_value=mock_result)

    with caplog.at_level(logging.WARNING, logger="cleverswitch.hook.hooks"):
        _run(_command("bad-command"), {})

    assert "exited with code 1" in caplog.text


def test_run_command_logs_warning_on_timeout(mocker, caplog):
    exc = subprocess.TimeoutExpired(cmd="slow-command", timeout=5)
    exc.process = mocker.MagicMock()
    mocker.patch("cleverswitch.hook.hooks.subprocess.run", side_effect=exc)

    with caplog.at_level(logging.WARNING, logger="cleverswitch.hook.hooks"):
        _run(_command("slow-command", timeout=5), {})

    assert "timed out" in caplog.text
    exc.process.kill.assert_called_once()


def test_run_command_logs_warning_on_unexpected_exception(mocker, caplog):
    mocker.patch("cleverswitch.hook.hooks.subprocess.run", side_effect=OSError("exec failed"))

    with caplog.at_level(logging.WARNING, logger="cleverswitch.hook.hooks"):
        _run(_command("broken-command"), {})

    assert "failed" in caplog.text
