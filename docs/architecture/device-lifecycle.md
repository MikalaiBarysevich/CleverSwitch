# Device lifecycle

```
discovery.discover()
  ├── hotplug/backend_factory.create_backend() → HotplugBackend, one per platform (nothing polls):
  │     Linux: NetlinkHotplugBackend — udevd's netlink group (2, after rules ran, so the uaccess ACL
  │     is already applied), root-sent messages only, hidraw add/remove → pid from DEVPATH; ENOBUFS →
  │     HotplugResyncEvent.
  │     macOS: IOKitHotplugBackend — an IOHIDManager matching Logitech's vendor id, scheduled on its
  │     own CFRunLoop thread; matching/removal callbacks read only ProductID (the IORegistry entry is
  │     already gone on removal; IOHIDDeviceRef values are reused, so never key by the ref). The
  │     manager is never opened, so it needs no Input Monitoring permission.
  │     Windows: CfgMgrHotplugBackend — CM_Register_Notification for GUID_DEVINTERFACE_HID; the
  │     callback runs on a system thread pool, parses the pid from the interface's symbolic link
  │     (USB `VID_046D&PID_xxxx`, BLE `VID&02046D_PID&xxxx`) and publishes. A switched-away BT
  │     device's interfaces are removed, so no extra Bluetooth signal is needed. stop() must never
  │     run on a callback: CM_Unregister_Notification waits for callbacks in flight.
  │     No backend for the platform, or one that cannot start → HotplugError →
  │     exit 1. Publishes HidNode{Added,Removed}Event(pid) on the hotplug topic
  ├── one HotplugResyncEvent after the backend is registered (startup sweep)
  ├── LinkManager (hotplug subscriber, single drain thread): every event re-enumerates its pid with
  │     hidapi — the event only says where to look — and creates the pid's link the first time,
  │     otherwise calls DeviceLink.update(collections). Links are parked, never destroyed
  └── link_factory.create_link(pid, collections) → DeviceLink — one per HID product id
      ├── update(collections): one HidChannel per (usage_page, usage), created on first sight;
      │     listed collections are attach(path)ed, missing ones detach()ed
      ├── HidChannel — one reader thread per HID collection (Bluetooth ones write output reports);
      │     driven by attach/detach (latest command wins; it sleeps when it has nothing to open);
      │     reports every open/close to DeviceLink.on_hid_state_changed (non-blocking). A failed
      │     open retries after 1/2/4/8/16 s, then waits for the next attach. A failed read, or a
      │     failed reopen after a write failure, closes the handle and waits for the next attach —
      │     unless an attach arrived since the open (Windows keeps one path across a quick drop and
      │     return), then it reopens at once. A failed write only reopens the handle quietly
      ├── GattChannel — macOS Bluetooth only (and only when bleak imports); see the BLE section
      ├── EventListener (thread, reads raw bytes → parses → publishes to hid_event)
      ├── the only write-topic subscriber for that pid: GATT first when subscribed, otherwise the
      │     HID collection its WriteRouter picks (ReportIdWriteRouter on Windows, where short/long
      │     reports are separate collections; first channel elsewhere) via HidChannel.submit()
      └── owns presence: the device is present while EVERY collection is open (and, for a Windows
            receiver, both its short and long HID++ collections have been listed — they arrive as
            separate events, so an early enumeration can see just one), and only changes
            are emitted (through EventListener.emit, in order with raw reports), so a
            multi-collection device connects and disconnects once:
            ├── TransportConnectedEvent(pid, "receiver") → ReceiverArmingSubscriber enables
            │     HID++ notifications + enumerates paired devices → DeviceConnectedEvent(s)
            ├── TransportConnectedEvent(pid, "bluetooth") → DirectDeviceConnectionSubscriber
            │     → DeviceConnectedEvent(slot=0xFF, wpid=pid)
            └── TransportDisconnectedEvent(pid) → TransportDisconnectionSubscriber fans out one
                  DeviceConnectedEvent(link_established=False) per registered device on that pid

DeviceConnectionSubscriber.notify(DeviceConnectedEvent)
  ├── idempotence: skips if logi_device.connected == event.link_established (absorbs duplicates,
  │     e.g. from the disconnect fan-out)
  ├── new device + cache hit → cached LogiDevice registered, then reconnection path (skips discovery)
  ├── new device + link_established=True  → LogiDevice registered (a replaced entry in the same (pid, slot)
  │     that is disconnected is unregistered first), DeviceInfoRequestEvent published
  ├── new device + link_established=False → skipped (stale pairing entry from receiver enumeration)
  └── reconnect → logi_device.connected updated, SetReportFlagEvent re-published if supported_flags known,
        DeviceInfoRequestEvent published only for still-pending_steps

DeviceInfoSubscriber.notify(DeviceInfoRequestEvent)
  └── starts InfoTask threads: CidReportingFeatureTask, ChangeHostFeatureTask, NameAndTypeFeatureTask, FriendlyNameFeatureTask

InfoTask (Thread + Subscriber)
  ├── doTask() — sends HID++ requests via write topic, blocks on response queue
  ├── on success: removes step from device.pending_steps, fires dependent tasks
  └── publishes InfoTaskProgressEvent to info_progress

InfoTaskOrchestrator.notify(InfoTaskProgressEvent)
  ├── success + pending_steps empty → cache.save(device), logs "Device fully discovered" (once per wpid).
  │     friendly_name is never back-filled from name; display_name already falls back to it.
  └── failure + device.connected → retries the task immediately, up to MAX_DISCOVERY_ATTEMPTS (5)
        for the steps in _CAPPED_STEPS (CHANGE_HOST, CID_REPORTING, FIND_ES_CIDS_FLAGS, GET_DEVICE_TYPE);
        on exhaustion logs once at CRITICAL and keeps running. Cosmetic steps retry unbounded.
        A task that failed after an error reply reports it only after ERROR_RETRY_DELAY (2s), so a
        device that answers everything with an error (a receiver's 0x09 for an unreachable device)
        is retried at the pace of a timeout, not in a hot loop.
        The step stays in pending_steps, so the device is never cached and gets a fresh budget
        when DeviceInfoRequestEvent arrives (the orchestrator's second subscription, on
        device_info) — two subscriptions mean two drain threads, hence the lock on _attempts.
```

## Receiver enable-notifications message

`ReceiverArmingSubscriber` (`subscriber/receiver_arming_subscriber.py`) sends `ENABLE_HIDPP_NOTIFICATIONS_MESSAGE` (SET_REGISTER 0x00 with `r1=0x09`: wireless notifications + software present) before the enumeration message. The receiver's register 0x00 is RAM-only and defaults to 0 at USB power-up, which blocks 0x41 device-connection notifications. Without enabling first, fresh-plugged receivers (notably on macOS) deliver no connection events. It reacts to the `TransportConnectedEvent(connection_type="receiver")` that `DeviceLink` emits whenever the receiver becomes present, so notifications are re-armed automatically after USB re-plug.
