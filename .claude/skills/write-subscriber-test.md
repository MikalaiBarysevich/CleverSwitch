# Skill: Write Subscriber Test

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
        divert=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )
```

Use `MagicMock(spec=Topic)` — not bare `MagicMock()` — so that incorrect method names fail loudly.

## Standard assertions

```python
# Assert exactly one publish with a specific event type
topics.divert.publish.assert_called_once()
event = topics.divert.publish.call_args[0][0]
assert isinstance(event, DivertEvent)
assert event.slot == SLOT

# Assert nothing was published
topics.device_info.publish.assert_not_called()

# Reset between calls in the same test
topics.hid_event.publish.reset_mock()
```

## LogiDevice factory pattern

```python
def _make_device(*, slot=1, wpid=0x407B, pid=BOLT_PID, role="keyboard",
                 features=None, divertable_cids=None, pending_steps=None):
    device = LogiDevice(
        wpid=wpid, pid=pid, slot=slot, role=role,
        available_features=features or {FEATURE_REPROG_CONTROLS_V4: 8, FEATURE_CHANGE_HOST: 9},
        divertable_cids=divertable_cids if divertable_cids is not None else set(),
    )
    if pending_steps is not None:
        device.pending_steps = pending_steps
    return device
```

## Subscriber construction

Most subscribers take `(registry, topics)` and self-subscribe in `__init__`. Construct them last after registry and topics are set up:

```python
registry = LogiDeviceRegistry()
topics = _make_topics()
sub = MySubscriber(registry, topics)
```

For subscribers that start background threads (e.g. `DisconnectPollerSubscriber`), bypass `__init__` to avoid spawning real threads:

```python
with patch.object(MySubscriber, "__init__", lambda self, *a, **kw: None):
    sub = MySubscriber.__new__(MySubscriber)
    sub._device_registry = registry
    sub._topics = topics
    sub._some_state = {}
```

## Prefer pytest fixtures for shared setup, plain functions for simple cases

Use `@pytest.fixture` when registry/topics are shared across multiple tests in a class. Use plain `_make_*` helper functions when tests need independent instances.
