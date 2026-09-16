import logging
import threading
import time

from ..event.device_connected_event import DeviceConnectedEvent
from ..event.host_change_event import HostChangeEvent
from ..model.config.easy_switch_config import EasySwitchConfig
from ..model.logi_device import LogiDevice
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)

# How long an externally-announced switch keeps the fallback suppressed. Covers the normal
# ordering, where the announcement is observed before the departing device's disconnect.
ANNOUNCED_SWITCH_WINDOW_S = 2.0

# How long the relay waits before publishing, to let a slightly-late announcement land first.
# See the class docstring for why this delay exists and why it cannot be a plain sleep.
ANNOUNCEMENT_GRACE_S = 0.25


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

    The publish is deferred by ANNOUNCEMENT_GRACE_S on a timer thread rather than sent inline.
    The CID path emits HostChangeEvent straight from the parser, so FIFO ordering on the shared
    hid_event queue guarantees it is seen before the disconnect. The x1814 path does not: the
    parser emits a generic HidppNotificationEvent, and ChangeHostNotificationSubscriber
    translates it on *its own* thread, so its HostChangeEvent can lose the race to the
    disconnect. Losing that race is not self-correcting — the relay would command the peer to the
    wrong host, the peer would tear down its link, and the correct command arriving afterwards
    would never reach it. The delay cannot be a plain sleep in notify(): the announcement arrives
    on this subscriber's own queue, which its drain thread would then not be draining.

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
        announcement_grace_s: float = ANNOUNCEMENT_GRACE_S,
    ):
        self._device_registry = device_registry
        self._topics = topics
        self._peer_host_index_by_role = easy_switch_config.peer_host_index
        self._announcement_grace_s = announcement_grace_s
        self._seen_connected: dict[int, bool] = {}
        self._lock = threading.Lock()
        self._announced_at: float | None = None
        self._relayed_event: HostChangeEvent | None = None
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

        timer = threading.Timer(self._announcement_grace_s, self._relay, args=(departed, peer, peer_host_index))
        timer.daemon = True
        timer.start()

    def _note_announced_switch(self, event: HostChangeEvent) -> None:
        with self._lock:
            if event is self._relayed_event:
                return
            self._announced_at = time.monotonic()

    def _relay(self, departed: LogiDevice, peer: LogiDevice, peer_host_index: int) -> None:
        with self._lock:
            if self._announced_at is not None and time.monotonic() - self._announced_at <= ANNOUNCED_SWITCH_WINDOW_S:
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
