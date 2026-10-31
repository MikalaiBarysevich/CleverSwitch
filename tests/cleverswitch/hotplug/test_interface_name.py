"""Unit tests for hotplug/windows/interface_name.py."""

from __future__ import annotations

import pytest

from cleverswitch.hotplug.windows.interface_name import hid_interface_pid

HID_GUID = "{4d1e55b2-f16f-11cf-88cb-001111000030}"


@pytest.mark.parametrize(
    ("link", "pid"),
    [
        (rf"\\?\HID#VID_046D&PID_C52B&MI_02&Col01#7&86f6c1c&0&0000#{HID_GUID}", 0xC52B),
        (rf"\\?\HID#VID_046D&PID_C548&MI_02&Col02#7&1&0&0001#{HID_GUID}", 0xC548),
        (rf"\\?\hid#vid_046d&pid_c52b&mi_00#7&1da9fda7&0&0000#{HID_GUID}\KBD", 0xC52B),
        (
            r"\\?\HID#{00001812-0000-1000-8000-00805f9b34fb}_Dev_VID&02046d_PID&b35b_REV&0013_e521240a5c28&Col03"
            rf"#9&1826784b&0&0002#{HID_GUID}",
            0xB35B,
        ),
        (
            r"\\?\HID#{00001812-0000-1000-8000-00805f9b34fb}_Dev_VID&02046d_PID&b023_REV&0013_d8a3b2c1e0f9"
            rf"#9&2a&0&0000#{HID_GUID}",
            0xB023,
        ),
        (
            r"\\?\HID#{00001124-0000-1000-8000-00805f9b34fb}_VID&0002046d_PID&b342&Col02"
            rf"#8&2a3b4c5d&0&0001#{HID_GUID}",
            0xB342,
        ),
    ],
)
def test_logitech_interfaces_give_their_pid(link, pid):
    assert hid_interface_pid(link) == pid


@pytest.mark.parametrize(
    "link",
    [
        rf"\\?\HID#VID_045E&PID_07A5&MI_01&Col01#7&2&0&0000#{HID_GUID}",
        r"\\?\HID#{00001812-0000-1000-8000-00805f9b34fb}_Dev_VID&02045e_PID&0b13_REV&0509_aa#9&3&0&0000",
        r"\\?\HID#{00001124-0000-1000-8000-00805f9b34fb}_VID&000205ac_PID&0255&Col01#8&1&0&0000",
        r"\\?\ACPI#PNP0303#4&1d401fb5&0#{884b96c3-56ef-11d1-bc8c-00a0c91405dd}",
        "",
    ],
)
def test_other_interfaces_give_none(link):
    assert hid_interface_pid(link) is None
