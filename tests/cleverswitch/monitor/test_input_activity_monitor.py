"""Tests for InputActivityMonitor — per-role activity timestamps from input collections.

All HID I/O is faked: enumeration returns scripted InputCollectionInfo entries and the
transport factory hands out FakeInputTransport objects fed from a queue.
"""

import queue
import threading
import time

import pytest

from cleverswitch.errors.errors import TransportError
from cleverswitch.hidpp.transport import InputCollectionInfo
from cleverswitch.monitor.input_activity_monitor import InputActivityMonitor

PID = 0xC548
KEYBOARD_PATH = b"/dev/hidraw1"
MOUSE_PATH = b"/dev/hidraw2"


class FakeInputTransport:
    """Blocks like HIDTransport.read: returns queued payloads, None on timeout."""

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self.closed = threading.Event()

    def feed(self, data: bytes) -> None:
        self._queue.put(data)

    def fail(self) -> None:
        self._queue.put(TransportError("gone"))

    def read(self, timeout: int = -1):
        try:
            item = self._queue.get(timeout=timeout / 1000)
        except queue.Empty:
            return None
        if isinstance(item, TransportError):
            raise item
        return item

    def close(self) -> None:
        self.closed.set()


@pytest.fixture
def shutdown() -> threading.Event:
    return threading.Event()


def _wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition never became true")


def _make_monitor(shutdown, collections, transports):
    def factory(path: bytes):
        transport = transports.get(path)
        if transport is None:
            raise OSError("open denied")
        return transport

    return InputActivityMonitor(shutdown, enumerate_fn=lambda: list(collections), transport_factory=factory)


class TestInputActivityMonitor:
    def test_reports_refresh_last_activity_for_the_right_role(self, shutdown):
        keyboard = FakeInputTransport()
        mouse = FakeInputTransport()
        collections = [
            InputCollectionInfo(KEYBOARD_PATH, PID, "keyboard"),
            InputCollectionInfo(MOUSE_PATH, PID, "mouse"),
        ]
        monitor = _make_monitor(shutdown, collections, {KEYBOARD_PATH: keyboard, MOUSE_PATH: mouse})
        monitor.start()

        mouse.feed(b"\x02\x01\x00")

        _wait_for(lambda: monitor.last_activity(PID, "mouse") is not None)
        assert monitor.last_activity(PID, "keyboard") is None
        shutdown.set()

    def test_no_reports_means_no_activity(self, shutdown):
        keyboard = FakeInputTransport()
        collections = [InputCollectionInfo(KEYBOARD_PATH, PID, "keyboard")]
        monitor = _make_monitor(shutdown, collections, {KEYBOARD_PATH: keyboard})
        monitor.start()

        time.sleep(0.05)

        assert monitor.last_activity(PID, "keyboard") is None
        shutdown.set()

    def test_unknown_key_returns_none(self, shutdown):
        monitor = _make_monitor(shutdown, [], {})

        assert monitor.last_activity(0xBEEF, "keyboard") is None

    def test_unopenable_collection_is_skipped_without_crashing(self, shutdown):
        """Windows denies opening keyboard/mouse top-level collections — the monitor must
        degrade to 'no data' (the subscriber then fails open), not die."""
        mouse = FakeInputTransport()
        collections = [
            InputCollectionInfo(KEYBOARD_PATH, PID, "keyboard"),  # no transport → OSError
            InputCollectionInfo(MOUSE_PATH, PID, "mouse"),
        ]
        monitor = _make_monitor(shutdown, collections, {MOUSE_PATH: mouse})
        monitor.start()

        mouse.feed(b"\x02")

        _wait_for(lambda: monitor.last_activity(PID, "mouse") is not None)
        assert monitor.last_activity(PID, "keyboard") is None
        shutdown.set()

    def test_transport_error_closes_the_reader(self, shutdown):
        """Receiver unplug surfaces as TransportError — the reader must close its transport
        and deregister so a later sweep can reopen the collection."""
        keyboard = FakeInputTransport()
        collections = [InputCollectionInfo(KEYBOARD_PATH, PID, "keyboard")]
        monitor = _make_monitor(shutdown, collections, {KEYBOARD_PATH: keyboard})
        monitor.start()

        keyboard.fail()

        _wait_for(keyboard.closed.is_set)
        shutdown.set()

    def test_enumeration_failure_is_survived(self, shutdown):
        def broken_enumerate():
            raise RuntimeError("hidapi exploded")

        monitor = InputActivityMonitor(shutdown, enumerate_fn=broken_enumerate, transport_factory=lambda p: None)
        monitor.start()

        time.sleep(0.05)

        assert monitor.last_activity(PID, "keyboard") is None
        shutdown.set()
