from unittest.mock import MagicMock

from cleverswitch.edgeswitch.bounds_cache import BoundsCache
from cleverswitch.edgeswitch.geometry import Rect


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_reads_once_within_ttl_and_again_after():
    clock = FakeClock()
    read = MagicMock(side_effect=[Rect(0, 0, 1, 1), Rect(0, 0, 2, 2)])
    cache = BoundsCache(read, clock, ttl_s=1.0)

    assert cache.get() == Rect(0, 0, 1, 1)
    clock.now += 0.5
    assert cache.get() == Rect(0, 0, 1, 1)
    clock.now += 0.5
    assert cache.get() == Rect(0, 0, 2, 2)
    assert read.call_count == 2


def test_missing_bounds_are_retried_on_next_get():
    read = MagicMock(side_effect=[None, Rect(0, 0, 1, 1)])
    cache = BoundsCache(read, FakeClock())

    assert cache.get() is None
    assert cache.get() == Rect(0, 0, 1, 1)
