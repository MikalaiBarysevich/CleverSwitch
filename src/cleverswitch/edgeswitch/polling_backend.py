from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from ..errors.errors import EdgeSwitchError
from ..event.edge_touched_event import EdgeTouchedEvent
from ..topic.topics import Topics
from .backend import EdgeBackend
from .edge_detector import EdgeDetector
from .sample import PointerSampler

log = logging.getLogger(__name__)

POLL_INTERVAL_S = 0.025
MAX_CONSECUTIVE_FAILURES = 50
_START_TIMEOUT = 5.0
_STOP_JOIN_TIMEOUT = 2.0


class PollingEdgeBackend(EdgeBackend):
    """Samples the cursor and modifier state every POLL_INTERVAL_S and feeds an EdgeDetector.

    Polling rather than an input hook: a slow Python callback gets a Windows low-level hook silently
    removed and a macOS event tap disabled, and both lag the cursor. The sampler is built on the
    polling thread, so whatever OS connection it holds belongs to that thread alone.
    """

    def __init__(
        self,
        sampler_factory: Callable[[], PointerSampler],
        detector: EdgeDetector,
        topics: Topics,
        name: str,
        interval_s: float = POLL_INTERVAL_S,
    ):
        self._sampler_factory = sampler_factory
        self._detector = detector
        self._topics = topics
        self._name = name
        self._interval_s = interval_s
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopping = threading.Event()
        self._error: Exception | None = None

    def start(self) -> None:
        thread = threading.Thread(target=self._run, name=self._name, daemon=True)
        self._thread = thread
        thread.start()
        if not self._ready.wait(_START_TIMEOUT):
            raise EdgeSwitchError(f"{self._name} did not start in time")
        if self._error is not None:
            self._thread = None
            raise EdgeSwitchError(f"cannot read the cursor: {self._error}") from self._error
        log.info(f"Watching screen edges ({self._name})")

    def stop(self) -> None:
        thread, self._thread = self._thread, None
        if thread is None:
            return
        self._stopping.set()
        thread.join(timeout=_STOP_JOIN_TIMEOUT)

    def revive(self) -> None:
        pass

    def _run(self) -> None:
        try:
            sampler = self._sampler_factory()
        except Exception as e:
            self._error = e
            self._ready.set()
            return
        self._ready.set()
        try:
            self._poll(sampler)
        finally:
            sampler.close()

    def _poll(self, sampler: PointerSampler) -> None:
        failures = 0
        while not self._stopping.wait(self._interval_s):
            try:
                sample = sampler.sample()
            except Exception as e:
                failures += 1
                if failures == 1:
                    log.warning(f"Cannot read the cursor: {e!r}")
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    log.warning(f"Edge switch stopped after {failures} failed cursor reads in a row")
                    return
                continue
            failures = 0
            edge = self._detector.feed(sample)
            if edge is not None:
                self._topics.edge.publish(EdgeTouchedEvent(slot=0, pid=0, edge=edge))
