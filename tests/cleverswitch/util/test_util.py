"""Unit tests for util/util.py."""

from __future__ import annotations

import pytest

from src.cleverswitch.util.util import decode_string_response


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"MX Keys", "MX Keys"),  # clean name, no NUL
        (b"MX Keys\x00\x00\x00", "MX Keys"),  # trailing NUL padding
        (b"MX Keys\x00eyboard", "MX Keys"),  # reflash leftover after first NUL
        (b"MX\x00Keys", "MX"),  # embedded NUL truncates
        (b"  MX Keys  ", "MX Keys"),  # surrounding whitespace stripped
        (b"MX Keys \x00", "MX Keys"),  # whitespace before NUL padding stripped
        (b"   ", None),  # whitespace-only → nothing printable
        (b"\x00\x00\x00", None),  # all NUL → nothing printable
        (b"", None),  # empty buffer
        (b"K\xff850", "K�850"),  # invalid UTF-8 byte replaced, not dropped
    ],
)
def test_decode_string_response(raw, expected):
    assert decode_string_response(raw) == expected
