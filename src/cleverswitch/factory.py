from .hidpp.constants import FEATURE_CHANGE_HOST, FEATURE_HOSTS_INFO, FEATURE_REPROG_CONTROLS_V4
from .hidpp.protocol import are_es_cids_divertable, get_host_info_1814, get_paired_hosts_1815, resolve_feature_index
from .hidpp.transport import HIDTransport, log
from .model import LogiProduct


def _make_logi_product(
    transport: HIDTransport,
    slot: int,
    role: str,
    name: str,
) -> LogiProduct | None:
    """Resolve CHANGE_HOST feature index and build a LogiProduct.

    For keyboards: also resolves REPROG_CONTROLS_V4 divertability.
    If ES CIDs are not divertable, falls back to disconnect-based host tracking
    using x1815 HOSTS_INFO — populating paired_hosts, current_host, and
    hosts_info_feat_idx so the listener can detect host changes on disconnect.

    Returns None if CHANGE_HOST is not supported (logs a warning).
    """
    feat_idx = resolve_feature_index(transport, slot, FEATURE_CHANGE_HOST)
    if feat_idx is None:
        log.warning(
            "%s (slot=0x%02X, %s) does not support CHANGE_HOST (0x1814) — skipping",
            name,
            slot,
            transport.kind,
        )
        return None
    log.debug(
        "%s (slot=0x%02X, %s) found CHANGE_HOST (0x1814) idx — %s",
        name,
        slot,
        transport.kind,
        feat_idx,
    )

    feat_idx_rep: int | None = None
    feat_idx_hosts_info: int | None = None
    paired_hosts: tuple[int, ...] | None = None
    current_host: int | None = None

    if role == "keyboard":
        feat_idx_rep = resolve_feature_index(transport, slot, FEATURE_REPROG_CONTROLS_V4)
        log.debug("feat_idx_rep=%s", feat_idx_rep)
        if feat_idx_rep is not None and are_es_cids_divertable(transport, slot, feat_idx_rep):
            log.debug(
                "%s (slot=0x%02X, %s) found FEATURE_REPROG_CONTROLS_V4 (0x1B04) idx — %s",
                name,
                slot,
                transport.kind,
                feat_idx_rep,
            )
        else:
            log.info(
                "%s (slot=0x%02X, %s) ES CIDs not divertable — will use disconnect-based host detection",
                name,
                slot,
                transport.kind,
            )
            feat_idx_rep = None
            feat_idx_hosts_info, paired_hosts, current_host = _resolve_hosts_info(transport, slot, feat_idx, name)

    log.info(f"'{name}' found via transport={transport.kind}")

    return LogiProduct(
        slot=slot,
        change_host_feat_idx=feat_idx,
        divert_feat_idx=feat_idx_rep,
        role=role,
        name=name,
        paired_hosts=paired_hosts,
        current_host=current_host,
        hosts_info_feat_idx=feat_idx_hosts_info,
    )


def _resolve_hosts_info(
    transport: HIDTransport,
    slot: int,
    change_host_feat_idx: int,
    name: str,
) -> tuple[int | None, tuple[int, ...] | None, int | None]:
    """Resolve x1815 HOSTS_INFO and query paired hosts via x1814 + x1815.

    Returns (hosts_info_feat_idx, paired_hosts, current_host).
    Any of the three may be None if the feature is absent or queries fail.
    This information is refreshed on each connection event so startup values
    are only a best-effort baseline.
    """
    feat_idx_hosts_info = resolve_feature_index(transport, slot, FEATURE_HOSTS_INFO)
    if feat_idx_hosts_info is None:
        log.debug("%s (slot=0x%02X) does not support HOSTS_INFO (0x1815)", name, slot)
        return None, None, None

    host_info = get_host_info_1814(transport, slot, change_host_feat_idx)
    if host_info is None:
        log.debug("%s (slot=0x%02X) get_host_info_1814 failed", name, slot)
        return feat_idx_hosts_info, None, None

    nb_host, curr_host = host_info
    paired = get_paired_hosts_1815(transport, slot, feat_idx_hosts_info, nb_host)
    if paired is None:
        log.debug("%s (slot=0x%02X) get_paired_hosts_1815 failed", name, slot)
        return feat_idx_hosts_info, None, curr_host

    log.debug("%s (slot=0x%02X) paired_hosts=%s current_host=%d", name, slot, paired, curr_host)
    return feat_idx_hosts_info, tuple(paired), curr_host
