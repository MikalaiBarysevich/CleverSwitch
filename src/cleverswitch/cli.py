"""CLI entry point."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading

from . import __version__, platform_setup
from . import config as cfg_module
from .errors import CleverSwitchError, ConfigError
from .monitor import run


def main() -> None:
    args = _parse_args()

    # Load config first so we get log_level before anything else
    try:
        cfg = cfg_module.load(args.config)
    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    _setup_logging(cfg.settings.log_level, args.verbose)
    log = logging.getLogger(__name__)

    log.info("CleverSwitch %s starting", __version__)
    platform_setup.check()

    if args.dry_run:
        log.info("Dry-run mode: discovery only, no commands will be sent")
        _dry_run()
        return

    # Graceful shutdown on Ctrl-C / SIGTERM
    shutdown = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: shutdown.set())
    signal.signal(signal.SIGTERM, lambda *_: shutdown.set())

    try:
        run(cfg, shutdown)
    except CleverSwitchError as e:
        log.error("%s", e)
        sys.exit(1)

    log.info("CleverSwitch stopped")


def _dry_run() -> None:
    """Discover devices, print info, then exit without sending any commands."""
    import logging

    log = logging.getLogger(__name__)
    from .discovery import discover
    from .errors import CleverSwitchError

    try:
        setup = discover()
    except CleverSwitchError as e:
        log.error("Discovery failed: %s", e)
        import sys

        sys.exit(1)

    if setup is None:
        log.error("Discovery failed: devices not found")
        import sys

        sys.exit(1)

    for device in setup.devices:
        log.info(
            "%s: dev=0x%02X via %s",
            device.name,
            device.devnumber,
            device.transport.kind,
        )
    for device in setup.devices:
        device.transport.close()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="cleverswitch",
        description="Synchronize host switching between Logitech devices",
    )
    p.add_argument("-c", "--config", metavar="FILE", help="path to config YAML file")
    p.add_argument("-v", "--verbose", action="store_true", help="force DEBUG logging")
    p.add_argument("--dry-run", action="store_true", help="discover devices and print info, then exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p.parse_args()


def _setup_logging(level: str, verbose: bool) -> None:
    if verbose:
        level = "DEBUG"
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet down the hid library's own logger
    logging.getLogger("hid").setLevel(logging.WARNING)
