import pytest

from cleverswitch.edgeswitch.geometry import Rect
from cleverswitch.edgeswitch.linux.xcb_sampler import XcbSampler, modifier_keycodes, modifiers_from_keymap
from cleverswitch.model.config.modifier import Modifier

# Two keysyms per keycode, starting at keycode 8.
KEYSYMS = [
    0x61,
    0x41,  # 8: a A
    0xFFE3,
    0,  # 9: Control_L
    0xFFE9,
    0xFFE7,  # 10: Alt_L Meta_L
    0xFFEB,
    0,  # 11: Super_L
    0xFFE2,
    0,  # 12: Shift_R
    0xFE03,
    0,  # 13: ISO_Level3_Shift
]


def _keymap(*keycodes):
    keys = bytearray(32)
    for keycode in keycodes:
        keys[keycode // 8] |= 1 << (keycode % 8)
    return bytes(keys)


class FakeXcb:
    def __init__(self, pointer=(5, 6, 0), keymap=None, geometry=(0, 0, 3840, 1080), mapping=(2, 8, KEYSYMS)):
        self.pointer = pointer
        self.keymap = keymap if keymap is not None else _keymap()
        self.geometry = geometry
        self.mapping = mapping
        self.error = False
        self.closed = False

    def has_error(self):
        return self.error

    def query_pointer(self):
        return self.pointer

    def query_keymap(self):
        return self.keymap

    def root_geometry(self):
        return self.geometry

    def keyboard_mapping(self):
        return self.mapping

    def close(self):
        self.closed = True


def _sampler(fake):
    return XcbSampler(xcb_factory=lambda: fake, clock=lambda: 0.0)


def test_modifier_keycodes_resolves_every_column():
    assert modifier_keycodes(2, 8, KEYSYMS) == {
        9: Modifier.CTRL,
        10: Modifier.ALT | Modifier.META,
        11: Modifier.META,
        12: Modifier.SHIFT,
        13: Modifier.ALT,
    }


def test_modifier_keycodes_with_no_columns_is_empty():
    assert modifier_keycodes(0, 8, KEYSYMS) == {}


def test_modifiers_from_keymap():
    keycodes = {9: Modifier.CTRL, 11: Modifier.META, 37: Modifier.CTRL}
    assert modifiers_from_keymap(_keymap(37, 11), keycodes) == Modifier.CTRL | Modifier.META
    assert modifiers_from_keymap(_keymap(8), keycodes) == Modifier.NONE


def test_sample_reports_pointer_and_root_bounds():
    sample = _sampler(FakeXcb(keymap=_keymap(9, 12))).sample()
    assert (sample.x, sample.y) == (5, 6)
    assert sample.bounds == Rect(0, 0, 3840, 1080)
    assert sample.modifiers == Modifier.CTRL | Modifier.SHIFT
    assert not sample.buttons_held


@pytest.mark.parametrize(("mask", "held"), [(1 << 8, True), (1 << 10, True), (1 << 11, False), (1 << 2, False)])
def test_buttons_one_to_three_count_as_held(mask, held):
    assert _sampler(FakeXcb(pointer=(0, 0, mask))).sample().buttons_held is held


@pytest.mark.parametrize(
    "fake",
    [FakeXcb(pointer=None), FakeXcb(geometry=None), FakeXcb(geometry=(0, 0, 0, 0))],
)
def test_missing_reply_gives_no_sample(fake):
    assert _sampler(fake).sample() is None


def test_missing_keymap_gives_no_sample():
    fake = FakeXcb()
    fake.keymap = None
    assert _sampler(fake).sample() is None


def test_no_keyboard_mapping_means_no_modifiers():
    sample = _sampler(FakeXcb(mapping=None, keymap=_keymap(9))).sample()
    assert sample.modifiers == Modifier.NONE


def test_lost_connection_raises():
    fake = FakeXcb()
    sampler = _sampler(fake)
    fake.error = True
    with pytest.raises(OSError, match="lost"):
        sampler.sample()


def test_close_disconnects():
    fake = FakeXcb()
    _sampler(fake).close()
    assert fake.closed
