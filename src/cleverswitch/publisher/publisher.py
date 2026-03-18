from ..event.event import Event
from ..subscriber.subscriber import Subscriber


class Publisher:
    def publish(self, event: Event) -> None:
        ...

    def subscribe(self, subscriber: Subscriber) -> None:
        ...