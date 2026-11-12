from unittest.mock import MagicMock

from cleverswitch.event.device_connected_event import DeviceConnectedEvent
from cleverswitch.event.hotplug_resync_event import HotplugResyncEvent
from cleverswitch.subscriber.edge_backend_revive_subscriber import EdgeBackendReviveSubscriber
from cleverswitch.topic.topic import Topic


def _subscriber():
    topics = MagicMock()
    topics.hid_event = MagicMock(spec=Topic)
    backend = MagicMock()
    return EdgeBackendReviveSubscriber(backend, topics), backend, topics


def test_subscribes_to_hid_events():
    sub, _, topics = _subscriber()
    topics.hid_event.subscribe.assert_called_once_with(sub)


def test_device_connection_revives_the_backend():
    sub, backend, _ = _subscriber()
    sub.notify(DeviceConnectedEvent(slot=1, pid=0xC52B, link_established=True, wpid=0x4082))
    backend.revive.assert_called_once()


def test_disconnection_and_other_events_do_not():
    sub, backend, _ = _subscriber()
    sub.notify(DeviceConnectedEvent(slot=1, pid=0xC52B, link_established=False, wpid=0x4082))
    sub.notify(HotplugResyncEvent(slot=0, pid=0))
    backend.revive.assert_not_called()
