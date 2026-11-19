import pytest

from cleverswitch.edgeswitch.geometry import Rect, edges_at, union
from cleverswitch.model.config.edge import Edge

SCREEN = Rect(0, 0, 1920, 1080)


def test_union_of_nothing_is_none():
    assert union([]) is None


def test_union_spans_monitors_with_negative_origin():
    assert union([Rect(0, 0, 1920, 1080), Rect(-1280, -200, 0, 824)]) == Rect(-1280, -200, 1920, 1080)


@pytest.mark.parametrize(
    ("x", "y", "expected"),
    [
        (0, 500, {Edge.LEFT}),
        (1919, 500, {Edge.RIGHT}),
        (900, 0, {Edge.TOP}),
        (900, 1079, {Edge.BOTTOM}),
        (0, 0, {Edge.LEFT, Edge.TOP}),
        (1919, 1079, {Edge.RIGHT, Edge.BOTTOM}),
        (900, 500, set()),
    ],
)
def test_edges_at(x, y, expected):
    assert edges_at(x, y, SCREEN) == frozenset(expected)


def test_edges_at_absorbs_one_pixel_of_rounding():
    assert edges_at(1.0, 500, SCREEN) == {Edge.LEFT}
    assert edges_at(1918.0, 500, SCREEN) == {Edge.RIGHT}
    assert edges_at(2.0, 500, SCREEN) == frozenset()


def test_inner_border_between_monitors_is_not_an_edge():
    desktop = union([Rect(0, 0, 1920, 1080), Rect(1920, 0, 3840, 1080)])
    assert edges_at(1919, 500, desktop) == frozenset()
    assert edges_at(1920, 500, desktop) == frozenset()
    assert edges_at(3839, 500, desktop) == {Edge.RIGHT}
