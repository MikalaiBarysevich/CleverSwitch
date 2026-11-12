from cleverswitch.edgeswitch.geometry import Rect
from cleverswitch.edgeswitch.windows.user32_sampler import User32Sampler
from cleverswitch.model.config.modifier import Modifier


class FakeUser32:
    def __init__(self, pos=(10, 20), keys=(), screen=(-1280, 0, 3200, 1080)):
        self.pos = pos
        self.keys = set(keys)
        self.screen = screen
        self.dpi_set = False

    def use_per_monitor_dpi(self):
        self.dpi_set = True

    def cursor_pos(self):
        return self.pos

    def key_down(self, vk):
        return vk in self.keys

    def virtual_screen(self):
        return self.screen


def _sampler(fake):
    return User32Sampler(user32_factory=lambda: fake, clock=lambda: 0.0)


def test_sets_dpi_awareness_on_creation():
    fake = FakeUser32()
    _sampler(fake)
    assert fake.dpi_set


def test_sample_reports_position_and_virtual_screen_bounds():
    sample = _sampler(FakeUser32()).sample()
    assert (sample.x, sample.y) == (10, 20)
    assert sample.bounds == Rect(-1280, 0, 1920, 1080)
    assert sample.modifiers == Modifier.NONE
    assert not sample.buttons_held


def test_modifiers_are_merged():
    sample = _sampler(FakeUser32(keys={0x11, 0x12, 0x5C})).sample()
    assert sample.modifiers == Modifier.CTRL | Modifier.ALT | Modifier.META


def test_shift_and_left_win():
    sample = _sampler(FakeUser32(keys={0x10, 0x5B})).sample()
    assert sample.modifiers == Modifier.SHIFT | Modifier.META


def test_any_mouse_button_counts_as_held():
    assert _sampler(FakeUser32(keys={0x06})).sample().buttons_held


def test_secure_desktop_gives_no_sample():
    assert _sampler(FakeUser32(pos=None)).sample() is None


def test_empty_virtual_screen_gives_no_sample():
    assert _sampler(FakeUser32(screen=(0, 0, 0, 0))).sample() is None


def test_close_is_harmless():
    _sampler(FakeUser32()).close()
