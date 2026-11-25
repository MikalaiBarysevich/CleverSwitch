from unittest.mock import MagicMock

import pytest

from cleverswitch.event.edge_touched_event import EdgeTouchedEvent
from cleverswitch.event.host_change_event import HostChangeEvent, SwitchSource
from cleverswitch.event.hotplug_resync_event import HotplugResyncEvent
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.edge_switch_config import EdgeSwitchConfig
from cleverswitch.subscriber.edge_switch_subscriber import EdgeSwitchSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
        hotplug=MagicMock(spec=Topic),
        edge=MagicMock(spec=Topic),
    )


def _subscriber(topics):
    cfg = EdgeSwitchConfig(enabled=True, edges={Edge.LEFT: 0, Edge.RIGHT: 1})
    return EdgeSwitchSubscriber(cfg, topics)


def test_subscribes_to_edge_topic():
    topics = _make_topics()
    sub = _subscriber(topics)
    topics.edge.subscribe.assert_called_once_with(sub)


def test_mapped_edge_publishes_host_change_from_edge_source():
    topics = _make_topics()
    _subscriber(topics).notify(EdgeTouchedEvent(slot=0, pid=0, edge=Edge.RIGHT))

    topics.hid_event.publish.assert_called_once_with(
        HostChangeEvent(slot=0, pid=0, target_host=1, source=SwitchSource.EDGE)
    )


def test_unmapped_edge_publishes_nothing():
    topics = _make_topics()
    _subscriber(topics).notify(EdgeTouchedEvent(slot=0, pid=0, edge=Edge.TOP))
    topics.hid_event.publish.assert_not_called()


def test_ignores_other_events():
    topics = _make_topics()
    _subscriber(topics).notify(HotplugResyncEvent(slot=0, pid=0))
    topics.hid_event.publish.assert_not_called()


def test_no_switch_is_requested_once_shutdown_began():
    topics = _make_topics()
    sub = EdgeSwitchSubscriber(EdgeSwitchConfig(enabled=True, edges={Edge.LEFT: 0}), topics, lambda: True)
    sub.notify(EdgeTouchedEvent(slot=0, pid=0, edge=Edge.LEFT))
    topics.hid_event.publish.assert_not_called()


@pytest.mark.parametrize(("shutdown_first", "expected_writes"), [(False, 1), (True, 0)])
def test_a_queued_edge_event_goes_through_real_queues(shutdown_first, expected_writes):
    """The real path: edge queue -> EdgeSwitchSubscriber -> hid_event -> HostChangeSubscriber -> write.

    discovery stops the backend and then un-diverts keys; an event already sitting in the edge queue must not
    produce a CHANGE_HOST write in between. The first case proves the wiring the second one relies on.
    """
    import threading
    import time

    from cleverswitch.event.write_event import WriteEvent
    from cleverswitch.hidpp.constants import FEATURE_CHANGE_HOST
    from cleverswitch.model.logi_device import ROLE_KEYBOARD, LogiDevice
    from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
    from cleverswitch.subscriber.host_change_subscriber import HostChangeSubscriber
    from cleverswitch.subscriber.subscriber import Subscriber

    class Collector(Subscriber):
        def __init__(self):
            self.events = []

        def notify(self, event):
            self.events.append(event)

    topics = Topics(
        hid_event=Topic(),
        write=Topic(),
        device_info=Topic(),
        flags=Topic(),
        info_progress=Topic(),
    )
    registry = LogiDeviceRegistry()
    registry.register(
        0x407B,
        LogiDevice(wpid=0x407B, pid=0xB034, slot=1, role=ROLE_KEYBOARD, available_features={FEATURE_CHANGE_HOST: 5}),
    )
    collector = Collector()
    topics.write.subscribe(collector)

    shutdown = threading.Event()
    HostChangeSubscriber(registry, topics, shutdown.is_set)
    EdgeSwitchSubscriber(EdgeSwitchConfig(enabled=True, edges={Edge.LEFT: 0}), topics, shutdown.is_set)

    if shutdown_first:
        shutdown.set()
    topics.edge.publish(EdgeTouchedEvent(slot=0, pid=0, edge=Edge.LEFT))
    time.sleep(0.2)

    writes = [e for e in collector.events if isinstance(e, WriteEvent)]
    assert len(writes) == expected_writes
