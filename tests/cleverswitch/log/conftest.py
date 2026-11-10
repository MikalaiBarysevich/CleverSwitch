import logging
import sys
import threading

import pytest

from cleverswitch.log import log_setup


@pytest.fixture(autouse=True)
def restore_logging(mocker):
    root = logging.getLogger()
    level = root.level
    handlers = list(root.handlers)
    excepthook = sys.excepthook
    thread_excepthook = threading.excepthook
    mocker.patch.object(log_setup, "atexit")
    yield
    log_setup.stop_logging()
    log_setup._remove_console()
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
    root.setLevel(level)
    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
