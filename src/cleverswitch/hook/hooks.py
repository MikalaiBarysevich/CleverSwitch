from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

from ..model.config.hook_entry import HookEntry
from ..model.config.hook_type import HookType
from ..model.config.hooks_config import HooksConfig
from ..model.logi_device import ROLE_KEYBOARD

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cleverswitch-hook")


def fire(hooks: tuple[HookEntry, ...], env_vars: dict[str, str], *, fire_for_all_devices: bool = False) -> None:
    is_keyboard = env_vars.get("CLEVERSWITCH_DEVICE") == ROLE_KEYBOARD
    for hook in hooks:
        all_devices = fire_for_all_devices if hook.fire_for_all_devices is None else hook.fire_for_all_devices
        if not all_devices and not is_keyboard:
            continue
        _executor.submit(_run, hook, env_vars)


def fire_switch(hooks_cfg: HooksConfig, device_name: str, role: str, target_host: int, source: str = "device") -> None:
    fire(
        hooks_cfg.for_type(HookType.SWITCH),
        {
            "CLEVERSWITCH_EVENT": "switch",
            "CLEVERSWITCH_DEVICE": role,
            "CLEVERSWITCH_DEVICE_NAME": device_name,
            "CLEVERSWITCH_TARGET_HOST": str(target_host + 1),  # 1-based for humans
            "CLEVERSWITCH_SWITCH_SOURCE": source,
        },
        fire_for_all_devices=hooks_cfg.fire_for_all_devices,
    )


def fire_connect(hooks_cfg: HooksConfig, device_name: str, role: str) -> None:
    fire(
        hooks_cfg.for_type(HookType.CONNECT),
        {
            "CLEVERSWITCH_EVENT": "connect",
            "CLEVERSWITCH_DEVICE": role,
            "CLEVERSWITCH_DEVICE_NAME": device_name,
        },
        fire_for_all_devices=hooks_cfg.fire_for_all_devices,
    )


def fire_disconnect(hooks_cfg: HooksConfig, device_name: str, role: str) -> None:
    fire(
        hooks_cfg.for_type(HookType.DISCONNECT),
        {
            "CLEVERSWITCH_EVENT": "disconnect",
            "CLEVERSWITCH_DEVICE": role,
            "CLEVERSWITCH_DEVICE_NAME": device_name,
        },
        fire_for_all_devices=hooks_cfg.fire_for_all_devices,
    )


def _run(hook: HookEntry, extra_env: dict[str, str]) -> None:
    env = {**os.environ, **extra_env}
    label = hook.name

    if hook.command is not None:
        cmd = hook.command
        shell = True
        log.debug(f"Running hook command '{label}': {hook.command} (timeout={hook.timeout}s)")
    else:
        expanded = os.path.expanduser(hook.path)
        if not os.path.isfile(expanded):
            log.warning(f"Hook '{label}' script not found: {expanded}")
            return
        cmd = [expanded]
        shell = False
        log.debug(f"Running hook script '{label}': {expanded} (timeout={hook.timeout}s)")

    try:
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            result = subprocess.run(
                cmd,
                env=env,
                timeout=hook.timeout,
                stdout=stdout,
                stderr=stderr,
                shell=shell,
            )
            out = _read_output(stdout)
            err = _read_output(stderr)
        if result.returncode != 0:
            log.warning(f"Hook {label} exited with code {result.returncode}")
            if err:
                log.warning(f"Hook stderr: {err}")
        elif out:
            log.debug(f"Hook stdout: {out}")
    except subprocess.TimeoutExpired:
        log.warning(f"Hook {label} timed out after {hook.timeout}s")
    except Exception as e:
        log.warning(f"Hook {label} failed: {e}")


def _read_output(output) -> str:
    output.seek(0)
    return output.read().decode(errors="replace").strip()
