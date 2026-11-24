# Pub-sub event system

The core of the architecture is a typed pub-sub system with one daemon thread per subscriber.

**`Topics`** (`topic/topics.py`) is a typed dataclass with seven channels:
- `hid_event` — all inbound HID++ events (DeviceConnectedEvent, HidppResponseEvent, HidppNotificationEvent, HidppErrorEvent, TransportDisconnectedEvent, etc.)
- `write` — outbound HID messages (WriteEvent)
- `device_info` — triggers device setup (DeviceInfoRequestEvent)
- `flags` — apply/re-apply key reporting flags (SetReportFlagEvent); `SetReportFlagSubscriber` selects analytics mode (byte 9) or divert mode (byte 6) based on `device.supported_flags`
- `info_progress` — task completion feedback (InfoTaskProgressEvent)
- `hotplug` — OS device notifications (HidNodeAddedEvent, HidNodeRemovedEvent, HotplugResyncEvent); only LinkManager subscribes. Defaults to a fresh `Topic`, so tests that build `Topics` field by field need not pass it
- `edge` — `EdgeTouchedEvent` from the edge-switch backend; only `EdgeSwitchSubscriber` subscribes. Defaults to a fresh `Topic`, like `hotplug`

**`Topic`** (`topic/topic.py`) — each `subscribe(subscriber)` call creates a private `queue.Queue` and a daemon thread that drains it by calling `subscriber.notify(event)`, and returns that queue as a handle. `publish(event)` enqueues on all subscriber queues simultaneously. `unsubscribe(subscription)` takes the handle back, removes the queue, and stops its drain thread via an internal sentinel — short-lived subscribers (`InfoTask`) must call it or they leak a thread and a queue for the life of the process.

**Subscribers** implement `notify(event) -> None` and filter by event type internally. All subscribers call `topics.<channel>.subscribe(self)` in `__init__`.
