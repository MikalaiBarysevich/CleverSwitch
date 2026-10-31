"""Unit tests for hotplug/backend_factory.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cleverswitch.errors.errors import HotplugError
from cleverswitch.hotplug.backend_factory import create_backend
from cleverswitch.hotplug.linux.netlink_backend import NetlinkHotplugBackend
from cleverswitch.hotplug.macos.iokit_backend import IOKitHotplugBackend
from cleverswitch.hotplug.windows.cfgmgr_backend import CfgMgrHotplugBackend
from cleverswitch.util.util import SYSTEM_LINUX, SYSTEM_MACOS, SYSTEM_WINDOWS


def test_linux_gets_the_netlink_backend(mocker):
    mocker.patch("cleverswitch.hotplug.backend_factory.get_system", return_value=SYSTEM_LINUX)
    assert isinstance(create_backend(MagicMock()), NetlinkHotplugBackend)


def test_macos_gets_the_iokit_backend(mocker):
    mocker.patch("cleverswitch.hotplug.backend_factory.get_system", return_value=SYSTEM_MACOS)
    assert isinstance(create_backend(MagicMock()), IOKitHotplugBackend)


def test_windows_gets_the_cfgmgr_backend(mocker):
    mocker.patch("cleverswitch.hotplug.backend_factory.get_system", return_value=SYSTEM_WINDOWS)
    assert isinstance(create_backend(MagicMock()), CfgMgrHotplugBackend)


def test_platform_without_a_backend_is_an_error(mocker):
    mocker.patch("cleverswitch.hotplug.backend_factory.get_system", return_value="FreeBSD")
    with pytest.raises(HotplugError, match="FreeBSD"):
        create_backend(MagicMock())
