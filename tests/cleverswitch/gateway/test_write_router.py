"""Unit tests for gateway/write_router.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.gateway.hid_channel import HidChannel
from cleverswitch.gateway.write_router import ReportIdWriteRouter, WriteRouter
from cleverswitch.hidpp.constants import (
    HIDPP_BT_USAGE_LONG,
    HIDPP_USAGE_LONG,
    HIDPP_USAGE_SHORT,
    REPORT_LONG,
    REPORT_SHORT,
)

SHORT_MSG = bytes([REPORT_SHORT]) + bytes(6)
LONG_MSG = bytes([REPORT_LONG]) + bytes(19)


def _hid_channel(usage: int) -> MagicMock:
    hid_channel = MagicMock(spec=HidChannel)
    hid_channel.device_info.usage = usage
    return hid_channel


def test_default_router_picks_the_first_hid_channel():
    first, second = _hid_channel(HIDPP_USAGE_SHORT), _hid_channel(HIDPP_USAGE_LONG)
    assert WriteRouter().select(LONG_MSG, [first, second]) is first


def test_default_router_without_hid_channel_selects_nothing():
    assert WriteRouter().select(LONG_MSG, []) is None


def test_report_id_router_sends_short_reports_to_the_short_collection():
    short, long = _hid_channel(HIDPP_USAGE_SHORT), _hid_channel(HIDPP_USAGE_LONG)
    assert ReportIdWriteRouter().select(SHORT_MSG, [long, short]) is short


def test_report_id_router_sends_long_reports_to_the_long_collection():
    short, long = _hid_channel(HIDPP_USAGE_SHORT), _hid_channel(HIDPP_USAGE_LONG)
    assert ReportIdWriteRouter().select(LONG_MSG, [short, long]) is long


def test_report_id_router_accepts_the_bluetooth_long_usage():
    bt_long = _hid_channel(HIDPP_BT_USAGE_LONG)
    assert ReportIdWriteRouter().select(LONG_MSG, [bt_long]) is bt_long


def test_report_id_router_selects_nothing_without_a_matching_collection():
    assert ReportIdWriteRouter().select(SHORT_MSG, [_hid_channel(HIDPP_USAGE_LONG)]) is None
