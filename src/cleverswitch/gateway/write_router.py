from collections.abc import Sequence

from ..gateway.hid_channel import HidChannel
from ..hidpp.constants import HIDPP_BT_USAGE_LONG, HIDPP_USAGE_LONG, HIDPP_USAGE_SHORT, REPORT_LONG, REPORT_SHORT

_USAGE_TO_REPORT_ID = {
    HIDPP_USAGE_SHORT: REPORT_SHORT,
    HIDPP_USAGE_LONG: REPORT_LONG,
    HIDPP_BT_USAGE_LONG: REPORT_LONG,
}


class WriteRouter:
    """Picks which of a device's HID collections an outbound message is written to."""

    def select(self, msg: bytes, hid_channels: Sequence[HidChannel]) -> HidChannel | None:
        return hid_channels[0] if hid_channels else None


class ReportIdWriteRouter(WriteRouter):
    """Windows exposes the short and long HID++ reports as separate collections, and each one
    accepts only its own report ID."""

    def select(self, msg: bytes, hid_channels: Sequence[HidChannel]) -> HidChannel | None:
        for hid_channel in hid_channels:
            if _USAGE_TO_REPORT_ID.get(hid_channel.device_info.usage) == msg[0]:
                return hid_channel
        return None
