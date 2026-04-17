"""External hook script execution.

Scripts are invoked asynchronously in a thread pool so they never block
the main monitor loop.
"""

from __future__ import annotations

import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

from ..model.config.hook_entry import HookEntry
from ..model.config.hooks_config import HooksConfig

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cleverswitch-hook")


def fire(hooks: tuple[HookEntry, ...], env_vars: dict[str, str], *, fire_for_all_devices: bool = False) -> None:
    """Submit all *hooks* for async execution with the given environment."""
    if not fire_for_all_devices and env_vars.get("CLEVERSWITCH_DEVICE") != "keyboard":
        return
    for hook in hooks:
        _executor.submit(_run, hook, env_vars)


def fire_switch(hooks_cfg: HooksConfig, device_name: str, role: str, target_host: int) -> None:
    fire(
        hooks_cfg.on_switch,
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
        hooks_cfg.on_connect,
        {
            "CLEVERSWITCH_EVENT": "connect",
            "CLEVERSWITCH_DEVICE": role,
            "CLEVERSWITCH_DEVICE_NAME": device_name,
        },
        fire_for_all_devices=hooks_cfg.fire_for_all_devices,
    )


def fire_disconnect(hooks_cfg: HooksConfig, device_name: str, role: str) -> None:
    fire(
        hooks_cfg.on_disconnect,
        {
            "CLEVERSWITCH_EVENT": "disconnect",
            "CLEVERSWITCH_DEVICE": role,
            "CLEVERSWITCH_DEVICE_NAME": device_name,
        },
        fire_for_all_devices=hooks_cfg.fire_for_all_devices,
    )


def _is_file_path(value: str) -> bool:
    """Heuristic: does the string look like a file path rather than a shell command?"""
    return value.startswith(("/", "~/", "./", "../"))


def _run(hook: HookEntry, extra_env: dict[str, str]) -> None:
    """Run one hook synchronously (called from a worker thread)."""
    env = {**os.environ, **extra_env}
    expanded = os.path.expanduser(hook.path)

    if _is_file_path(hook.path):
        if not os.path.exists(expanded):
            log.warning(f"Hook script not found: {expanded}")
            return
        cmd = [expanded]
        shell = False
        label = expanded
        log.debug(f"Running hook script: {label} (timeout={hook.timeout}s)")
    else:
        cmd = hook.path
        shell = True
        label = hook.path
        log.debug(f"Running hook command: {label} (timeout={hook.timeout}s)")

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
