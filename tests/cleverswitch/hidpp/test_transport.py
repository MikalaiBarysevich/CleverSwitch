"""Concurrency tests for the direct HIDAPI binding."""

from __future__ import annotations

import threading
import time

import pytest

from cleverswitch.hidpp import transport


def test_hidapi_lifecycle_operations_are_serialized(mocker):
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    calls = 0
    active_calls = 0
    max_active_calls = 0
    calls_lock = threading.Lock()

    def fake_enumerate(_vendor_id, _product_id):
        nonlocal calls, active_calls, max_active_calls
        with calls_lock:
            calls += 1
            call_number = calls
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
        if call_number == 1:
            first_entered.set()
            assert release_first.wait(timeout=2)
        else:
            second_entered.set()
        with calls_lock:
            active_calls -= 1
        return None

    mocker.patch.object(transport._lib, "hid_enumerate", side_effect=fake_enumerate)
    mocker.patch.object(transport._lib, "hid_free_enumeration")

    first = threading.Thread(target=transport.enumerate_hid_devices)
    second = threading.Thread(target=transport.enumerate_hid_devices)
    first.start()
    assert first_entered.wait(timeout=2)
    second.start()

    time.sleep(0.05)
    assert not second_entered.is_set()
    release_first.set()

    first.join(timeout=2)
    second.join(timeout=2)
    assert not first.is_alive()
    assert not second.is_alive()
    assert second_entered.is_set()
    assert max_active_calls == 1


def test_hidapi_open_waits_for_enumeration(mocker):
    enumerate_entered = threading.Event()
    release_enumeration = threading.Event()
    open_entered = threading.Event()

    def fake_enumerate(_vendor_id, _product_id):
        enumerate_entered.set()
        assert release_enumeration.wait(timeout=2)
        return None

    def fake_open_path(_path):
        open_entered.set()
        return 1

    mocker.patch.object(transport._lib, "hid_enumerate", side_effect=fake_enumerate)
    mocker.patch.object(transport._lib, "hid_free_enumeration")
    mocker.patch.object(transport._lib, "hid_open_path", side_effect=fake_open_path)

    enumerate_thread = threading.Thread(target=transport.enumerate_hid_devices)
    enumerate_thread.start()
    assert enumerate_entered.wait(timeout=2)

    hid_transport = transport.HIDTransport.__new__(transport.HIDTransport)
    hid_transport._path = b"test-path"
    open_thread = threading.Thread(target=hid_transport.try_open)
    open_thread.start()

    time.sleep(0.05)
    assert not open_entered.is_set()
    release_enumeration.set()

    enumerate_thread.join(timeout=2)
    open_thread.join(timeout=2)
    assert not enumerate_thread.is_alive()
    assert not open_thread.is_alive()
    assert open_entered.is_set()


def test_open_failure_reads_global_error_without_deadlock(mocker):
    mocker.patch.object(transport._lib, "hid_open_path", return_value=None)
    mocker.patch.object(transport._lib, "hid_error", return_value="device unavailable")
    hid_transport = transport.HIDTransport.__new__(transport.HIDTransport)
    hid_transport._path = b"test-path"

    with pytest.raises(OSError, match="device unavailable"):
        hid_transport.try_open()


def test_enumeration_exception_frees_list_and_releases_lock(mocker):
    node = transport._DeviceInfo()
    node.path = b"test-path"
    node.vendor_id = 0x046D
    node.product_id = 0xB38E
    node.usage_page = next(iter(transport.HIDPP_USAGE_PAGES))
    node.usage = 0x0001
    node.next = None
    head = transport.ctypes.pointer(node)

    mocker.patch.object(transport._lib, "hid_enumerate", return_value=head)
    free = mocker.patch.object(transport._lib, "hid_free_enumeration")
    mocker.patch.object(transport, "HidDeviceInfo", side_effect=RuntimeError("copy failed"))

    with pytest.raises(RuntimeError, match="copy failed"):
        transport.enumerate_hid_devices()

    free.assert_called_once_with(head)
    assert transport._HID_LIFECYCLE_LOCK.acquire(timeout=0.1)
    transport._HID_LIFECYCLE_LOCK.release()


def test_close_waits_for_enumeration_and_clears_handle_once(mocker):
    enumerate_entered = threading.Event()
    release_enumeration = threading.Event()
    close_entered = threading.Event()

    def fake_enumerate(_vendor_id, _product_id):
        enumerate_entered.set()
        assert release_enumeration.wait(timeout=2)
        return None

    def fake_close(_dev):
        close_entered.set()

    mocker.patch.object(transport._lib, "hid_enumerate", side_effect=fake_enumerate)
    mocker.patch.object(transport._lib, "hid_free_enumeration")
    close = mocker.patch.object(transport._lib, "hid_close", side_effect=fake_close)

    enumerate_thread = threading.Thread(target=transport.enumerate_hid_devices)
    enumerate_thread.start()
    assert enumerate_entered.wait(timeout=2)

    hid_transport = transport.HIDTransport.__new__(transport.HIDTransport)
    hid_transport._dev = 123
    close_thread = threading.Thread(target=hid_transport.close)
    close_thread.start()

    time.sleep(0.05)
    assert not close_entered.is_set()
    release_enumeration.set()

    enumerate_thread.join(timeout=2)
    close_thread.join(timeout=2)
    assert not enumerate_thread.is_alive()
    assert not close_thread.is_alive()
    assert hid_transport._dev is None
    close.assert_called_once_with(123)

    hid_transport.close()
    close.assert_called_once_with(123)


def test_blocking_read_does_not_block_close(mocker):
    read_entered = threading.Event()
    release_read = threading.Event()
    close_entered = threading.Event()

    def fake_read_timeout(_dev, _buf, _size, _timeout):
        read_entered.set()
        assert release_read.wait(timeout=2)
        return 0

    def fake_close(_dev):
        close_entered.set()

    mocker.patch.object(transport._lib, "hid_read_timeout", side_effect=fake_read_timeout)
    mocker.patch.object(transport._lib, "hid_close", side_effect=fake_close)

    hid_transport = transport.HIDTransport.__new__(transport.HIDTransport)
    hid_transport._dev = 123

    read_thread = threading.Thread(target=hid_transport.read)
    read_thread.start()
    assert read_entered.wait(timeout=2)

    close_thread = threading.Thread(target=hid_transport.close)
    close_thread.start()
    assert close_entered.wait(timeout=0.5)
    close_thread.join(timeout=2)

    release_read.set()
    read_thread.join(timeout=2)
    assert not read_thread.is_alive()
    assert not close_thread.is_alive()
