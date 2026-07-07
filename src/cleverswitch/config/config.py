"""Configuration loading and validation."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Any

import yaml

from ..errors.errors import ConfigError
from ..model.config.args_settings import ArgsSettings
from ..model.config.config import Config
from ..model.config.hook_entry import HookEntry
from ..model.config.hook_type import HookType
from ..model.config.hooks_config import HooksConfig

log = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path("~/.config/cleverswitch/config.yaml").expanduser()
_DEFAULT_CACHE_PATH = Path("~/.config/cleverswitch/device_cache.json").expanduser()

# ── Default config ────────────────────────────────────────────────────────────


def default_config() -> Config:
    return Config(
        hooks=HooksConfig(),
        arguments_settings=ArgsSettings(),
        cache_path=_DEFAULT_CACHE_PATH,
    )


# ── YAML loading ──────────────────────────────────────────────────────────────


def load(cli_args: argparse.Namespace) -> Config:
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
    h = raw.get("hooks", {})
    hooks = HooksConfig(
        fire_for_all_devices=bool(h.get("fire_for_all_devices", False)),
        hooks=_parse_hooks(h),
    )

    arguments_settings = ArgsSettings(
        verbose_extra=cli_args.verbose_extra if cli_args.verbose_extra is not None else False,
    )

    c = raw.get("cache", {})
    cache_path = Path(os.path.expanduser(str(c["path"]))) if c.get("path") else _DEFAULT_CACHE_PATH

    config = Config(hooks=hooks, arguments_settings=arguments_settings, cache_path=cache_path)
    _validate(config)
    return config


def _parse_hooks(raw_hooks: dict[str, Any]) -> dict[str, HookEntry]:
    """Parse the named-hook mapping. Malformed entries are logged and skipped so a
    single bad hook never brings down the daemon."""
    result: dict[str, HookEntry] = {}
    for name, spec in (raw_hooks or {}).items():
        if name == "fire_for_all_devices":
            continue
        if not isinstance(spec, dict):
            log.error(f"Hook '{name}' must be a mapping; skipping")
            continue

        path = spec.get("path")
        command = spec.get("command")
        if path and command:
            log.error(f"Hook '{name}' specifies both 'path' and 'command'; skipping")
            continue
        if not path and not command:
            log.error(f"Hook '{name}' specifies neither 'path' nor 'command'; skipping")
            continue

        types = _parse_hook_types(name, spec.get("type"))
        if not types:
            log.error(f"Hook '{name}' has no valid 'type'; skipping")
            continue

        override = spec.get("fire_for_all_devices")
        result[name] = HookEntry(
            name=name,
            types=types,
            path=str(path) if path else None,
            command=str(command) if command else None,
            timeout=int(spec.get("timeout", 5)),
            fire_for_all_devices=None if override is None else bool(override),
        )
    return result


def _parse_hook_types(name: str, raw_type: Any) -> frozenset[HookType]:
    if raw_type is None:
        return frozenset()
    values = raw_type if isinstance(raw_type, list) else [raw_type]
    result: set[HookType] = set()
    for value in values:
        try:
            result.add(HookType[str(value).strip().upper()])
        except KeyError:
            log.error(f"Hook '{name}' has invalid type '{value}'; ignoring")
    return frozenset(result)


def _validate(config: Config) -> None:
    pass
