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
CTRL = Modifier.CTRL
NONE = Modifier.NONE


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


def _detector(clock, edges=(Edge.LEFT, Edge.RIGHT), modifiers=CTRL, cooldown_s=1.0):
    return EdgeDetector(frozenset(edges), modifiers, cooldown_s, clock=clock)


def _at(d, *positions):
    return [d.on_pointer(x, y, SCREEN) for x, y in positions]


def test_fires_when_cursor_moves_onto_edge_while_held(clock):
    d = _detector(clock)
    d.on_state(CTRL, False)
    assert _at(d, MIDDLE, LEFT) == [None, Edge.LEFT]


def test_inactive_until_modifier_held():
    d = _detector(FakeClock())
    assert not d.active
    assert _at(d, MIDDLE, LEFT) == [None, None]
    d.on_state(CTRL, False)
    assert d.active


def test_first_position_at_the_edge_never_fires(clock):
    d = _detector(clock)
    d.on_state(CTRL, False)
    assert _at(d, LEFT, LEFT) == [None, None]


def test_pressing_the_modifier_at_the_edge_does_not_fire(clock):
    d = _detector(clock)
    d.on_state(CTRL, False)
    _at(d, MIDDLE)
    d.on_state(NONE, False)
    d.on_state(CTRL, False)
    assert _at(d, LEFT) == [None]


def test_held_button_blocks_and_disarms(clock):
    d = _detector(clock)
    d.on_state(CTRL, False)
    _at(d, MIDDLE)
    d.on_state(CTRL, True)
    assert not d.active
    assert _at(d, LEFT) == [None]
    d.on_state(CTRL, False)
    assert _at(d, LEFT) == [None]


def test_modifier_set_must_match_exactly(clock):
    d = _detector(clock)
    d.on_state(CTRL | Modifier.SHIFT, False)
    assert not d.active
    assert _at(d, MIDDLE, LEFT) == [None, None]


def test_combination_fires(clock):
    both = CTRL | Modifier.ALT
    d = _detector(clock, modifiers=both)
    d.on_state(both, False)
    assert _at(d, MIDDLE, LEFT) == [None, Edge.LEFT]


def test_unmapped_edge_never_fires(clock):
    d = _detector(clock, edges=(Edge.RIGHT,))
    d.on_state(CTRL, False)
    assert _at(d, MIDDLE, LEFT) == [None, None]


def test_corner_prefers_horizontal_edge(clock):
    d = _detector(clock, edges=(Edge.LEFT, Edge.TOP))
    d.on_state(CTRL, False)
    assert _at(d, MIDDLE, TOP_LEFT) == [None, Edge.LEFT]


def test_unknown_bounds_change_nothing(clock):
    d = _detector(clock)
    d.on_state(CTRL, False)
    _at(d, MIDDLE)
    assert d.on_pointer(0, 500, None) is None
    assert _at(d, LEFT) == [Edge.LEFT]


def test_repeated_state_keeps_arming(clock):
    d = _detector(clock)
    d.on_state(CTRL, False)
    _at(d, MIDDLE)
    d.on_state(CTRL, False)
    assert _at(d, LEFT) == [Edge.LEFT]


def test_latched_after_firing_until_modifier_released(clock):
    d = _detector(clock, cooldown_s=0)
    d.on_state(CTRL, False)
    assert _at(d, MIDDLE, LEFT) == [None, Edge.LEFT]
    assert not d.active
    assert _at(d, MIDDLE, RIGHT) == [None, None]

    d.on_state(NONE, False)
    d.on_state(CTRL, False)
    assert _at(d, MIDDLE, RIGHT) == [None, Edge.RIGHT]


def test_button_press_does_not_release_the_latch(clock):
    d = _detector(clock, cooldown_s=0)
    d.on_state(CTRL, False)
    _at(d, MIDDLE, LEFT)
    d.on_state(CTRL, True)
    d.on_state(CTRL, False)
    assert not d.active


def test_cooldown_suppresses_and_suppressed_touch_does_not_fire_on_expiry(clock):
    d = _detector(clock, cooldown_s=1.0)
    d.on_state(CTRL, False)
    assert _at(d, MIDDLE, LEFT) == [None, Edge.LEFT]
    d.on_state(NONE, False)
    d.on_state(CTRL, False)

    clock.now += 0.5
    assert _at(d, MIDDLE, RIGHT) == [None, None]

    clock.now += 1.0
    assert _at(d, RIGHT) == [None]
    assert _at(d, MIDDLE, RIGHT) == [None, Edge.RIGHT]


def test_feed_adapter(clock):
    d = _detector(clock)

    def sample(pos, modifiers=CTRL):
        return PointerSample(x=pos[0], y=pos[1], modifiers=modifiers, buttons_held=False, bounds=SCREEN)

    assert d.feed(None) is None
    assert [d.feed(sample(MIDDLE)), d.feed(sample(LEFT))] == [None, Edge.LEFT]
