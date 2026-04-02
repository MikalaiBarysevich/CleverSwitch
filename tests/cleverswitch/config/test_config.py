"""Unit tests for configuration loading and parsing."""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

import pytest

from cleverswitch.config.config import (
    _parse,
    _parse_hooks,
    default_config,
    load,
)
from cleverswitch.errors.errors import ConfigError
from cleverswitch.model.config.config import Config


def _cli_args(**overrides) -> argparse.Namespace:
    defaults = {"config": None, "verbose_extra": None}
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ── default_config ────────────────────────────────────────────────────────────


def test_default_config_returns_config_instance():
    cfg = default_config()
    assert isinstance(cfg, Config)


def test_default_config_has_default_read_timeout():
    cfg = default_config()
    assert cfg.settings.read_timeout_ms == 2000


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
            settings:
              read_timeout_ms: 3000
        """)
    )
    args = _cli_args(config=str(cfg_file))
    cfg = load(args)
    assert cfg.settings.read_timeout_ms == 3000


def test_load_returns_default_config_when_no_default_path_exists(mocker):
    mocker.patch("cleverswitch.config.config._DEFAULT_CONFIG_PATH", Path("/nonexistent/cleverswitch/config.yaml"))
    args = _cli_args()
    cfg = load(args)
    assert isinstance(cfg, Config)


# ── _parse ────────────────────────────────────────────────────────────────────


def test_parse_empty_dict_falls_back_to_all_defaults():
    cfg = _parse({}, _cli_args())
    defaults = default_config()
    assert cfg.settings.read_timeout_ms == defaults.settings.read_timeout_ms


def test_parse_preferred_host_converts_to_zero_based():
    """User-facing value 1/2/3 should be stored as 0-based index 0/1/2."""
    assert _parse({"settings": {"preferred_host": 1}}, _cli_args()).settings.preferred_host == 0
    assert _parse({"settings": {"preferred_host": 2}}, _cli_args()).settings.preferred_host == 1
    assert _parse({"settings": {"preferred_host": 3}}, _cli_args()).settings.preferred_host == 2


def test_parse_preferred_host_defaults_to_none():
    cfg = _parse({}, _cli_args())
    assert cfg.settings.preferred_host is None


def test_parse_preferred_host_raises_for_invalid_value():
    from cleverswitch.errors import ConfigError

    with pytest.raises(ConfigError, match="preferred_host"):
        _parse({"settings": {"preferred_host": 4}}, _cli_args())


def test_parse_populates_on_switch_hooks_from_mixed_entries():
    raw = {
        "hooks": {
            "on_switch": [
                "/usr/local/bin/switch.sh",
                {"path": "/opt/myhook.sh", "timeout": 10},
            ]
        }
    }
    cfg = _parse(raw, _cli_args())
    assert len(cfg.hooks.on_switch) == 2
    assert cfg.hooks.on_switch[0].path == "/usr/local/bin/switch.sh"
    assert cfg.hooks.on_switch[0].timeout == 5  # default timeout
    assert cfg.hooks.on_switch[1].timeout == 10


def test_parse_sets_verbose_extra_from_cli_args():
    cfg = _parse({}, _cli_args(verbose_extra=True))
    assert cfg.arguments_settings.verbose_extra is True


# ── _parse_hooks ──────────────────────────────────────────────────────────────


def test_parse_hooks_returns_empty_list_for_none_input():
    assert _parse_hooks(None) == []


def test_parse_hooks_returns_empty_list_for_empty_list():
    assert _parse_hooks([]) == []


def test_parse_hooks_parses_plain_string_entry_with_default_timeout():
    result = _parse_hooks(["/usr/bin/myhook.sh"])
    assert len(result) == 1
    assert result[0].path == "/usr/bin/myhook.sh"
    assert result[0].timeout == 5


def test_parse_hooks_parses_dict_entry_with_custom_timeout():
    result = _parse_hooks([{"path": "/bin/hook.sh", "timeout": 15}])
    assert result[0].timeout == 15


def test_parse_hooks_expands_tilde_in_string_entry():
    result = _parse_hooks(["~/myhook.sh"])
    assert not result[0].path.startswith("~")


def test_parse_hooks_expands_tilde_in_dict_entry():
    result = _parse_hooks([{"path": "~/scripts/hook.sh"}])
    assert not result[0].path.startswith("~")
