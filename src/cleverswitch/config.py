"""Configuration loading and validation."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError
from .hidpp.constants import BOLT_PID, UNIFYING_PIDS

_DEFAULT_CONFIG_PATH = Path("~/.config/cleverswitch/config.yaml").expanduser()


@dataclasses.dataclass(frozen=True)
class ReceiverConfig:
    vendor_id: int = 0x046D
    product_id: int = BOLT_PID
    path: str | None = None  # force a specific HID path


@dataclasses.dataclass(frozen=True)
class HookEntry:
    path: str
    timeout: int = 5


@dataclasses.dataclass(frozen=True)
class HooksConfig:
    on_switch: tuple[HookEntry, ...] = ()
    on_connect: tuple[HookEntry, ...] = ()
    on_disconnect: tuple[HookEntry, ...] = ()


@dataclasses.dataclass(frozen=True)
class Settings:
    read_timeout_ms: int = 1000
    retry_interval_s: int = 5
    max_retries: int = 0  # 0 = infinite
    log_level: str = "INFO"


@dataclasses.dataclass(frozen=True)
class Config:
    receiver: ReceiverConfig
    hooks: HooksConfig
    settings: Settings


# ── Default config ────────────────────────────────────────────────────────────


def default_config() -> Config:
    return Config(
        receiver=ReceiverConfig(),
        hooks=HooksConfig(),
        settings=Settings(),
    )


# ── YAML loading ──────────────────────────────────────────────────────────────


def load(path: Path | str | None = None) -> Config:
    """Load config from *path*. Falls back to ~/.config/cleverswitch/config.yaml,
    then to built-in defaults if no file is found."""
    cfg_path = Path(path).expanduser() if path else _DEFAULT_CONFIG_PATH

    if not cfg_path.exists():
        if path:
            raise ConfigError(f"Config file not found: {cfg_path}")
        return default_config()

    try:
        with open(cfg_path) as f:
            raw: dict = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {cfg_path}: {e}") from e

    try:
        return _parse(raw)
    except (KeyError, TypeError, ValueError) as e:
        raise ConfigError(f"Config error in {cfg_path}: {e}") from e


def _parse(raw: dict[str, Any]) -> Config:
    defaults = default_config()

    # ── receiver ──────────────────────────────────────────────────────────────
    r = raw.get("receiver", {})
    receiver = ReceiverConfig(
        vendor_id=_hex_or_int(r.get("vendor_id", defaults.receiver.vendor_id)),
        product_id=_hex_or_int(r.get("product_id", defaults.receiver.product_id)),
        path=r.get("path"),
    )

    # ── hooks ─────────────────────────────────────────────────────────────────
    h = raw.get("hooks", {})
    hooks = HooksConfig(
        on_switch=tuple(_parse_hooks(h.get("on_switch", []))),
        on_connect=tuple(_parse_hooks(h.get("on_connect", []))),
        on_disconnect=tuple(_parse_hooks(h.get("on_disconnect", []))),
    )

    # ── settings ──────────────────────────────────────────────────────────────
    s = raw.get("settings", {})
    settings = Settings(
        read_timeout_ms=int(s.get("read_timeout_ms", defaults.settings.read_timeout_ms)),
        retry_interval_s=int(s.get("retry_interval_s", defaults.settings.retry_interval_s)),
        max_retries=int(s.get("max_retries", defaults.settings.max_retries)),
        log_level=str(s.get("log_level", defaults.settings.log_level)).upper(),
    )

    _validate(receiver, settings)
    return Config(receiver=receiver, hooks=hooks, settings=settings)


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


def _validate(receiver: ReceiverConfig, settings: Settings) -> None:
    valid_pids = (BOLT_PID,) + UNIFYING_PIDS
    if receiver.product_id not in valid_pids:
        raise ConfigError(
            f"receiver.product_id 0x{receiver.product_id:04X} is not a known Bolt/Unifying PID. Expected one of: "
            + ", ".join(f"0x{p:04X}" for p in valid_pids)
        )
    if settings.log_level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        raise ConfigError(f"Invalid log_level: {settings.log_level!r}")


def _hex_or_int(value) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 16) if value.startswith("0x") or value.startswith("0X") else int(value)
    raise TypeError(f"Expected int or hex string, got {type(value).__name__}: {value!r}")
