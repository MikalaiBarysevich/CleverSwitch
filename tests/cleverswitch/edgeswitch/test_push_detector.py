import pytest

from cleverswitch.edgeswitch.push_detector import PushDetector
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.modifier import Modifier

ALL_EDGES = frozenset(Edge)


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


def _held(clock, edges=ALL_EDGES, cooldown_s=1.0, threshold=100):
    d = PushDetector(edges, Modifier.CTRL, cooldown_s, threshold, clock=clock)
    d.on_state(Modifier.CTRL, False)
    return d


@pytest.mark.parametrize(
    ("dx", "dy", "edge"),
    [(-60, 0, Edge.LEFT), (60, 0, Edge.RIGHT), (0, -60, Edge.TOP), (0, 60, Edge.BOTTOM)],
)
def test_fires_at_threshold_per_direction(clock, dx, dy, edge):
    d = _held(clock)
    assert d.on_motion(dx, dy) is None
    assert d.on_motion(dx, dy) == edge


def test_ignores_motion_without_modifier(clock):
    d = PushDetector(ALL_EDGES, Modifier.CTRL, 1.0, 100, clock=clock)
    assert d.on_motion(500, 0) is None


def test_ignores_motion_with_wrong_modifier_set(clock):
    d = _held(clock)
    d.on_state(Modifier.CTRL | Modifier.SHIFT, False)
    assert d.on_motion(500, 0) is None


def test_ignores_motion_with_button_held(clock):
    d = _held(clock)
    d.on_state(Modifier.CTRL, True)
    assert d.on_motion(500, 0) is None


def test_reversal_restarts_the_axis(clock):
    d = _held(clock)
    assert d.on_motion(90, 0) is None
    assert d.on_motion(-20, 0) is None
    assert d.on_motion(90, 0) is None
    assert d.on_motion(20, 0) == Edge.RIGHT


def test_state_change_resets_accumulators(clock):
    d = _held(clock)
    d.on_motion(90, 0)
    d.on_state(Modifier.NONE, False)
    d.on_state(Modifier.CTRL, False)
    assert d.on_motion(20, 0) is None


def test_repeated_identical_state_keeps_accumulators(clock):
    d = _held(clock)
    d.on_motion(90, 0)
    d.on_state(Modifier.CTRL, False)
    assert d.on_motion(20, 0) == Edge.RIGHT


def test_latched_until_gesture_ends(clock):
    d = _held(clock, cooldown_s=0)
    assert d.on_motion(200, 0) == Edge.RIGHT
    assert d.on_motion(200, 0) is None
    d.on_state(Modifier.NONE, False)
    d.on_state(Modifier.CTRL, False)
    assert d.on_motion(200, 0) == Edge.RIGHT


def test_cooldown_resets_without_latching(clock):
    d = _held(clock, cooldown_s=1.0)
    assert d.on_motion(200, 0) == Edge.RIGHT
    d.on_state(Modifier.NONE, False)
    d.on_state(Modifier.CTRL, False)
    clock.now += 0.5
    assert d.on_motion(200, 0) is None
    clock.now += 1.0
    assert d.on_motion(50, 0) is None
    assert d.on_motion(60, 0) == Edge.RIGHT


def test_unmapped_direction_never_fires(clock):
    d = _held(clock, edges=frozenset({Edge.LEFT}))
    assert d.on_motion(500, 0) is None
    assert d.on_motion(0, 500) is None


def test_horizontal_wins_when_both_axes_cross(clock):
    d = _held(clock)
    assert d.on_motion(150, 150) == Edge.RIGHT
