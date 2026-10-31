"""Unit tests for hotplug/backend_factory.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cleverswitch.errors.errors import HotplugError
from cleverswitch.hotplug.backend_factory import create_backend
from cleverswitch.hotplug.linux.netlink_backend import NetlinkHotplugBackend
from cleverswitch.util.util import SYSTEM_LINUX, SYSTEM_MACOS, SYSTEM_WINDOWS


def test_linux_gets_the_netlink_backend(mocker):
    mocker.patch("cleverswitch.hotplug.backend_factory.get_system", return_value=SYSTEM_LINUX)
    assert isinstance(create_backend(MagicMock()), NetlinkHotplugBackend)


@pytest.mark.parametrize("system", [SYSTEM_MACOS, SYSTEM_WINDOWS, "FreeBSD"])
def test_platform_without_a_backend_is_an_error(mocker, system):
    mocker.patch("cleverswitch.hotplug.backend_factory.get_system", return_value=system)
    with pytest.raises(HotplugError, match=system):
        create_backend(MagicMock())
