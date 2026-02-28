class CleverSwitchError(Exception):
    pass


class ReceiverNotFound(CleverSwitchError):
    pass


class DeviceNotFound(CleverSwitchError):
    """Raised when a configured device (keyboard or mouse) cannot be located."""

    def __init__(self, role: str, wpid: int | None = None):
        self.role = role
        self.wpid = wpid
        super().__init__(f"{role} not found" + (f" (wpid=0x{wpid:04X})" if wpid else ""))


class FeatureNotSupported(CleverSwitchError):
    """Raised when CHANGE_HOST (0x1814) is not supported by the device."""

    def __init__(self, role: str, devnumber: int):
        self.role = role
        self.devnumber = devnumber
        super().__init__(f"{role} (device {devnumber}) does not support CHANGE_HOST (0x1814)")


class TransportError(CleverSwitchError):
    """Raised on HID read/write failure — usually means device was unplugged."""

    pass


class ConfigError(CleverSwitchError):
    pass
