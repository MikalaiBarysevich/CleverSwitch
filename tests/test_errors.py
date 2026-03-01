"""Unit tests for custom exception classes."""

from __future__ import annotations

import pytest

from cleverswitch.errors import (
    CleverSwitchError,
    ConfigError,
    DeviceNotFound,
    FeatureNotSupported,
    ReceiverNotFound,
    TransportError,
)


# ── Inheritance ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "exc_class",
    [DeviceNotFound, FeatureNotSupported, TransportError, ConfigError, ReceiverNotFound],
)
def test_all_errors_are_subclasses_of_clever_switch_error(exc_class):
    assert issubclass(exc_class, CleverSwitchError)


@pytest.mark.parametrize(
    "exc_class",
    [DeviceNotFound, FeatureNotSupported, TransportError, ConfigError, ReceiverNotFound],
)
def test_all_errors_are_subclasses_of_exception(exc_class):
    assert issubclass(exc_class, Exception)


# ── DeviceNotFound ────────────────────────────────────────────────────────────


def test_device_not_found_message_includes_role():
    exc = DeviceNotFound("keyboard")
    assert "keyboard" in str(exc)


def test_device_not_found_message_omits_wpid():
    exc = DeviceNotFound("keyboard")
    assert "wpid" not in str(exc)


def test_device_not_found_stores_role_attribute():
    exc = DeviceNotFound("keyboard")
    assert exc.role == "keyboard"


# ── FeatureNotSupported ───────────────────────────────────────────────────────


def test_feature_not_supported_message_includes_role_and_device_number():
    exc = FeatureNotSupported("keyboard", devnumber=1)
    assert "keyboard" in str(exc)
    assert "1" in str(exc)


def test_feature_not_supported_message_mentions_change_host_feature():
    exc = FeatureNotSupported("keyboard", devnumber=1)
    assert "CHANGE_HOST" in str(exc)


def test_feature_not_supported_stores_role_attribute():
    exc = FeatureNotSupported("mouse", devnumber=2)
    assert exc.role == "mouse"


def test_feature_not_supported_stores_devnumber_attribute():
    exc = FeatureNotSupported("keyboard", devnumber=3)
    assert exc.devnumber == 3


# ── TransportError / ConfigError / ReceiverNotFound ──────────────────────────


def test_transport_error_can_be_raised_and_caught_as_clever_switch_error():
    with pytest.raises(CleverSwitchError):
        raise TransportError("device unplugged")


def test_config_error_preserves_message():
    exc = ConfigError("bad log_level")
    assert "bad log_level" in str(exc)
