"""Unit tests for topic/topic.py — pub/sub event bus."""

from __future__ import annotations

import threading
import time

from cleverswitch.event.event import Event
from cleverswitch.subscriber.subscriber import Subscriber
from cleverswitch.topic.topic import Topic


class _FakeSubscriber(Subscriber):
    def __init__(self):
        self.received = []
        self._event = threading.Event()

    def notify(self, event):
        self.received.append(event)
        self._event.set()

    def wait(self, timeout=1.0):
        self._event.wait(timeout)


class _FailingSubscriber(Subscriber):
    def __init__(self):
        self.call_count = 0
        self._event = threading.Event()

    def notify(self, event):
        self.call_count += 1
        self._event.set()
        raise RuntimeError("boom")

    def wait(self, timeout=1.0):
        self._event.wait(timeout)


def test_publish_delivers_event_to_subscriber():
    topic = Topic()
    sub = _FakeSubscriber()
    topic.subscribe(sub)
    event = Event(slot=1, pid=0xC548)
    topic.publish(event)
    sub.wait()
    assert len(sub.received) == 1
    assert sub.received[0] is event


def test_publish_delivers_to_multiple_subscribers():
    topic = Topic()
    sub1 = _FakeSubscriber()
    sub2 = _FakeSubscriber()
    topic.subscribe(sub1)
    topic.subscribe(sub2)
    event = Event(slot=1, pid=0xC548)
    topic.publish(event)
    sub1.wait()
    sub2.wait()
    assert len(sub1.received) == 1
    assert len(sub2.received) == 1


def test_subscriber_exception_does_not_crash_topic():
    topic = Topic()
    failing = _FailingSubscriber()
    good = _FakeSubscriber()
    topic.subscribe(failing)
    topic.subscribe(good)

    topic.publish(Event(slot=1, pid=0xC548))
    failing.wait()
    good.wait()

    # Failing subscriber still processed the event (then raised)
    assert failing.call_count == 1
    assert len(good.received) == 1

    # Topic still works after failure
    topic.publish(Event(slot=2, pid=0xC548))
    time.sleep(0.1)
    assert len(good.received) == 2


def test_no_subscribers_publish_does_not_raise():
    topic = Topic()
    topic.publish(Event(slot=1, pid=0xC548))  # must not raise
