from __future__ import annotations

import logging
import os

from ..errors.errors import EdgeSwitchError
from ..model.config.edge_switch_config import EdgeSwitchConfig
from ..topic.topics import Topics
from ..util.util import SYSTEM_LINUX, SYSTEM_MACOS, SYSTEM_WINDOWS, get_system
from .backend import EdgeBackend
from .edge_detector import EdgeDetector
from .polling_backend import PollingEdgeBackend
from .session import LinuxSession, detect_linux_session

log = logging.getLogger(__name__)


def create_backend(cfg: EdgeSwitchConfig, topics: Topics) -> EdgeBackend | None:
    system = get_system()
    if system == SYSTEM_WINDOWS:
        from .windows.user32_sampler import User32Sampler

        return PollingEdgeBackend(User32Sampler, _edge_detector(cfg), topics, "edge-windows")
    if system == SYSTEM_MACOS:
        from .macos.quartz_sampler import QuartzSampler

        return PollingEdgeBackend(QuartzSampler, _edge_detector(cfg), topics, "edge-macos")
    if system == SYSTEM_LINUX:
        session = detect_linux_session(os.environ)
        if session == LinuxSession.X11:
            from .linux.xcb_sampler import XcbSampler

            return PollingEdgeBackend(XcbSampler, _edge_detector(cfg), topics, "edge-x11")
        log.warning(f"Edge switch is not supported on a {session} Linux session yet")
        return None
    log.warning(f"Edge switch is not supported on {system} yet")
    return None


def _edge_detector(cfg: EdgeSwitchConfig) -> EdgeDetector:
    return EdgeDetector(frozenset(cfg.edges), cfg.modifiers, cfg.cooldown_ms / 1000)


def start_edge_switch(cfg: EdgeSwitchConfig, topics: Topics) -> EdgeBackend | None:
    if not cfg.enabled:
        return None
    try:
        backend = create_backend(cfg, topics)
        if backend is None:
            return None
        backend.start()
    except EdgeSwitchError as e:
        log.warning(f"Edge switch disabled: {e}")
        return None
    except Exception as e:
        log.warning(f"Edge switch disabled after an unexpected error: {e!r}")
        return None
    log.info("Edge switch started")
    return backend
