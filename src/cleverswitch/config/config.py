"""Configuration loading and validation."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Any

import yaml

from ..errors.errors import ConfigError
from ..hidpp.constants import HOST_SWITCH_CIDS
from ..model.config.args_settings import ArgsSettings
from ..model.config.config import Config
from ..model.config.edge import Edge
from ..model.config.edge_switch_config import EdgeSwitchConfig
from ..model.config.hook_entry import HookEntry
from ..model.config.hook_type import HookType
from ..model.config.hooks_config import HooksConfig
from ..model.config.logging_config import DEFAULT_BACKUP_COUNT, DEFAULT_MAX_BYTES, LoggingConfig
from ..model.config.modifier import MODIFIER_NAMES, Modifier

log = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path("~/.config/cleverswitch/config.yaml").expanduser()
_DEFAULT_CACHE_PATH = Path("~/.config/cleverswitch/device_cache.json").expanduser()
_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
_MAX_SIZE_MB_RANGE = (1, 1024)
_BACKUP_COUNT_RANGE = (1, 50)
_COOLDOWN_MS_RANGE = (0, 60000)
_PUSH_THRESHOLD_RANGE = (1, 100000)
_VALID_HOSTS = frozenset(HOST_SWITCH_CIDS.values())

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

    if not isinstance(raw, dict):
        raise ConfigError(f"Config error in {cfg_path}: top level must be a mapping")

    try:
        return _parse(raw, cli_args)
    except (KeyError, TypeError, ValueError) as e:
        raise ConfigError(f"Config error in {cfg_path}: {e}") from e


def _parse(raw: dict[str, Any], cli_args: argparse.Namespace) -> Config:
    h = _section(raw, "hooks")
    hooks = HooksConfig(
        fire_for_all_devices=bool(h.get("fire_for_all_devices", False)),
        hooks=_parse_hooks(h),
    )

    arguments_settings = ArgsSettings(
        verbose_extra=cli_args.verbose_extra if cli_args.verbose_extra is not None else False,
    )

    c = _section(raw, "cache")
    cache_path = Path(os.path.expanduser(str(c["path"]))) if c.get("path") else _DEFAULT_CACHE_PATH

    config = Config(
        hooks=hooks,
        arguments_settings=arguments_settings,
        cache_path=cache_path,
        logging=_parse_logging(raw),
        edge_switch=_parse_edge_switch(raw),
    )
    _validate(config)
    return config


def _section(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"'{key}' must be a mapping")
    return value


def _parse_logging(raw: dict[str, Any]) -> LoggingConfig:
    section = _section(raw, "logging")
    file_section = _section(section, "file")
    defaults = LoggingConfig()

    level = defaults.level
    if "level" in section:
        name = str(section["level"]).strip().upper()
        if name in _LOG_LEVELS:
            level = _LOG_LEVELS[name]
        else:
            log.error(f"Invalid logging 'level' '{section['level']}'; using INFO")

    raw_path = file_section.get("path")
    file_path = Path(os.path.expanduser(os.path.expandvars(str(raw_path)))) if raw_path else defaults.file_path

    max_size_mb = _parse_bounded_int(
        "logging 'file.max_size_mb'", "max_size_mb", file_section, _MAX_SIZE_MB_RANGE, DEFAULT_MAX_BYTES // 2**20
    )
    backup_count = _parse_bounded_int(
        "logging 'file.backup_count'", "backup_count", file_section, _BACKUP_COUNT_RANGE, DEFAULT_BACKUP_COUNT
    )

    return LoggingConfig(
        level=level,
        file_enabled=bool(file_section.get("enabled", True)),
        file_path=file_path,
        max_bytes=max_size_mb * 2**20,
        backup_count=backup_count,
    )


def _parse_bounded_int(label: str, key: str, section: dict[str, Any], bounds: tuple[int, int], default: int) -> int:
    if key not in section:
        return default
    value = section[key]
    low, high = bounds
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        log.error(f"Invalid {label} '{value}' (expected an integer {low}..{high}); using {default}")
        return default
    return value


# Edge switch is optional: a malformed section turns it off instead of stopping the daemon.
def _parse_edge_switch(raw: dict[str, Any]) -> EdgeSwitchConfig:
    section = raw.get("edge_switch")
    if not section:
        return EdgeSwitchConfig()
    if not isinstance(section, dict):
        log.error("'edge_switch' must be a mapping; edge switch disabled")
        return EdgeSwitchConfig()
    defaults = EdgeSwitchConfig()

    enabled = section.get("enabled", True)
    if not isinstance(enabled, bool):
        log.error(f"edge_switch 'enabled' must be true or false, not '{enabled}'; edge switch disabled")
        enabled = False
    modifiers = _parse_modifiers(section.get("modifier", "ctrl"))
    raw_edges = section.get("edges") or {}
    if not isinstance(raw_edges, dict):
        log.error("edge_switch 'edges' must be a mapping of edge to host")
        raw_edges = {}
    edges = _parse_edges(raw_edges)
    cooldown_ms = _parse_bounded_int(
        "edge_switch 'cooldown_ms'", "cooldown_ms", section, _COOLDOWN_MS_RANGE, defaults.cooldown_ms
    )
    push_threshold = _parse_bounded_int(
        "edge_switch 'push_threshold'", "push_threshold", section, _PUSH_THRESHOLD_RANGE, defaults.push_threshold
    )

    if enabled and modifiers is None:
        log.error("edge_switch disabled: no valid 'modifier'")
        enabled = False
    if enabled and not edges:
        log.warning("edge_switch enabled but no valid edges; disabled")
        enabled = False

    return EdgeSwitchConfig(
        enabled=enabled,
        modifiers=modifiers if modifiers is not None else defaults.modifiers,
        cooldown_ms=cooldown_ms,
        edges=edges,
        push_threshold=push_threshold,
    )


def _parse_modifiers(raw_modifier: Any) -> Modifier | None:
    values = raw_modifier if isinstance(raw_modifier, list) else [raw_modifier]
    if not values:
        log.error("edge_switch 'modifier' is an empty list")
        return None
    result = Modifier.NONE
    for value in values:
        modifier = MODIFIER_NAMES.get(str(value).strip().lower())
        if modifier is None:
            log.error(f"edge_switch has invalid modifier '{value}' (expected one of {', '.join(MODIFIER_NAMES)})")
            return None
        result |= modifier
    return result


def _parse_edges(raw_edges: dict[str, Any]) -> dict[Edge, int]:
    result: dict[Edge, int] = {}
    for name, host in raw_edges.items():
        try:
            edge = Edge(str(name).strip().lower())
        except ValueError:
            log.error(f"edge_switch has unknown edge '{name}'; skipping")
            continue
        if isinstance(host, bool) or not isinstance(host, int) or host - 1 not in _VALID_HOSTS:
            log.error(f"edge_switch edge '{name}' has invalid host '{host}' (expected 1..3); skipping")
            continue
        result[edge] = host - 1
    return result


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

        timeout = _parse_hook_timeout(name, spec.get("timeout", 5))
        if timeout is None:
            continue

        override = spec.get("fire_for_all_devices")
        result[name] = HookEntry(
            name=name,
            types=types,
            path=str(path) if path else None,
            command=str(command) if command else None,
            timeout=timeout,
            fire_for_all_devices=None if override is None else bool(override),
        )
    return result


def _parse_hook_timeout(name: str, raw_timeout: Any) -> int | None:
    try:
        timeout = int(raw_timeout)
    except (TypeError, ValueError):
        timeout = 0
    if isinstance(raw_timeout, bool) or timeout <= 0:
        log.error(f"Hook '{name}' has invalid 'timeout' '{raw_timeout}'; skipping")
        return None
    return timeout


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
