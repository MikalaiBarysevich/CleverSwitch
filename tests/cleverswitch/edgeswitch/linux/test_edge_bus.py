from unittest.mock import MagicMock

import pytest

from cleverswitch.edgeswitch.linux.edge_bus import (
    ACCESS_DENIED,
    BUS_NAME,
    DBUS,
    UNKNOWN_METHOD,
    EdgeBus,
    decode_edges,
    has_owner,
)
from cleverswitch.errors.errors import EdgeSwitchError
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.modifier import Modifier

from .fake_bus import PEER_OWNER, FakeBus, call, owner_changed, signal

PEER = "org.kde.KWin"


def _edge_bus(decode_state=None, **kwargs):
    bus = FakeBus(owners={PEER: PEER_OWNER}, **kwargs)
    return EdgeBus(bus, PEER, decode_state), bus


@pytest.mark.parametrize(
    ("mask", "edges"),
    [(0, set()), (1, {Edge.LEFT}), (2.0, {Edge.RIGHT}), (5, {Edge.LEFT, Edge.TOP}), (15, set(Edge)), (16, set())],
)
def test_decode_edges(mask, edges):
    assert decode_edges(mask) == frozenset(edges)


@pytest.mark.parametrize("mask", ["1", None, True])
def test_decode_edges_rejects_non_numbers(mask):
    with pytest.raises(ValueError):
        decode_edges(mask)


def test_has_owner():
    bus = FakeBus(owners={PEER: PEER_OWNER})
    assert has_owner(bus, PEER)
    assert not has_owner(bus, "org.gnome.Shell")


def test_start_watches_the_peer_before_resolving_and_taking_the_name():
    _, bus = _edge_bus()
    members = [c[3] for c in bus.calls]
    # The watch must precede the owner lookup, or an owner change in between would be missed forever.
    assert members == ["AddMatch", "GetNameOwner", "RequestName"]
    assert f"arg0='{PEER}'" in bus.calls[0][4][0]
    assert bus.calls[2][4] == (BUS_NAME, 4)


def test_a_second_instance_is_refused():
    with pytest.raises(EdgeSwitchError, match="already watching"):
        _edge_bus(request_name=3)


def test_missing_peer_raises():
    with pytest.raises(OSError):
        EdgeBus(FakeBus(), PEER)


def test_edges_from_the_peer_reach_the_sink():
    edge_bus, bus = _edge_bus()
    sink = MagicMock()
    bus.push(call("Edges", 1), call("Edges", 0))
    edge_bus.drain(sink)
    assert [c.args[0] for c in sink.on_edges.call_args_list] == [frozenset({Edge.LEFT}), frozenset()]
    assert bus.replies == ["Edges", "Edges"]


def test_other_senders_are_denied():
    edge_bus, bus = _edge_bus()
    sink = MagicMock()
    bus.push(call("Edges", 1, sender=":1.99"))
    edge_bus.drain(sink)
    sink.on_edges.assert_not_called()
    assert bus.errors == [("Edges", ACCESS_DENIED)]


@pytest.mark.parametrize(
    "message",
    [
        call("Edges", 1, path="/other"),
        call("Edges", 1, interface="other.Iface"),
        call("Bogus", 1),
        call("Edges"),
        call("Edges", "x"),
        call("State", 4),  # only GNOME takes state
    ],
)
def test_unknown_or_malformed_calls_get_an_error(message):
    edge_bus, bus = _edge_bus()
    sink = MagicMock()
    bus.push(message)
    edge_bus.drain(sink)
    sink.on_edges.assert_not_called()
    sink.on_state.assert_not_called()
    assert bus.errors == [(message.member, UNKNOWN_METHOD)]


def test_state_is_decoded_when_a_decoder_is_given():
    edge_bus, bus = _edge_bus(decode_state=lambda mask: (Modifier.CTRL, bool(mask & 1)))
    sink = MagicMock()
    bus.push(call("State", 1))
    edge_bus.drain(sink)
    sink.on_state.assert_called_once_with(Modifier.CTRL, True)
    assert bus.replies == ["State"]


def test_peer_going_away_raises():
    edge_bus, bus = _edge_bus()
    bus.push(owner_changed(PEER, ""))
    with pytest.raises(OSError, match="went away"):
        edge_bus.drain(MagicMock())


def test_unrelated_owner_changes_are_ignored():
    edge_bus, bus = _edge_bus()
    bus.push(owner_changed("org.other", ""), owner_changed(PEER, PEER_OWNER))
    edge_bus.drain(MagicMock())


def test_a_spoofed_owner_change_is_ignored():
    edge_bus, bus = _edge_bus()
    spoof = signal("NameOwnerChanged", PEER, "", "", sender=":1.99", interface=DBUS)
    bus.push(spoof)
    edge_bus.drain(MagicMock(), None)  # would raise OSError if the sender were not checked


def test_a_short_owner_change_is_ignored():
    edge_bus, bus = _edge_bus()
    bus.push(signal("NameOwnerChanged", PEER, sender=DBUS, interface=DBUS))
    edge_bus.drain(MagicMock())


def test_other_signals_go_to_the_handler():
    edge_bus, bus = _edge_bus()
    handler = MagicMock()
    message = signal("ExtensionStateChanged", "uuid", {})
    bus.push(message, signal("Ignored"))
    edge_bus.drain(MagicMock(), handler)
    assert handler.call_count == 2
    edge_bus.drain(MagicMock())  # no handler: nothing happens


def test_other_message_kinds_are_skipped_and_close_closes_the_bus():
    from cleverswitch.edgeswitch.linux.edge_bus import BusMessage

    edge_bus, bus = _edge_bus()
    bus.push(BusMessage("return"))
    edge_bus.drain(MagicMock())
    edge_bus.add_match("type='signal'")
    assert edge_bus.bus is bus
    assert edge_bus.fd() == bus.fd()
    edge_bus.close()
    assert bus.closed
