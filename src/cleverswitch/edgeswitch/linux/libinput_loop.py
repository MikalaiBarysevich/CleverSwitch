from __future__ import annotations

import errno
import logging
import os
import select
from collections.abc import Callable
from typing import Protocol

from ..edge_sink import EdgeSink
from .libinput import Libinput
from .libinput_event import (
    DEVICE_ADDED,
    DEVICE_REMOVED,
    KEYBOARD_KEY,
    POINTER_BUTTON,
    POINTER_MOTION,
    POINTER_MOTION_ABSOLUTE,
    LibinputEvent,
)
from .seat_state import SeatState

log = logging.getLogger(__name__)

PERMISSION_HINT = (
    "Edge switch cannot read any keyboard or mouse in /dev/input; install the current "
    "rules.d/42-cleverswitch.rules or add your user to the 'input' group, then restart CleverSwitch"
)
SEAT = "seat0"
# libinput asks for read-write; reading is all we do, and only LED writes would need more.
OPEN_FLAGS = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC
_RETRY_ERRNOS = frozenset({errno.EINTR, errno.EAGAIN})

BindingFactory = Callable[[str, Callable[[bytes, int], int], Callable[[int], None]], Libinput]


class CursorFeed(Protocol):
    """Where the cursor is, from the compositor: asked per motion burst (Hyprland) or reported over its own fd
    (KWin). Raises OSError once the compositor is gone."""

    name: str

    def fd(self) -> int | None: ...

    def drain(self, sink: EdgeSink) -> None: ...

    def health_check(self) -> bool: ...

    def on_motion(self, sink: EdgeSink) -> None: ...

    def close(self) -> None: ...


class LibinputLoop:
    """Keys and buttons through libinput, which follows device hotplug itself, and the cursor from the
    compositor (Hyprland, KWin), which hides it from everyone else.

    It works like the Windows loop: libinput events stand in for WM_INPUT, and the feed turns motion, or its own
    reports, into EdgeSink input. A compositor that goes away raises out of run(), so the backend is revived on
    the next device connection. The loop owns the feed and closes it.
    """

    def __init__(
        self,
        binding_factory: BindingFactory,
        sink: EdgeSink,
        feed: CursorFeed,
        os_open: Callable[[bytes, int], int] = os.open,
        os_close: Callable[[int], None] = os.close,
        seat: str = SEAT,
    ):
        self._sink = sink
        self._feed = feed
        self._os_open = os_open
        self._os_close = os_close
        self._seat = seat
        self._state = SeatState()
        self._motion_pending = False
        self._devices: dict[int, LibinputEvent] = {}
        self._denied = 0
        self._warned = False
        self._interrupted = False
        self._li: Libinput | None = None
        self._wake_r: int | None = None
        self._wake_w: int | None = None
        try:
            self._wake_r, self._wake_w = os.pipe()
            self._li = binding_factory(self._seat, self._open_restricted, self._close_restricted)
            self._dispatch()
        except BaseException:
            self.close()
            raise
        log.info(f"Edge switch reads {len(self._devices)} input devices and the cursor position from {feed.name}")

    def run(self) -> None:
        poller = select.poll()
        poller.register(self._wake_r, select.POLLIN)
        poller.register(self._li.fd(), select.POLLIN)
        if (feed_fd := self._feed.fd()) is not None:
            poller.register(feed_fd, select.POLLIN)
        while not self._interrupted:
            poller.poll()
            if self._interrupted:
                return
            self._dispatch()

    def interrupt(self) -> None:
        self._interrupted = True
        os.write(self._wake_w, b"x")

    def health_check(self) -> bool:
        return self._feed.health_check()

    def close(self) -> None:
        self._feed.close()
        if self._li is not None:
            self._li.close()
            self._li = None
        for fd in (self._wake_r, self._wake_w):
            if fd is not None:
                os.close(fd)
        self._wake_r = self._wake_w = None

    # Called by libinput from inside assign_seat and dispatch; an exception here would hand libinput fd 0.
    def _open_restricted(self, path: bytes, _flags: int) -> int:
        try:
            return self._os_open(path, OPEN_FLAGS)
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EPERM):
                self._denied += 1
            log.debug(f"Cannot open {os.fsdecode(path)}: {e}")
            return -(e.errno or errno.EIO)
        except BaseException:
            return -errno.EIO

    def _close_restricted(self, fd: int) -> None:
        try:
            self._os_close(fd)
        except OSError:
            pass

    def _dispatch(self) -> None:
        rc = self._li.dispatch()
        if rc < 0 and -rc not in _RETRY_ERRNOS:
            raise OSError(-rc, "libinput_dispatch failed")
        if rc >= 0:
            while (event := self._li.read_event()) is not None:
                self._handle(event)
            if self._motion_pending:
                self._motion_pending = False
                self._feed.on_motion(self._sink)
            self._check_permission()
        self._feed.drain(self._sink)

    def _handle(self, event: LibinputEvent) -> None:
        if event.type == DEVICE_ADDED:
            if event.keyboard or event.pointer:
                self._devices[event.device] = event
                log.debug(f"Edge switch reads '{event.name}'")
        elif event.type == DEVICE_REMOVED:
            if self._devices.pop(event.device, None) is not None:
                # libinput releases a removed device's keys first; this only covers a release it skipped.
                if not any(d.keyboard for d in self._devices.values()):
                    self._state.clear_keys()
                if not any(d.pointer for d in self._devices.values()):
                    self._state.clear_buttons()
                self._push_state()
        elif event.type == KEYBOARD_KEY:
            if self._state.on_key(event.code, event.seat_count):
                self._push_state()
        elif event.type == POINTER_BUTTON:
            if self._state.on_button(event.code, event.seat_count):
                self._push_state()
        elif event.type in (POINTER_MOTION, POINTER_MOTION_ABSOLUTE):
            # Absolute devices (tablets, absolute touchscreens) never emit a relative motion event.
            self._motion_pending = True

    def _push_state(self) -> None:
        self._sink.on_state(self._state.modifiers, self._state.buttons_held)

    def _check_permission(self) -> None:
        if self._denied and not self._devices and not self._warned:
            log.warning(PERMISSION_HINT)
            self._warned = True
        self._denied = 0
