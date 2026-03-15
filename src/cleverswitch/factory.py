from .hidpp.constants import FEATURE_CHANGE_HOST, FEATURE_REPROG_CONTROLS_V4
from .hidpp.protocol import are_es_cids_divertable, resolve_feature_index
from .hidpp.transport import HIDTransport, log
from .model import LogiProduct


def _make_logi_product(
    transport: HIDTransport,
    slot: int,
    role: str,
    name: str,
) -> LogiProduct | None:
    """Resolve CHANGE_HOST feature index and build a DeviceContext.

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

    feat_idx_rep = None
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
                "%s (slot=0x%02X, %s) ES CIDs not divertable — will use CHANGE_HOST notifications",
                name,
                slot,
                transport.kind,
            )
            feat_idx_rep = None

    log.info(f"'{name}' found via transport={transport.kind}")

    return LogiProduct(
        slot=slot,
        change_host_feat_idx=feat_idx,
        divert_feat_idx=feat_idx_rep,
        role=role,
        name=name,
    )
