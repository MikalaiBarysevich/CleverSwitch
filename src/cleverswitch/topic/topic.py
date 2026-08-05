import logging
import queue
import threading
from threading import Thread

from ..event.event import Event
from ..subscriber.subscriber import Subscriber

log = logging.getLogger(__name__)

_UNSUBSCRIBE = object()


class Topic:
    def __init__(self):
        self._subscriber_queues: list[queue.Queue] = []
        self._lock = threading.Lock()

    def publish(self, event: Event) -> None:
        with self._lock:
            subscriptions = list(self._subscriber_queues)
        for q in subscriptions:
            q.put(event)

    def subscribe(self, subscriber: Subscriber) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subscriber_queues.append(q)
        Thread(target=self._notify, args=(subscriber, q), daemon=True).start()
        return q

    def unsubscribe(self, subscription: queue.Queue) -> None:
        with self._lock:
            removed = subscription in self._subscriber_queues
            if removed:
                self._subscriber_queues.remove(subscription)
        if removed:
            subscription.put(_UNSUBSCRIBE)

    def _notify(self, subscriber: Subscriber, q: queue.Queue) -> None:
        while True:
            event = q.get()
            if event is _UNSUBSCRIBE:
                break
            try:
                subscriber.notify(event)
            except Exception:
                log.exception(f"Subscriber {subscriber} failed to handle event {event}")
