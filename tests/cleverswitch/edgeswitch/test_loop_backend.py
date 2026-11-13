import logging
import threading
from unittest.mock import MagicMock

import pytest

from cleverswitch.edgeswitch.loop_backend import LoopEdgeBackend
from cleverswitch.errors.errors import EdgeSwitchError
from cleverswitch.event.edge_touched_event import EdgeTouchedEvent
from cleverswitch.model.config.edge import Edge
from cleverswitch.topic.topic import Topic


class FakeLoop:
    """run() blocks until interrupted, or raises / returns on request."""

    def __init__(self, on_run=None):
        self._interrupted = threading.Event()
        self.on_run = on_run
        self.running = threading.Event()
        self.closed = threading.Event()
        self.events = []
        self.fail = None

    def run(self):
        self.events.append("run")
        self.running.set()
        if self.on_run is not None:
            self.on_run()
        self._interrupted.wait(5)
        if self.fail is not None:
            raise self.fail

    def interrupt(self):
        self.events.append("interrupt")
        self._interrupted.set()

    def close(self):
        self.events.append("close")
        self.closed.set()


def _topics():
    topics = MagicMock()
    topics.edge = MagicMock(spec=Topic)
    return topics


def _backend(factory, topics=None, start_timeout_s=2.0):
    return LoopEdgeBackend("edge-test", factory, topics or _topics(), start_timeout_s=start_timeout_s)


def test_runs_the_loop_and_stops_it():
    loop = FakeLoop()
    backend = _backend(lambda publish, stopping: loop)

    backend.start()
    assert loop.running.wait(2)
    backend.stop()

    assert loop.events == ["run", "interrupt", "close"]


def test_loop_publishes_edges_until_stopping():
    topics = _topics()
    captured = {}

    def factory(publish, stopping):
        captured["publish"], captured["stopping"] = publish, stopping
        return FakeLoop()

    backend = _backend(factory, topics)
    backend.start()
    assert captured["stopping"]() is False
    captured["publish"](Edge.LEFT)
    backend.stop()
    captured["publish"](Edge.RIGHT)

    assert captured["stopping"]() is True
    topics.edge.publish.assert_called_once_with(EdgeTouchedEvent(slot=0, pid=0, edge=Edge.LEFT))


def test_factory_error_fails_start():
    def factory(publish, stopping):
        raise OSError("no display")

    with pytest.raises(EdgeSwitchError, match="no display"):
        _backend(factory).start()


def test_timed_out_start_closes_the_loop_without_running_it():
    release = threading.Event()
    loop = FakeLoop()

    def factory(publish, stopping):
        release.wait(5)
        return loop

    backend = _backend(factory, start_timeout_s=0.01)
    with pytest.raises(EdgeSwitchError, match="did not start"):
        backend.start()
    release.set()

    assert loop.closed.wait(2)
    assert loop.events == ["close"]


def test_loop_that_ends_on_its_own_is_closed_and_logged(caplog):
    loop = FakeLoop(on_run=lambda: loop._interrupted.set())
    backend = _backend(lambda publish, stopping: loop)

    backend.start()
    assert loop.closed.wait(2)

    assert "lost its input source" in caplog.text


def test_loop_that_raises_is_closed_and_logged(caplog):
    loop = FakeLoop()
    loop.fail = OSError("X gone")
    loop.on_run = lambda: loop._interrupted.set()
    backend = _backend(lambda publish, stopping: loop)

    backend.start()
    assert loop.closed.wait(2)

    assert "X gone" in caplog.text


def test_failure_after_stop_is_not_logged(caplog):
    loop = FakeLoop()
    loop.fail = OSError("interrupted")
    backend = _backend(lambda publish, stopping: loop)
    backend.start()
    backend.stop()
    assert "interrupted" not in caplog.text


def test_close_failure_is_logged_not_raised(caplog):
    loop = FakeLoop()
    loop.close = MagicMock(side_effect=OSError("close"))
    backend = _backend(lambda publish, stopping: loop)
    backend.start()
    backend.stop()
    assert "Cannot release" in caplog.text


def test_stop_never_raises_when_interrupt_fails(caplog):
    loop = FakeLoop()
    original = loop.interrupt

    def interrupt():
        original()
        raise OSError("bad fd")

    loop.interrupt = interrupt
    backend = _backend(lambda publish, stopping: loop)
    backend.start()
    backend.stop()
    assert "Cannot interrupt" in caplog.text


def test_stop_is_idempotent_and_safe_before_start():
    backend = _backend(lambda publish, stopping: FakeLoop())
    backend.stop()
    backend.stop()
    with pytest.raises(EdgeSwitchError, match="stopped"):
        backend.start()


def test_start_while_running_is_a_no_op():
    loops = []
    backend = _backend(lambda publish, stopping: loops.append(FakeLoop()) or loops[-1])
    backend.start()
    backend.start()
    backend.stop()
    assert len(loops) == 1


def test_revive_restarts_a_loop_that_ended():
    loops = []

    def factory(publish, stopping):
        loop = FakeLoop(on_run=None if loops else (lambda: loops[0]._interrupted.set()))
        loops.append(loop)
        return loop

    backend = _backend(factory)
    backend.start()
    assert loops[0].closed.wait(2)
    backend._thread.join(2)

    backend.revive()
    assert loops[1].running.wait(2)
    backend.revive()
    backend.stop()

    assert len(loops) == 2


def test_revive_retries_a_start_that_failed_and_warns_once_per_reason(caplog):
    caplog.set_level(logging.DEBUG)
    attempts = []

    def factory(publish, stopping):
        attempts.append(1)
        if len(attempts) < 3:
            raise OSError("no permission")
        return FakeLoop()

    backend = _backend(factory)
    with pytest.raises(EdgeSwitchError):
        backend.start()
    backend.revive()
    backend.revive()
    backend.stop()

    assert len(attempts) == 3
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "still unavailable" in r.message]
    assert len(warnings) == 1


def test_revive_after_stop_does_nothing():
    factory = MagicMock()
    backend = _backend(factory)
    backend.stop()
    backend.revive()
    factory.assert_not_called()
