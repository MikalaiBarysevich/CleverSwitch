import collections
import logging

_MAX_RECORDS = 1000


class StartupBuffer(logging.Handler):
    def __init__(self, capacity: int = _MAX_RECORDS):
        super().__init__(logging.NOTSET)
        self._records: collections.deque[logging.LogRecord] = collections.deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        self._records.append(record)

    def drain(self) -> list[logging.LogRecord]:
        self.acquire()
        try:
            records = list(self._records)
            self._records.clear()
        finally:
            self.release()
        return records
