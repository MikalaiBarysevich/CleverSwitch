from ..errors.errors import HotplugError
from ..topic.topics import Topics
from ..util.util import SYSTEM_LINUX, SYSTEM_MACOS, get_system
from .backend import HotplugBackend


def create_backend(topics: Topics) -> HotplugBackend:
    system = get_system()
    if system == SYSTEM_LINUX:
        from .linux.netlink_backend import NetlinkHotplugBackend

        return NetlinkHotplugBackend(topics)
    if system == SYSTEM_MACOS:
        from .macos.iokit_backend import IOKitHotplugBackend

        return IOKitHotplugBackend(topics)
    raise HotplugError(f"Device hotplug is not supported on {system}")
