"""Unit tests for gateway/device_link.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.write_event import WriteEvent
from cleverswitch.gateway.device_link import DeviceLink
from cleverswitch.gateway.hid_gateway import HidGateway
from cleverswitch.gateway.write_router import WriteRouter
from cleverswitch.hidpp.constants import BOLT_PID, REPORT_LONG
from cleverswitch.listener.event_listener import EventListener
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

MSG = bytes([REPORT_LONG]) + bytes(19)


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _make_link(gateways=None, router=None):
    topics = _make_topics()
    listener = MagicMock(spec=EventListener)
    gateways = gateways if gateways is not None else [MagicMock(spec=HidGateway)]
    router = router or WriteRouter()
    link = DeviceLink(BOLT_PID, topics, listener, gateways, router)
    return link, topics, listener, gateways


def test_subscribes_to_write_topic():
    link, topics, _, _ = _make_link()
    topics.write.subscribe.assert_called_once_with(link)


def test_routes_write_to_selected_gateway():
    first, second = MagicMock(spec=HidGateway), MagicMock(spec=HidGateway)
    router = MagicMock(spec=WriteRouter)
    router.select.return_value = second
    link, _, _, _ = _make_link([first, second], router)

    link.notify(WriteEvent(slot=1, pid=BOLT_PID, hid_message=MSG))

    router.select.assert_called_once_with(MSG, [first, second])
    second.submit.assert_called_once_with(MSG)
    first.submit.assert_not_called()


def test_ignores_writes_for_other_pids():
    link, _, _, gateways = _make_link()
    link.notify(WriteEvent(slot=1, pid=0x9999, hid_message=MSG))
    gateways[0].submit.assert_not_called()


def test_ignores_non_write_events():
    link, _, _, gateways = _make_link()
    link.notify("not a WriteEvent")
    gateways[0].submit.assert_not_called()


def test_drops_write_when_router_selects_nothing():
    router = MagicMock(spec=WriteRouter)
    router.select.return_value = None
    link, _, _, gateways = _make_link(router=router)

    link.notify(WriteEvent(slot=1, pid=BOLT_PID, hid_message=MSG))

    gateways[0].submit.assert_not_called()


def test_start_starts_gateways_and_listener():
    link, _, listener, gateways = _make_link([MagicMock(spec=HidGateway), MagicMock(spec=HidGateway)])
    link.start()
    for gateway in gateways:
        gateway.start.assert_called_once()
    listener.start.assert_called_once()


def test_close_closes_every_gateway():
    link, _, _, gateways = _make_link([MagicMock(spec=HidGateway), MagicMock(spec=HidGateway)])
    link.close()
    for gateway in gateways:
        gateway.close.assert_called_once()
