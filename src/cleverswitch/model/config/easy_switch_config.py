import dataclasses


@dataclasses.dataclass(frozen=True)
class EasySwitchConfig:
    # This machine's Easy-Switch host index for "the other machine", per device role. Feature
    # 0x1814 notifications, which the notification-based relay depends on, do not fire at all for
    # some device/receiver combinations (confirmed via raw HID capture, no target-host
    # information is ever available on the departing host) — this is the two-host fallback: any
    # disconnect of either device while its paired counterpart is still locally connected is
    # treated as "switched away", and the counterpart is commanded to follow to its own
    # role-specific index (in both directions, unlike Logitech's own keyboard-only Enhanced
    # Easy-Switch).
    #
    # Keyed by role ("keyboard"/"mouse", matching LogiDevice.role); an empty/missing entry for a
    # role disables the relay towards that role. Each device has its own independent host pairing
    # table, so the keyboard's and the mouse's index for "the same other machine" are not
    # guaranteed to match — hence per-role, not a single shared index. The value is simply the
    # number printed on that device's own Easy-Switch key for the other machine.
    #
    # 0-indexed internally (config.yaml's values are 1-based for humans — Easy-Switch key 1 is
    # index 0 — converted on load).
    peer_host_index: dict[str, int] = dataclasses.field(default_factory=dict)
