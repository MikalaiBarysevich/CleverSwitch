from unittest.mock import MagicMock

from cleverswitch.edgeswitch.edge_detector import EdgeDetector
from cleverswitch.edgeswitch.edge_sink import EdgeSink
from cleverswitch.edgeswitch.geometry import Rect
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.modifier import Modifier

SCREEN = Rect(0, 0, 1920, 1080)


def _sink(stopping=lambda: False):
    detector = EdgeDetector(frozenset({Edge.LEFT}), Modifier.CTRL, 0, clock=lambda: 0.0)
    publish = MagicMock()
    return EdgeSink(detector, publish, stopping), publish


def test_location_is_looked_up_only_while_the_gesture_is_held():
    sink, publish = _sink()
    locate = MagicMock(return_value=(900, 500, SCREEN))

    sink.on_motion(locate)
    locate.assert_not_called()

    sink.on_state(Modifier.CTRL, False)
    sink.on_motion(locate)
    locate.assert_called_once()
    publish.assert_not_called()


def test_entering_the_edge_publishes():
    sink, publish = _sink()
    sink.on_state(Modifier.CTRL, False)
    sink.on_motion(lambda: (900, 500, SCREEN))
    sink.on_motion(lambda: (0, 500, SCREEN))
    publish.assert_called_once_with(Edge.LEFT)


def test_unknown_location_is_skipped():
    sink, publish = _sink()
    sink.on_state(Modifier.CTRL, False)
    sink.on_motion(lambda: None)
    publish.assert_not_called()


def test_nothing_is_looked_up_or_published_while_stopping():
    sink, publish = _sink(stopping=lambda: True)
    locate = MagicMock(return_value=(0, 500, SCREEN))
    sink.on_state(Modifier.CTRL, False)
    sink.on_motion(locate)
    locate.assert_not_called()
    publish.assert_not_called()


def test_stop_during_lookup_suppresses_publish():
    stopping = MagicMock(side_effect=[False, False, True])
    sink, publish = _sink(stopping=stopping)
    sink.on_state(Modifier.CTRL, False)
    sink.on_motion(lambda: (900, 500, SCREEN))
    sink.on_motion(lambda: (0, 500, SCREEN))
    publish.assert_not_called()
