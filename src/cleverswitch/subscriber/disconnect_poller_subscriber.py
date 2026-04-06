import logging
import random
import time
from threading import Thread

from ..event.device_connected_event import DeviceConnectedEvent
from ..event.hidpp_response_event import HidppResponseEvent
from ..event.write_event import WriteEvent
from ..hidpp.constants import DEVICE_RECEIVER, REPORT_SHORT, SW_ID
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)

POLL_INTERVAL_S = 0.5
DISCONNECT_TIMEOUT_S = 0.5
PING_FN_SW = (1 << 4) | SW_ID  # function 1 (getProtocolVersion) | SW_ID


class DisconnectPollerSubscriber(Subscriber):
    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics) -> None:
        self._device_registry = device_registry
        self._topics = topics
        self._last_seen: dict[int, float] = {}  # slot → timestamp
        self._connected: dict[int, bool] = {}  # slot → connected flag
        topics.hid_event.subscribe(self)
        self._poller = Thread(target=self._poll_loop, daemon=True)
        self._poller.start()

    def notify(self, event) -> None:
        if isinstance(event, HidppResponseEvent) and event.feature_index == 0 and event.sw_id == SW_ID:
            self._last_seen[event.slot] = time.monotonic()
            self._connected[event.slot] = True

    def _poll_loop(self) -> None:
        while True:
            self._poll_loop_once()
            time.sleep(POLL_INTERVAL_S)
            self._check_timeouts()

    def _poll_loop_once(self) -> None:
        devices = self._device_registry.all_entries()
        now = time.monotonic()

        for device in devices:
            if device.slot == DEVICE_RECEIVER:
                continue

            slot = device.slot

            if slot not in self._last_seen:
                self._last_seen[slot] = now
                self._connected[slot] = True

            ping_data = random.randint(1, 255)
            message = bytes([REPORT_SHORT, slot, 0x00, PING_FN_SW, 0x00, 0x00, ping_data])
            self._topics.write.publish(WriteEvent(slot=slot, pid=device.pid, hid_message=message))

    def _check_timeouts(self) -> None:
        devices = self._device_registry.all_entries()
        now = time.monotonic()

        for device in devices:
            if device.slot == DEVICE_RECEIVER:
                continue

            slot = device.slot
            elapsed = now - self._last_seen.get(slot, 0)

            if elapsed > DISCONNECT_TIMEOUT_S and self._connected.get(slot, False):
                self._connected[slot] = False
                log.info("Ping timeout for slot=%d wpid=0x%04X — publishing disconnect", slot, device.wpid)
                self._topics.hid_event.publish(
                    DeviceConnectedEvent(
                        slot=slot,
                        pid=device.pid,
                        link_established=False,
                        wpid=device.wpid,
                    )
                )
