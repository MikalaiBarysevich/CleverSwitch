from cleverswitch.edgeswitch.geometry import Rect
from cleverswitch.edgeswitch.macos.quartz_sampler import QuartzSampler
from cleverswitch.model.config.modifier import Modifier


class FakeQuartz:
    def __init__(self, pos=(10.5, 20.25), flags=0, buttons=(), displays=((0, 0, 1512, 982), (-1920, -98, 1920, 1080))):
        self.pos = pos
        self._flags = flags
        self.buttons = set(buttons)
        self.displays = list(displays)

    def cursor_pos(self):
        return self.pos

    def flags(self):
        return self._flags

    def button_down(self, button):
        return button in self.buttons

    def display_bounds(self):
        return self.displays


def _sampler(fake):
    return QuartzSampler(quartz_factory=lambda: fake, clock=lambda: 0.0)


def test_sample_reports_position_and_union_of_displays():
    sample = _sampler(FakeQuartz()).sample()
    assert (sample.x, sample.y) == (10.5, 20.25)
    assert sample.bounds == Rect(-1920, -98, 1512, 982)
    assert sample.modifiers == Modifier.NONE
    assert not sample.buttons_held


def test_modifier_flags_are_mapped():
    sample = _sampler(FakeQuartz(flags=0x00040000 | 0x00100000 | 0x100)).sample()
    assert sample.modifiers == Modifier.CTRL | Modifier.META


def test_shift_and_option():
    sample = _sampler(FakeQuartz(flags=0x00020000 | 0x00080000)).sample()
    assert sample.modifiers == Modifier.SHIFT | Modifier.ALT


def test_any_mouse_button_counts_as_held():
    assert _sampler(FakeQuartz(buttons={3})).sample().buttons_held


def test_no_window_server_gives_no_sample():
    assert _sampler(FakeQuartz(pos=None)).sample() is None


def test_no_displays_gives_no_sample():
    assert _sampler(FakeQuartz(displays=[])).sample() is None


def test_zero_sized_display_is_ignored():
    sample = _sampler(FakeQuartz(displays=[(0, 0, 0, 0), (0, 0, 800, 600)])).sample()
    assert sample.bounds == Rect(0, 0, 800, 600)


def test_close_is_harmless():
    _sampler(FakeQuartz()).close()
