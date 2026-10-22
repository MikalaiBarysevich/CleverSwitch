"""Unit tests for subscriber/channel_rearm_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cleverswitch.event.link_channel_changed_event import CHANNEL_GATT, LinkChannelChangedEvent
from cleverswitch.event.set_report_flag_event import SetReportFlagEvent
from cleverswitch.event.transport_disconnected_event import TransportDisconnectedEvent
from cleverswitch.hidpp.constants import FEATURE_REPROG_CONTROLS_V4
from cleverswitch.model.logi_device import LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.channel_rearm_subscriber import ChannelRearmSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

KEYBOARD = 0xB35B
MOUSE = 0xB023


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _device(wpid, connected=True, reprog=True):
    features = {FEATURE_REPROG_CONTROLS_V4: 8} if reprog else {}
    return LogiDevice(wpid=wpid, pid=wpid, slot=0xFF, role=None, available_features=features, connected=connected)


def _setup(*devices):
    registry = LogiDeviceRegistry()
    for device in devices:
        registry.register(device.wpid, device)
    topics = _make_topics()
    return ChannelRearmSubscriber(registry, topics), topics


def _changed(pid=KEYBOARD, up=True):
    return LinkChannelChangedEvent(slot=0, pid=pid, channel=CHANNEL_GATT, up=up)


def test_subscribes_to_hid_event():
    subscriber, topics = _setup()
    topics.hid_event.subscribe.assert_called_once_with(subscriber)


@pytest.mark.parametrize("up", [True, False])
def test_rearms_a_connected_reprog_device_on_either_change(up):
    subscriber, topics = _setup(_device(KEYBOARD))

    subscriber.notify(_changed(up=up))

    topics.flags.publish.assert_called_once_with(SetReportFlagEvent(slot=0xFF, pid=KEYBOARD, wpid=KEYBOARD))


def test_skips_a_disconnected_device():
    subscriber, topics = _setup(_device(KEYBOARD, connected=False))
    subscriber.notify(_changed())
    topics.flags.publish.assert_not_called()


def test_skips_a_device_without_reprog_controls():
    subscriber, topics = _setup(_device(KEYBOARD, reprog=False))
    subscriber.notify(_changed())
    topics.flags.publish.assert_not_called()


def test_skips_devices_on_other_pids():
    subscriber, topics = _setup(_device(MOUSE))
    subscriber.notify(_changed(pid=KEYBOARD))
    topics.flags.publish.assert_not_called()


def test_ignores_other_events():
    subscriber, topics = _setup(_device(KEYBOARD))
    subscriber.notify(TransportDisconnectedEvent(slot=0, pid=KEYBOARD))
    topics.flags.publish.assert_not_called()
