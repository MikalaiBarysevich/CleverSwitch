"""Shared fixtures and test helpers for the CleverSwitch test suite."""

from __future__ import annotations

import threading

import pytest

from cleverswitch.config.config import default_config
from cleverswitch.hidpp.constants import BOLT_PID
from cleverswitch.model.config.config import Config


class FakeTransport:
    """Minimal HIDTransport stub that replays pre-programmed byte responses.

    Captures all written bytes in `written` for assertion.
    Pops responses one-by-one on each read(); returns None when exhausted.

    Set `fail_next` to a TransportError to make the next read() or write() raise, simulating a
    device that drops mid-operation. `closed_by` records the thread that called close().
    """

    def __init__(
        self,
        responses: list[bytes] | None = None,
        kind: str = "bolt",
        pid: int = BOLT_PID,
    ):
        self.written: list[bytes] = []
        self._responses: list[bytes] = list(responses or [])
        self.kind = kind
        self.pid = pid
        self.closed = False
        self.close_count = 0
        self.closed_by: str | None = None
        self.reopened = 0
        self.fail_next: Exception | None = None

    def _maybe_fail(self) -> None:
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error

    def write(self, data: bytes) -> None:
        self._maybe_fail()
        self.written.append(bytes(data))

    def write_output_report(self, data: bytes) -> None:
        self.write(data)

    def read(self, timeout: int = 500) -> bytes | None:
        self._maybe_fail()
        return self._responses.pop(0) if self._responses else None

    def try_open(self) -> None:
        self.closed = False

    def try_reopen(self) -> None:
        self.reopened += 1
        self.closed = False

    def close(self) -> None:
        self.closed = True
        self.close_count += 1
        self.closed_by = threading.current_thread().name


@pytest.fixture
def fake_transport() -> FakeTransport:
    """An empty FakeTransport — returns None on all reads."""
    return FakeTransport()


@pytest.fixture
def make_fake_transport():
    """Factory fixture for creating independent FakeTransport instances."""

    def _make(responses: list[bytes] | None = None, kind: str = "bolt", pid: int = BOLT_PID) -> FakeTransport:
        return FakeTransport(responses=responses, kind=kind, pid=pid)

    return _make


@pytest.fixture
def default_cfg() -> Config:
    """Minimal valid Config with all defaults."""
    return default_config()
