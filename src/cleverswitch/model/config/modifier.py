import enum


class Modifier(enum.Flag):
    NONE = 0
    CTRL = enum.auto()
    SHIFT = enum.auto()
    ALT = enum.auto()
    META = enum.auto()


MODIFIER_NAMES = {
    "ctrl": Modifier.CTRL,
    "control": Modifier.CTRL,
    "shift": Modifier.SHIFT,
    "alt": Modifier.ALT,
    "option": Modifier.ALT,
    "meta": Modifier.META,
    "cmd": Modifier.META,
    "command": Modifier.META,
    "win": Modifier.META,
    "super": Modifier.META,
}
