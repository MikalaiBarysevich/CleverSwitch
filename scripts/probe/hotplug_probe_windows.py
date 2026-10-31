"""Hotplug probe for Windows — records what the OS reports while a Logitech device comes and goes.

Run in a terminal (no admin needed), with CleverSwitch and Logi Options+ stopped:

    python scripts\\probe\\hotplug_probe_windows.py > probe-windows.log

Optional WinRT section (Bluetooth LE connection status, as shown in Settings):

    pip install winrt-runtime winrt-Windows.Foundation winrt-Windows.Foundation.Collections ^
                winrt-Windows.Devices.Bluetooth winrt-Windows.Devices.Enumeration

Scenario, waiting ~10 s between steps:
  1. start the probe and wait for the initial snapshot
  2. Easy-Switch the BT keyboard to another host, then back
  3. Easy-Switch the BT mouse to another host, then back
  4. turn the BT keyboard off, then on
  5. unplug the Bolt/Unifying receiver, then plug it back
  6. Ctrl-C, send probe-windows.log
"""

import argparse
import asyncio
import ctypes
import ctypes.wintypes as wt
import datetime
import threading
import time
import uuid

_print_lock = threading.Lock()
_show_all = False


def emit(msg: str) -> None:
    with _print_lock:
        print(f"{datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]} {msg}", flush=True)


def interesting(text: str) -> bool:
    low = text.lower()
    return _show_all or "046d" in low or "bthle" in low or "00001812" in low


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, text: str) -> "GUID":
        guid = cls()
        ctypes.memmove(ctypes.byref(guid), uuid.UUID(text).bytes_le, 16)
        return guid

    def __str__(self) -> str:
        return "{" + str(uuid.UUID(bytes_le=bytes(self))) + "}"


class DEVPROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wt.ULONG)]


def propkey(fmtid: str, pid: int) -> DEVPROPKEY:
    return DEVPROPKEY(GUID.parse(fmtid), pid)


class DEVPROPCOMPKEY(ctypes.Structure):
    _fields_ = [("Key", DEVPROPKEY), ("Store", ctypes.c_int), ("LocaleName", wt.LPCWSTR)]


class DEVPROPERTY(ctypes.Structure):
    _fields_ = [("CompKey", DEVPROPCOMPKEY), ("Type", wt.ULONG), ("BufferSize", wt.ULONG), ("Buffer", ctypes.c_void_p)]


class _FilterUnion(ctypes.Union):
    _fields_ = [("ClassGuid", GUID), ("hTarget", ctypes.c_void_p), ("InstanceId", wt.WCHAR * 200)]


class CM_NOTIFY_FILTER(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("Flags", wt.DWORD),
        ("FilterType", ctypes.c_int),
        ("Reserved", wt.DWORD),
        ("u", _FilterUnion),
    ]


GUID_DEVINTERFACE_HID = GUID.parse("4d1e55b2-f16f-11cf-88cb-001111000030")
DEVPKEY_Device_InstanceId = propkey("78c34fc8-104a-4aca-9ea4-524d52996e57", 256)
DEVPKEY_Device_ContainerId = propkey("8c7ed206-3f8a-4827-b3ab-ae9e1faefc6c", 2)
DEVPKEY_DeviceContainer_IsConnected = propkey("78c34fc8-104a-4aca-9ea4-524d52996e57", 55)

CR_SUCCESS = 0
CR_BUFFER_SMALL = 0x1A
DN_STARTED = 0x8
DEV_OBJECT_TYPE_DEVICE_CONTAINER = 2
DEVPROP_TYPE_BOOLEAN = 0x11

CM_NOTIFY_FILTER_FLAG_ALL_INTERFACE_CLASSES = 0x1
CM_NOTIFY_FILTER_FLAG_ALL_DEVICE_INSTANCES = 0x2
CM_NOTIFY_FILTER_TYPE_DEVICEINTERFACE = 0
CM_NOTIFY_FILTER_TYPE_DEVICEINSTANCE = 2

ACTIONS = {
    0: "INTERFACE_ARRIVAL",
    1: "INTERFACE_REMOVAL",
    2: "QUERY_REMOVE",
    3: "QUERY_REMOVE_FAILED",
    4: "REMOVE_PENDING",
    5: "REMOVE_COMPLETE",
    6: "CUSTOM_EVENT",
    7: "INSTANCE_ENUMERATED",
    8: "INSTANCE_STARTED",
    9: "INSTANCE_REMOVED",
}

cfg = ctypes.WinDLL("cfgmgr32")

CM_NOTIFY_CALLBACK = ctypes.WINFUNCTYPE(
    wt.DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wt.DWORD
)
cfg.CM_Register_Notification.argtypes = [
    ctypes.POINTER(CM_NOTIFY_FILTER),
    ctypes.c_void_p,
    CM_NOTIFY_CALLBACK,
    ctypes.POINTER(ctypes.c_void_p),
]
cfg.CM_Register_Notification.restype = wt.DWORD
cfg.CM_Unregister_Notification.argtypes = [ctypes.c_void_p]
cfg.CM_Unregister_Notification.restype = wt.DWORD

try:
    _dev_get_props = cfg.DevGetObjectProperties
    _dev_free_props = cfg.DevFreeObjectProperties
except AttributeError:
    _query = ctypes.WinDLL("api-ms-win-devices-query-l1-1-0")
    _dev_get_props = _query.DevGetObjectProperties
    _dev_free_props = _query.DevFreeObjectProperties
_dev_get_props.argtypes = [
    ctypes.c_int,
    wt.LPCWSTR,
    wt.ULONG,
    wt.ULONG,
    ctypes.POINTER(DEVPROPCOMPKEY),
    ctypes.POINTER(wt.ULONG),
    ctypes.POINTER(ctypes.POINTER(DEVPROPERTY)),
]
_dev_get_props.restype = ctypes.c_long
_dev_free_props.argtypes = [wt.ULONG, ctypes.POINTER(DEVPROPERTY)]
_dev_free_props.restype = None


def present_hid_interfaces() -> list[str]:
    for _ in range(5):
        size = wt.ULONG()
        if cfg.CM_Get_Device_Interface_List_SizeW(ctypes.byref(size), ctypes.byref(GUID_DEVINTERFACE_HID), None, 0):
            return []
        buf = ctypes.create_unicode_buffer(size.value)
        cr = cfg.CM_Get_Device_Interface_ListW(ctypes.byref(GUID_DEVINTERFACE_HID), None, buf, size.value, 0)
        if cr == CR_BUFFER_SMALL:
            continue
        if cr != CR_SUCCESS:
            return []
        return [s for s in buf[: size.value].split("\0") if s]
    return []


def interface_instance_id(link: str) -> str | None:
    prop_type = wt.ULONG()
    size = wt.ULONG(0)
    key = ctypes.byref(DEVPKEY_Device_InstanceId)
    cfg.CM_Get_Device_Interface_PropertyW(link, key, ctypes.byref(prop_type), None, ctypes.byref(size), 0)
    if size.value == 0:
        return None
    buf = ctypes.create_string_buffer(size.value)
    if cfg.CM_Get_Device_Interface_PropertyW(link, key, ctypes.byref(prop_type), buf, ctypes.byref(size), 0):
        return None
    return ctypes.wstring_at(buf)


def devnode_state(instance_id: str) -> tuple[str, str | None]:
    devinst = wt.DWORD()
    cr = cfg.CM_Locate_DevNodeW(ctypes.byref(devinst), instance_id, 0)
    if cr != CR_SUCCESS:
        return f"locate cr=0x{cr:X}", None
    status, problem = wt.ULONG(), wt.ULONG()
    cr = cfg.CM_Get_DevNode_Status(ctypes.byref(status), ctypes.byref(problem), devinst, 0)
    state = f"cr=0x{cr:X}" if cr else f"started={bool(status.value & DN_STARTED)} problem={problem.value}"
    guid = GUID()
    prop_type = wt.ULONG()
    size = wt.ULONG(ctypes.sizeof(guid))
    key = ctypes.byref(DEVPKEY_Device_ContainerId)
    cr = cfg.CM_Get_DevNode_PropertyW(devinst, key, ctypes.byref(prop_type), ctypes.byref(guid), ctypes.byref(size), 0)
    return state, (str(guid) if cr == CR_SUCCESS else None)


def container_is_connected(container_id: str) -> str:
    request = DEVPROPCOMPKEY(DEVPKEY_DeviceContainer_IsConnected, 0, None)
    count = wt.ULONG()
    props = ctypes.POINTER(DEVPROPERTY)()
    hr = _dev_get_props(
        DEV_OBJECT_TYPE_DEVICE_CONTAINER,
        container_id,
        0,
        1,
        ctypes.byref(request),
        ctypes.byref(count),
        ctypes.byref(props),
    )
    if hr != 0:
        return f"hr=0x{hr & 0xFFFFFFFF:08X}"
    try:
        for i in range(count.value):
            prop = props[i]
            if prop.Type == DEVPROP_TYPE_BOOLEAN and prop.Buffer:
                return str(ctypes.c_byte.from_address(prop.Buffer).value != 0)
        return "empty"
    finally:
        _dev_free_props(count, props)


def snapshot() -> dict[str, str]:
    result = {}
    for link in present_hid_interfaces():
        if "046d" not in link.lower():
            continue
        instance_id = interface_instance_id(link) or "?"
        state, container = devnode_state(instance_id)
        connected = container_is_connected(container) if container else "no-container"
        result[link] = f"{state} container={container} container_connected={connected}"
    return result


def poll_loop(stop: threading.Event) -> None:
    previous: dict[str, str] = {}
    first = True
    while not stop.is_set():
        current = snapshot()
        for link in sorted(set(previous) | set(current)):
            before, after = previous.get(link), current.get(link)
            if before == after:
                continue
            if first:
                emit(f"SNAPSHOT  {link}  {after}")
            elif after is None:
                emit(f"POLL gone  {link}")
            elif before is None:
                emit(f"POLL new   {link}  {after}")
            else:
                emit(f"POLL change {link}  {before}  ->  {after}")
        if first:
            emit("SNAPSHOT done — start the scenario")
        first = False
        previous = current
        stop.wait(0.5)


@CM_NOTIFY_CALLBACK
def on_notification(_handle, context, action, data, _size):
    try:
        kind = ctypes.cast(context, ctypes.c_void_p).value
        if kind == 1:
            class_guid = GUID.from_address(data + 8)
            name = ctypes.wstring_at(data + 24)
            if interesting(name):
                emit(f"CM {ACTIONS.get(action, action)} class={class_guid} {name}")
        else:
            name = ctypes.wstring_at(data + 8)
            if interesting(name):
                emit(f"CM {ACTIONS.get(action, action)} {name}")
    except Exception as e:
        emit(f"callback error: {e!r}")
    return 0


def register(flags: int, filter_type: int, context: int) -> ctypes.c_void_p:
    flt = CM_NOTIFY_FILTER()
    flt.cbSize = ctypes.sizeof(CM_NOTIFY_FILTER)
    flt.Flags = flags
    flt.FilterType = filter_type
    handle = ctypes.c_void_p()
    cr = cfg.CM_Register_Notification(
        ctypes.byref(flt), ctypes.c_void_p(context), on_notification, ctypes.byref(handle)
    )
    emit(f"CM_Register_Notification type={filter_type} cr=0x{cr:X}")
    return handle


def winrt_watch() -> None:
    try:
        from winrt.windows.devices.bluetooth import BluetoothLEDevice
        from winrt.windows.devices.enumeration import DeviceInformation
    except ImportError as e:
        emit(f"WINRT skipped ({e})")
        return

    async def main() -> None:
        selector = BluetoothLEDevice.get_device_selector_from_pairing_state(True)
        try:
            infos = await DeviceInformation.find_all_async(selector)
        except TypeError:
            infos = await DeviceInformation.find_all_async_aqs_filter(selector)
        keep = []
        for info in infos:
            device = await BluetoothLEDevice.from_id_async(info.id)
            if device is None:
                continue

            def on_change(sender, _args, name=info.name):
                emit(f"WINRT {name} connection_status={sender.connection_status}")

            device.add_connection_status_changed(on_change)
            keep.append(device)
            emit(f"WINRT watching {info.name} id={info.id} connection_status={device.connection_status}")
        await asyncio.Event().wait()

    asyncio.run(main())


def main() -> None:
    global _show_all
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="print notifications for every device, not just Logitech")
    _show_all = parser.parse_args().all

    handles = [
        register(CM_NOTIFY_FILTER_FLAG_ALL_INTERFACE_CLASSES, CM_NOTIFY_FILTER_TYPE_DEVICEINTERFACE, 1),
        register(CM_NOTIFY_FILTER_FLAG_ALL_DEVICE_INSTANCES, CM_NOTIFY_FILTER_TYPE_DEVICEINSTANCE, 2),
    ]
    stop = threading.Event()
    threading.Thread(target=poll_loop, args=(stop,), daemon=True).start()
    threading.Thread(target=winrt_watch, daemon=True).start()
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    stop.set()
    for handle in handles:
        if handle:
            cfg.CM_Unregister_Notification(handle)
    emit("stopped")


if __name__ == "__main__":
    main()
