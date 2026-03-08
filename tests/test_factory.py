"""Unit tests for factory.py — LogiProduct construction."""

from __future__ import annotations

import pytest

from cleverswitch.factory import _make_logi_product


def test_make_logi_product_returns_none_when_change_host_not_supported(mocker, fake_transport):
    mocker.patch("cleverswitch.factory.resolve_feature_index", return_value=None)
    result = _make_logi_product(fake_transport, slot=1, role="mouse", name="MX Master")
    assert result is None


def test_make_logi_product_returns_logi_product_for_mouse(mocker, fake_transport):
    mocker.patch("cleverswitch.factory.resolve_feature_index", return_value=3)
    result = _make_logi_product(fake_transport, slot=2, role="mouse", name="MX Master")
    assert result is not None
    assert result.slot == 2
    assert result.role == "mouse"
    assert result.change_host_feat_idx == 3
    assert result.divert_feat_idx is None


def test_make_logi_product_resolves_reprog_controls_for_keyboard(mocker, fake_transport):
    mocker.patch(
        "cleverswitch.factory.resolve_feature_index",
        side_effect=[3, 4],  # CHANGE_HOST=3, REPROG=4
    )
    result = _make_logi_product(fake_transport, slot=1, role="keyboard", name="MX Keys")
    assert result is not None
    assert result.change_host_feat_idx == 3
    assert result.divert_feat_idx == 4


def test_make_logi_product_returns_none_when_keyboard_lacks_reprog(mocker, fake_transport):
    mocker.patch(
        "cleverswitch.factory.resolve_feature_index",
        side_effect=[3, None],  # CHANGE_HOST=3, REPROG missing
    )
    result = _make_logi_product(fake_transport, slot=1, role="keyboard", name="MX Keys")
    assert result is None


def test_make_logi_product_name_is_preserved(mocker, fake_transport):
    mocker.patch("cleverswitch.factory.resolve_feature_index", return_value=2)
    result = _make_logi_product(fake_transport, slot=3, role="mouse", name="MX Anywhere 3")
    assert result.name == "MX Anywhere 3"
