---
name: write-subscriber-test
description: Pattern for writing or extending unit tests for a CleverSwitch Subscriber subclass. Use when adding a subscriber, touching subscriber tests, or when a test needs Topics mocks, a LogiDevice factory, or publish assertions.
---

# Write a Subscriber Test

Use this pattern when writing tests for any `Subscriber` subclass in CleverSwitch.

## Standard fixture setup

```python
from unittest.mock import MagicMock

from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )
```

`Topics` has two extra channels, `hotplug` and `edge`, that default to a fresh `Topic`; pass them explicitly only when the subscriber under test uses them.

Use `MagicMock(spec=Topic)` — not bare `MagicMock()` — so that incorrect method names fail loudly. All HID I/O is mocked; a test must never open a real device.

## Standard assertions

```python
# Assert exactly one publish with a specific event type
topics.flags.publish.assert_called_once()
event = topics.flags.publish.call_args[0][0]
assert isinstance(event, SetReportFlagEvent)
assert event.wpid == WPID

# Assert nothing was published
topics.write.publish.assert_not_called()

# Reset between calls in the same test
topics.hid_event.publish.reset_mock()
```

## LogiDevice factory

`LogiDevice` requires four fields; the rest have defaults:

```python
from cleverswitch.model.logi_device import ROLE_KEYBOARD, LogiDevice


def _make_device(*, wpid=0x407B, pid=BOLT_PID, slot=1, role=ROLE_KEYBOARD, features=None, supported_flags=None):
    device = LogiDevice(
        wpid=wpid,
        pid=pid,
        slot=slot,
        role=role,
        available_features=features or {FEATURE_REPROG_CONTROLS_V4: 8, FEATURE_CHANGE_HOST: 9},
    )
    if supported_flags is not None:
        device.supported_flags = set(supported_flags)
    return device
```

Set `pending_steps`, `supported_flags` or `connected` after construction rather than reconstructing the whole device. Do not assert on `name`; label devices with `display_name` in code under test.

## Subscriber construction

Most subscribers take `(registry, topics)` and self-subscribe in `__init__`. Construct them after the registry and topics exist:

```python
registry = LogiDeviceRegistry()
topics = _make_topics()
sub = SetReportFlagSubscriber(registry, topics)
registry.register(WPID, device)
```

If `__init__` starts a real thread (a task, a poller, a backend), bypass it and set only the attributes the test needs:

```python
with patch.object(MySubscriber, "__init__", lambda self, *a, **kw: None):
    sub = MySubscriber.__new__(MySubscriber)
    sub._device_registry = registry
    sub._topics = topics
```

Close the thread loop with the shutdown event instead when the code under test checks it.

## Events

Build real event dataclasses rather than mocks — subscribers filter on `isinstance`, so a mock silently never matches:

```python
sub.notify(SetReportFlagEvent(slot=1, pid=PID, wpid=WPID))
sub.notify("not an event")  # must not raise
```

## InfoTask tests

`InfoTask` owns a private response queue that `_send_request` drains before every request, so a pre-loaded reply is always dropped. Deliver replies on publish instead:

```python
from tests.task_helpers import deliver_on_request

deliver_on_request(task, topics, [response_event_1, response_event_2])
```

## Fixtures vs helpers

Use `@pytest.fixture` when registry and topics are shared across tests in a class. Use plain `_make_*` functions when each test needs an independent instance.
