"""CLI entry point."""

from __future__ import annotations

import argparse
import logging
import sys
import threading

from .. import __version__
from ..cache.device_cache import DeviceCache
from ..config import config as cfg_module
from ..discovery.discovery import discover
from ..errors.errors import CleverSwitchError, ConfigError
from ..hidpp.transport import hidapi_version
from ..log.log_setup import bootstrap_logging, configure_logging
from ..model.config.logging_config import LoggingConfig
from ..setup.app_setup import setup_context
from ..util.util import get_system

_SYSTEM = get_system()


def main() -> None:
    args = _parse_args()

    verbose = args.verbose or args.verbose_extra
    bootstrap_logging(verbose)
    log = logging.getLogger(__name__)

    if args.clear_cache:
        try:
            config = cfg_module.load(args)
        except ConfigError as e:
            configure_logging(LoggingConfig(), verbose, file_allowed=False)
            log.error(f"{e}")
            sys.exit(1)
        configure_logging(config.logging, verbose, file_allowed=False)
        DeviceCache(config.cache_path).clear()
        return

    app_context = setup_context(args)

    failures: list[Exception] = []
    try:
        discovery_thread = threading.Thread(
            target=_run_discovery,
            args=(app_context, failures),
        )

        discovery_thread.start()
        discovery_thread.join()
    except CleverSwitchError as e:
        failures.append(e)
    if failures:
        if isinstance(failures[0], CleverSwitchError):
            log.error(f"{failures[0]}")
        sys.exit(1)

    log.info("CleverSwitch stopped")


def _run_discovery(app_context, failures: list[Exception]) -> None:
    try:
        discover(app_context)
    except CleverSwitchError as e:
        failures.append(e)
    except Exception as e:
        logging.getLogger(__name__).exception(f"Discovery crashed: {e}")
        failures.append(e)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="cleverswitch",
        description="Synchronize host switching between Logitech devices",
    )
    p.add_argument("-c", "--config", metavar="FILE", help="path to config YAML file")
    p.add_argument("-v", "--verbose", action="store_true", help="force DEBUG logging")
    p.add_argument("-vv", "--verbose-extra", action="store_true", help="force DEBUG logging including discovery")
    p.add_argument("--clear-cache", action="store_true", help="delete the discovered-device cache and exit")
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__} (hidapi {hidapi_version()}, {_SYSTEM})",
    )
    return p.parse_args()
