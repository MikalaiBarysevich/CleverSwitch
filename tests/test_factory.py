"""Unit tests for factory.py — LogiProduct construction."""

from __future__ import annotations

import pytest

from cleverswitch.factory import _make_logi_product, _resolve_hosts_info


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
    assert result.paired_hosts is None
    assert result.hosts_info_feat_idx is None


def test_make_logi_product_resolves_reprog_controls_for_keyboard(mocker, fake_transport):
    mocker.patch(
        "cleverswitch.factory.resolve_feature_index",
        side_effect=[3, 4],  # CHANGE_HOST=3, REPROG=4
    )
    mocker.patch("cleverswitch.factory.are_es_cids_divertable", return_value=True)
    result = _make_logi_product(fake_transport, slot=1, role="keyboard", name="MX Keys")
    assert result is not None
    assert result.change_host_feat_idx == 3
    assert result.divert_feat_idx == 4
    # Divertable keyboard: hosts_info fields should be None
    assert result.paired_hosts is None
    assert result.hosts_info_feat_idx is None


def test_make_logi_product_keyboard_non_divertable_uses_disconnect_detection(mocker, fake_transport):
    """Non-divertable keyboard: falls back to disconnect-based host detection via x1815."""
    mocker.patch(
        "cleverswitch.factory.resolve_feature_index",
        side_effect=[3, None, 7],  # CHANGE_HOST=3, REPROG missing, HOSTS_INFO=7
    )
    mocker.patch("cleverswitch.factory.get_host_info_1814", return_value=(3, 1))
    mocker.patch("cleverswitch.factory.get_paired_hosts_1815", return_value=[0, 1])
    result = _make_logi_product(fake_transport, slot=1, role="keyboard", name="MX Keys S")
    assert result is not None
    assert result.change_host_feat_idx == 3
    assert result.divert_feat_idx is None
    assert result.hosts_info_feat_idx == 7
    assert result.paired_hosts == (0, 1)
    assert result.current_host == 1


def test_make_logi_product_keyboard_non_divertable_no_hosts_info(mocker, fake_transport):
    """Non-divertable keyboard without x1815: hosts_info fields remain None."""
    mocker.patch(
        "cleverswitch.factory.resolve_feature_index",
        side_effect=[3, None, None],  # CHANGE_HOST=3, REPROG missing, HOSTS_INFO absent
    )
    result = _make_logi_product(fake_transport, slot=1, role="keyboard", name="MX Keys S")
    assert result is not None
    assert result.change_host_feat_idx == 3
    assert result.divert_feat_idx is None
    assert result.hosts_info_feat_idx is None
    assert result.paired_hosts is None


def test_make_logi_product_keyboard_non_divertable_es_cids(mocker, fake_transport):
    """ES CIDs found but not divertable: same fallback path as REPROG absent."""
    mocker.patch(
        "cleverswitch.factory.resolve_feature_index",
        side_effect=[3, 4, None],  # CHANGE_HOST=3, REPROG=4, HOSTS_INFO absent
    )
    mocker.patch("cleverswitch.factory.are_es_cids_divertable", return_value=False)
    result = _make_logi_product(fake_transport, slot=1, role="keyboard", name="MX Keys S")
    assert result is not None
    assert result.change_host_feat_idx == 3
    assert result.divert_feat_idx is None
    assert result.hosts_info_feat_idx is None


def test_make_logi_product_name_is_preserved(mocker, fake_transport):
    mocker.patch("cleverswitch.factory.resolve_feature_index", return_value=2)
    result = _make_logi_product(fake_transport, slot=3, role="mouse", name="MX Anywhere 3")
    assert result.name == "MX Anywhere 3"


# ── _resolve_hosts_info ───────────────────────────────────────────────────────


def test_resolve_hosts_info_returns_all_none_when_hosts_info_absent(mocker, fake_transport):
    mocker.patch("cleverswitch.factory.resolve_feature_index", return_value=None)
    feat_idx, paired, curr = _resolve_hosts_info(fake_transport, slot=1, change_host_feat_idx=3, name="KB")
    assert feat_idx is None
    assert paired is None
    assert curr is None


def test_resolve_hosts_info_returns_feat_idx_when_get_host_info_fails(mocker, fake_transport):
    mocker.patch("cleverswitch.factory.resolve_feature_index", return_value=7)
    mocker.patch("cleverswitch.factory.get_host_info_1814", return_value=None)
    feat_idx, paired, curr = _resolve_hosts_info(fake_transport, slot=1, change_host_feat_idx=3, name="KB")
    assert feat_idx == 7
    assert paired is None
    assert curr is None


def test_resolve_hosts_info_returns_curr_host_when_paired_hosts_query_fails(mocker, fake_transport):
    mocker.patch("cleverswitch.factory.resolve_feature_index", return_value=7)
    mocker.patch("cleverswitch.factory.get_host_info_1814", return_value=(3, 2))
    mocker.patch("cleverswitch.factory.get_paired_hosts_1815", return_value=None)
    feat_idx, paired, curr = _resolve_hosts_info(fake_transport, slot=1, change_host_feat_idx=3, name="KB")
    assert feat_idx == 7
    assert paired is None
    assert curr == 2


def test_resolve_hosts_info_returns_full_info_on_success(mocker, fake_transport):
    mocker.patch("cleverswitch.factory.resolve_feature_index", return_value=7)
    mocker.patch("cleverswitch.factory.get_host_info_1814", return_value=(3, 0))
    mocker.patch("cleverswitch.factory.get_paired_hosts_1815", return_value=[0, 2])
    feat_idx, paired, curr = _resolve_hosts_info(fake_transport, slot=1, change_host_feat_idx=3, name="KB")
    assert feat_idx == 7
    assert paired == (0, 2)
    assert curr == 0
