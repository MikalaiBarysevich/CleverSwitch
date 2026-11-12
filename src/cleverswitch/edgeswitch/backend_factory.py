from __future__ import annotations

import logging

from ..errors.errors import EdgeSwitchError
from ..model.config.edge_switch_config import EdgeSwitchConfig
from ..topic.topics import Topics
from ..util.util import get_system
from .backend import EdgeBackend

log = logging.getLogger(__name__)


def create_backend(cfg: EdgeSwitchConfig, topics: Topics) -> EdgeBackend | None:
    log.warning(f"Edge switch is not supported on {get_system()} yet")
    return None


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
