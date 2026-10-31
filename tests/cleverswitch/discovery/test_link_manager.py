"""Unit tests for discovery/link_manager.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.discovery.link_manager import LinkManager
from cleverswitch.event.hid_node_added_event import HidNodeAddedEvent
from cleverswitch.event.hid_node_removed_event import HidNodeRemovedEvent
from cleverswitch.event.hotplug_resync_event import HotplugResyncEvent
from cleverswitch.gateway.device_link import DeviceLink
from cleverswitch.hidpp.constants import BOLT_PID, CONNECTION_BLUETOOTH, CONNECTION_RECEIVER
from cleverswitch.hidpp.transport import HidDeviceInfo
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

BT_PID = 0xB35B


def _topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
        hotplug=MagicMock(spec=Topic),
    )


def _info(pid, path=b"/dev/hidraw0"):
    connection_type = CONNECTION_RECEIVER if pid == BOLT_PID else CONNECTION_BLUETOOTH
    return HidDeviceInfo(
        path=path, vid=0x046D, pid=pid, usage_page=0xFF00, usage=0x0002, connection_type=connection_type
    )


class _Fixture:
    def __init__(self, listed=None):
        self.listed: dict[int, list[HidDeviceInfo]] = listed or {}
        self.topics = _topics()
        self.links: dict[int, MagicMock] = {}
        self.link_factory = MagicMock(side_effect=self._make_link)
        self.enumerate = MagicMock(side_effect=self._enumerate)
        self.manager = LinkManager(
            self.topics, verbose_extra=True, link_factory=self.link_factory, enumerate_devices=self.enumerate
        )

    def _make_link(self, pid, _collections, _topics):
        link = MagicMock(spec=DeviceLink)
        self.links[pid] = link
        return link

    def _enumerate(self, product_id=0, verbose_extra=False):
        if product_id:
            return {product_id: self.listed[product_id]} if self.listed.get(product_id) else {}
        return {pid: infos for pid, infos in self.listed.items() if infos}


def test_subscribes_to_the_hotplug_topic():
    f = _Fixture()
    f.topics.hotplug.subscribe.assert_called_once_with(f.manager)


def test_added_node_creates_and_starts_a_link_from_what_is_listed():
    f = _Fixture({BT_PID: [_info(BT_PID)]})

    f.manager.notify(HidNodeAddedEvent(slot=0, pid=BT_PID))

    f.enumerate.assert_called_once_with(product_id=BT_PID, verbose_extra=True)
    f.link_factory.assert_called_once_with(BT_PID, [_info(BT_PID)], f.topics)
    f.links[BT_PID].start.assert_called_once_with()


def test_event_for_a_pid_with_nothing_listed_creates_no_link():
    f = _Fixture()

    f.manager.notify(HidNodeAddedEvent(slot=0, pid=0x408A))

    f.link_factory.assert_not_called()


def test_later_events_update_the_existing_link():
    f = _Fixture({BT_PID: [_info(BT_PID, b"/dev/hidraw5")]})
    f.manager.notify(HidNodeAddedEvent(slot=0, pid=BT_PID))
    f.listed[BT_PID] = [_info(BT_PID, b"/dev/hidraw7")]

    f.manager.notify(HidNodeAddedEvent(slot=0, pid=BT_PID))

    f.link_factory.assert_called_once()
    f.links[BT_PID].update.assert_called_once_with([_info(BT_PID, b"/dev/hidraw7")])


def test_removed_node_parks_the_link_with_what_is_left():
    f = _Fixture({BT_PID: [_info(BT_PID)]})
    f.manager.notify(HidNodeAddedEvent(slot=0, pid=BT_PID))
    f.listed[BT_PID] = []

    f.manager.notify(HidNodeRemovedEvent(slot=0, pid=BT_PID))

    f.links[BT_PID].update.assert_called_once_with([])
    f.links[BT_PID].close.assert_not_called()


def test_resync_creates_links_for_everything_listed():
    f = _Fixture({BOLT_PID: [_info(BOLT_PID)], BT_PID: [_info(BT_PID)]})

    f.manager.notify(HotplugResyncEvent(slot=0, pid=0))

    f.enumerate.assert_called_once_with(verbose_extra=True)
    assert set(f.links) == {BOLT_PID, BT_PID}


def test_resync_parks_known_links_that_are_no_longer_listed():
    f = _Fixture({BOLT_PID: [_info(BOLT_PID)], BT_PID: [_info(BT_PID)]})
    f.manager.notify(HotplugResyncEvent(slot=0, pid=0))
    f.listed[BT_PID] = []

    f.manager.notify(HotplugResyncEvent(slot=0, pid=0))

    f.links[BT_PID].update.assert_called_once_with([])
    f.links[BOLT_PID].update.assert_called_once_with([_info(BOLT_PID)])


def test_ignores_other_events():
    f = _Fixture({BT_PID: [_info(BT_PID)]})

    f.manager.notify("something else")

    f.enumerate.assert_not_called()


def test_close_all_closes_every_link_and_ignores_later_events():
    f = _Fixture({BOLT_PID: [_info(BOLT_PID)], BT_PID: [_info(BT_PID)]})
    f.manager.notify(HotplugResyncEvent(slot=0, pid=0))

    f.manager.close_all()
    f.manager.notify(HidNodeRemovedEvent(slot=0, pid=BT_PID))

    for link in f.links.values():
        link.close.assert_called_once_with()
        link.update.assert_not_called()
