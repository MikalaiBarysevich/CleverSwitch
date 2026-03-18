from threading import Thread


class EventListener(Thread):

    def listen(self, raw_event: bytes) -> None:
        ...
