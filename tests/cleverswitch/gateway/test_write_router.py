"""Unit tests for gateway/write_router.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.gateway.hid_gateway import HidGateway
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


def _gateway(usage: int) -> MagicMock:
    gateway = MagicMock(spec=HidGateway)
    gateway.device_info.usage = usage
    return gateway


def test_default_router_picks_the_first_gateway():
    first, second = _gateway(HIDPP_USAGE_SHORT), _gateway(HIDPP_USAGE_LONG)
    assert WriteRouter().select(LONG_MSG, [first, second]) is first


def test_default_router_without_gateways_selects_nothing():
    assert WriteRouter().select(LONG_MSG, []) is None


def test_report_id_router_sends_short_reports_to_the_short_collection():
    short, long = _gateway(HIDPP_USAGE_SHORT), _gateway(HIDPP_USAGE_LONG)
    assert ReportIdWriteRouter().select(SHORT_MSG, [long, short]) is short


def test_report_id_router_sends_long_reports_to_the_long_collection():
    short, long = _gateway(HIDPP_USAGE_SHORT), _gateway(HIDPP_USAGE_LONG)
    assert ReportIdWriteRouter().select(LONG_MSG, [short, long]) is long


def test_report_id_router_accepts_the_bluetooth_long_usage():
    bt_long = _gateway(HIDPP_BT_USAGE_LONG)
    assert ReportIdWriteRouter().select(LONG_MSG, [bt_long]) is bt_long


def test_report_id_router_selects_nothing_without_a_matching_collection():
    assert ReportIdWriteRouter().select(SHORT_MSG, [_gateway(HIDPP_USAGE_LONG)]) is None
