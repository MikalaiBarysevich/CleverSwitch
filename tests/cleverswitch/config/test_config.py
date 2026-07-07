"""Unit tests for configuration loading and parsing."""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

import pytest

from src.cleverswitch.config.config import (
    _parse,
    _parse_hooks,
    default_config,
    load,
)
from src.cleverswitch.errors.errors import ConfigError
from src.cleverswitch.model.config.config import Config
from src.cleverswitch.model.config.hook_type import HookType


def _cli_args(**overrides) -> argparse.Namespace:
    defaults = {"config": None, "verbose_extra": None}
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ── default_config ────────────────────────────────────────────────────────────


def test_default_config_returns_config_instance():
    cfg = default_config()
    assert isinstance(cfg, Config)


# ── load ──────────────────────────────────────────────────────────────────────


def test_load_raises_config_error_for_missing_explicit_path(tmp_path):
    missing = tmp_path / "nonexistent.yaml"
    args = _cli_args(config=str(missing))
    with pytest.raises(ConfigError, match="not found"):
        load(args)


def test_load_raises_config_error_for_malformed_yaml(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("key: [unclosed bracket")
    args = _cli_args(config=str(bad))
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load(args)


def test_load_parses_valid_yaml_file(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        textwrap.dedent("""\
            hooks:
              myHook:
                path: "/usr/bin/hook.sh"
                type: SWITCH
        """)
    )
    args = _cli_args(config=str(cfg_file))
    cfg = load(args)
    assert len(cfg.hooks.for_type(HookType.SWITCH)) == 1


def test_load_returns_default_config_when_no_default_path_exists(mocker):
    mocker.patch("cleverswitch.config.config._DEFAULT_CONFIG_PATH", Path("/nonexistent/cleverswitch/config.yaml"))
    args = _cli_args()
    cfg = load(args)
    assert isinstance(cfg, Config)


# ── _parse ────────────────────────────────────────────────────────────────────


def test_parse_empty_dict_falls_back_to_all_defaults():
    cfg = _parse({}, _cli_args())
    defaults = default_config()
    assert cfg.hooks == defaults.hooks


def test_parse_populates_named_hooks_and_fire_for_all_devices():
    raw = {
        "hooks": {
            "fire_for_all_devices": True,
            "notify": {"command": "notify-send hi", "type": "SWITCH"},
            "syncInput": {"path": "/opt/myhook.sh", "type": ["CONNECT", "DISCONNECT"], "timeout": 10},
        }
    }
    cfg = _parse(raw, _cli_args())
    assert cfg.hooks.fire_for_all_devices is True
    assert set(cfg.hooks.hooks) == {"notify", "syncInput"}
    assert cfg.hooks.hooks["notify"].command == "notify-send hi"
    assert cfg.hooks.hooks["notify"].timeout == 5  # default timeout
    assert cfg.hooks.hooks["syncInput"].path == "/opt/myhook.sh"
    assert cfg.hooks.hooks["syncInput"].timeout == 10
    assert cfg.hooks.for_type(HookType.CONNECT) == (cfg.hooks.hooks["syncInput"],)
    assert cfg.hooks.for_type(HookType.DISCONNECT) == (cfg.hooks.hooks["syncInput"],)


def test_parse_sets_verbose_extra_from_cli_args():
    cfg = _parse({}, _cli_args(verbose_extra=True))
    assert cfg.arguments_settings.verbose_extra is True


def test_parse_uses_default_cache_path_when_unset():
    from src.cleverswitch.config.config import _DEFAULT_CACHE_PATH

    cfg = _parse({}, _cli_args())
    assert cfg.cache_path == _DEFAULT_CACHE_PATH


def test_parse_reads_cache_path_from_config():
    raw = {"cache": {"path": "/var/lib/cleverswitch/devices.json"}}
    cfg = _parse(raw, _cli_args())
    assert cfg.cache_path == Path("/var/lib/cleverswitch/devices.json")


def test_parse_expands_tilde_in_cache_path():
    cfg = _parse({"cache": {"path": "~/custom/devices.json"}}, _cli_args())
    assert cfg.cache_path == Path("~/custom/devices.json").expanduser()


# ── _parse_hooks ──────────────────────────────────────────────────────────────


def test_parse_hooks_returns_empty_dict_for_none_input():
    assert _parse_hooks(None) == {}


def test_parse_hooks_returns_empty_dict_for_empty_dict():
    assert _parse_hooks({}) == {}


def test_parse_hooks_ignores_fire_for_all_devices_key():
    result = _parse_hooks({"fire_for_all_devices": True, "h": {"path": "/a.sh", "type": "SWITCH"}})
    assert set(result) == {"h"}


def test_parse_hooks_parses_command_entry_with_type_list():
    result = _parse_hooks({"h": {"command": "echo hi", "type": ["CONNECT", "SWITCH"]}})
    assert result["h"].name == "h"
    assert result["h"].command == "echo hi"
    assert result["h"].path is None
    assert result["h"].types == frozenset({HookType.CONNECT, HookType.SWITCH})


def test_parse_hooks_parses_path_entry_with_custom_timeout():
    result = _parse_hooks({"h": {"path": "/bin/hook.sh", "type": "SWITCH", "timeout": 15}})
    assert result["h"].timeout == 15
    assert result["h"].types == frozenset({HookType.SWITCH})


def test_parse_hooks_type_is_case_insensitive():
    result = _parse_hooks({"h": {"path": "/a.sh", "type": "connect"}})
    assert result["h"].types == frozenset({HookType.CONNECT})


def test_parse_hooks_fire_for_all_devices_defaults_to_none_when_absent():
    result = _parse_hooks({"h": {"path": "/a.sh", "type": "SWITCH"}})
    assert result["h"].fire_for_all_devices is None


def test_parse_hooks_fire_for_all_devices_reads_explicit_true_and_false():
    result = _parse_hooks(
        {
            "on": {"path": "/a.sh", "type": "SWITCH", "fire_for_all_devices": True},
            "off": {"path": "/b.sh", "type": "SWITCH", "fire_for_all_devices": False},
        }
    )
    assert result["on"].fire_for_all_devices is True
    assert result["off"].fire_for_all_devices is False


def test_parse_hooks_skips_entry_with_both_path_and_command(caplog):
    with caplog.at_level("ERROR"):
        result = _parse_hooks({"h": {"path": "/a.sh", "command": "echo hi", "type": "SWITCH"}})
    assert result == {}
    assert "both" in caplog.text


def test_parse_hooks_skips_entry_with_neither_path_nor_command(caplog):
    with caplog.at_level("ERROR"):
        result = _parse_hooks({"h": {"type": "SWITCH"}})
    assert result == {}
    assert "neither" in caplog.text


def test_parse_hooks_skips_entry_with_no_valid_type(caplog):
    with caplog.at_level("ERROR"):
        result = _parse_hooks({"h": {"path": "/a.sh", "type": "BOGUS"}})
    assert result == {}


def test_parse_hooks_skips_non_mapping_entry(caplog):
    with caplog.at_level("ERROR"):
        result = _parse_hooks({"h": "/a.sh"})
    assert result == {}


def test_parse_hooks_ignores_unknown_type_but_keeps_valid_ones(caplog):
    with caplog.at_level("ERROR"):
        result = _parse_hooks({"h": {"path": "/a.sh", "type": ["SWITCH", "BOGUS"]}})
    assert result["h"].types == frozenset({HookType.SWITCH})
    assert "invalid type" in caplog.text


def test_verbose_extra_applied_when_no_config_file():
    args = argparse.Namespace(config=None, verbose_extra=True)
    config = load(args)
    assert config.arguments_settings.verbose_extra is True
