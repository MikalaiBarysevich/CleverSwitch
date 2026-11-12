import logging
from unittest.mock import MagicMock

import pytest

from cleverswitch.edgeswitch.fallback_backend import FallbackEdgeBackend
from cleverswitch.errors.errors import EdgeSwitchError


def _failing(message):
    backend = MagicMock()
    backend.start.side_effect = EdgeSwitchError(message)
    return backend


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
    primary = _failing("no X server")
    fallback = MagicMock()
    backend = FallbackEdgeBackend(primary, lambda: fallback)

    backend.start()
    backend.stop()

    fallback.start.assert_called_once()
    fallback.stop.assert_called_once()
    primary.stop.assert_called_once()
    assert "no X server" in caplog.text


def test_fallback_failure_propagates():
    with pytest.raises(EdgeSwitchError, match="no permission"):
        FallbackEdgeBackend(_failing("no X server"), lambda: _failing("no permission")).start()


def test_stop_before_start_stops_the_primary_only():
    primary, factory = MagicMock(), MagicMock()
    FallbackEdgeBackend(primary, factory).stop()
    primary.stop.assert_called_once()
    factory.assert_not_called()


def test_revive_delegates_to_the_active_backend():
    primary = MagicMock()
    backend = FallbackEdgeBackend(primary, MagicMock())
    backend.start()
    backend.revive()
    primary.revive.assert_called_once()


def test_revive_retries_a_start_that_failed():
    primary = _failing("no X server")
    fallback = _failing("no permission")
    backend = FallbackEdgeBackend(primary, lambda: fallback)
    with pytest.raises(EdgeSwitchError):
        backend.start()

    fallback.start.side_effect = None
    backend.revive()

    assert fallback.start.call_count == 2
    backend.revive()
    fallback.revive.assert_called_once()


def test_revive_that_still_fails_is_quiet():
    backend = FallbackEdgeBackend(_failing("no X server"), lambda: _failing("no permission"))
    backend.revive()


def test_revive_after_stop_does_nothing():
    primary = MagicMock()
    backend = FallbackEdgeBackend(primary, MagicMock())
    backend.stop()
    backend.revive()
    primary.start.assert_not_called()
