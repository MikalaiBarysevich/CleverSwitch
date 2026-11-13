from __future__ import annotations

from collections.abc import Callable

from ...model.config.modifier import Modifier
from ..edge_detector import EdgeDetector
from ..edge_sink import EdgeSink, Location
from ..geometry import Rect
from ..loop_backend import LoopFactory
from .user32 import WM_INPUT, User32

# VK_CONTROL, VK_SHIFT and VK_MENU already cover the left and right keys.
MODIFIER_KEYS = {
    0x11: Modifier.CTRL,
    0x10: Modifier.SHIFT,
    0x12: Modifier.ALT,
    0x5B: Modifier.META,  # VK_LWIN
    0x5C: Modifier.META,  # VK_RWIN
}
BUTTON_KEYS = (0x01, 0x02, 0x04, 0x05, 0x06)  # left, right, middle, X1, X2


class RawInputLoop:
    """Windows input through Raw Input rather than low-level hooks: a hook whose callback is slow (the GIL)
    is silently removed by Windows and lags the cursor, while WM_INPUT messages just queue up. Each message
    only says something happened; the live key, button and cursor state is read once per burst."""

    def __init__(self, user32: User32, sink: EdgeSink):
        self._user32 = user32
        self._sink = sink
        user32.use_per_monitor_dpi()
        self._thread_id = user32.current_thread_id()
        user32.open_sink_window()

    @classmethod
    def factory(cls, user32_factory: Callable[[], User32], detector: EdgeDetector) -> LoopFactory:
        def build(publish, stopping) -> RawInputLoop:
            return cls(user32_factory(), EdgeSink(detector, publish, stopping))

        return build

    def run(self) -> None:
        pending = False
        while True:
            result, message = self._user32.next_message()
            if result == 0:
                return
            if result == -1:
                raise OSError("GetMessageW failed")
            if message == WM_INPUT:
                pending = True
            self._user32.dispatch()
            if pending and not self._user32.raw_input_pending():
                pending = False
                self._evaluate()

    def interrupt(self) -> None:
        self._user32.post_quit(self._thread_id)

    def close(self) -> None:
        self._user32.close_sink_window()

    def _evaluate(self) -> None:
        modifiers = Modifier.NONE
        for vk, modifier in MODIFIER_KEYS.items():
            if self._user32.key_down(vk):
                modifiers |= modifier
        buttons_held = any(self._user32.key_down(vk) for vk in BUTTON_KEYS)
        self._sink.on_state(modifiers, buttons_held)
        self._sink.on_motion(self._locate)

    def _locate(self) -> Location | None:
        pos = self._user32.cursor_pos()
        if pos is None:
            return None
        x, y, width, height = self._user32.virtual_screen()
        bounds = Rect(x, y, x + width, y + height) if width > 0 and height > 0 else None
        return pos[0], pos[1], bounds
