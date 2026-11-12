import pytest

from cleverswitch.edgeswitch.edge_detector import EdgeDetector
from cleverswitch.edgeswitch.geometry import Rect
from cleverswitch.edgeswitch.sample import PointerSample
from cleverswitch.model.config.edge import Edge
from cleverswitch.model.config.modifier import Modifier

SCREEN = Rect(0, 0, 1920, 1080)
MIDDLE = (900, 500)
LEFT = (0, 500)
RIGHT = (1919, 500)
TOP_LEFT = (0, 0)


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


def _detector(clock, edges=(Edge.LEFT, Edge.RIGHT), modifiers=Modifier.CTRL, cooldown_s=1.0):
    return EdgeDetector(frozenset(edges), modifiers, cooldown_s, clock=clock)


def _sample(pos, modifiers=Modifier.CTRL, buttons_held=False):
    return PointerSample(x=pos[0], y=pos[1], modifiers=modifiers, buttons_held=buttons_held, bounds=SCREEN)


def _feed(detector, *samples):
    return [detector.feed(s) for s in samples]


def test_fires_when_cursor_moves_onto_edge_while_held(clock):
    d = _detector(clock)
    assert _feed(d, _sample(MIDDLE), _sample(LEFT)) == [None, Edge.LEFT]


def test_first_sample_at_the_edge_never_fires(clock):
    d = _detector(clock)
    assert _feed(d, _sample(LEFT), _sample(LEFT)) == [None, None]


def test_pressing_the_modifier_at_the_edge_does_not_fire(clock):
    d = _detector(clock)
    results = _feed(d, _sample(MIDDLE, Modifier.NONE), _sample(LEFT, Modifier.NONE), _sample(LEFT))
    assert results == [None, None, None]


def test_releasing_the_modifier_disarms(clock):
    d = _detector(clock)
    results = _feed(d, _sample(MIDDLE), _sample(MIDDLE, Modifier.NONE), _sample(LEFT, Modifier.NONE), _sample(LEFT))
    assert results == [None, None, None, None]


def test_held_button_blocks_and_disarms(clock):
    d = _detector(clock)
    assert _feed(d, _sample(MIDDLE), _sample(LEFT, buttons_held=True), _sample(LEFT)) == [None, None, None]


def test_modifier_set_must_match_exactly(clock):
    d = _detector(clock)
    both = Modifier.CTRL | Modifier.SHIFT
    assert _feed(d, _sample(MIDDLE, both), _sample(LEFT, both)) == [None, None]


def test_combination_fires(clock):
    both = Modifier.CTRL | Modifier.ALT
    d = _detector(clock, modifiers=both)
    assert _feed(d, _sample(MIDDLE, both), _sample(LEFT, both)) == [None, Edge.LEFT]


def test_unmapped_edge_never_fires(clock):
    d = _detector(clock, edges=(Edge.RIGHT,))
    assert _feed(d, _sample(MIDDLE), _sample(LEFT)) == [None, None]


def test_corner_prefers_horizontal_edge(clock):
    d = _detector(clock, edges=(Edge.LEFT, Edge.TOP))
    assert _feed(d, _sample(MIDDLE), _sample(TOP_LEFT)) == [None, Edge.LEFT]


def test_missing_sample_keeps_state(clock):
    d = _detector(clock)
    assert _feed(d, _sample(MIDDLE), None, _sample(LEFT)) == [None, None, Edge.LEFT]


def test_staying_at_the_edge_fires_once(clock):
    d = _detector(clock, cooldown_s=0)
    assert _feed(d, _sample(MIDDLE), _sample(LEFT), _sample(LEFT), _sample(LEFT)) == [None, Edge.LEFT, None, None]


def test_rearms_after_leaving_the_edge(clock):
    d = _detector(clock, cooldown_s=0)
    assert _feed(d, _sample(MIDDLE), _sample(LEFT), _sample(MIDDLE), _sample(LEFT)) == [
        None,
        Edge.LEFT,
        None,
        Edge.LEFT,
    ]


def test_rearms_after_release_and_press_off_the_edge(clock):
    d = _detector(clock, cooldown_s=0)
    results = _feed(d, _sample(MIDDLE), _sample(LEFT), _sample(LEFT, Modifier.NONE), _sample(MIDDLE), _sample(LEFT))
    assert results == [None, Edge.LEFT, None, None, Edge.LEFT]


def test_cooldown_suppresses_and_suppressed_touch_does_not_fire_on_expiry(clock):
    d = _detector(clock, cooldown_s=1.0)
    assert _feed(d, _sample(MIDDLE), _sample(LEFT), _sample(MIDDLE)) == [None, Edge.LEFT, None]

    clock.now += 0.5
    assert d.feed(_sample(RIGHT)) is None

    clock.now += 1.0
    assert d.feed(_sample(RIGHT)) is None
    assert _feed(d, _sample(MIDDLE), _sample(RIGHT)) == [None, Edge.RIGHT]
