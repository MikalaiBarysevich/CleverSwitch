import logging

from cleverswitch.log.startup_buffer import StartupBuffer


def _record(msg: str) -> logging.LogRecord:
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None)


def test_buffer_keeps_only_the_newest_records_up_to_capacity():
    buffer = StartupBuffer(capacity=3)
    for i in range(5):
        buffer.handle(_record(f"m{i}"))
    assert [r.getMessage() for r in buffer.drain()] == ["m2", "m3", "m4"]


def test_default_capacity_is_bounded():
    buffer = StartupBuffer()
    for i in range(1500):
        buffer.handle(_record(f"m{i}"))
    assert len(buffer.drain()) == 1000


def test_drain_empties_the_buffer():
    buffer = StartupBuffer()
    buffer.handle(_record("x"))
    buffer.drain()
    assert buffer.drain() == []
