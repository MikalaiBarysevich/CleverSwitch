"""Unit tests for hotplug/macos/iokit_backend.py — IOKit itself is replaced by a fake."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from cleverswitch.errors.errors import HotplugError
from cleverswitch.event.hid_node_added_event import HidNodeAddedEvent
from cleverswitch.event.hid_node_removed_event import HidNodeRemovedEvent
from cleverswitch.hidpp.constants import LOGITECH_VENDOR_ID
from cleverswitch.hotplug.macos import iokit_backend
from cleverswitch.hotplug.macos.iokit_backend import IOKitHotplugBackend
from cleverswitch.topic.topic import Topic

MANAGER = 0x1000
RUN_LOOP = 0x2000
KEYBOARD_REF = 0x10
RECEIVER_REF = 0x20


class FakeIOKit:
    def __init__(self, products=None, create_error=None, product_error=None):
        self.products = products or {}
        self.create_error = create_error
        self.product_error = product_error
        self.vendor_id = None
        self.on_match = None
        self.on_remove = None
        self.released = []
        self.stopped = []
        self.runs = 0
        self._wake = threading.Event()

    def create_manager(self, vendor_id, on_match, on_remove):
        if self.create_error is not None:
            raise self.create_error
        self.vendor_id, self.on_match, self.on_remove = vendor_id, on_match, on_remove
        return MANAGER

    def current_run_loop(self):
        return RUN_LOOP

    def run(self, seconds):
        self.runs += 1
        self._wake.wait(seconds)
        self._wake.clear()

    def stop(self, run_loop):
        self.stopped.append(run_loop)
        self._wake.set()

    def release_manager(self, manager):
        self.released.append(manager)

    def product_id(self, device):
        if self.product_error is not None:
            raise self.product_error
        return self.products.get(device)


@pytest.fixture
def topics():
    t = MagicMock()
    t.hotplug = MagicMock(spec=Topic)
    return t


def _started(topics, fake):
    backend = IOKitHotplugBackend(topics, iokit_factory=lambda: fake)
    backend.start()
    return backend


def test_start_matches_logitech_devices_and_runs_the_loop(topics):
    fake = FakeIOKit()
    backend = _started(topics, fake)
    try:
        assert fake.vendor_id == LOGITECH_VENDOR_ID
        assert fake.on_match is not None and fake.on_remove is not None
    finally:
        backend.stop()


def test_stop_stops_the_run_loop_and_releases_the_manager(topics):
    fake = FakeIOKit()
    backend = _started(topics, fake)
    thread = backend._thread

    backend.stop()

    assert not thread.is_alive()
    assert fake.stopped == [RUN_LOOP]
    assert fake.released == [MANAGER]


def test_stop_is_idempotent_and_safe_before_start(topics):
    IOKitHotplugBackend(topics, iokit_factory=FakeIOKit).stop()
    backend = _started(topics, FakeIOKit())
    backend.stop()
    backend.stop()


@pytest.mark.parametrize(
    ("callback", "event_type"), [("on_match", HidNodeAddedEvent), ("on_remove", HidNodeRemovedEvent)]
)
def test_callbacks_publish_the_device_product_id(topics, callback, event_type):
    fake = FakeIOKit(products={KEYBOARD_REF: 0xB35B})
    backend = _started(topics, fake)
    try:
        getattr(fake, callback)(None, 0, None, KEYBOARD_REF)
    finally:
        backend.stop()

    topics.hotplug.publish.assert_called_once_with(event_type(slot=0, pid=0xB35B))


def test_each_receiver_interface_publishes_its_own_event(topics):
    fake = FakeIOKit(products={KEYBOARD_REF: 0xC52B, RECEIVER_REF: 0xC52B})
    backend = _started(topics, fake)
    try:
        fake.on_match(None, 0, None, KEYBOARD_REF)
        fake.on_match(None, 0, None, RECEIVER_REF)
    finally:
        backend.stop()

    assert topics.hotplug.publish.call_count == 2


def test_device_without_a_product_id_publishes_nothing(topics):
    fake = FakeIOKit()
    backend = _started(topics, fake)
    try:
        fake.on_remove(None, 0, None, KEYBOARD_REF)
    finally:
        backend.stop()

    topics.hotplug.publish.assert_not_called()


def test_unreadable_product_id_is_logged_not_raised(topics, caplog):
    fake = FakeIOKit(product_error=OSError("service gone"))
    backend = _started(topics, fake)
    try:
        fake.on_remove(None, 0, None, KEYBOARD_REF)
    finally:
        backend.stop()

    topics.hotplug.publish.assert_not_called()
    assert any("product id" in r.message for r in caplog.records)


def test_start_fails_when_iokit_cannot_load(topics):
    def no_iokit():
        raise OSError("dlopen failed")

    backend = IOKitHotplugBackend(topics, iokit_factory=no_iokit)

    with pytest.raises(HotplugError, match="dlopen failed"):
        backend.start()
    backend.stop()


def test_start_fails_when_the_manager_cannot_be_created(topics):
    fake = FakeIOKit(create_error=OSError("IOHIDManagerCreate failed"))
    backend = IOKitHotplugBackend(topics, iokit_factory=lambda: fake)

    with pytest.raises(HotplugError, match="IOHIDManagerCreate failed"):
        backend.start()
    assert fake.released == []


def test_start_fails_when_the_loop_never_becomes_ready(topics, mocker):
    mocker.patch.object(iokit_backend, "_START_TIMEOUT", 0.05)
    release = threading.Event()

    def slow_iokit():
        release.wait(2.0)
        return FakeIOKit()

    backend = IOKitHotplugBackend(topics, iokit_factory=slow_iokit)
    try:
        with pytest.raises(HotplugError, match="did not start in time"):
            backend.start()
    finally:
        release.set()
        backend.stop()
