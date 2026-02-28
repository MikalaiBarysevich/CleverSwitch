"""External hook script execution.

Scripts are invoked asynchronously in a thread pool so they never block
the main monitor loop.
"""

from __future__ import annotations

import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

from .config import HookEntry, HooksConfig

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cleverswitch-hook")


def fire(hooks: tuple[HookEntry, ...], env_vars: dict[str, str]) -> None:
    """Submit all *hooks* for async execution with the given environment."""
    for hook in hooks:
        _executor.submit(_run, hook, env_vars)


def fire_switch(hooks_cfg: HooksConfig, device_name: str, role: str, target_host: int, previous_host: int) -> None:
    fire(
        hooks_cfg.on_switch,
        {
            "CLEVERSWITCH_EVENT": "switch",
            "CLEVERSWITCH_DEVICE": role,
            "CLEVERSWITCH_DEVICE_NAME": device_name,
            "CLEVERSWITCH_TARGET_HOST": str(target_host + 1),  # 1-based for humans
            "CLEVERSWITCH_PREVIOUS_HOST": str(previous_host + 1),
        },
    )


def fire_connect(hooks_cfg: HooksConfig, device_name: str, role: str) -> None:
    fire(
        hooks_cfg.on_connect,
        {
            "CLEVERSWITCH_EVENT": "connect",
            "CLEVERSWITCH_DEVICE": role,
            "CLEVERSWITCH_DEVICE_NAME": device_name,
        },
    )


def fire_disconnect(hooks_cfg: HooksConfig, device_name: str, role: str) -> None:
    fire(
        hooks_cfg.on_disconnect,
        {
            "CLEVERSWITCH_EVENT": "disconnect",
            "CLEVERSWITCH_DEVICE": role,
            "CLEVERSWITCH_DEVICE_NAME": device_name,
        },
    )


def _run(hook: HookEntry, extra_env: dict[str, str]) -> None:
    """Run one hook script synchronously (called from a worker thread)."""
    env = {**os.environ, **extra_env}
    script = os.path.expanduser(hook.path)

    if not os.path.exists(script):
        log.warning("Hook script not found: %s", script)
        return

    log.debug("Running hook: %s (timeout=%ds)", script, hook.timeout)
    try:
        result = subprocess.run(
            [script],
            env=env,
            timeout=hook.timeout,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log.warning("Hook %s exited with code %d", script, result.returncode)
            if result.stderr:
                log.warning("Hook stderr: %s", result.stderr.strip())
        elif result.stdout:
            log.debug("Hook stdout: %s", result.stdout.strip())
    except subprocess.TimeoutExpired:
        log.warning("Hook %s timed out after %ds", script, hook.timeout)
    except Exception as e:
        log.warning("Hook %s failed: %s", script, e)
