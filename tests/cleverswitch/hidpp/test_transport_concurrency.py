"""Concurrency guards for hidpp/transport.py — the issue #108 use-after-free.

The crash was a write landing inside hid_close's free: the reader thread ran
_try_connect → try_reopen → hid_close while the write topic's drain thread was inside
hid_write on the same hid_device*. These tests drive that exact interleaving against a fake
hidapi that reports any call made with a handle it has already closed.
"""

from __future__ import annotations

import threading
import time

import pytest

from cleverswitch.errors.errors import TransportError
from cleverswitch.hidpp.transport import HIDTransport


class FakeHidLib:
    """Tracks which handles are open and records any hidapi call made against a closed one."""

    def __init__(self) -> None:
        self._next_handle = 1000
        self._open: set[int] = set()
        self._guard = threading.Lock()
        self.violations: list[str] = []

    def hid_open_path(self, _path):
        with self._guard:
            self._next_handle += 1
            handle = self._next_handle
            self._open.add(handle)
            return handle

    def hid_close(self, handle) -> None:
        with self._guard:
            self._open.discard(handle)
        time.sleep(0)  # widen the window a real free would occupy

    def _check(self, call: str, handle) -> bool:
        with self._guard:
            live = handle in self._open
        if not live:
            self.violations.append(f"{call} on closed handle {handle}")
        return live

    def hid_write(self, handle, _buf, size):
        if not self._check("hid_write", handle):
            return -1
        time.sleep(0)
        return size

    def hid_read_timeout(self, handle, _buf, _size, _timeout):
        if not self._check("hid_read_timeout", handle):
            return -1
        time.sleep(0)
        return 0

    def hid_error(self, _dev=None) -> str:
        return "fake error"


@pytest.fixture
def fake_lib(mocker) -> FakeHidLib:
    lib = FakeHidLib()
    mocker.patch("cleverswitch.hidpp.transport._lib", lib)
    return lib


def _hammer(target, count: int, stop: threading.Event) -> list[threading.Thread]:
    threads = [threading.Thread(target=target, daemon=True) for _ in range(count)]
    for thread in threads:
        thread.start()
    return threads


def test_write_never_reaches_hidapi_while_another_thread_reopens(fake_lib):
    transport = HIDTransport("receiver", b"/dev/hidraw0")
    stop = threading.Event()
    unexpected: list[BaseException] = []
    msg = bytes([0x11]) + bytes(19)

    def writer() -> None:
        while not stop.is_set():
            try:
                transport.write(msg)
            except TransportError:
                pass  # expected while the handle is briefly closed
            except BaseException as error:  # noqa: BLE001 — the test is asserting on this
                unexpected.append(error)

    def reopener() -> None:
        while not stop.is_set():
            transport.try_reopen()

    threads = _hammer(writer, 4, stop) + _hammer(reopener, 1, stop)
    time.sleep(0.5)
    stop.set()
    for thread in threads:
        thread.join(timeout=2.0)

    assert fake_lib.violations == []
    assert unexpected == []


def test_read_never_reaches_hidapi_while_another_thread_closes(fake_lib):
    transport = HIDTransport("receiver", b"/dev/hidraw0")
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            try:
                transport.read(timeout=0)
            except TransportError:
                pass

    def closer() -> None:
        while not stop.is_set():
            transport.close()
            transport.try_open()

    threads = _hammer(reader, 3, stop) + _hammer(closer, 1, stop)
    time.sleep(0.5)
    stop.set()
    for thread in threads:
        thread.join(timeout=2.0)

    assert fake_lib.violations == []


def test_write_on_closed_transport_raises_transport_error(fake_lib):
    transport = HIDTransport("receiver", b"/dev/hidraw0")
    transport.close()

    with pytest.raises(TransportError):
        transport.write(bytes([0x11]) + bytes(19))

    assert fake_lib.violations == []


def test_write_output_report_falls_back_without_deadlocking(fake_lib, mocker):
    """The hidapi < 0.15 fallback re-enters the write path — it must not re-acquire the lock."""
    mocker.patch("cleverswitch.hidpp.transport._hid_send_output_report", None)
    transport = HIDTransport("bluetooth", b"/dev/hidraw1")

    done = threading.Event()

    def call() -> None:
        transport.write_output_report(bytes([0x11]) + bytes(19))
        done.set()

    thread = threading.Thread(target=call, daemon=True)
    thread.start()
    thread.join(timeout=2.0)

    assert done.is_set(), "write_output_report fallback deadlocked on the handle lock"
    assert fake_lib.violations == []
