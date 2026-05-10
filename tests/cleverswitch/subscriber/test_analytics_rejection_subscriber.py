"""Unit tests for subscriber/analytics_rejection_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.hidpp_response_event import HidppResponseEvent
from cleverswitch.event.set_report_flag_event import SetReportFlagEvent
from cleverswitch.hidpp.constants import (
    BOLT_PID,
    FEATURE_CHANGE_HOST,
    FEATURE_REPROG_CONTROLS_V4,
    KEY_FLAG_ANALYTICS,
    KEY_FLAG_DIVERTABLE,
    KEY_FLAG_PERSISTENTLY_DIVERTABLE,
    SW_ID_DIVERT,
)
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.analytics_rejection_subscriber import AnalyticsRejectionSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

PID = BOLT_PID
WPID = 0x4062
SLOT = 1
REPROG_IDX = 8


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _make_device(*, with_analytics: bool = True) -> LogiDevice:
    flags = {KEY_FLAG_DIVERTABLE, KEY_FLAG_PERSISTENTLY_DIVERTABLE}
    if with_analytics:
        flags.add(KEY_FLAG_ANALYTICS)
    return LogiDevice(
        wpid=WPID,
        pid=PID,
        slot=SLOT,
        role="keyboard",
        available_features={FEATURE_CHANGE_HOST: 9, FEATURE_REPROG_CONTROLS_V4: REPROG_IDX},
        supported_flags=flags,
    )


def _make_payload(cid: int, byte9: int) -> bytes:
    buf = bytearray(16)
    buf[0] = (cid >> 8) & 0xFF
    buf[1] = cid & 0xFF
    buf[5] = byte9
    return bytes(buf)


def _make_response(
    *, cid: int = 0x00D1, byte9: int = 0x00, sw_id: int = SW_ID_DIVERT, function: int = 3
) -> HidppResponseEvent:
    return HidppResponseEvent(
        slot=SLOT,
        pid=PID,
        feature_index=REPROG_IDX,
        function=function,
        sw_id=sw_id,
        payload=_make_payload(cid, byte9),
    )


def _setup(*, with_analytics: bool = True) -> tuple[AnalyticsRejectionSubscriber, Topics, LogiDevice]:
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = AnalyticsRejectionSubscriber(registry, topics)
    device = _make_device(with_analytics=with_analytics)
    registry.register(WPID, device)
    return sub, topics, device


def test_zero_byte9_echo_with_analytics_drops_flag_and_republishes():
    sub, topics, device = _setup()

    sub.notify(_make_response(cid=0x00D1, byte9=0x00))

    assert KEY_FLAG_ANALYTICS not in device.supported_flags
    topics.flags.publish.assert_called_once()
    published = topics.flags.publish.call_args[0][0]
    assert isinstance(published, SetReportFlagEvent)
    assert published.wpid == WPID
    assert published.pid == PID
    assert published.slot == SLOT


def test_nonzero_byte9_echo_no_state_change():
    sub, topics, device = _setup()

    sub.notify(_make_response(cid=0x00D1, byte9=0x03))

    assert KEY_FLAG_ANALYTICS in device.supported_flags
    topics.flags.publish.assert_not_called()


def test_foreign_sw_id_ignored():
    sub, topics, device = _setup()

    # sw_id values 1-7 belong to other apps (Solaar, etc.)
    sub.notify(_make_response(byte9=0x00, sw_id=5))

    assert KEY_FLAG_ANALYTICS in device.supported_flags
    topics.flags.publish.assert_not_called()


def test_non_host_switch_cid_ignored():
    sub, topics, device = _setup()

    sub.notify(_make_response(cid=0x00C4, byte9=0x00))

    assert KEY_FLAG_ANALYTICS in device.supported_flags
    topics.flags.publish.assert_not_called()


def test_device_without_analytics_flag_ignored():
    sub, topics, device = _setup(with_analytics=False)

    sub.notify(_make_response(cid=0x00D1, byte9=0x00))

    topics.flags.publish.assert_not_called()


def test_function_other_than_3_ignored():
    sub, topics, device = _setup()

    # function 0 = divertedKeyEvents notification path, not setCidReporting
    sub.notify(_make_response(byte9=0x00, function=0))

    assert KEY_FLAG_ANALYTICS in device.supported_flags
    topics.flags.publish.assert_not_called()


def test_second_rejection_after_fallback_ignored():
    sub, topics, device = _setup()

    sub.notify(_make_response(cid=0x00D1, byte9=0x00))
    sub.notify(_make_response(cid=0x00D2, byte9=0x00))

    topics.flags.publish.assert_called_once()


def test_unregistered_device_ignored():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = AnalyticsRejectionSubscriber(registry, topics)

    sub.notify(_make_response(cid=0x00D1, byte9=0x00))

    topics.flags.publish.assert_not_called()


def test_short_payload_ignored():
    sub, topics, device = _setup()

    response = HidppResponseEvent(
        slot=SLOT, pid=PID, feature_index=REPROG_IDX, function=3, sw_id=SW_ID_DIVERT, payload=b"\x00\xd1"
    )
    sub.notify(response)

    assert KEY_FLAG_ANALYTICS in device.supported_flags
    topics.flags.publish.assert_not_called()


def test_non_response_event_is_noop():
    sub, topics, _device = _setup()

    sub.notify("not an event")  # must not raise

    topics.flags.publish.assert_not_called()
