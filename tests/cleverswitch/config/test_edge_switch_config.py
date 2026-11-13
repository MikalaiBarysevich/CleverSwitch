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


@pytest.mark.parametrize("text", ["edge_switch: yes\n", "edge_switch: [left]\n", "edge_switch:\n  edges: [left]\n"])
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
            "push_threshold": 1200,
        }
    )
    assert cfg == EdgeSwitchConfig(
        enabled=True,
        modifiers=Modifier.CTRL | Modifier.ALT,
        cooldown_ms=500,
        edges={Edge.LEFT: 0, Edge.RIGHT: 2},
        push_threshold=1200,
    )


def test_present_section_defaults_to_enabled_with_ctrl():
    cfg = _edge({"edges": {"left": 1}})
    assert cfg.enabled is True
    assert cfg.modifiers == Modifier.CTRL
    assert cfg.cooldown_ms == 1000
    assert cfg.push_threshold == 200


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
    [("cooldown_ms", -1, 1000), ("cooldown_ms", 60001, 1000), ("push_threshold", 0, 200), ("push_threshold", "x", 200)],
)
def test_out_of_range_numbers_fall_back(key, value, default, caplog):
    cfg = _edge({key: value, "edges": {"left": 1}})
    assert getattr(cfg, key) == default
    assert f"edge_switch '{key}'" in caplog.text


def test_cooldown_zero_allowed():
    assert _edge({"cooldown_ms": 0, "edges": {"left": 1}}).cooldown_ms == 0
