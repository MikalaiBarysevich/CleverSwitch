import logging
import queue
from threading import Thread

from ..event.event import Event
from ..subscriber.subscriber import Subscriber

log = logging.getLogger(__name__)


class Topic:
    def __init__(self):
        self._subscriber_queues: list[queue.Queue] = []

    def publish(self, event: Event) -> None:
        for q in self._subscriber_queues:
            q.put(event)

    def subscribe(self, subscriber: Subscriber) -> None:
        q: queue.Queue = queue.Queue()
        self._subscriber_queues.append(q)
        Thread(target=self._notify, args=(subscriber, q), daemon=True).start()

    def _notify(self, subscriber: Subscriber, q: queue.Queue) -> None:
        while True:
            event = q.get()
            try:
                subscriber.notify(event)
            except Exception:
                log.exception("Subscriber %s failed to handle event %s", subscriber, event)
