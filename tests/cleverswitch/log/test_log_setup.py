import logging
import logging.handlers
import re
import sys
import threading
from pathlib import Path

import pytest

from cleverswitch.log import log_setup
from cleverswitch.log.instance_lock import try_lock
from cleverswitch.log.log_setup import bootstrap_logging, configure_logging, stop_logging
from cleverswitch.model.config.logging_config import LoggingConfig

log = logging.getLogger("cleverswitch.test")


@pytest.fixture
def console_wanted(mocker):
    return mocker.patch.object(log_setup, "_console_wanted", return_value=False)


def _cfg(tmp_path: Path, **overrides) -> LoggingConfig:
    return LoggingConfig(file_path=tmp_path / "logs" / "cleverswitch.log", **overrides)


def _file_text(cfg: LoggingConfig) -> str:
    stop_logging()
    return cfg.file_path.read_text()


def test_pre_config_records_reach_the_file(tmp_path, console_wanted):
    bootstrap_logging(False)
    log.info("early record")
    cfg = _cfg(tmp_path)
    configure_logging(cfg, False)
    log.info("late record")

    text = _file_text(cfg)
    assert text.index("early record") < text.index("late record")
    assert f"Logging to {cfg.file_path}" in text


def test_config_error_logged_after_default_config_reaches_the_file(tmp_path, console_wanted):
    bootstrap_logging(False)
    cfg = _cfg(tmp_path)
    configure_logging(cfg, False)
    log.error("Config error in x.yaml")
    assert "ERROR    [MainThread] cleverswitch.test: Config error in x.yaml" in _file_text(cfg)


def test_records_from_other_threads_arrive_through_the_queue(tmp_path, console_wanted):
    bootstrap_logging(False)
    cfg = _cfg(tmp_path)
    configure_logging(cfg, False)
    worker = threading.Thread(target=lambda: log.info("from worker"), name="worker-1")
    worker.start()
    worker.join()

    line = next(ln for ln in _file_text(cfg).splitlines() if "from worker" in ln)
    assert re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3} INFO     \[worker-1\] cleverswitch\.test: ", line)


def test_file_handler_sits_behind_a_queue_handler(tmp_path, console_wanted):
    bootstrap_logging(False)
    configure_logging(_cfg(tmp_path), False)
    root_types = {type(h) for h in logging.getLogger().handlers}
    assert logging.handlers.QueueHandler in root_types
    assert log_setup.SafeRotatingFileHandler not in root_types


def test_disabled_file_creates_no_file_and_logs_to_console(tmp_path, console_wanted, capsys):
    bootstrap_logging(False)
    log.info("early record")
    cfg = _cfg(tmp_path, file_enabled=False)
    configure_logging(cfg, False)
    log.info("late record")

    assert not cfg.file_path.parent.exists()
    err = capsys.readouterr().err
    assert "early record" in err
    assert "late record" in err


def test_file_not_allowed_creates_no_file(tmp_path, console_wanted):
    bootstrap_logging(False)
    cfg = _cfg(tmp_path)
    configure_logging(cfg, False, file_allowed=False)
    assert not cfg.file_path.parent.exists()
    assert log_setup._state.console is not None


def test_unopenable_file_falls_back_to_console(tmp_path, console_wanted, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("")
    cfg = LoggingConfig(file_path=blocker / "cleverswitch.log")

    bootstrap_logging(False)
    configure_logging(cfg, False)
    log.info("still logging")

    err = capsys.readouterr().err
    assert "Cannot open log file" in err
    assert "still logging" in err


def test_open_failure_after_lock_releases_the_lock(tmp_path, console_wanted, mocker):
    mocker.patch.object(log_setup, "SafeRotatingFileHandler", side_effect=PermissionError("denied"))
    cfg = _cfg(tmp_path)
    bootstrap_logging(False)
    configure_logging(cfg, False)

    lock = try_lock(cfg.file_path.with_name("cleverswitch.log.lock"))
    assert lock is not None
    lock.close()


def test_lock_held_by_another_instance_logs_to_console_only(tmp_path, console_wanted, capsys):
    cfg = _cfg(tmp_path)
    cfg.file_path.parent.mkdir(parents=True)
    other = try_lock(cfg.file_path.with_name("cleverswitch.log.lock"))
    try:
        bootstrap_logging(False)
        configure_logging(cfg, False)
        log.info("console only")
    finally:
        other.close()

    err = capsys.readouterr().err
    assert "Another CleverSwitch instance" in err
    assert "console only" in err
    assert not cfg.file_path.exists()


def test_console_off_when_file_open_and_not_interactive(tmp_path, console_wanted, capsys):
    bootstrap_logging(False)
    configure_logging(_cfg(tmp_path), False)
    log.info("file only")
    assert log_setup._state.console is None
    assert "file only" not in capsys.readouterr().err


def test_console_on_alongside_file_when_interactive(tmp_path, console_wanted, capsys):
    console_wanted.return_value = True
    bootstrap_logging(False)
    log.info("early record")
    cfg = _cfg(tmp_path)
    configure_logging(cfg, False)

    assert capsys.readouterr().err.count("early record") == 1
    assert "early record" in _file_text(cfg)


def test_console_attached_at_bootstrap_is_removed_when_no_longer_wanted(tmp_path, console_wanted):
    console_wanted.return_value = True
    bootstrap_logging(False)
    console_wanted.return_value = False
    configure_logging(_cfg(tmp_path), False)
    assert log_setup._state.console is None


@pytest.mark.parametrize(
    ("isatty", "journal", "expected"),
    [(True, None, True), (False, "8:123", True), (False, None, False)],
)
def test_console_wanted_rule(mocker, monkeypatch, isatty, journal, expected):
    stderr = mocker.MagicMock()
    stderr.isatty.return_value = isatty
    monkeypatch.setattr(sys, "stderr", stderr)
    if journal is None:
        monkeypatch.delenv("JOURNAL_STREAM", raising=False)
    else:
        monkeypatch.setenv("JOURNAL_STREAM", journal)
    assert log_setup._console_wanted() is expected


def test_console_not_wanted_without_stderr(monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)
    assert log_setup._console_wanted() is False


def test_verbose_overrides_configured_level(tmp_path, console_wanted):
    bootstrap_logging(True)
    cfg = _cfg(tmp_path, level=logging.WARNING)
    configure_logging(cfg, True)
    log.debug("debug detail")
    assert "debug detail" in _file_text(cfg)


def test_configured_level_filters_live_and_buffered_records(tmp_path, console_wanted):
    bootstrap_logging(False)
    log.info("buffered info")
    log.warning("buffered warning")
    cfg = _cfg(tmp_path, level=logging.WARNING)
    configure_logging(cfg, False)
    log.info("live info")
    log.warning("live warning")

    text = _file_text(cfg)
    assert "buffered info" not in text
    assert "live info" not in text
    assert "buffered warning" in text
    assert "live warning" in text


def test_bootstrap_console_level_follows_verbose(console_wanted):
    console_wanted.return_value = True
    bootstrap_logging(True)
    assert log_setup._state.console.level == logging.DEBUG
    bootstrap_logging(False)
    assert log_setup._state.console.level == logging.INFO
    assert logging.getLogger("hid").level == logging.WARNING


def test_stop_logging_is_idempotent(tmp_path, console_wanted):
    bootstrap_logging(False)
    configure_logging(_cfg(tmp_path), False)
    stop_logging()
    stop_logging()
    assert log_setup._state.listener is None


def test_stop_without_configure_dumps_buffer_to_stderr(console_wanted, capsys):
    bootstrap_logging(False)
    log.error("crashed before config")
    stop_logging()
    assert "crashed before config" in capsys.readouterr().err


def test_stop_without_configure_and_without_stderr_is_silent(console_wanted, monkeypatch):
    bootstrap_logging(False)
    log.error("lost")
    monkeypatch.setattr(sys, "stderr", None)
    stop_logging()


def test_bootstrap_registers_atexit_once(console_wanted):
    log_setup._state.atexit_registered = False
    bootstrap_logging(False)
    bootstrap_logging(False)
    log_setup.atexit.register.assert_called_once_with(stop_logging)


def test_sys_excepthook_logs_critical_with_traceback(console_wanted, caplog):
    bootstrap_logging(False)
    try:
        raise ValueError("boom")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    record = next(r for r in caplog.records if r.levelno == logging.CRITICAL)
    assert record.exc_info[0] is ValueError


def test_sys_excepthook_passes_keyboard_interrupt_to_default(console_wanted, mocker, caplog):
    default = mocker.patch.object(sys, "__excepthook__")
    bootstrap_logging(False)
    sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    default.assert_called_once()
    assert not [r for r in caplog.records if r.levelno == logging.CRITICAL]


def test_thread_excepthook_logs_critical_with_thread_name(console_wanted, caplog):
    bootstrap_logging(False)
    worker = threading.Thread(target=lambda: 1 / 0, name="doomed")
    worker.start()
    worker.join()
    record = next(r for r in caplog.records if r.levelno == logging.CRITICAL)
    assert "doomed" in record.getMessage()
    assert record.exc_info[0] is ZeroDivisionError


def test_thread_excepthook_ignores_system_exit(console_wanted, caplog):
    bootstrap_logging(False)
    worker = threading.Thread(target=sys.exit)
    worker.start()
    worker.join()
    assert not [r for r in caplog.records if r.levelno == logging.CRITICAL]


def test_thread_excepthook_without_thread_object(console_wanted, caplog):
    bootstrap_logging(False)
    args = threading.ExceptHookArgs([RuntimeError, RuntimeError("x"), None, None])
    threading.excepthook(args)
    assert "unknown" in caplog.text
