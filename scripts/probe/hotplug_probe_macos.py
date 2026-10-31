"""Hotplug probe for macOS — records what IOHIDManager reports while a Logitech device comes and goes.

Run from Terminal, with CleverSwitch stopped (Logi Options+ may stay as it is — note which):

    python3 scripts/probe/hotplug_probe_macos.py > probe-macos.log
    python3 scripts/probe/hotplug_probe_macos.py --no-open > probe-macos-no-open.log

The second run checks whether callbacks arrive without IOHIDManagerOpen (Input Monitoring).

Scenario, waiting ~10 s between steps:
  1. start the probe and wait for the initial MATCH lines
  2. Easy-Switch the BT keyboard to another host, then back
  3. Easy-Switch the BT mouse to another host, then back
  4. turn the BT keyboard off, then on
  5. unplug the Bolt/Unifying receiver, then plug it back
  6. Ctrl-C, send the logs
"""

import argparse
import ctypes
import ctypes.util
import datetime

cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
iokit = ctypes.CDLL(ctypes.util.find_library("IOKit"))

kCFStringEncodingUTF8 = 0x08000100
kCFNumberSInt32Type = 3
kCFNumberSInt64Type = 4

cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
cf.CFStringCreateWithCString.restype = ctypes.c_void_p
cf.CFNumberCreate.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
cf.CFNumberCreate.restype = ctypes.c_void_p
cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
cf.CFNumberGetValue.restype = ctypes.c_bool
cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
cf.CFStringGetCString.restype = ctypes.c_bool
cf.CFGetTypeID.argtypes = [ctypes.c_void_p]
cf.CFGetTypeID.restype = ctypes.c_ulong
cf.CFNumberGetTypeID.restype = ctypes.c_ulong
cf.CFStringGetTypeID.restype = ctypes.c_ulong
cf.CFDictionaryCreateMutable.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]
cf.CFDictionaryCreateMutable.restype = ctypes.c_void_p
cf.CFDictionarySetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
cf.CFRunLoopGetCurrent.restype = ctypes.c_void_p
cf.CFRunLoopRunInMode.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_bool]
cf.CFRunLoopRunInMode.restype = ctypes.c_int32

iokit.IOHIDManagerCreate.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
iokit.IOHIDManagerCreate.restype = ctypes.c_void_p
iokit.IOHIDManagerSetDeviceMatching.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
iokit.IOHIDManagerScheduleWithRunLoop.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
iokit.IOHIDManagerOpen.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
iokit.IOHIDManagerOpen.restype = ctypes.c_int32
iokit.IOHIDDeviceGetProperty.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
iokit.IOHIDDeviceGetProperty.restype = ctypes.c_void_p
iokit.IOHIDDeviceGetService.argtypes = [ctypes.c_void_p]
iokit.IOHIDDeviceGetService.restype = ctypes.c_uint32
iokit.IORegistryEntryGetRegistryEntryID.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint64)]
iokit.IORegistryEntryGetRegistryEntryID.restype = ctypes.c_int32

IOHIDDeviceCallback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)
iokit.IOHIDManagerRegisterDeviceMatchingCallback.argtypes = [ctypes.c_void_p, IOHIDDeviceCallback, ctypes.c_void_p]
iokit.IOHIDManagerRegisterDeviceRemovalCallback.argtypes = [ctypes.c_void_p, IOHIDDeviceCallback, ctypes.c_void_p]

kCFRunLoopDefaultMode = ctypes.c_void_p.in_dll(cf, "kCFRunLoopDefaultMode")
_key_callbacks = ctypes.addressof(ctypes.c_byte.in_dll(cf, "kCFTypeDictionaryKeyCallBacks"))
_value_callbacks = ctypes.addressof(ctypes.c_byte.in_dll(cf, "kCFTypeDictionaryValueCallBacks"))


def emit(msg: str) -> None:
    print(f"{datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]} {msg}", flush=True)


def cfstr(text: str) -> int:
    return cf.CFStringCreateWithCString(None, text.encode(), kCFStringEncodingUTF8)


def cfnum(value: int) -> int:
    v = ctypes.c_int32(value)
    return cf.CFNumberCreate(None, kCFNumberSInt32Type, ctypes.byref(v))


def prop(device: int, name: str):
    ref = iokit.IOHIDDeviceGetProperty(device, cfstr(name))
    if not ref:
        return None
    type_id = cf.CFGetTypeID(ref)
    if type_id == cf.CFNumberGetTypeID():
        v = ctypes.c_int64()
        cf.CFNumberGetValue(ref, kCFNumberSInt64Type, ctypes.byref(v))
        return v.value
    if type_id == cf.CFStringGetTypeID():
        buf = ctypes.create_string_buffer(512)
        if cf.CFStringGetCString(ref, buf, 512, kCFStringEncodingUTF8):
            return buf.value.decode(errors="replace")
    return f"<type {type_id}>"


def describe(device: int) -> str:
    entry_id = ctypes.c_uint64()
    service = iokit.IOHIDDeviceGetService(device)
    rc = iokit.IORegistryEntryGetRegistryEntryID(service, ctypes.byref(entry_id)) if service else -1
    pid = prop(device, "ProductID")
    pid_text = f"0x{pid:04X}" if isinstance(pid, int) else str(pid)
    page = prop(device, "PrimaryUsagePage")
    usage = prop(device, "PrimaryUsage")
    page_text = f"0x{page:04X}" if isinstance(page, int) else str(page)
    usage_text = f"0x{usage:04X}" if isinstance(usage, int) else str(usage)
    return (
        f"ref=0x{device:X} pid={pid_text} transport={prop(device, 'Transport')} "
        f"page={page_text} usage={usage_text} product={prop(device, 'Product')!r} "
        f"registry_id={entry_id.value if rc == 0 else f'rc={rc}'}"
    )


@IOHIDDeviceCallback
def on_match(_context, result, _sender, device):
    try:
        emit(f"MATCH   result={result} {describe(device)}")
    except Exception as e:
        emit(f"MATCH   error {e!r}")


@IOHIDDeviceCallback
def on_remove(_context, result, _sender, device):
    try:
        emit(f"REMOVE  result={result} {describe(device)}")
    except Exception as e:
        emit(f"REMOVE  error {e!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-open", action="store_true", help="skip IOHIDManagerOpen")
    no_open = parser.parse_args().no_open

    manager = iokit.IOHIDManagerCreate(None, 0)
    matching = cf.CFDictionaryCreateMutable(None, 0, _key_callbacks, _value_callbacks)
    cf.CFDictionarySetValue(matching, cfstr("VendorID"), cfnum(0x046D))
    iokit.IOHIDManagerSetDeviceMatching(manager, matching)
    iokit.IOHIDManagerRegisterDeviceMatchingCallback(manager, on_match, None)
    iokit.IOHIDManagerRegisterDeviceRemovalCallback(manager, on_remove, None)
    iokit.IOHIDManagerScheduleWithRunLoop(manager, cf.CFRunLoopGetCurrent(), kCFRunLoopDefaultMode)
    if no_open:
        emit("IOHIDManagerOpen skipped")
    else:
        emit(f"IOHIDManagerOpen rc=0x{iokit.IOHIDManagerOpen(manager, 0) & 0xFFFFFFFF:08X}")
    emit("running — start the scenario after the initial MATCH lines")
    try:
        while True:
            cf.CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.5, False)
    except KeyboardInterrupt:
        emit("stopped")


if __name__ == "__main__":
    main()
