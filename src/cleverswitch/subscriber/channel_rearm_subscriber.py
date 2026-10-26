import logging

from ..event.link_channel_changed_event import LinkChannelChangedEvent
from ..event.set_report_flag_event import SetReportFlagEvent
from ..hidpp.constants import FEATURE_REPROG_CONTROLS_V4
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)


class ChannelRearmSubscriber(Subscriber):
    """Re-arms Easy-Switch reporting when a device's GATT channel comes up or goes down.

    Reporting is bound to the channel the last setCidReporting arrived on, and writes prefer GATT
    while it is up. Re-arming on every change moves reporting onto a channel CleverSwitch is
    reading: onto GATT once it is subscribed, back onto HID when it drops.
    """

    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics) -> None:
        self._device_registry = device_registry
        self._topics = topics
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, LinkChannelChangedEvent):
            return
        for device in self._device_registry.all_entries():
            if device.pid != event.pid or not device.connected:
                continue
            if FEATURE_REPROG_CONTROLS_V4 not in device.available_features:
                continue
            state = "up" if event.up else "down"
            log.debug(f"{event.channel} {state} for wpid=0x{device.wpid:04X}: re-arming key reporting")
            self._topics.flags.publish(SetReportFlagEvent(slot=device.slot, pid=device.pid, wpid=device.wpid))
