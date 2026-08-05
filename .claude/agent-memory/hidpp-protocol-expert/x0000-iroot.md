---
name: x0000-iroot
description: IRoot (0x0000) feature-index lookup semantics and feature-index stability across resets/firmware
metadata:
  type: reference
---

## x0000 IRoot (v2)
- Source: `x0000_root_v2.pdf`
- getFeature(featId) → featureIndex (0=not found, 1-N=index), featureType, featureVersion
- featureType bits: bit7=obsolete, bit6=hidden, bit5=engineering, bit4=manuf_deact, bit3=compl_deact
- Feature indices are one-based; 0 means not found

## Feature index stability
- Feature indices are stable within a firmware version (ROM-based feature table)
- They only change after a firmware update, not on reconnect or host switch
- Safe to cache for lifetime of a device session/registry entry — but a persisted cache
  (e.g. CleverSwitch's `DeviceCache`) can go stale across a firmware update; see
  [[x1814-change-host]] diagnostic heuristic for a concrete symptom of this.
