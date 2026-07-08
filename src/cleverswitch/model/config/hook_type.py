import enum


class HookType(enum.Enum):
    CONNECT = "CONNECT"
    SWITCH = "SWITCH"
    DISCONNECT = "DISCONNECT"
