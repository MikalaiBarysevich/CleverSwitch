import threading
from unittest.mock import MagicMock

import pytest

from cleverswitch.edgeswitch import polling_backend
from cleverswitch.edgeswitch.polling_backend import MAX_CONSECUTIVE_FAILURES, PollingEdgeBackend
from cleverswitch.errors.errors import EdgeSwitchError
from cleverswitch.event.edge_touched_event import EdgeTouchedEvent
from cleverswitch.model.config.edge import Edge
from cleverswitch.topic.topic import Topic


class ScriptedSampler:
    """Returns scripted results, then signals `done` and returns None forever."""

    def __init__(self, results):
        self._results = list(results)
        self.done = threading.Event()
        self.closed = threading.Event()

    def sample(self):
        if not self._results:
            self.done.set()
            return None
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def close(self):
        self.closed.set()


def _topics():
    topics = MagicMock()
    topics.edge = MagicMock(spec=Topic)
    return topics


def _backend(sampler, detector, topics):
    return PollingEdgeBackend(lambda: sampler, detector, topics, "edge-test", interval_s=0.001)


def test_publishes_detected_edges_and_closes_sampler_on_stop():
    sampler = ScriptedSampler(["s1", "s2"])
    detector = MagicMock()
    detector.feed.side_effect = lambda s: Edge.LEFT if s == "s2" else None
    topics = _topics()
    backend = _backend(sampler, detector, topics)

    backend.start()
    assert sampler.done.wait(2)
    backend.stop()

    topics.edge.publish.assert_called_once_with(EdgeTouchedEvent(slot=0, pid=0, edge=Edge.LEFT))
    assert sampler.closed.is_set()


def test_sampler_that_cannot_be_built_fails_start():
    def factory():
        raise OSError("no display")

    backend = PollingEdgeBackend(factory, MagicMock(), _topics(), "edge-test")
    with pytest.raises(EdgeSwitchError, match="no display"):
        backend.start()


def test_start_timeout(mocker):
    mocker.patch.object(polling_backend, "_START_TIMEOUT", 0.01)
    release = threading.Event()

    def factory():
        release.wait(2)
        return ScriptedSampler([])

    backend = PollingEdgeBackend(factory, MagicMock(), _topics(), "edge-test")
    with pytest.raises(EdgeSwitchError, match="did not start"):
        backend.start()
    release.set()


def test_a_failed_read_is_skipped(caplog):
    sampler = ScriptedSampler([OSError("blip"), "s"])
    detector = MagicMock()
    detector.feed.return_value = None
    backend = _backend(sampler, detector, _topics())

    backend.start()
    assert sampler.done.wait(2)
    backend.stop()

    assert "blip" in caplog.text
    assert "s" in [c.args[0] for c in detector.feed.call_args_list]


def test_too_many_failed_reads_stop_the_thread(caplog):
    sampler = ScriptedSampler([OSError("gone")] * MAX_CONSECUTIVE_FAILURES)
    backend = _backend(sampler, MagicMock(), _topics())

    backend.start()
    assert sampler.closed.wait(2)
    backend.stop()

    assert "stopped after" in caplog.text
    assert caplog.text.count("gone") == 1


def test_stop_without_start_is_a_no_op():
    PollingEdgeBackend(MagicMock(), MagicMock(), _topics(), "edge-test").stop()
