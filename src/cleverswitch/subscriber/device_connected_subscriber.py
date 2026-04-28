import logging

from ..event.device_connected_event import DeviceConnectedEvent
from ..event.device_info_request_event import DeviceInfoRequestEvent
from ..event.set_report_flag_event import SetReportFlagEvent
from ..hidpp.constants import FEATURE_REPROG_CONTROLS_V4
from ..model.logi_device import LogiDevice
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)


class DeviceConnectionSubscriber(Subscriber):
    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics) -> None:
        self._device_registry = device_registry
        self._topics = topics
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, DeviceConnectedEvent):
            return

        logi_device = self._device_registry.get_by_wpid(event.wpid)

        if logi_device is not None and logi_device.connected == event.link_established:
            return

        if logi_device is not None:
            self._reconnection(event, logi_device)
        else:
            self._new_connection(event)

    def _reconnection(self, event: DeviceConnectedEvent, logi_device: LogiDevice) -> None:
        name = f"'{logi_device.name}'" if logi_device.name is not None else f"Device wpid=0x{event.wpid:04X}"
        connection = "reconnected" if event.link_established else "disconnected"
        message = f"{name} {connection}"

        log.info(message)

        logi_device.connected = event.link_established
        if not event.link_established:
            return

        if FEATURE_REPROG_CONTROLS_V4 in logi_device.available_features:
            self._topics.flags.publish(
                SetReportFlagEvent(
                    slot=event.slot,
                    pid=logi_device.pid,
                    wpid=logi_device.wpid,
                )
            )

        missing = logi_device.pending_steps

        if missing:
            log.debug(f"Device reconnected with incomplete setup (missing={missing}): wpid=0x{event.wpid:04X}")
            self._topics.device_info.publish(
                DeviceInfoRequestEvent(
                    slot=event.slot,
                    pid=event.pid,
                    wpid=event.wpid,
                    type=logi_device.role is None,
                    name=logi_device.name is None,
                )
            )

    def _new_connection(self, event: DeviceConnectedEvent) -> None:
        role = None
        if not event.link_established:
            # First seen but not active device. Most likely stale connection.
            log.debug("Received new connection with link_established=False. Stale pair. Skipping")
            return

        if event.device_type is not None:
            role = "keyboard" if event.device_type == 1 else "mouse"

        device = LogiDevice(
            wpid=event.wpid,
            pid=event.pid,
            slot=event.slot,
            role=role,
            available_features={},
            connected=event.link_established,
        )

        self._device_registry.register(event.wpid, device)

        self._topics.device_info.publish(
            DeviceInfoRequestEvent(
                slot=event.slot,
                pid=event.pid,
                wpid=event.wpid,
                type=event.device_type is None,
            )
        )
