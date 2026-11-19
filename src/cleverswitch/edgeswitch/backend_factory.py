from __future__ import annotations

import logging
from collections.abc import Callable

from ..errors.errors import EdgeSwitchError
from ..model.config.edge_switch_config import EdgeSwitchConfig
from ..topic.topics import Topics
from ..util.util import SYSTEM_LINUX, SYSTEM_MACOS, SYSTEM_WINDOWS, get_system
from .backend import EdgeBackend
from .edge_detector import EdgeDetector
from .loop_backend import LoopEdgeBackend

log = logging.getLogger(__name__)


def create_backend(cfg: EdgeSwitchConfig, topics: Topics) -> EdgeBackend | None:
    system = get_system()
    if system == SYSTEM_WINDOWS:
        from .windows.raw_input_loop import RawInputLoop
        from .windows.user32 import User32

        return LoopEdgeBackend("edge-windows", RawInputLoop.factory(User32, _detector_factory(cfg)), topics)
    if system == SYSTEM_MACOS:
        from .macos.event_tap_loop import EventTapLoop
        from .macos.quartz import Quartz

        return LoopEdgeBackend("edge-macos", EventTapLoop.factory(Quartz, _detector_factory(cfg)), topics)
    if system == SYSTEM_LINUX:
        from .linux.desktop import linux_loop_factory

        return LoopEdgeBackend("edge-linux", linux_loop_factory(_detector_factory(cfg)), topics)
    log.warning(f"Edge switch is not supported on {system} yet")
    return None


def _edge_detector(cfg: EdgeSwitchConfig) -> EdgeDetector:
    return EdgeDetector(frozenset(cfg.edges), cfg.modifiers, cfg.cooldown_ms / 1000)


# A revived backend builds a new loop, and must also start from a clean detector: the old one may still be
# latched or armed from a hold that ended when its loop died.
def _detector_factory(cfg: EdgeSwitchConfig) -> Callable[[], EdgeDetector]:
    return lambda: _edge_detector(cfg)


# A backend that cannot start yet is still returned, so it can be revived when a device connects.
def start_edge_switch(cfg: EdgeSwitchConfig, topics: Topics) -> EdgeBackend | None:
    if not cfg.enabled:
        return None
    try:
        backend = create_backend(cfg, topics)
    except Exception as e:
        log.warning(f"Edge switch disabled after an unexpected error: {e!r}")
        return None
    if backend is None:
        return None
    try:
        backend.start()
    except EdgeSwitchError as e:
        log.warning(f"Edge switch is not running: {e}; it retries when a device connects")
        return backend
    except Exception as e:
        log.warning(f"Edge switch disabled after an unexpected error: {e!r}")
        backend.stop()
        return None
    log.info("Edge switch started")
    return backend
