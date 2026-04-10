"""Unit tests for setup/app_setup.py."""

from __future__ import annotations

import argparse
import sys

import pytest

from cleverswitch.model.context.app_context import AppContext


def _cli_args(**overrides):
    defaults = {"config": None, "verbose": False, "verbose_extra": False, "dry_run": False}
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_setup_context_returns_app_context(mocker):
    mocker.patch("cleverswitch.setup.app_setup.check")
    mocker.patch("cleverswitch.setup.app_setup.cfg_module.load")
    mocker.patch("cleverswitch.setup.app_setup.signal.signal")
    mocker.patch("cleverswitch.setup.app_setup.get_system", return_value="Linux")

    from cleverswitch.setup.app_setup import setup_context

    ctx = setup_context(_cli_args())
    assert isinstance(ctx, AppContext)
    assert ctx.device_registry is not None
    assert ctx.topics.hid_event is not None
    assert ctx.topics.write is not None
    assert ctx.topics.device_info is not None
    assert ctx.topics.flags is not None


def test_setup_context_exits_on_config_error(mocker):
    from cleverswitch.errors.errors import ConfigError

    mocker.patch("cleverswitch.setup.app_setup.check")
    mocker.patch("cleverswitch.setup.app_setup.cfg_module.load", side_effect=ConfigError("bad"))
    mocker.patch("cleverswitch.setup.app_setup.signal.signal")
    mocker.patch("cleverswitch.setup.app_setup.get_system", return_value="Linux")

    from cleverswitch.setup.app_setup import setup_context

    with pytest.raises(SystemExit) as exc:
        setup_context(_cli_args())
    assert exc.value.code == 1


def test_setup_context_initializes_subscribers(mocker):
    mocker.patch("cleverswitch.setup.app_setup.check")
    mocker.patch("cleverswitch.setup.app_setup.cfg_module.load")
    mocker.patch("cleverswitch.setup.app_setup.signal.signal")
    mocker.patch("cleverswitch.setup.app_setup.get_system", return_value="Linux")

    mock_init = mocker.patch("cleverswitch.setup.app_setup._init_subscribers")

    from cleverswitch.setup.app_setup import setup_context

    setup_context(_cli_args())
    mock_init.assert_called_once()
