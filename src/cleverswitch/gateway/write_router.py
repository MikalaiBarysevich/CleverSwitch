from collections.abc import Sequence

from ..gateway.hid_gateway import HidGateway
from ..hidpp.constants import HIDPP_BT_USAGE_LONG, HIDPP_USAGE_LONG, HIDPP_USAGE_SHORT, REPORT_LONG, REPORT_SHORT

_USAGE_TO_REPORT_ID = {
    HIDPP_USAGE_SHORT: REPORT_SHORT,
    HIDPP_USAGE_LONG: REPORT_LONG,
    HIDPP_BT_USAGE_LONG: REPORT_LONG,
}


class WriteRouter:
    """Picks which of a device's HID collections an outbound message is written to."""

    def select(self, msg: bytes, gateways: Sequence[HidGateway]) -> HidGateway | None:
        return gateways[0] if gateways else None


class ReportIdWriteRouter(WriteRouter):
    """Windows exposes the short and long HID++ reports as separate collections, and each one
    accepts only its own report ID."""

    def select(self, msg: bytes, gateways: Sequence[HidGateway]) -> HidGateway | None:
        for gateway in gateways:
            if _USAGE_TO_REPORT_ID.get(gateway.device_info.usage) == msg[0]:
                return gateway
        return None
