import logging

from ..event.device_connected_event import DeviceConnectedEvent
from ..event.event import Event
from ..event.external_unset_flag_event import ExternalUnsetFlagEvent
from ..event.hidpp_error_event import HidppErrorEvent
from ..event.hidpp_notification_event import HidppNotificationEvent
from ..event.hidpp_response_event import HidppResponseEvent
from ..hidpp.constants import (
    ANALYTICS_AVALID,
    ANALYTICS_KEY_EVT,
    GET_LONG_REGISTER_RSP,
    HOST_SWITCH_CIDS,
    MAP_FLAG_DIVERTED,
    REGISTER_PAIRING_INFO,
    REPORT_LONG,
    REPORT_SHORT,
    SW_ID_MASK,
)

log = logging.getLogger(__name__)


def parse(pid: int, raw_event: bytes) -> Event | None:
    report_id = raw_event[0]
    slot = raw_event[1]
    feature_id = raw_event[2]

    # HID++ 1.0 Device Connection notification (0x41)
    if report_id == REPORT_SHORT and feature_id == 0x41:
        r1 = raw_event[4]
        device_type = r1 & 0x0F
        link_established = (r1 & 0x40) == 0
        wpid = raw_event[6] << 8 | raw_event[5]
        return DeviceConnectedEvent(
            slot=slot,
            pid=pid,
            link_established=link_established,
            wpid=wpid,
            device_type=device_type if device_type != 0 else None,
        )

    # HID++ 1.0 error (sub_id=0x8F)
    if report_id == REPORT_SHORT and feature_id == 0x8F:
        sw_id = raw_event[3] & 0x0F
        error_code = raw_event[5]
        return HidppErrorEvent(slot=slot, pid=pid, sw_id=sw_id, error_code=error_code)

    # HID++ 1.0 GET_LONG_REGISTER_RSP for Pairing Information (0xB5)
    if report_id == REPORT_LONG and feature_id == GET_LONG_REGISTER_RSP and raw_event[3] == REGISTER_PAIRING_INFO:
        sub_page = raw_event[4]
        slot = sub_page - 0x1F  # 0x20 → slot 1, 0x25 → slot 6
        wpid = (raw_event[7] << 8) | raw_event[8]  # MSB-first (opposite of 0x41)
        device_type = raw_event[11]
        return DeviceConnectedEvent(
            slot=slot,
            pid=pid,
            link_established=False,
            wpid=wpid,
            device_type=device_type if device_type != 0 else None,
        )

    if report_id == REPORT_LONG:
        sw_id = raw_event[3] & 0x0F

        # HID++ 2.0 error (feature_index=0xFF)
        if feature_id == 0xFF:
            error_code = raw_event[5]
            return HidppErrorEvent(slot=slot, pid=pid, sw_id=sw_id, error_code=error_code)

        function = (raw_event[3] & 0xF0) >> 4

        # Response from CleverSwitch (any sw_id with bit 3 set)
        if sw_id & SW_ID_MASK:
            payload = raw_event[4:]
            return HidppResponseEvent(
                slot=slot,
                pid=pid,
                feature_index=feature_id,
                function=function,
                sw_id=sw_id,
                payload=payload,
            )

        # Notification from device (sw_id == 0)
        if sw_id == 0:
            payload = raw_event[4:]
            return HidppNotificationEvent(
                slot=slot,
                pid=pid,
                feature_index=feature_id,
                function=function,
                payload=payload,
            )

        # External app response (sw_id 1–7): log setCidReporting (fn=3) and resetAllCidReportSettings (fn=6)
        if function == 3:
            cid = (raw_event[4] << 8) | raw_event[5]
            bfield = raw_event[6]
            byte9 = raw_event[9]
            log.info(
                "External setCidReporting (sw_id=%d): slot=%d feat_idx=%d CID=0x%04X bfield=0x%02X byte9=0x%02X",
                sw_id,
                slot,
                feature_id,
                cid,
                bfield,
                byte9,
            )
            if cid in HOST_SWITCH_CIDS:
                divert_valid = bfield & (MAP_FLAG_DIVERTED << 1)
                divert_set = bfield & MAP_FLAG_DIVERTED
                if (byte9 & ANALYTICS_AVALID and not (byte9 & ANALYTICS_KEY_EVT)) or (divert_valid and not divert_set):
                    return ExternalUnsetFlagEvent(slot=slot, pid=pid, feature_index=feature_id, cid=cid)

        if function == 6:
            log.info(
                "External resetAllCidReportSettings (sw_id=%d): slot=%d feat_idx=%d raw=%s",
                sw_id,
                slot,
                feature_id,
                raw_event.hex(),
            )

    return None
