"""Configuration loading and validation."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import yaml

from ..errors.errors import ConfigError
from ..model.config.args_settings import ArgsSettings
from ..model.config.config import Config
from ..model.config.hook_entry import HookEntry
from ..model.config.hooks_config import HooksConfig
from ..model.config.settings import Settings

_DEFAULT_CONFIG_PATH = Path("~/.config/cleverswitch/config.yaml").expanduser()

# ── Default config ────────────────────────────────────────────────────────────


def default_config() -> Config:
    return Config(
        hooks=HooksConfig(),
        settings=Settings(),
        arguments_settings=ArgsSettings(),
    )


# ── YAML loading ──────────────────────────────────────────────────────────────


def load(cli_args: argparse.Namespace) -> Config:
    """Load config from *path*. Falls back to ~/.config/cleverswitch/config.yaml,
    then to built-in defaults if no file is found."""
    path = cli_args.config
    cfg_path = Path(path).expanduser() if path else _DEFAULT_CONFIG_PATH

    if not cfg_path.exists():
        if path:
            raise ConfigError(f"Config file not found: {cfg_path}")
        return _parse({}, cli_args)

    try:
        with open(cfg_path) as f:
            raw: dict = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {cfg_path}: {e}") from e

    try:
        return _parse(raw, cli_args)
    except (KeyError, TypeError, ValueError) as e:
        raise ConfigError(f"Config error in {cfg_path}: {e}") from e


def _parse(raw: dict[str, Any], cli_args: argparse.Namespace) -> Config:
    defaults = default_config()

    # ── hooks ─────────────────────────────────────────────────────────────────
    h = raw.get("hooks", {})
    hooks = HooksConfig(
        on_switch=tuple(_parse_hooks(h.get("on_switch", []))),
        on_connect=tuple(_parse_hooks(h.get("on_connect", []))),
        on_disconnect=tuple(_parse_hooks(h.get("on_disconnect", []))),
    )

    # ── settings ──────────────────────────────────────────────────────────────
    s = raw.get("settings", {})

    raw_preferred_host = s.get("preferred_host")
    preferred_host_internal = None
    if raw_preferred_host is not None:
        raw_preferred_host = int(raw_preferred_host)
        if raw_preferred_host not in (1, 2, 3):
            raise ConfigError(f"settings.preferred_host must be 1, 2, or 3, got {raw_preferred_host}")
        preferred_host_internal: int | None = raw_preferred_host - 1  # convert to 0-based

    settings = Settings(
        read_timeout_ms=int(s.get("read_timeout_ms", defaults.settings.read_timeout_ms)),
        preferred_host=preferred_host_internal,
    )

    arguments_settings = ArgsSettings(
        verbose_extra=cli_args.verbose_extra if cli_args.verbose_extra is not None else False,
    )

    config = Config(hooks=hooks, settings=settings, arguments_settings=arguments_settings)
    _validate(config)
    return config


def _parse_hooks(entries: list) -> list[HookEntry]:
    result = []
    for entry in entries or []:
        if isinstance(entry, str):
            result.append(HookEntry(path=os.path.expanduser(entry)))
        elif isinstance(entry, dict):
            result.append(
                HookEntry(
                    path=os.path.expanduser(str(entry["path"])),
                    timeout=int(entry.get("timeout", 5)),
                )
            )
    return result


def _validate(config: Config) -> None:
    pass
