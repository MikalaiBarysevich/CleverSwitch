import logging
import threading
import time

from ..event.device_connected_event import DeviceConnectedEvent
from ..event.host_change_event import HostChangeEvent
from ..model.config.easy_switch_config import EasySwitchConfig
from ..model.logi_device import LogiDevice
from ..monitor.input_activity_monitor import InputActivityMonitor
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)

# How long an externally-announced switch keeps the fallback suppressed. Covers the normal
# ordering, where the announcement is observed before the departing device's disconnect.
#
# Sized against the same physical interval measured from the other side: how long a device takes
# to actually drop its link after being told to switch. On MX Keys S + MX Ergo S through a Bolt
# receiver (n=37) that is p50 0.71s, p90 1.02s, p95 1.17s, max 1.87s. That measurement is an
# upper bound on the interval this window actually has to cover — it also includes the outbound
# write and the time the device spends processing an inbound command, neither of which exists on
# the announcement path, where the device only reports a switch it has already decided to make.
ANNOUNCED_SWITCH_WINDOW_S = 1.0

# How long the relay waits before publishing. Serves two purposes:
#
# 1. Debounce against RF micro-dropouts. A brief link loss during active use is reported as the
#    same bare 0x41 disconnect as a genuine Easy-Switch departure, and misfires the relay —
#    observed heavily on MX Keys S + MX Ergo S through a Bolt receiver while one device streams
#    continuously (e.g. selecting text with a key held down). Journal data over 3.5 days of real
#    use: the dropped device reconnects within p50 1.03s / p90 1.68s / max <2s (n=70). A device
#    that genuinely switched away never reconnects on its own, so waiting out the window costs
#    only latency on the follow, never correctness. If the device reconnects inside the window,
#    the pending relay is cancelled (generation check in _relay).
#
# 2. Letting a slightly-late x1814 announcement land first — the original reason the publish is
#    deferred at all (0.25s was enough for that alone). See the class docstring for why this
#    cannot be a plain sleep.
RECONNECT_DEBOUNCE_S = 2.0

# Activity gating, applied only when an InputActivityMonitor is injected. A genuine
# Easy-Switch departure happens in one of exactly two shapes: the user was just working at
# this machine (input on the departing device moments before the press — the ES key itself is
# consumed by firmware and never reported), or the user walked up after a break, woke the
# already-slept device and pressed ES immediately (link comes up, then drops right away). An
# idle power-save link drop matches neither: the link had been up for a long time and the
# device had been silent — observed on MX Keys S as 0x41 link-down after inactivity with no
# reconnect for 13-41s, far beyond any debounce that wouldn't also swallow real switches.
#
# ACTIVITY_WINDOW_S bounds "moments before": how far back input on the departing device still
# counts as the user being at this machine. Sized generously — reading a page before
# switching is normal; the cost of too-large is only that a power-save drop within the window
# still relays (today's behaviour), while too-small suppresses genuine switches.
ACTIVITY_WINDOW_S = 30.0

# FRESH_LINK_S bounds the wake→switch shape: how long after a reconnect a drop still looks
# like "woke it just to switch away" rather than an established session going idle.
FRESH_LINK_S = 5.0


class PeerHostFollowSubscriber(Subscriber):
    """Fallback Easy-Switch relay for pairings where feature 0x1814 never announces a switch.

    ChangeHostNotificationSubscriber (the #105 fix) relies on the device emitting an unsolicited
    x1814 fn=0 notification on the departing host, carrying the target host. That notification
    does not fire at all for some MX Keys S + Bolt-receiver pairings (confirmed via raw HID
    capture on both Linux and macOS: the departing host receives nothing but the bare
    connection-lost report, no target-host information whatsoever) — so that mechanism has
    nothing to react to here.

    This subscriber is a pragmatic two-host fallback: `easy_switch.peer_host_index` is a fixed,
    user-configured index representing "the other machine", keyed by device role (see
    config.example.yaml for how to learn each value). Each device has its own independent host
    pairing table, so the keyboard's and the mouse's index for "the same other machine" are not
    guaranteed to match — this is why the lookup is per-role, not one shared index for both
    devices. There is no way to tell a genuine Easy-Switch press apart from an ordinary RF
    dropout on the wire — any disconnect of either device while its paired counterpart is still
    locally connected is treated as "it switched away", and the counterpart is commanded to
    follow, using *its own* role's configured index. Unlike Logitech's own Enhanced Easy-Switch
    (keyboard-only — pressing the mouse's Easy-Switch key does not normally drive the keyboard),
    this fallback is intentionally symmetric in both directions: either device leaving brings the
    other along. Devices are paired by shared `pid` (same receiver) and differing `role`;
    Bluetooth-direct devices don't share a pid with anything and are never matched.

    Only reacts to a disconnect that follows a locally-observed connect in this process's own
    lifetime (tracked in `_seen_connected`, keyed by wpid — mirrors EventHookSubscriber's
    `_last_state` dedup pattern). Without this guard, the gateway's very first enumeration on
    daemon startup reports every device that happens to be paired elsewhere right now as
    "disconnected" — indistinguishable, on the wire, from a genuine departure — which would
    otherwise fire the relay and yank a device that never actually moved.

    Suppressed by any HostChangeEvent it did not publish itself, for ANNOUNCED_SWITCH_WINDOW_S.
    Without that, a device whose announcement *does* work would be commanded twice per press:
    once to the announced target, then again to the configured peer index once the disconnect
    lands — and on a three-host setup the second command overrides the correct one and sends the
    peer to the wrong machine. Suppression is deliberately not keyed per device, because the
    announcement and the disconnect that must be ignored can come from *different* devices: the
    departing device announces the switch, HostChangeSubscriber commands its counterpart to
    follow, and then the counterpart's own disconnect must not trigger a second relay.

    The publish is deferred by RECONNECT_DEBOUNCE_S on a timer thread rather than sent inline,
    for two reasons. First, debounce: an RF micro-dropout is indistinguishable on the wire from a
    genuine departure, but the dropped device reconnects within ~2s (measured; see the constant),
    while a genuinely-departed device never does — so a reconnect observed inside the window
    cancels the pending relay (via a per-wpid generation counter bumped on every reconnect).
    Second, ordering: the CID path emits HostChangeEvent straight from the parser, so FIFO
    ordering on the shared hid_event queue guarantees it is seen before the disconnect. The x1814
    path does not: the parser emits a generic HidppNotificationEvent, and
    ChangeHostNotificationSubscriber translates it on *its own* thread, so its HostChangeEvent
    can lose the race to the disconnect. Losing that race is not self-correcting — the relay
    would command the peer to the wrong host, the peer would tear down its link, and the correct
    command arriving afterwards would never reach it. The delay cannot be a plain sleep in
    notify(): the announcement arrives on this subscriber's own queue, which its drain thread
    would then not be draining.

    Because the relay fires long after the disconnect, the suppression check is anchored to the
    disconnect timestamp, not to the moment the timer fires: an announcement suppresses the relay
    if it landed no earlier than ANNOUNCED_SWITCH_WINDOW_S before the disconnect (any
    announcement arriving later, during the debounce window itself, suppresses too).

    When an InputActivityMonitor is injected, disconnects are additionally activity-gated (see
    _looks_like_genuine_departure and the constants above): an idle power-save link drop — the
    departing device silent for longer than ACTIVITY_WINDOW_S on a link older than FRESH_LINK_S —
    is not treated as a departure at all. This covers the dropout class the reconnect debounce
    cannot: a slept device reconnects only when the user touches it again, which after a genuine
    misfire is tens of seconds to minutes away. The gate fails open whenever activity data is
    missing.

    A receiver unplug also fires this relay. TransportDisconnectionSubscriber fans out one
    disconnect per registered device, and because that fan-out runs on its own thread, the peer's
    `connected` flag may still be True when the first device's disconnect is handled. The
    resulting write is dropped by the gateway (the transport is gone), so there is no wire-level
    effect, but the relay's INFO line is logged and SWITCH hooks do fire — worth knowing if a
    hook performs real work.
    """

    def __init__(
        self,
        device_registry: LogiDeviceRegistry,
        topics: Topics,
        easy_switch_config: EasySwitchConfig,
        relay_delay_s: float = RECONNECT_DEBOUNCE_S,
        activity_monitor: InputActivityMonitor | None = None,
    ):
        self._device_registry = device_registry
        self._topics = topics
        self._peer_host_index_by_role = easy_switch_config.peer_host_index
        self._relay_delay_s = relay_delay_s
        self._activity_monitor = activity_monitor
        self._seen_connected: dict[int, bool] = {}
        self._lock = threading.Lock()
        self._announced_at: float | None = None
        self._relayed_event: HostChangeEvent | None = None
        # Bumped on every reconnect; a pending relay snapshots the value at disconnect time and
        # aborts if it changed — that reconnect proves the disconnect was a dropout, not a switch.
        self._reconnect_generation: dict[int, int] = {}
        # Monotonic timestamp of the last locally-observed connect per wpid, for the
        # fresh-link (wake→switch) branch of the activity gate.
        self._connected_at: dict[int, float] = {}
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, HostChangeEvent):
            self._note_announced_switch(event)
            return

        if not isinstance(event, DeviceConnectedEvent):
            return

        was_connected = self._seen_connected.get(event.wpid, False)
        self._seen_connected[event.wpid] = event.link_established

        if event.link_established:
            with self._lock:
                self._reconnect_generation[event.wpid] = self._reconnect_generation.get(event.wpid, 0) + 1
            self._connected_at[event.wpid] = time.monotonic()
            return

        if not was_connected:
            return

        departed = self._device_registry.get_by_wpid(event.wpid)
        if departed is None or departed.role is None:
            return

        peer = self._find_peer(departed)
        if peer is None or not peer.connected or peer.role is None:
            return

        peer_host_index = self._peer_host_index_by_role.get(peer.role)
        if peer_host_index is None:
            return

        if not self._looks_like_genuine_departure(departed, departed.role):
            return

        with self._lock:
            generation = self._reconnect_generation.get(event.wpid, 0)
        timer = threading.Timer(
            self._relay_delay_s,
            self._relay,
            args=(departed, peer, peer_host_index, time.monotonic(), generation),
        )
        timer.daemon = True
        timer.start()

    def _looks_like_genuine_departure(self, departed: LogiDevice, role: str) -> bool:
        """Activity gate: distinguish a user-driven switch from an idle power-save link drop.

        Fail-open by design: without a monitor, or without any data for this role yet (fresh
        daemon start, or a platform where the input collection cannot be opened — Windows
        denies keyboard/mouse top-level collections), behave exactly as before gating existed.
        A wrong suppression silently breaks real switches; a wrong relay is today's status quo.
        """
        if self._activity_monitor is None:
            return True

        now = time.monotonic()

        connected_at = self._connected_at.get(departed.wpid)
        if connected_at is not None and now - connected_at <= FRESH_LINK_S:
            return True

        last_input = self._activity_monitor.last_activity(departed.pid, role)
        if last_input is None:
            return True
        idle_s = now - last_input
        if idle_s <= ACTIVITY_WINDOW_S:
            return True

        log.info(
            f"'{departed.display_name}' link dropped after {idle_s:.0f}s without input — "
            f"treating as idle power-save, not following"
        )
        return False

    def _note_announced_switch(self, event: HostChangeEvent) -> None:
        with self._lock:
            if event is self._relayed_event:
                return
            self._announced_at = time.monotonic()

    def _relay(
        self,
        departed: LogiDevice,
        peer: LogiDevice,
        peer_host_index: int,
        disconnected_at: float,
        generation: int,
    ) -> None:
        with self._lock:
            if self._reconnect_generation.get(departed.wpid, 0) != generation:
                log.debug(
                    f"'{departed.display_name}' reconnected within the debounce window — "
                    f"treating the disconnect as an RF dropout, not following"
                )
                return
            if self._announced_at is not None and self._announced_at >= disconnected_at - ANNOUNCED_SWITCH_WINDOW_S:
                log.debug(
                    f"'{departed.display_name}' left this host, but a host switch was already "
                    f"announced — not following '{peer.display_name}'"
                )
                return
            if not peer.connected:
                log.debug(f"'{peer.display_name}' left too — nothing to follow")
                return
            relayed = HostChangeEvent(slot=departed.slot, pid=departed.pid, target_host=peer_host_index)
            self._relayed_event = relayed

        log.info(
            f"'{departed.display_name}' left this host — following '{peer.display_name}' to host {peer_host_index + 1}"
        )
        self._topics.hid_event.publish(relayed)

    def _find_peer(self, device: LogiDevice) -> LogiDevice | None:
        for entry in self._device_registry.all_entries():
            if entry.pid == device.pid and entry.role is not None and entry.role != device.role:
                return entry
        return None
