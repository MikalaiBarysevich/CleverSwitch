"""Unit tests for hotplug/windows/cfgmgr_backend.py — CfgMgr32 itself is replaced by a fake."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cleverswitch.errors.errors import HotplugError
from cleverswitch.event.hid_node_added_event import HidNodeAddedEvent
from cleverswitch.event.hid_node_removed_event import HidNodeRemovedEvent
from cleverswitch.hotplug.windows.cfgmgr32 import ACTION_INTERFACE_ARRIVAL, ACTION_INTERFACE_REMOVAL, ERROR_SUCCESS
from cleverswitch.hotplug.windows.cfgmgr_backend import CfgMgrHotplugBackend
from cleverswitch.topic.topic import Topic

HANDLE = 0x5000
RECEIVER_LINK = r"\\?\HID#VID_046D&PID_C52B&MI_02&Col01#7&86f6c1c&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}"
OTHER_LINK = r"\\?\HID#VID_045E&PID_07A5&MI_01&Col01#7&2&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}"


class FakeCfgMgr:
    def __init__(self, register_error=None):
        self.register_error = register_error
        self.callback = None
        self.unregistered = []
        self.links = {}

    def register_hid_interfaces(self, callback):
        if self.register_error is not None:
            raise self.register_error
        self.callback = callback
        return HANDLE

    def unregister(self, handle):
        self.unregistered.append(handle)

    def symbolic_link(self, event_data):
        return self.links[event_data]


@pytest.fixture
def topics():
    t = MagicMock()
    t.hotplug = MagicMock(spec=Topic)
    return t


def _started(topics, fake):
    backend = CfgMgrHotplugBackend(topics, cfgmgr_factory=lambda: fake)
    backend.start()
    return backend


def _notify(backend, action, event_data):
    return backend._on_notification(HANDLE, None, action, event_data, 0)


def test_start_registers_the_callback(topics):
    fake = FakeCfgMgr()
    backend = _started(topics, fake)
    assert fake.callback is backend._callback


@pytest.mark.parametrize(
    ("action", "event_type"),
    [(ACTION_INTERFACE_ARRIVAL, HidNodeAddedEvent), (ACTION_INTERFACE_REMOVAL, HidNodeRemovedEvent)],
)
def test_interface_events_publish_the_pid(topics, action, event_type):
    fake = FakeCfgMgr()
    fake.links[1] = RECEIVER_LINK
    backend = _started(topics, fake)

    assert _notify(backend, action, 1) == ERROR_SUCCESS

    topics.hotplug.publish.assert_called_once_with(event_type(slot=0, pid=0xC52B))


def test_other_vendors_publish_nothing(topics):
    fake = FakeCfgMgr()
    fake.links[1] = OTHER_LINK
    backend = _started(topics, fake)

    _notify(backend, ACTION_INTERFACE_ARRIVAL, 1)

    topics.hotplug.publish.assert_not_called()


def test_other_actions_publish_nothing(topics):
    fake = FakeCfgMgr()
    fake.links[1] = RECEIVER_LINK
    backend = _started(topics, fake)

    _notify(backend, 3, 1)

    topics.hotplug.publish.assert_not_called()


def test_a_failing_callback_is_logged_and_still_succeeds(topics, caplog):
    backend = _started(topics, FakeCfgMgr())

    assert _notify(backend, ACTION_INTERFACE_ARRIVAL, 99) == ERROR_SUCCESS

    topics.hotplug.publish.assert_not_called()
    assert any("Windows device notification" in r.message for r in caplog.records)


def test_start_fails_when_cfgmgr32_cannot_load(topics):
    def no_cfgmgr():
        raise OSError("cfgmgr32 not found")

    backend = CfgMgrHotplugBackend(topics, cfgmgr_factory=no_cfgmgr)

    with pytest.raises(HotplugError, match="cfgmgr32 not found"):
        backend.start()
    backend.stop()


def test_start_fails_when_registration_fails(topics):
    fake = FakeCfgMgr(register_error=OSError("CONFIGRET 0x3"))
    backend = CfgMgrHotplugBackend(topics, cfgmgr_factory=lambda: fake)

    with pytest.raises(HotplugError, match="CONFIGRET 0x3"):
        backend.start()
    backend.stop()
    assert fake.unregistered == []


def test_stop_unregisters_once(topics):
    fake = FakeCfgMgr()
    backend = _started(topics, fake)

    backend.stop()
    backend.stop()

    assert fake.unregistered == [HANDLE]
