"""CLI entry point."""

from __future__ import annotations

import argparse
import logging
import platform
import sys
import threading

from .. import __version__
from ..discovery.discovery import discover
from ..errors.errors import CleverSwitchError
from ..setup.app_setup import setup_context

_SYSTEM = platform.system()


def main() -> None:
    args = _parse_args()

    _setup_logging(args.verbose or args.verbose_extra)
    log = logging.getLogger(__name__)

    app_context = setup_context(args)

    try:
        discovery_thread = threading.Thread(
            target=discover,
            args=(app_context,),
        )

        discovery_thread.start()
        discovery_thread.join()
    except CleverSwitchError as e:
        log.error(f"{e}")
        sys.exit(1)

    log.info("CleverSwitch stopped")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="cleverswitch",
        description="Synchronize host switching between Logitech devices",
    )
    p.add_argument("-c", "--config", metavar="FILE", help="path to config YAML file")
    p.add_argument("-v", "--verbose", action="store_true", help="force DEBUG logging")
    p.add_argument("-vv", "--verbose-extra", action="store_true", help="force DEBUG logging including discovery")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p.parse_args()


def _setup_logging(verbose: bool) -> None:
    if verbose:
        level = "DEBUG"
    else:
        level = "INFO"
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet down the hid library's own logger
    logging.getLogger("hid").setLevel(logging.WARNING)
