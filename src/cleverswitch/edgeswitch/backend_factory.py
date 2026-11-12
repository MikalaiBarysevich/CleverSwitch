from __future__ import annotations

import logging
import os

from ..errors.errors import EdgeSwitchError
from ..model.config.edge_switch_config import EdgeSwitchConfig
from ..topic.topics import Topics
from ..util.util import SYSTEM_LINUX, SYSTEM_MACOS, SYSTEM_WINDOWS, get_system
from .backend import EdgeBackend
from .edge_detector import EdgeDetector
from .fallback_backend import FallbackEdgeBackend
from .loop_backend import LoopEdgeBackend
from .polling_backend import PollingEdgeBackend
from .push_detector import PushDetector
from .session import LinuxSession, detect_linux_session

log = logging.getLogger(__name__)


def create_backend(cfg: EdgeSwitchConfig, topics: Topics) -> EdgeBackend | None:
    system = get_system()
    if system == SYSTEM_WINDOWS:
        from .windows.raw_input_loop import RawInputLoop
        from .windows.user32 import User32

        return LoopEdgeBackend("edge-windows", RawInputLoop.factory(User32, _edge_detector(cfg)), topics)
    if system == SYSTEM_MACOS:
        from .macos.quartz_sampler import QuartzSampler

        return PollingEdgeBackend(QuartzSampler, _edge_detector(cfg), topics, "edge-macos")
    if system == SYSTEM_LINUX:
        from .linux.evdev_backend import EvdevEdgeBackend

        def evdev() -> EdgeBackend:
            return EvdevEdgeBackend(_push_detector(cfg), topics)

        if detect_linux_session(os.environ) == LinuxSession.X11:
            from .linux.xcb_sampler import XcbSampler

            return FallbackEdgeBackend(PollingEdgeBackend(XcbSampler, _edge_detector(cfg), topics, "edge-x11"), evdev)
        return evdev()
    log.warning(f"Edge switch is not supported on {system} yet")
    return None


def _edge_detector(cfg: EdgeSwitchConfig) -> EdgeDetector:
    return EdgeDetector(frozenset(cfg.edges), cfg.modifiers, cfg.cooldown_ms / 1000)


def _push_detector(cfg: EdgeSwitchConfig) -> PushDetector:
    return PushDetector(frozenset(cfg.edges), cfg.modifiers, cfg.cooldown_ms / 1000, cfg.push_threshold)


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
