from __future__ import annotations

import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

from ..model.config.hook_entry import HookEntry
from ..model.config.hook_type import HookType
from ..model.config.hooks_config import HooksConfig

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cleverswitch-hook")


def fire(hooks: tuple[HookEntry, ...], env_vars: dict[str, str], *, fire_for_all_devices: bool = False) -> None:
    is_keyboard = env_vars.get("CLEVERSWITCH_DEVICE") == "keyboard"
    for hook in hooks:
        all_devices = fire_for_all_devices if hook.fire_for_all_devices is None else hook.fire_for_all_devices
        if not all_devices and not is_keyboard:
            continue
        _executor.submit(_run, hook, env_vars)


def fire_switch(hooks_cfg: HooksConfig, device_name: str, role: str, target_host: int) -> None:
    fire(
        hooks_cfg.for_type(HookType.SWITCH),
        {
            "CLEVERSWITCH_EVENT": "switch",
            "CLEVERSWITCH_DEVICE": role,
            "CLEVERSWITCH_DEVICE_NAME": device_name,
            "CLEVERSWITCH_TARGET_HOST": str(target_host + 1),  # 1-based for humans
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
        result = subprocess.run(
            cmd,
            env=env,
            timeout=hook.timeout,
            capture_output=True,
            text=True,
            shell=shell,
        )
        if result.returncode != 0:
            log.warning(f"Hook {label} exited with code {result.returncode}")
            if result.stderr:
                log.warning(f"Hook stderr: {result.stderr.strip()}")
        elif result.stdout:
            log.debug(f"Hook stdout: {result.stdout.strip()}")
    except subprocess.TimeoutExpired as e:
        proc = getattr(e, "process", None)
        if proc is not None:
            proc.kill()
            proc.communicate()
        else:
            log.warning(f"Hook {label} timed out but process handle unavailable — child may still be running")
        log.warning(f"Hook {label} timed out after {hook.timeout}s")
    except Exception as e:
        log.warning(f"Hook {label} failed: {e}")
