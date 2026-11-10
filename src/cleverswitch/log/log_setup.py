import atexit
import logging
import os
import sys
import threading
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path
from queue import SimpleQueue
from typing import IO

from ..model.config.logging_config import LoggingConfig
from .instance_lock import try_lock
from .safe_rotating_file_handler import SafeRotatingFileHandler
from .startup_buffer import StartupBuffer

log = logging.getLogger(__name__)

_CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_CONSOLE_DATEFMT = "%H:%M:%S"
_FILE_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-8s [%(threadName)s] %(name)s: %(message)s"
_FILE_DATEFMT = "%Y-%m-%d %H:%M:%S"


class _State:
    def __init__(self):
        self.buffer: StartupBuffer | None = None
        self.console: logging.Handler | None = None
        self.queue_handler: QueueHandler | None = None
        self.listener: QueueListener | None = None
        self.file_handler: logging.Handler | None = None
        self.lock_handle: IO | None = None
        self.atexit_registered = False


_state = _State()
_lock = threading.RLock()


def bootstrap_logging(verbose: bool) -> None:
    with _lock:
        stop_logging()
        _remove_console()
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        _state.buffer = StartupBuffer()
        root.addHandler(_state.buffer)
        if _console_wanted():
            _add_console(logging.DEBUG if verbose else logging.INFO)
        logging.getLogger("hid").setLevel(logging.WARNING)
        sys.excepthook = _sys_excepthook
        threading.excepthook = _thread_excepthook
        if not _state.atexit_registered:
            atexit.register(stop_logging)
            _state.atexit_registered = True


def configure_logging(cfg: LoggingConfig, verbose: bool, file_allowed: bool = True) -> None:
    with _lock:
        level = logging.DEBUG if verbose else cfg.level
        root = logging.getLogger()
        file_handler = _open_file(cfg, level) if file_allowed and cfg.file_enabled else None

        console_added = False
        if _console_wanted() or file_handler is None:
            if _state.console is None:
                _add_console(level)
                console_added = True
            _state.console.setLevel(level)
        else:
            _remove_console()

        records = _detach_buffer()
        for record in records:
            if record.levelno < level:
                continue
            if file_handler is not None:
                file_handler.handle(record)
            if console_added:
                _state.console.handle(record)

        if file_handler is not None:
            q: SimpleQueue = SimpleQueue()
            _state.queue_handler = QueueHandler(q)
            _state.queue_handler.setLevel(level)
            _state.listener = QueueListener(q, file_handler, respect_handler_level=True)
            _state.listener.start()
            root.addHandler(_state.queue_handler)

        root.setLevel(level)
        if file_handler is not None:
            log.info(f"Logging to {cfg.file_path}")


def stop_logging() -> None:
    with _lock:
        root = logging.getLogger()
        if _state.queue_handler is not None:
            root.removeHandler(_state.queue_handler)
            _state.queue_handler = None
        if _state.listener is not None:
            _state.listener.stop()
            _state.listener = None
        if _state.file_handler is not None:
            _state.file_handler.close()
            _state.file_handler = None
        if _state.lock_handle is not None:
            _state.lock_handle.close()
            _state.lock_handle = None
        records = _detach_buffer()
        if records and _state.console is None:
            _dump_to_stderr(records)


def _open_file(cfg: LoggingConfig, level: int) -> logging.Handler | None:
    path: Path = cfg.file_path
    lock_handle = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_handle = try_lock(path.with_name(f"{path.name}.lock"))
        if lock_handle is None:
            log.warning(f"Another CleverSwitch instance is logging to {path}; logging to the console only")
            return None
        handler = SafeRotatingFileHandler(
            path, maxBytes=cfg.max_bytes, backupCount=cfg.backup_count, encoding="utf-8", delay=False
        )
    except OSError as e:
        if lock_handle is not None:
            lock_handle.close()
        log.warning(f"Cannot open log file {path}: {e}; logging to the console only")
        return None
    handler.setFormatter(logging.Formatter(_FILE_FORMAT, _FILE_DATEFMT))
    handler.setLevel(level)
    _state.file_handler = handler
    _state.lock_handle = lock_handle
    return handler


def _console_wanted() -> bool:
    return sys.stderr is not None and (sys.stderr.isatty() or bool(os.environ.get("JOURNAL_STREAM")))


def _make_console_handler() -> logging.Handler:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT, _CONSOLE_DATEFMT))
    return handler


def _add_console(level: int) -> None:
    _state.console = _make_console_handler()
    _state.console.setLevel(level)
    logging.getLogger().addHandler(_state.console)


def _remove_console() -> None:
    if _state.console is not None:
        logging.getLogger().removeHandler(_state.console)
        _state.console = None


def _detach_buffer() -> list[logging.LogRecord]:
    if _state.buffer is None:
        return []
    logging.getLogger().removeHandler(_state.buffer)
    records = _state.buffer.drain()
    _state.buffer = None
    return records


def _dump_to_stderr(records: list[logging.LogRecord]) -> None:
    if sys.stderr is None:
        return
    handler = _make_console_handler()
    for record in records:
        handler.handle(record)
    handler.flush()


def _sys_excepthook(exc_type, exc_value, exc_tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    log.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))


def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
    if issubclass(args.exc_type, SystemExit):
        return
    name = args.thread.name if args.thread is not None else "unknown"
    log.critical(f"Uncaught exception in thread {name}", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
