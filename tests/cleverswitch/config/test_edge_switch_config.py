"""Parsing of the edge_switch config section."""

from __future__ import annotations

import argparse

import pytest

from src.cleverswitch.config.config import _parse
from src.cleverswitch.model.config.edge import Edge
from src.cleverswitch.model.config.edge_switch_config import EdgeSwitchConfig
from src.cleverswitch.model.config.modifier import Modifier


def _cli_args() -> argparse.Namespace:
    return argparse.Namespace(config=None, verbose_extra=None)


def _edge(section):
    return _parse({"edge_switch": section}, _cli_args()).edge_switch


def test_missing_section_is_disabled():
    assert _parse({}, _cli_args()).edge_switch == EdgeSwitchConfig()


def test_null_section_is_disabled():
    assert _edge(None).enabled is False


@pytest.mark.parametrize(
    "text",
    [
        "edge_switch: yes\n",
        "edge_switch: [left]\n",
        "edge_switch: []\n",
        "edge_switch: 0\n",
        "edge_switch:\n  edges: [left]\n",
    ],
)
def test_malformed_section_disables_edge_switch_but_loads_the_rest(tmp_path, caplog, text):
    from src.cleverswitch.config.config import load

    path = tmp_path / "c.yaml"
    path.write_text(text + "logging:\n  level: DEBUG\n")
    cfg = load(argparse.Namespace(config=str(path), verbose_extra=None))

    assert cfg.edge_switch.enabled is False
    assert cfg.logging.level == 10
    assert "edge_switch" in caplog.text


def test_full_section():
    cfg = _edge(
        {
            "enabled": True,
            "modifier": ["ctrl", "Alt"],
            "cooldown_ms": 500,
            "edges": {"left": 1, "RIGHT": 3},
        }
    )
    assert cfg == EdgeSwitchConfig(
        enabled=True,
        modifiers=Modifier.CTRL | Modifier.ALT,
        cooldown_ms=500,
        edges={Edge.LEFT: 0, Edge.RIGHT: 2},
    )


def test_present_section_defaults_to_enabled_with_ctrl():
    cfg = _edge({"edges": {"left": 1}})
    assert cfg.enabled is True
    assert cfg.modifiers == Modifier.CTRL
    assert cfg.cooldown_ms == 1000


def test_leftover_push_threshold_is_ignored_but_reported(caplog):
    """The push gesture is gone; saying so is kinder than silently doing nothing with the key."""
    cfg = _edge({"edges": {"left": 1}, "push_threshold": 200})
    assert cfg == EdgeSwitchConfig(enabled=True, edges={Edge.LEFT: 0})
    assert "unknown key 'push_threshold'" in caplog.text


def test_explicitly_disabled():
    assert _edge({"enabled": False, "edges": {"left": 1}}).enabled is False


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("control", Modifier.CTRL),
        ("option", Modifier.ALT),
        ("cmd", Modifier.META),
        ("win", Modifier.META),
        ("super", Modifier.META),
        ("command", Modifier.META),
        ("shift", Modifier.SHIFT),
    ],
)
def test_modifier_aliases(name, expected):
    assert _edge({"modifier": name, "edges": {"left": 1}}).modifiers == expected


@pytest.mark.parametrize("value", ["hyper", ["ctrl", "fn"], [], 5])
def test_invalid_modifier_disables(value, caplog):
    cfg = _edge({"modifier": value, "edges": {"left": 1}})
    assert cfg.enabled is False
    assert cfg.modifiers == Modifier.CTRL
    assert "modifier" in caplog.text


def test_unknown_edge_is_skipped(caplog):
    cfg = _edge({"edges": {"middle": 1, "left": 2}})
    assert cfg.edges == {Edge.LEFT: 1}
    assert "unknown edge 'middle'" in caplog.text


@pytest.mark.parametrize("host", [0, 4, "1", True, 1.0, None])
def test_invalid_host_is_skipped(host, caplog):
    cfg = _edge({"edges": {"left": host, "right": 2}})
    assert cfg.edges == {Edge.RIGHT: 1}
    assert "invalid host" in caplog.text


def test_no_valid_edges_disables(caplog):
    cfg = _edge({"edges": {"left": 9}})
    assert cfg.enabled is False
    assert "no valid edges" in caplog.text


def test_missing_edges_disables():
    assert _edge({"modifier": "ctrl"}).enabled is False


@pytest.mark.parametrize("value", ["no", "false", 0, None])
def test_non_boolean_enabled_disables(value, caplog):
    assert _edge({"enabled": value, "edges": {"left": 1}}).enabled is False
    assert "'enabled' must be true or false" in caplog.text


@pytest.mark.parametrize(
    ("key", "value", "default"),
    [("cooldown_ms", -1, 1000), ("cooldown_ms", 60001, 1000), ("cooldown_ms", "x", 1000)],
)
def test_out_of_range_numbers_fall_back(key, value, default, caplog):
    cfg = _edge({key: value, "edges": {"left": 1}})
    assert getattr(cfg, key) == default
    assert f"edge_switch '{key}'" in caplog.text


def test_cooldown_zero_allowed():
    assert _edge({"cooldown_ms": 0, "edges": {"left": 1}}).cooldown_ms == 0


@pytest.mark.parametrize("empty", [[], 0, False])
def test_empty_section_is_treated_as_malformed(empty, caplog):
    """A falsy value that is not a mapping is a mistake, not an absent section."""
    cfg = _edge(empty)
    assert cfg.enabled is False
    assert "must be a mapping" in caplog.text


def test_edges_mapping_of_the_wrong_type_is_reported(caplog):
    cfg = _edge({"edges": ["left"]})
    assert cfg.enabled is False
    assert "must be a mapping of edge to host" in caplog.text


def test_unknown_keys_are_reported(caplog):
    cfg = _edge({"modifer": "alt", "edges": {"left": 1}})
    assert cfg.enabled is True
    assert "unknown key 'modifer'" in caplog.text
