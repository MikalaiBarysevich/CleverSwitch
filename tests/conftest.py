"""Shared fixtures and test helpers for the CleverSwitch test suite."""

from __future__ import annotations

import pytest

from cleverswitch.config import Config, DeviceConfig, HooksConfig, ReceiverConfig, Settings
from cleverswitch.hidpp.constants import BOLT_PID, MX_KEYS_BTID, MX_KEYS_WPID, MX_MASTER_3_BTID, MX_MASTER_3_WPID


class FakeTransport:
    """Minimal HIDTransport stub that replays pre-programmed byte responses.

    Captures all written bytes in `written` for assertion.
    Pops responses one-by-one on each read(); returns None when exhausted.
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

    def write(self, data: bytes) -> None:
        self.written.append(bytes(data))

    def read(self) -> bytes | None:
        return self._responses.pop(0) if self._responses else None

    def close(self) -> None:
        self.closed = True


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
    """Minimal valid Config using default MX Keys + MX Master 3 identifiers."""
    return Config(
        receiver=ReceiverConfig(),
        keyboard=DeviceConfig(name="MX Keys", wpid=MX_KEYS_WPID, btid=MX_KEYS_BTID),
        mouse=DeviceConfig(name="MX Master 3", wpid=MX_MASTER_3_WPID, btid=MX_MASTER_3_BTID),
        hooks=HooksConfig(),
        settings=Settings(),
    )
