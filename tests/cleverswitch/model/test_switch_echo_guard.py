from cleverswitch.model.switch_echo_guard import SwitchEchoGuard


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_nothing_recorded_is_not_an_echo():
    assert not SwitchEchoGuard(clock=FakeClock()).is_echo(1)


def test_same_target_inside_window_is_an_echo():
    clock = FakeClock()
    guard = SwitchEchoGuard(clock=clock, window_s=2.0)
    guard.record(1)
    clock.now += 2.0
    assert guard.is_echo(1)


def test_other_target_is_not_an_echo():
    guard = SwitchEchoGuard(clock=FakeClock())
    guard.record(1)
    assert not guard.is_echo(2)


def test_same_target_after_window_is_not_an_echo():
    clock = FakeClock()
    guard = SwitchEchoGuard(clock=clock, window_s=2.0)
    guard.record(1)
    clock.now += 2.1
    assert not guard.is_echo(1)
