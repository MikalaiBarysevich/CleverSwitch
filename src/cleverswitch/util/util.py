import platform

SYSTEM_LINUX = "Linux"
SYSTEM_MACOS = "Darwin"
SYSTEM_WINDOWS = "Windows"


def get_system() -> str:
    return platform.system()


def decode_string_response(raw: bytes) -> str | None:
    name = raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()
    return name or None
