from ..gateway.hid_gateway import HidGateway


class HidGatewayBT(HidGateway):
    def _do_write(self, msg: bytes) -> None:
        self._transport.write_output_report(msg)

    def _set_connected(self, state: bool) -> None:
        super()._set_connected(state)
        self._event_listener.listen(self._create_connection_event())

    def _create_connection_event(self) -> bytes:
        pid = self._device_info.pid
        # Synthesize a HID++ 1.0 Device Connection short report (0x41)
        # Layout: [report_id, slot, 0x41, 0x00, r1, wpid_lo, wpid_hi]
        # r1: bits[3:0]=device_type (unknown=0), bit[6]: 0=connected, 1=disconnected
        r1 = 0x00 if self._connected else 0x40
        wpid_lo = pid & 0xFF
        wpid_hi = (pid >> 8) & 0xFF
        return bytes([0x10, 0xFF, 0x41, 0x00, r1, wpid_lo, wpid_hi])
