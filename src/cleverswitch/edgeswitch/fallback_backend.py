from __future__ import annotations

import logging
from collections.abc import Callable

from ..errors.errors import EdgeSwitchError
from .backend import EdgeBackend

log = logging.getLogger(__name__)


class FallbackEdgeBackend(EdgeBackend):
    """Starts the primary backend, or the fallback when the primary cannot start."""

    def __init__(self, primary: EdgeBackend, fallback_factory: Callable[[], EdgeBackend]):
        self._primary = primary
        self._fallback_factory = fallback_factory
        self._active: EdgeBackend | None = None

    def start(self) -> None:
        try:
            self._primary.start()
            self._active = self._primary
            return
        except EdgeSwitchError as e:
            log.info(f"Edge switch falls back to evdev: {e}")
        fallback = self._fallback_factory()
        fallback.start()
        self._active = fallback

    def stop(self) -> None:
        active, self._active = self._active, None
        if active is not None:
            active.stop()
