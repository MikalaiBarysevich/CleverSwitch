import logging
from unittest.mock import MagicMock

import pytest

from cleverswitch.edgeswitch.fallback_backend import FallbackEdgeBackend
from cleverswitch.errors.errors import EdgeSwitchError


def test_primary_starts_and_stops():
    primary, factory = MagicMock(), MagicMock()
    backend = FallbackEdgeBackend(primary, factory)

    backend.start()
    backend.stop()

    primary.start.assert_called_once()
    primary.stop.assert_called_once()
    factory.assert_not_called()


def test_falls_back_when_primary_cannot_start(caplog):
    caplog.set_level(logging.INFO)
    primary = MagicMock()
    primary.start.side_effect = EdgeSwitchError("no X server")
    fallback = MagicMock()
    backend = FallbackEdgeBackend(primary, lambda: fallback)

    backend.start()
    backend.stop()

    fallback.start.assert_called_once()
    fallback.stop.assert_called_once()
    primary.stop.assert_not_called()
    assert "no X server" in caplog.text


def test_fallback_failure_propagates():
    primary = MagicMock()
    primary.start.side_effect = EdgeSwitchError("no X server")
    fallback = MagicMock()
    fallback.start.side_effect = EdgeSwitchError("no permission")

    with pytest.raises(EdgeSwitchError, match="no permission"):
        FallbackEdgeBackend(primary, lambda: fallback).start()


def test_stop_before_start_is_a_no_op():
    FallbackEdgeBackend(MagicMock(), MagicMock()).stop()
