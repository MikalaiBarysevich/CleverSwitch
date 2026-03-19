import logging
import queue
import time

from ..errors import ResponseTimeoutError
from ..event.device_info_request_event import DeviceInfoRequestEvent
from ..event.divert_event import DivertEvent
from ..event.hidpp_error_event import HidppErrorEvent
from ..event.hidpp_response_event import HidppResponseEvent
from ..event.write_event import WriteEvent
from ..hidpp.constants import (
    FEATURE_CHANGE_HOST,
    FEATURE_DEVICE_TYPE_AND_NAME,
    FEATURE_REPROG_CONTROLS_V4,
    FEATURE_ROOT,
    HOST_SWITCH_CIDS,
    KEY_FLAG_DIVERTABLE,
    SW_ID,
)
from ..hidpp.protocol import build_msg, pack_params
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topic import Topic

log = logging.getLogger(__name__)

RESPONSE_TIMEOUT = 2.0


class DeviceInfoSubscriber(Subscriber):

    def __init__(self, device_registry: LogiDeviceRegistry, topics: dict[str, Topic]) -> None:
        self._device_registry = device_registry
        self._topics = topics
        self._response_queue: queue.Queue = queue.Queue()

    def notify(self, event) -> None:
        if isinstance(event, DeviceInfoRequestEvent):
            self._handle_setup(event)
        elif isinstance(event, (HidppResponseEvent, HidppErrorEvent)):
            self._response_queue.put(event)

    def _handle_setup(self, event: DeviceInfoRequestEvent) -> None:
        slot = event.slot
        pid = event.pid
        wpid = event.wpid
        device = self._device_registry.get_by_wpid(wpid)
        if device is None:
            log.warning("DeviceInfoSubscriber: device wpid=0x%04X not found in registry", wpid)
            return

        step = device.info_step
        log.info("Starting device info setup for slot=%d wpid=0x%04X (step %d/5)", slot, wpid, step)

        try:
            # Step 1: Resolve REPROG_CONTROLS_V4 feature index
            if step < 1:
                reprog_idx = self._resolve_feature(slot, pid, FEATURE_REPROG_CONTROLS_V4)
                if reprog_idx is not None:
                    device.available_features[FEATURE_REPROG_CONTROLS_V4] = reprog_idx
                    log.info("slot=%d: REPROG_CONTROLS_V4 at index %d", slot, reprog_idx)
                else:
                    log.info("slot=%d: REPROG_CONTROLS_V4 not supported", slot)
                device.info_step = 1

            # Step 2: Find divertable CIDs and divert them
            if step < 2:
                reprog_idx = device.available_features.get(FEATURE_REPROG_CONTROLS_V4)
                if reprog_idx is not None:
                    divertable = self._find_divertable_cids(slot, pid, reprog_idx)
                    device.divertable_cids = divertable
                    if divertable:
                        log.info("slot=%d: divertable ES CIDs: %s", slot, {f"0x{c:04X}" for c in divertable})
                        self._topics["divert_topic"].publish(DivertEvent(
                            slot=slot,
                            pid=pid,
                            wpid=wpid,
                            cids=divertable,
                        ))
                device.info_step = 2

            # Step 3: Resolve CHANGE_HOST feature index
            if step < 3:
                change_host_idx = self._resolve_feature(slot, pid, FEATURE_CHANGE_HOST)
                if change_host_idx is not None:
                    device.available_features[FEATURE_CHANGE_HOST] = change_host_idx
                    log.info("slot=%d: CHANGE_HOST at index %d", slot, change_host_idx)
                else:
                    log.info("slot=%d: CHANGE_HOST not supported", slot)
                device.info_step = 3

            # Step 4: Resolve DEVICE_TYPE_AND_NAME + get device type
            if step < 4:
                x0005_idx = device.available_features.get(FEATURE_DEVICE_TYPE_AND_NAME)
                if x0005_idx is None:
                    x0005_idx = self._resolve_feature(slot, pid, FEATURE_DEVICE_TYPE_AND_NAME)
                    if x0005_idx is not None:
                        device.available_features[FEATURE_DEVICE_TYPE_AND_NAME] = x0005_idx
                if x0005_idx is not None and device.role is None:
                    device_type = self._get_device_type(slot, pid, x0005_idx)
                    if device_type is not None:
                        device.role = "keyboard" if device_type == 0 else "mouse"
                        log.info("slot=%d: type=%s", slot, device.role)
                elif x0005_idx is None:
                    log.info("slot=%d: DEVICE_TYPE_AND_NAME not supported", slot)
                device.info_step = 4

            # Step 5: Get device name
            if step < 5:
                x0005_idx = device.available_features.get(FEATURE_DEVICE_TYPE_AND_NAME)
                if x0005_idx is not None and device.name is None:
                    name = self._get_device_name(slot, pid, x0005_idx)
                    if name is not None:
                        device.name = name
                        log.info("slot=%d: name=%s", slot, name)
                device.info_step = 5

        except ResponseTimeoutError:
            log.warning("Device info setup interrupted at step %d for slot=%d wpid=0x%04X", device.info_step, slot, wpid)
            return

        log.info(
            "Device info setup complete for slot=%d: name=%s, role=%s, features=%s, divertable_cids=%s",
            slot, device.name, device.role, device.available_features, device.divertable_cids,
        )

    def _resolve_feature(self, slot: int, pid: int, feature_code: int) -> int | None:
        request_id = (FEATURE_ROOT << 8) | 0x00
        response = self._send_request(slot, pid, request_id, feature_code >> 8, feature_code & 0xFF, 0x00)
        if response is not None and response.payload[0] != 0x00:
            return response.payload[0]
        return None

    def _get_device_type(self, slot: int, pid: int, feat_idx: int) -> int | None:
        request_id = (feat_idx << 8) | 0x20  # fn[2] getDeviceType
        response = self._send_request(slot, pid, request_id)
        if response is not None:
            return response.payload[0]
        return None

    def _get_device_name(self, slot: int, pid: int, feat_idx: int) -> str | None:
        # fn[0] getDeviceNameCount
        request_id = (feat_idx << 8) | 0x00
        response = self._send_request(slot, pid, request_id)
        if response is None:
            return None
        name_len = response.payload[0]
        if name_len == 0:
            return None

        # fn[1] getDeviceName(charIndex) — up to 16 chars per long-report chunk
        chars: list[int] = []
        while len(chars) < name_len:
            request_id = (feat_idx << 8) | 0x10  # fn[1]
            response = self._send_request(slot, pid, request_id, len(chars))
            if response is None:
                break
            remaining = name_len - len(chars)
            chunk = response.payload[:remaining]
            if not chunk:
                break
            chars.extend(chunk)

        return bytes(chars).decode("utf-8", errors="replace") if chars else None

    def _find_divertable_cids(self, slot: int, pid: int, reprog_idx: int) -> set[int]:
        # fn[0] getCount
        request_id = (reprog_idx << 8) | 0x00
        response = self._send_request(slot, pid, request_id)
        if response is None:
            return set()
        count = response.payload[0]

        divertable: set[int] = set()
        for index in range(count):
            # fn[1] getCidInfo(index)
            request_id = (reprog_idx << 8) | 0x10
            response = self._send_request(slot, pid, request_id, index)
            if response is None:
                continue
            cid = (response.payload[0] << 8) | response.payload[1]
            if cid not in HOST_SWITCH_CIDS:
                continue
            flags = response.payload[4]
            if flags & KEY_FLAG_DIVERTABLE:
                divertable.add(cid)

        return divertable

    def _send_request(self, slot: int, pid: int, request_id: int, *params) -> HidppResponseEvent | None:
        request_id = (request_id & 0xFFF0) | SW_ID
        expected_feat_idx = (request_id >> 8) & 0xFF
        expected_fn = (request_id >> 4) & 0x0F
        params_bytes = pack_params(params)
        msg = build_msg(slot, request_id, params_bytes)
        self._topics["write_topic"].publish(WriteEvent(slot=slot, pid=pid, hid_message=msg))
        return self._wait_response(slot, expected_feat_idx, expected_fn)

    def _wait_response(self, slot: int, feat_idx: int, function: int) -> HidppResponseEvent | None:
        deadline = time.monotonic() + RESPONSE_TIMEOUT
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ResponseTimeoutError(f"Response timeout for slot={slot} feat_idx={feat_idx} fn={function}")
            try:
                event = self._response_queue.get(timeout=remaining)
                if isinstance(event, HidppErrorEvent) and event.slot == slot:
                    log.debug("HID++ error for slot=%d: 0x%02X", slot, event.error_code)
                    return None
                if (
                    isinstance(event, HidppResponseEvent)
                    and event.slot == slot
                    and event.feature_index == feat_idx
                    and event.function == function
                ):
                    return event
                # Non-matching event, discard and retry
            except queue.Empty:
                raise ResponseTimeoutError(f"Response timeout for slot={slot} feat_idx={feat_idx} fn={function}")
