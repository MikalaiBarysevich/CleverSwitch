import logging

from ..event.hidpp_response_event import HidppResponseEvent
from ..event.set_report_flag_event import SetReportFlagEvent
from ..hidpp.constants import HOST_SWITCH_CIDS, KEY_FLAG_ANALYTICS, SW_ID_DIVERT
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)


class AnalyticsRejectionSubscriber(Subscriber):
    """Detects silent analytics rejection in setCidReporting echoes.

    Some keyboards (e.g. K850) advertise KEY_FLAG_ANALYTICS in getCidInfo but
    silently reject the analytics enable: the device echoes the setCidReporting
    request with byte 9 cleared to 0x00 instead of the requested 0x03. When that
    happens, drop KEY_FLAG_ANALYTICS from the device's supported flags and
    republish SetReportFlagEvent so SetReportFlagSubscriber re-arms via divert.
    """

    def __init__(self, device_registry: LogiDeviceRegistry, topics: Topics):
        self._device_registry = device_registry
        self._topics = topics
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if not isinstance(event, HidppResponseEvent):
            return
        if event.sw_id != SW_ID_DIVERT or event.function != 3:
            return
        if len(event.payload) < 6:
            return

        cid = (event.payload[0] << 8) | event.payload[1]
        if cid not in HOST_SWITCH_CIDS:
            return

        device = None
        for entry in self._device_registry.all_entries():
            if entry.slot == event.slot and entry.pid == event.pid:
                device = entry
                break
        if device is None:
            return

        if KEY_FLAG_ANALYTICS not in device.supported_flags:
            return

        if event.payload[5] != 0x00:
            return

        log.debug(f"wpid=0x{device.wpid:04X}: analytics rejected on CID 0x{cid:04X}, falling back to divert")
        device.supported_flags.discard(KEY_FLAG_ANALYTICS)
        self._topics.flags.publish(SetReportFlagEvent(slot=event.slot, pid=device.pid, wpid=device.wpid))
