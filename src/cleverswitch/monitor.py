"""Main event loop.

Reads HID++ notifications from the keyboard's transport and dispatches:
  - CHANGE_HOST events  → relay to mouse via switcher
  - Device status events → fire connect/disconnect hooks

Handles receiver reconnection transparently.
"""

from __future__ import annotations

import logging
import threading
import time

from . import hooks as hook_runner
from .config import Config
from .discovery import Setup, discover, DeviceContext
from .errors import DeviceNotFound, FeatureNotSupported, ReceiverNotFound, TransportError
from .hidpp.constants import HOST_SWITCH_KEYS_CIDS, HOST_SWITCH_CIDS
from .hidpp.protocol import (
    DeviceStatusEvent, HostChangeEvent,
    parse_message, send_change_host, set_cid_divert,
)

log = logging.getLogger(__name__)


def run(cfg: Config, shutdown: threading.Event) -> None:
    """Main loop. Blocks until *shutdown* is set.

    Reconnects automatically on transport errors or when devices are not found.
    """

    attempt = 0
    while not shutdown.is_set():
        attempt += 1
        try:
            setup = discover(cfg)
        except (DeviceNotFound, FeatureNotSupported, ReceiverNotFound) as e:
            _log_retry(e, cfg.settings.retry_interval_s)
            shutdown.wait(cfg.settings.retry_interval_s)
            if 0 < cfg.settings.max_retries <= attempt:
                log.error("Max retries (%d) exceeded. Giving up.", cfg.settings.max_retries)
                return
            continue

        _fire_startup_hooks(setup, cfg)

        try:
            _monitor_loop(setup, cfg, shutdown)
        except TransportError as e:
            log.warning("Transport error: %s — reconnecting in %ds…", e, cfg.settings.retry_interval_s)
            _close_setup(setup)
            shutdown.wait(cfg.settings.retry_interval_s)
        finally:
            _close_setup(setup)


# ── Inner event loop ──────────────────────────────────────────────────────────

def _monitor_loop(setup: Setup, cfg: Config, shutdown: threading.Event) -> None:
    """Block-read from the keyboard's transport until shutdown or transport error."""
    kbd = setup.keyboard
    mouse = setup.mouse

    log.info("Monitoring — waiting for Easy-Switch press on %s…", kbd.name)

    while not shutdown.is_set():
        time.sleep(0.015)
        raw = kbd.transport.read(timeout_ms=cfg.settings.read_timeout_ms)
        _divert_all_es_keys(kbd)
        if not raw:
            continue  # timeout, loop back to check shutdown

        event = parse_message(raw)
        log.debug("parsed event: %s", event)

        if event is None:
            continue

        if isinstance(event, HostChangeEvent) and event.devnumber == kbd.devnumber:
            # target_host = event.target_host
            # prev_host = current_host["keyboard"]
            # current_host["keyboard"] = target_host
            # log.info(
            #     "%s switched to host %d (DJ host-change)",
            #     kbd.name, target_host + 1,
            # )
            # send_change_host(
            #     mouse.transport, mouse.devnumber,
            #     mouse.change_host_feat_idx, target_host,
            #     long=mouse.long_msg,
            # )
            # current_host["mouse"] = target_host
            # hook_runner.fire_switch(cfg.hooks, kbd.name, "keyboard", target_host, prev_host)
            # hook_runner.fire_switch(cfg.hooks, mouse.name, "mouse", target_host, prev_host)
            continue

        # ── Device connect / disconnect ───────────────────────────────────────
        if isinstance(event, DeviceStatusEvent):
            role = _role_for_devnumber(event.devnumber, setup)
            if role is None:
                continue

            ctx = kbd if role == "keyboard" else mouse
            if event.connected:
                log.info("%s connected", ctx.name)
                hook_runner.fire_connect(cfg.hooks, ctx.name, role)
            else:
                log.info("%s disconnected", ctx.name)
                hook_runner.fire_disconnect(cfg.hooks, ctx.name, role)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _role_for_devnumber(devnumber: int, setup: Setup) -> str | None:
    if devnumber == setup.keyboard.devnumber:
        return "keyboard"
    if devnumber == setup.mouse.devnumber:
        return "mouse"
    return None


def _fire_startup_hooks(setup: Setup, cfg: Config) -> None:
    for ctx in (setup.keyboard, setup.mouse):
        hook_runner.fire_connect(cfg.hooks, ctx.name, ctx.role)


def _close_setup(setup: Setup) -> None:
    for ctx in (setup.keyboard, setup.mouse):
        if ctx.reprog_feat_idx is not None and ctx.diverted_cids:
            for cid in ctx.diverted_cids:
                try:
                    set_cid_divert(
                        ctx.transport, ctx.devnumber, ctx.reprog_feat_idx,
                        cid, False, long=ctx.long_msg,
                    )
                    log.debug("Undiverted CID 0x%04X on %s", cid, ctx.name)
                except Exception as e:
                    log.debug("Failed to undivert CID 0x%04X on %s: %s", cid, ctx.name, e)
    for transport in setup.unique_transports():
        transport.close()


def _log_retry(error: Exception, interval: int) -> None:
    log.warning("%s — retrying in %ds…", error, interval)

def _divert_all_es_keys(kbd: DeviceContext) -> None:
    for cid in HOST_SWITCH_CIDS.keys():
        set_cid_divert(kbd.transport, kbd.devnumber, kbd.divert_feat_idx, cid, True, True)
