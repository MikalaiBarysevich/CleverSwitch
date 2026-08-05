"""Unit tests for topic/topic.py — pub/sub event bus."""

from __future__ import annotations

import queue
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


# ── unsubscribe ───────────────────────────────────────────────────────────────


class _GatedSubscriber(Subscriber):
    def __init__(self):
        self.received = []
        self.entered = threading.Event()
        self.release = threading.Event()

    def notify(self, event):
        self.entered.set()
        self.release.wait(timeout=1.0)
        self.received.append(event)


def _drain_thread_of(topic, subscriber):
    before = set(threading.enumerate())
    subscription = topic.subscribe(subscriber)
    new_threads = set(threading.enumerate()) - before
    assert len(new_threads) == 1
    return subscription, new_threads.pop()


def test_unsubscribe_stops_delivery():
    topic = Topic()
    sub = _FakeSubscriber()
    subscription = topic.subscribe(sub)

    topic.publish(Event(slot=1, pid=0xC548))
    sub.wait()

    topic.unsubscribe(subscription)
    topic.publish(Event(slot=2, pid=0xC548))
    time.sleep(0.1)

    assert len(sub.received) == 1


def test_unsubscribe_terminates_drain_thread():
    topic = Topic()
    sub = _FakeSubscriber()
    subscription, thread = _drain_thread_of(topic, sub)

    topic.unsubscribe(subscription)
    thread.join(timeout=1.0)

    assert not thread.is_alive()


def test_unsubscribe_delivers_events_already_queued():
    topic = Topic()
    sub = _GatedSubscriber()
    subscription, thread = _drain_thread_of(topic, sub)

    first = Event(slot=1, pid=0xC548)
    second = Event(slot=2, pid=0xC548)
    topic.publish(first)
    sub.entered.wait(timeout=1.0)
    topic.publish(second)
    topic.unsubscribe(subscription)
    sub.release.set()
    thread.join(timeout=1.0)

    assert not thread.is_alive()
    assert sub.received == [first, second]


def test_unsubscribe_twice_does_not_raise():
    topic = Topic()
    sub = _FakeSubscriber()
    subscription = topic.subscribe(sub)

    topic.unsubscribe(subscription)
    topic.unsubscribe(subscription)  # must not raise


def test_unsubscribe_unknown_handle_does_not_raise():
    topic = Topic()
    sub = _FakeSubscriber()
    topic.subscribe(sub)

    topic.unsubscribe(queue.Queue())  # must not raise

    topic.publish(Event(slot=1, pid=0xC548))
    sub.wait()
    assert len(sub.received) == 1


def test_unsubscribe_leaves_other_subscribers_unaffected():
    topic = Topic()
    leaving = _FakeSubscriber()
    staying = _FakeSubscriber()
    subscription = topic.subscribe(leaving)
    topic.subscribe(staying)

    topic.unsubscribe(subscription)
    topic.publish(Event(slot=1, pid=0xC548))
    staying.wait()
    time.sleep(0.1)

    assert len(staying.received) == 1
    assert leaving.received == []
