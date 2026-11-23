from __future__ import annotations

import dataclasses
import logging
import threading
from collections.abc import Callable
from typing import Protocol

from ..errors.errors import EdgeSwitchError
from ..event.edge_touched_event import EdgeTouchedEvent
from ..model.config.edge import Edge
from ..topic.topics import Topics
from .backend import EdgeBackend

log = logging.getLogger(__name__)

START_TIMEOUT_S = 5.0
JOIN_TIMEOUT_S = 2.0


class InputLoop(Protocol):
    # Dispatches OS input events until interrupted; raises when the input source is lost.
    def run(self) -> None: ...

    # Any thread, idempotent, sticky: called before run(), run() returns at once.
    def interrupt(self) -> None: ...

    # Backend thread only; releases every OS resource the loop owns.
    def close(self) -> None: ...


# Called on the backend thread with (publish, stopping); must close what it opened before raising.
LoopFactory = Callable[[Callable[[Edge], None], Callable[[], bool]], InputLoop]


@dataclasses.dataclass
class _Attempt:
    ready: threading.Event = dataclasses.field(default_factory=threading.Event)
    stopping: threading.Event = dataclasses.field(default_factory=threading.Event)
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    loop: InputLoop | None = None
    error: Exception | None = None
    cancelled: bool = False


class LoopEdgeBackend(EdgeBackend):
    """Runs an event-driven InputLoop on its own thread.

    The loop is built on that thread, so the OS connection it holds belongs to the thread alone. interrupt()
    is only called while the loop is registered, and close() only runs after it was unregistered under the
    same lock, so a stop can never touch a closed fd. A start that times out marks its attempt stopping and
    forgets it, so a later revive starts a fresh attempt instead of being turned away by is_alive(); if the
    abandoned factory returns later, its thread closes the loop instead of running it.
    """

    def __init__(
        self,
        name: str,
        loop_factory: LoopFactory,
        topics: Topics,
        start_timeout_s: float = START_TIMEOUT_S,
        join_timeout_s: float = JOIN_TIMEOUT_S,
    ):
        self._name = name
        self._loop_factory = loop_factory
        self._topics = topics
        self._start_timeout_s = start_timeout_s
        self._join_timeout_s = join_timeout_s
        self._lock = threading.Lock()
        self._attempt: _Attempt | None = None
        self._thread: threading.Thread | None = None
        self._closed = False
        self._last_revive_error: str | None = None

    def start(self) -> None:
        with self._lock:
            if self._closed:
                raise EdgeSwitchError(f"{self._name} is stopped")
            if self._thread is not None and self._thread.is_alive():
                return
            attempt = _Attempt()
            thread = threading.Thread(target=self._run, args=(attempt,), name=self._name, daemon=True)
            self._attempt, self._thread = attempt, thread
        thread.start()
        if not attempt.ready.wait(self._start_timeout_s):
            self._abandon(attempt)
            raise EdgeSwitchError(f"{self._name} did not start in time")
        if attempt.cancelled:
            raise EdgeSwitchError(f"{self._name} is stopped")
        if attempt.error is not None:
            thread.join(self._join_timeout_s)
            raise EdgeSwitchError(f"{self._name} cannot start: {attempt.error}") from attempt.error
        log.info(f"Watching screen edges ({self._name})")

    def stop(self) -> None:
        with self._lock:
            self._closed = True
            attempt, thread = self._attempt, self._thread
        if attempt is None:
            return
        self._end(attempt)
        # start() publishes the thread before Thread.start(); a stop in that window has nothing to join.
        if thread.ident is not None:
            thread.join(self._join_timeout_s)

    def revive(self) -> None:
        with self._lock:
            if self._closed:
                return
            attempt, thread = self._attempt, self._thread
        if thread is not None and thread.is_alive():
            if attempt is None or _still_healthy(attempt):
                return
            # The loop is alive but its source is gone (a compositor restarted while nothing moved).
            # Restart instead of waiting for the next device connection to notice.
            log.info(f"Edge switch restarts: {self._name} lost its input source")
            self._end(attempt)
            thread.join(self._join_timeout_s)
        try:
            self.start()
            self._last_revive_error = None
        except EdgeSwitchError as e:
            if self._closed:
                return
            message = str(e)
            if message != self._last_revive_error:
                log.warning(f"Edge switch still unavailable: {message}")
            else:
                log.debug(f"Edge switch still unavailable: {message}")
            self._last_revive_error = message

    def _run(self, attempt: _Attempt) -> None:
        try:
            loop = self._loop_factory(self._publish_from(attempt), attempt.stopping.is_set)
        except Exception as e:
            attempt.error = e
            attempt.ready.set()
            return
        with attempt.lock:
            abandoned = attempt.stopping.is_set()
            if not abandoned:
                attempt.loop = loop
        if abandoned:
            _close_quietly(loop)
            return
        attempt.ready.set()
        try:
            loop.run()
            if not attempt.stopping.is_set():
                log.warning(
                    f"Edge switch stopped: {self._name} lost its input source; retrying on the next device connection"
                )
        except Exception as e:
            if not attempt.stopping.is_set():
                log.warning(f"Edge switch stopped: {e!r}; retrying on the next device connection")
        finally:
            with attempt.lock:
                attempt.loop = None
            _close_quietly(loop)

    def _end(self, attempt: _Attempt) -> None:
        attempt.stopping.set()
        attempt.cancelled = True
        # A start() still waiting on ready must wake up and see cancelled instead of burning the whole timeout.
        attempt.ready.set()
        with attempt.lock:
            if attempt.loop is None:
                return
            try:
                attempt.loop.interrupt()
            except Exception:
                log.exception(f"Cannot interrupt {self._name}")

    # A timed-out start leaves its factory thread running. Forget the attempt, so a later revive starts a fresh
    # one instead of being turned away by is_alive(); the abandoned thread closes its loop when the factory
    # returns and, because stopping is already set, can never run or publish it.
    def _abandon(self, attempt: _Attempt) -> None:
        self._end(attempt)
        with self._lock:
            if self._attempt is attempt:
                self._attempt = self._thread = None

    def _publish_from(self, attempt: _Attempt) -> Callable[[Edge], None]:
        def publish(edge: Edge) -> None:
            if not attempt.stopping.is_set():
                self._topics.edge.publish(EdgeTouchedEvent(slot=0, pid=0, edge=edge))

        return publish


# An InputLoop may expose health_check(); without one its run() is trusted to notice a lost source.
def _still_healthy(attempt: _Attempt) -> bool:
    with attempt.lock:
        loop = attempt.loop
    check = getattr(loop, "health_check", None)
    return True if check is None else bool(check())


def _close_quietly(loop: InputLoop) -> None:
    try:
        loop.close()
    except Exception:
        log.exception("Cannot release the edge-switch input source")
