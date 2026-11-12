from unittest.mock import MagicMock

from cleverswitch.event.edge_touched_event import EdgeTouchedEvent
from cleverswitch.event.host_change_event import HostChangeEvent, SwitchSource
from cleverswitch.event.hotplug_resync_event import HotplugResyncEvent
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.edge_switch_config import EdgeSwitchConfig
from cleverswitch.model.switch_echo_guard import SwitchEchoGuard
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


def _subscriber(topics, guard=None):
    cfg = EdgeSwitchConfig(enabled=True, edges={Edge.LEFT: 0, Edge.RIGHT: 1})
    return EdgeSwitchSubscriber(cfg, topics, guard or MagicMock(spec=SwitchEchoGuard))


def test_subscribes_to_edge_topic():
    topics = _make_topics()
    sub = _subscriber(topics)
    topics.edge.subscribe.assert_called_once_with(sub)


def test_mapped_edge_publishes_host_change_from_edge_source():
    topics = _make_topics()
    guard = MagicMock(spec=SwitchEchoGuard)
    _subscriber(topics, guard).notify(EdgeTouchedEvent(slot=0, pid=0, edge=Edge.RIGHT))

    topics.hid_event.publish.assert_called_once_with(
        HostChangeEvent(slot=0, pid=0, target_host=1, source=SwitchSource.EDGE)
    )
    guard.record.assert_called_once_with(1)


def test_unmapped_edge_publishes_nothing():
    topics = _make_topics()
    _subscriber(topics).notify(EdgeTouchedEvent(slot=0, pid=0, edge=Edge.TOP))
    topics.hid_event.publish.assert_not_called()


def test_ignores_other_events():
    topics = _make_topics()
    _subscriber(topics).notify(HotplugResyncEvent(slot=0, pid=0))
    topics.hid_event.publish.assert_not_called()
