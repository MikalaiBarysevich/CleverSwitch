import logging

from cleverswitch.log.safe_rotating_file_handler import ROLLOVER_RETRY_DELAY, SafeRotatingFileHandler


def _record(msg: str) -> logging.LogRecord:
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None)


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_rolls_over_when_size_exceeded(tmp_path):
    path = tmp_path / "cs.log"
    handler = SafeRotatingFileHandler(path, maxBytes=50, backupCount=2)
    for i in range(10):
        handler.handle(_record(f"message number {i:03d} " * 2))
    handler.close()
    assert (tmp_path / "cs.log.1").exists()
    assert (tmp_path / "cs.log.2").exists()
    assert not (tmp_path / "cs.log.3").exists()


def test_failed_rename_keeps_appending_and_warns_once(tmp_path, mocker, capsys):
    path = tmp_path / "cs.log"
    clock = _Clock()
    handler = SafeRotatingFileHandler(path, maxBytes=50, backupCount=2, clock=clock)
    real_rotate = handler.rotate
    failing = [True]

    def rotate_side_effect(source, dest):
        if failing[0]:
            raise PermissionError("locked")
        real_rotate(source, dest)

    rotate = mocker.patch.object(handler, "rotate", side_effect=rotate_side_effect)

    for i in range(5):
        handler.handle(_record(f"message number {i:03d} " * 2))

    assert rotate.call_count == 1
    assert capsys.readouterr().err.count("log rollover failed") == 1
    assert not (tmp_path / "cs.log.1").exists()
    assert "message number 004" in path.read_text()

    clock.now += ROLLOVER_RETRY_DELAY + 1
    handler.handle(_record("after delay " * 5))
    assert rotate.call_count == 2
    assert capsys.readouterr().err == ""
    assert "after delay" in path.read_text()

    failing[0] = False
    clock.now += ROLLOVER_RETRY_DELAY + 1
    handler.handle(_record("rotated " * 10))
    handler.close()
    assert (tmp_path / "cs.log.1").exists()
