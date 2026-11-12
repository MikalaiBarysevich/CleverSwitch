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
        self._fallback: EdgeBackend | None = None
        self._active: EdgeBackend | None = None
        self._closed = False

    def start(self) -> None:
        try:
            self._primary.start()
            self._active = self._primary
            return
        except EdgeSwitchError as e:
            log.info(f"Edge switch falls back to evdev: {e}")
        if self._fallback is None:
            self._fallback = self._fallback_factory()
        self._fallback.start()
        self._active = self._fallback

    def stop(self) -> None:
        self._closed = True
        self._primary.stop()
        if self._fallback is not None:
            self._fallback.stop()

    def revive(self) -> None:
        if self._closed:
            return
        if self._active is not None:
            self._active.revive()
            return
        try:
            self.start()
        except EdgeSwitchError as e:
            log.debug(f"Edge switch still unavailable: {e}")
