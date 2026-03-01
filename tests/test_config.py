"""Unit tests for configuration loading and parsing.

Tests cover:
  - load()         — file not found, invalid YAML, valid file, default fallback
  - _parse()       — mapping raw YAML dicts → Config dataclasses
  - _validate()    — rejection of invalid PIDs, bad log levels
  - _hex_or_int()  — hex-string and integer coercion
  - _parse_hooks() — string / dict hook entries, tilde expansion
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from cleverswitch.config import (
    Config,
    HooksConfig,
    ReceiverConfig,
    Settings,
    _hex_or_int,
    _parse,
    _parse_hooks,
    _validate,
    default_config,
    load,
)
from cleverswitch.errors import ConfigError
from cleverswitch.hidpp.constants import BOLT_PID, UNIFYING_PIDS


# ── default_config ────────────────────────────────────────────────────────────


def test_default_config_uses_bolt_receiver_by_default():
    cfg = default_config()
    assert cfg.receiver.product_id == BOLT_PID


# ── load ──────────────────────────────────────────────────────────────────────


def test_load_raises_config_error_for_missing_explicit_path(tmp_path):
    # Arrange
    missing = tmp_path / "nonexistent.yaml"
    # Act / Assert
    with pytest.raises(ConfigError, match="not found"):
        load(path=missing)


def test_load_raises_config_error_for_malformed_yaml(tmp_path):
    # Arrange
    bad = tmp_path / "bad.yaml"
    bad.write_text("key: [unclosed bracket")
    # Act / Assert
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load(path=bad)


def test_load_parses_valid_yaml_file(tmp_path):
    # Arrange
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        textwrap.dedent("""\
            settings:
              log_level: DEBUG
        """)
    )
    # Act
    cfg = load(path=cfg_file)
    # Assert
    assert cfg.settings.log_level == "DEBUG"


def test_load_returns_default_config_when_no_default_path_exists(mocker):
    # Patch the module-level default path to a location that never exists
    mocker.patch("cleverswitch.config._DEFAULT_CONFIG_PATH", Path("/nonexistent/cleverswitch/config.yaml"))
    cfg = load(path=None)
    assert isinstance(cfg, Config)


# ── _parse ────────────────────────────────────────────────────────────────────


def test_parse_empty_dict_falls_back_to_all_defaults():
    cfg = _parse({})
    defaults = default_config()
    assert cfg.settings.log_level == defaults.settings.log_level


def test_parse_normalises_log_level_to_uppercase():
    cfg = _parse({"settings": {"log_level": "warning"}})
    assert cfg.settings.log_level == "WARNING"


def test_parse_accepts_hex_string_for_receiver_vendor_id():
    cfg = _parse({"receiver": {"vendor_id": "0x046D"}})
    assert cfg.receiver.vendor_id == 0x046D


def test_parse_populates_on_switch_hooks_from_mixed_entries():
    # Arrange: one string entry and one dict entry with a custom timeout
    raw = {
        "hooks": {
            "on_switch": [
                "/usr/local/bin/switch.sh",
                {"path": "/opt/myhook.sh", "timeout": 10},
            ]
        }
    }
    # Act
    cfg = _parse(raw)
    # Assert
    assert len(cfg.hooks.on_switch) == 2
    assert cfg.hooks.on_switch[0].path == "/usr/local/bin/switch.sh"
    assert cfg.hooks.on_switch[0].timeout == 5  # default timeout
    assert cfg.hooks.on_switch[1].timeout == 10


# ── _validate ─────────────────────────────────────────────────────────────────


def _receiver(pid: int = BOLT_PID) -> ReceiverConfig:
    return ReceiverConfig(product_id=pid)


def _settings(log_level: str = "INFO") -> Settings:
    return Settings(log_level=log_level)


def test_validate_raises_for_unknown_receiver_product_id():
    with pytest.raises(ConfigError, match="not a known Bolt/Unifying PID"):
        _validate(_receiver(0xFFFF), _settings())


@pytest.mark.parametrize("unifying_pid", UNIFYING_PIDS)
def test_validate_accepts_all_known_unifying_receiver_pids(unifying_pid):
    # Should not raise for any of the known Unifying PIDs
    _validate(_receiver(unifying_pid), _settings())


def test_validate_raises_for_invalid_log_level():
    with pytest.raises(ConfigError, match="Invalid log_level"):
        _validate(_receiver(), _settings("VERBOSE"))


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_validate_accepts_all_valid_log_levels(level):
    # Should not raise for any standard log level
    _validate(_receiver(), _settings(level))


# ── _hex_or_int ───────────────────────────────────────────────────────────────


def test_hex_or_int_returns_plain_integer_unchanged():
    assert _hex_or_int(42) == 42


def test_hex_or_int_parses_lowercase_0x_prefix_hex_string():
    assert _hex_or_int("0x046D") == 0x046D


def test_hex_or_int_parses_uppercase_0X_prefix_hex_string():
    assert _hex_or_int("0X1234") == 0x1234


def test_hex_or_int_parses_plain_decimal_string():
    assert _hex_or_int("255") == 255


def test_hex_or_int_raises_type_error_for_float():
    with pytest.raises(TypeError, match="Expected int or hex string"):
        _hex_or_int(3.14)


def test_hex_or_int_raises_type_error_for_none():
    with pytest.raises(TypeError, match="Expected int or hex string"):
        _hex_or_int(None)


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
