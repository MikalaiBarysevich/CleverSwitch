---
name: x1814-change-host
description: Feature 0x1814 CHANGE_HOST byte layout, the undocumented notification behavior, discriminating it from setCurrentHost echoes/0x1D4B, version history (v0 vs v1), and the undocumented fn4 (possible Enhanced Easy-Switch lead-capability getter)
metadata:
  type: reference
---

## Function 4 — UNDOCUMENTED, possible Enhanced Easy-Switch capability getter (2026-08, CleverSwitch issue #102 full -vv log)
**[INFERENCE — no source names fn4's purpose; only circumstantial evidence below]**
- Observed: Logi Options+ (sw_id=11) calls feature_index=10 (=0x1814, confirmed), function=4,
  immediately after a getHostInfo (fn0) call on the SAME device. Response payload:
  `01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00` (byte0=0x01, rest zero).
- **Keyboard-only in this session**: called twice on the MX Keys S (pid 45944, leadCoupledEasySwitch
  per Options+' own `devices.json` catalog), never on the MX Master 3 (pid 45091) in the same
  session — even though Options+ repeatedly polls the mouse's fn0 getHostInfo. CAVEAT: the MX
  Master 3 (non-S) is absent from Options+' coupled-device list entirely (only MX Master 3S has
  `followCoupledEasySwitch`), so this session cannot distinguish "fn4 is keyboard-only by protocol
  design" from "Options+ simply never asks a mouse its local catalog already knows is ineligible."
  Needs a capture containing an EES-eligible mouse (e.g. MX Master 3S) to settle which explanation
  is correct.
- **No source documents fn4 or any 0x1814 function beyond fn3**: checked OpenLogi
  (github.com/AprilNEA/OpenLogi, `crates/openlogi-hidpp/src/feature/change_host.rs`) — implements
  only fn0 `get_host_info`, fn1 `set_current_host`, fn2 `get_cookies`, fn3 `set_cookie`; no fn4.
  Also checked Logitech's own cpg-docs (`hidpp20/README.rst`) — lists 0x1814 by name only, no
  function table at all (matches prior finding that cpg-docs only fully documents 0x0000 as a
  worked example). No hit in Solaar, PixlOne/logiops wiki, or cvuchener/hidpp either (all already
  confirmed to have zero 0x1814 function-level detail — see notes above).
- **Version history — CONFIRMED, this resolves a real gap**: OpenLogi's `change_host.rs` module
  declares itself as targeting "Feature ID: 0x1814, Version: 0" (their own minimum-supported-version
  constant, likely NOT read live from the device — they only need fn0-3 which plausibly exist in
  both v0 and v1). But a real-world OpenLogi device-support issue
  (github.com/AprilNEA/OpenLogi#521, MX Keys) contains a raw feature-table dump showing
  **`10   0x1814  v1   ChangeHost`** — feature index 10 (0x0A), matching the index independently
  resolved for MX Keys S in both #91 and #102. So **0x1814 v1 is confirmed to exist in the wild**
  on the MX Keys product family. This is consistent with fn4 being a v1-only addition that OpenLogi
  (whose own code only implements v0-era functions) simply hasn't reverse-engineered/added yet —
  the most parsimonious explanation for "undocumented function on a feature every other source
  claims stops at fn3." The exact function list v1 adds beyond v0 is NOT documented anywhere found.
- **Why "EES lead-capability getter" is the leading hypothesis over mundane alternatives**:
  - Payload shape (single boolean-looking byte, 0x01, rest zero) matches the common HID++
    "capability/enabled getter" pattern used throughout the protocol far more than a host-name or
    cookie-variant call would (cookies are already fn2/fn3 and take a host-index parameter; this
    call takes none visible and returns a flat scalar).
  - Timing (called right after getHostInfo, on the keyboard specifically) matches Options+ needing
    "does this specific currently-connected device support being an EES lead" state, which logically
    piggybacks on the per-device host-info query it already just made.
  - Logitech's own support article (support.logi.com, "Enhanced Easy-Switch Feature Guide") states
    coupling **"settings are stored directly on the device"** and that pressing Easy-Switch on the
    *mouse* does NOT trigger following — only the *keyboard's* Easy-Switch key drives the sync. This
    establishes an asymmetric keyboard-is-special protocol role independent of any packet capture,
    which is consistent with (though does not prove) a keyboard-queried lead-capability getter.
  - No dedicated separate feature for this was found anywhere: surveyed cpg-docs' full feature list
    (checked 2026-08) for anything host/pair/couple/multi/link/lead/follow-named near 0x1814-0x1820
    — only hits were 0x1814 itself, 0x1df0 "Remaining Pairings" (receiver pairing-slot count, an
    unrelated Bolt/Unifying receiver capacity feature) and 0x4530 "Dual Platform" (OS-layout mode
    switching — Windows/Mac icon set — unrelated to host coupling despite the "platform" name).
    OpenLogi's own `hosts_info.rs` (0x1815) implementation likewise has zero coupled/lead/follow
    fields. Absence of a dedicated feature anywhere in the surveyed sources is circumstantial
    support for "bolted onto 0x1814" over "lives on a separate unresolved feature" (question 4),
    but is not conclusive — a brand-new feature ID that simply hasn't been reverse-engineered by
    any of these community projects yet remains possible and unfalsifiable from available sources.
- **Recommendation if CleverSwitch ever needs to resolve this empirically**: call fn4 (with a
  zero-length or single-parameter request, matching what was captured) against a known
  EES-ineligible device and a known EES-eligible device of the same generation and diff the
  response; also worth calling fn4 on a follower-capable mouse (MX Master 3S) to resolve the
  keyboard-only-vs-catalog-skipped ambiguity above. Design decision on whether to actually build on
  an undocumented function belongs to `@software-architect` per CLAUDE.md, not this note.

## Feature 0x1814 — CHANGE_HOST
- Source: `x1814_change_host_v0.pdf` — **no events defined in the spec at all**
- The keyboard notification on Easy-Switch press is unsolicited firmware behaviour, not a
  spec-defined event. Corroborated by Solaar (checked 2026-08): `notifications.py` and
  `hidpp20.py` have ZERO code paths mentioning 0x1814 anywhere — Solaar doesn't handle any
  0x1814 notification either.
- Byte 3 fn nibble (upper) = 0x0 always for the notification.
- **CORRECTED 2026-08 (was wrong)**: sw_id for a genuine device-originated notification is ALWAYS
  0x00 — this is a universal HID++ 2.0 convention, not specific to 0x1814. Confirmed against the
  actual spec text (`logitech_hidpp_2.0_specification_draft_2012-06-04.pdf`, Software ID field):
  *"0 Do not use (allows to distinguish a notification from a response)."* Compliant software
  MUST pick a non-zero sw_id for its own requests; the firmware echoes that same non-zero sw_id
  back in the response. Therefore sw_id==0 is definitionally "this is a notification, not a
  reply" for every feature, including 0x1814. The previously-recorded "0x0D observed on a Windows
  customer device" was almost certainly a **misread Logi Options+ getHostInfo reply** (fn=0,
  sw_id=0x0D belongs to Options+'s own request), not a genuine notification with non-zero sw_id —
  see CleverSwitch issue #102 for a concrete captured example of exactly this shape
  (`11 ff 0a 07 | 03 00 ...`, sw_id=7, decoded as getHostInfo reply nbHost=3/currHost=0). Retracting
  the old claim that sw_id "can be non-zero for a genuine notification."
- setCurrentHost (fn=[1]) response/echo has fn nibble = 0x1 (byte3 & 0xF0 == 0x10) — this is the
  key discriminator against notifications
- **Correct filter**: `fn=0 (byte3 & 0xF0 == 0x00)` AND `sw_id == 0 (byte3 & 0x0F == 0x00)`.
  This matches CleverSwitch's actual current parser convention for ALL device notifications
  (`src/cleverswitch/parser/parser.py`, `sw_id == 0` branch, used today for 0x1B04 CID
  notifications) — the same sw_id==0 rule generalizes to 0x1814, it isn't a special case.
- **Wrong filter (caused loop, per repo history)**: `sw_id != SW_ID` (CleverSwitch's own sw_id)
  alone, without checking sw_id==0 specifically and without an fn=0 check — this matched BOTH
  setCurrentHost echoes (fn=1, some other sw_id) AND other software's getHostInfo replies
  (fn=0, e.g. Options+'s sw_id 0x0D/0x07), because "not equal to my own sw_id" is satisfied by
  every sw_id in 1-15 except mine, not just by 0.
- **Notification payload layout — REVISED 2026-08, previous "mirrors getHostInfo" claim REFUTED**:
  No spec table actually documents this notification (line above: "no events defined in the spec
  at all" — the old "Table 1, v0 spec" citation for the notification layout was an error/conflation
  with the getHostInfo *response* table; there is no spec text for the notification itself).
  Refuted by CleverSwitch issues #91/#102 (MX Keys S, wpid 0xB378, two independent devices/OSes):
  - byte[4] is NOT nbHost — it varies with switch direction (0x01 on macOS switching away from
    host 2, 0x00 on Windows switching away from host 1), whereas nbHost is constant (3) on this
    device (confirmed via an independently-captured getHostInfo reply, see below). nbHost would
    never be 0x00 on an ES-capable keyboard, which was already flagged as a red flag in the old
    diagnostic heuristic below — that red flag correctly fired, it was just resolved wrong (it
    correctly proved "not nbHost", but the old note wrongly concluded "maybe 0x1D4B" instead of
    "wrong field mapping for 0x1814").
  - Corrected layout, confirmed self-consistent across both independent captures:
    **byte[4] = source/departing host, 0-indexed; byte[5] = target/new host, 0-indexed.**
    macOS: departing host 2 (idx 1), target host 1 (idx 0) → `01 00` ✓.
    Windows: departing host 1 (idx 0), target host 2 (idx 1) → `00 01` ✓.
  - byte[5]=target-host was actually the one part both the old ("mirrors getHostInfo") and new
    hypotheses agreed on — but that agreement is coincidental, not corroborating: both hypotheses
    independently guessed "the OTHER field must be the target," they just disagreed on what
    byte[4] was. The real evidence for byte[5]=target is the direction-flip test above, not the
    old getHostInfo-mirror reasoning (which is now retracted for byte[4]).
  - 0-indexing matches this project's own `HOST_SWITCH_CIDS` convention (`hidpp/constants.py`:
    `{0x00D1: 0, 0x00D2: 1, 0x00D3: 2}`) — internally consistent with how CleverSwitch already
    treats host indices elsewhere in the codebase.
- getHostInfo response: byte[4]=nbHost, byte[5]=currHost, byte[6]=flags — this layout is UNCHANGED
  and re-confirmed by the #102 capture (`03 00` on a 3-host device = nbHost=3, currHost=0). Do not
  confuse this reply layout with the (structurally different) unsolicited notification above.
- setCurrentHost request: byte[4]=target host (fn=1, byte[3]&0xF0==0x10)
- **NEGATIVE RESULT, worth recording so nobody tries this again — byte[6] (flags) is NOT an
  Enhanced Easy-Switch marker (2026-08, CleverSwitch #102 full -vv log)**: every getHostInfo reply
  captured in the session is `03 01 00` (nbHost=3, currHost=1, **flags=0x00**) — on a keyboard that
  demonstrably fires 0x1814 host-switch notifications and is `leadCoupledEasySwitch=True` per
  Options+'s own catalog. The mouse (not EES-coupled) returns the byte-identical `03 01 00`. So
  flags=0x00 carries no EES signal either way here — it's indistinguishable between a coupled-lead
  keyboard and a non-coupled mouse in this capture. OpenLogi's `change_host.rs` names the one flag
  bit it documents in this byte `ENHANCED_HOST_SWITCH` (bit 0, `1<<0`) with the description "on a
  failed connection the device falls back to another host with a non-zero cookie before returning
  to the original host" — i.e. **cookie-based connection failover**, not Logitech's marketing
  "Enhanced Easy-Switch" coupling feature. This is a plain **name collision** between OpenLogi's
  internal bitflag name and Logitech's product marketing term — do not conflate them, and do not
  build EES-lead detection on this bit. (No prior CleverSwitch memory actually claimed this bit was
  an EES marker — recording this now purely to prevent the mistake being made later.)
- **Fourth independent confirmation of the `[departing_host, target_host]` notification layout**:
  the same #102 log captures the notification directly — `HidppNotificationEvent(feature_index=10,
  function=0, payload=b'\x01\x00\x00...')` — with the device on host 2 (currHost=1 per a
  getHostInfo reply 8 seconds earlier in the same session) pressing host 1. `01` = departing host 2
  (0-indexed 1), `00` = target host 1 (0-indexed 0). Matches the layout exactly, and independently
  re-confirms byte[4] is not nbHost (nbHost=3 in the same session's getHostInfo replies, byte[4]=
  0x01 in the notification) on the very same physical device/session as the getHostInfo evidence —
  no cross-session or cross-device inference needed for this one, strongest single data point yet.
- **No independent 3rd-party doc corroborates the notification's byte layout** (checked 2026-08:
  Solaar has zero 0x1814 code at all in both `hidpp20.py` and `notifications.py`; PixlOne/logiops
  wiki and cvuchener/hidpp have no 0x1814 event definitions either). The layout above is derived
  purely from the #91/#102 field evidence, not from any spec/reference-implementation source.
- **Feature-index identity as ground truth**: when in doubt whether a captured index is really
  0x1814, the strongest proof isn't payload-shape guessing — it's (a) an explicit `getFeature(0x1814)`
  IRoot resolution (done in both #91 and #102, both landed on index 0x0A/10, consistent across two
  independent hardware units of the same model), and/or (b) an independently-decodable reply at
  that index using an unrelated feature's *documented* layout (the #102 getHostInfo-reply capture,
  which cleanly decodes as nbHost/currHost). A feature index is 1:1 with a feature per firmware
  table (see [[x0000-iroot]]), so (a) and (b) together are conclusive — no other feature can
  coexist at that same index on that firmware.
- **0x1814 notification confirmed to survive RF teardown over a Bolt receiver, not just BT
  direct**: issue #91 captured the fn=0/sw_id=0 notification over a Bolt receiver on Linux
  (`11 02 0a 00 | 00 01 00 ...`), not just BT-direct (#102, macOS/Windows). Do not assume the
  departing-host visibility window (see "Host topology" section below) is BT-only.
- 0x1815 HOSTS_INFO also has zero notification code paths in Solaar — apparently also defines
  no events (not spec-verified this pass, PDF unavailable; Solaar-only corroboration)

## Diagnostic heuristic: is a mystery notification really 0x1814, or actually 0x1D4B?
**REVISED 2026-08 — the byte0=0x00 red-flag reasoning below was superseded, see #91/#102 findings
above.** byte[4]=0x00 is no longer a red flag by itself: since the notification does NOT mirror
getHostInfo (byte[4] is source-host, 0-indexed, not nbHost), byte[4]=0x00 legitimately means
"switching away from host 1" and is expected, not anomalous. Use index-identity proof instead
(see "Feature-index identity as ground truth" above) — it is strictly stronger than payload-shape
guessing and doesn't require assuming a layout in the first place.
- Historical reasoning (now retracted, kept for context): payload byte0=0x00 was read as a red flag
  against 0x1814 assuming byte0=nbHost, favoring a `status=0x00,request=0x01,reason=0x00` 0x1D4B
  reading instead. This mis-attributed a real anomaly (byte0 isn't constant like nbHost should be)
  to the wrong cause (wrong feature) rather than the right one (wrong field mapping within 0x1814).
- Plausible real sequence on an Easy-Switch press: physical key press wakes the RF link with the
  CURRENTLY-linked (soon-to-be-departing) host BEFORE the device executes the actual host switch →
  device may ALSO emit 0x1D4B and/or the 0x1B04 diverted-CID notification (0xD1/D2/D3) to that same
  still-current host in the same brief window, on devices/firmware where those paths are active.
  This is not mutually exclusive with an 0x1814 notification also being sent — a departing host can
  see more than one event type in that window. Not confirmed to co-occur on MX Keys S specifically
  (only the 0x1814 notification was captured in #91/#102); flagged as a plausible sequence for
  other device generations, not a general rule.
- If feature_index doesn't line up with payload semantics, suspect a stale/incorrect index
  resolution before assuming a new event type. In CleverSwitch specifically, `DeviceCache`
  persists `available_features` (feature code → index) across daemon restarts; indices are
  stable within a firmware version but WILL shift after a firmware update (see
  [[x0000-iroot]] "Feature index stability") — a cached 0x1814 index surviving a firmware update
  that reshuffled the table is a concrete way to get a stale "feature 0x1814 at index N" log line.

## Host topology: why the mouse can never organically observe the keyboard's switch (2026-08)
Easy-Switch host slots (1-3) are separate PAIRINGS, typically to separate physical
receivers/computers (or BT hosts), not logical channels on one shared receiver. Switching host
means the device tears down its RF/BT link to the departing receiver and re-pairs with a
different one entirely (`setCurrentHost` doc note: "device will most probably reset" — full
re-negotiation, not a soft channel change). Consequence: there is NO HID++ channel by which a
second device (e.g. the mouse) paired to a *different* receiver could ever see the keyboard's
switch — the keyboard and mouse are, from the protocol's point of view, on entirely separate
transport links once the keyboard has moved to a new host. This is *why* CleverSwitch's
architecture must catch the keyboard's outgoing notification on the departing host and proactively
send CHANGE_HOST to the mouse itself — there is no cross-device HID++ signaling mechanism, and
0x1815 HOSTS_INFO has no push notification either (see above, Solaar-corroborated).
Only the DEPARTING host is briefly positioned to see anything at all, and only in the narrow
window before the RF link tears down — see the "plausible real sequence" note below. No known
Logitech mechanism lets the ARRIVING host or a third device learn "device X just switched to me"
except the device's own post-switch reconnect events (0x1D4B on that specific device, once IT
also reconnects) — useless for cross-device sync since the mouse won't reconnect until CleverSwitch
tells it to.

## Host Switch Channel CIDs (0xD1/0xD2/0xD3) sometimes present but NOT divertable
- Solaar issue pwr-Solaar/Solaar#1751 (MX Mechanical Mini, WPID B367): device's getCidInfo for the
  three Host Switch Channel CIDs reports them present (FN, FN-sensitive) but WITHOUT the
  divertable flag bit set, unlike other keys on the same device. Attempting to divert them has no
  effect; the ES press is handled natively by the device firmware and never surfaces as an 0x1B04
  notification to the host at all. Confirmed quirk category (device-model-dependent), NOT
  confirmed for MX Keys S specifically — flag as inferred-by-analogy if cited for MX Keys S.
- MX Keys S Solaar device descriptor (per web search, not independently read from source):
  documented as supporting divert-keys but NOT listed for reprogrammable-keys /
  persistent-remappable-keys settings — consistent with ES CIDs being divertable-only rather than
  fully remappable, matches CleverSwitch's KEY_FLAG_DIVERTABLE / KEY_FLAG_PERSISTENTLY_DIVERTABLE.
- **MX Keys S (wpid 0xB378) confirmed quirk (2026-08, CleverSwitch issue #102), a NEW category**:
  `setCidReporting` on the 0xD1/D2/D3 CIDs is acked VERBATIM with byte9=0x03 (avalid+
  analyticsKeyEvt both set, i.e. NOT the K850-style rejection where byte9 is cleared to 0x00 —
  see [[x1b04-setCidReporting]]) but the device then never emits an `analyticsKeyEvt` HID++
  notification on ES press at all; it announces the switch via the undocumented 0x1814 fn=0
  notification instead. This is functionally distinct from both known categories: not "rejected"
  (K850) and not "not divertable but analytics fires" (MX Keys Mini/MX Mechanical Mini, see below)
  — here analytics is acked but silently never fires, full stop. No independent public source
  documents this exact category; treat as observed-in-the-field, not spec-confirmed.
- **Likely explanation (inferred, not verified)**: Logitech's Options+ "Enhanced Easy-Switch"
  feature (support.logi.com article "Enhanced-Easy-Switch-Feature-Guide-Support"; requested for
  Solaar in pwr-Solaar/Solaar#3228, explicitly listing MX Keys S as a supported device) lets a
  paired mouse auto-follow a keyboard's channel switch. #3228 confirms this is a real, currently
  Options+-exclusive feature but neither the issue nor its linked support article expose protocol
  internals (no feature ID, no byte layout). Plausible hypothesis: on devices with this
  capability, the firmware's official "tell software a switch happened" channel is the 0x1814
  notification (which is exactly what Options+ would need to relay to a paired mouse), and
  analyticsKeyEvt on the ES CIDs is simply legacy/vestigial on these newer devices — acked for
  backward compatibility but not actually wired to fire. Not confirmed against any Logitech
  source; flag as inference if cited elsewhere.
- Not established whether this quirk is transport-dependent. #91 (same wpid, Bolt receiver,
  Linux) also shows the 0x1814 fn=0 notification, but does not by itself prove analytics is
  silently acked-but-not-fired over that transport too (no 0x1B04 setCidReporting echo captured
  in #91) — both observations are consistent with a uniform (not transport-dependent) firmware
  behavior, but this is corroborating, not conclusive.
- No other known 0x1B04 configuration change makes this class of device deliver the ES press as
  an 0x1B04 notification: per the divertable-flag survey above, the newer small-form-factor
  keyboards (MX Keys Mini, MX Mechanical Mini) already show the ES CIDs lack divert capability
  entirely (bfield divert bits are moot), leaving analyticsKeyEvt as the only 0x1B04-level lever —
  and on MX Keys S that lever appears to be a no-op per the finding above.

## Re-entry risk: does setCurrentHost trigger the mouse's own 0x1814 notification? (2026-08, UNVERIFIED)
No documentation (spec, Solaar, or field capture) confirms or refutes whether a host switch
initiated via `setCurrentHost` (fn=1, software-initiated) produces the SAME fn=0/sw_id=0
notification as a physical Easy-Switch keypress. This is a real open architecture question, not
just a theoretical one, because of how `HostChangeSubscriber` is wired today
(`src/cleverswitch/subscriber/host_change_subscriber.py`): it reacts to `HostChangeEvent` by
sending `setCurrentHost` to **every** registered device unconditionally. Unlike the receiver
topology assumed in "Host topology" below, CleverSwitch's daemon runs on the SAME host machine as
both keyboard and mouse (that's the whole premise — they're both paired to the host the daemon
runs on), so if the mouse also emits its own fn=0/sw_id=0 notification as a side effect of the
commanded switch, THIS daemon (still connected to the mouse in that instant) would receive it on
the same `hid_event` channel and could re-parse it into a second `HostChangeEvent`, resending
`setCurrentHost` to both devices again. Two things are known and NOT in question:
- The setCurrentHost RESPONSE to CleverSwitch's own request comes back with CleverSwitch's own
  non-zero sw_id and fn=1 — that's caught by the `sw_id & SW_ID_MASK` branch in `parser.py`
  (existing code, unrelated to this risk) and would not itself be mis-parsed as a notification.
- **Confirmed (not just suspected): `CHANGE_HOST_FN_SET` (setCurrentHost, fn=1) has NO reply at
  all** — `hidpp/constants.py` line 79 comment: `"SetCurrentHost — switches to target; no reply"`.
  This means the response-path bullet above is moot for setCurrentHost specifically: CleverSwitch
  sends the command and gets nothing back through the `sw_id & SW_ID_MASK` branch (there is no
  response to land there). The ONLY possible traffic CleverSwitch could see afterward on that
  link is a self-triggered notification, if the mouse emits one — which makes this risk sharper
  than a generic request/response race: there is no software-originated echo to use as a
  came-from-us signal, and the notification shape (fn=0, sw_id=0) is indistinguishable from a
  physical-keypress-triggered one purely by looking at the bytes. A guard against this loop, if
  needed, would have to be state-based (e.g. "we just sent setCurrentHost(X) to this device within
  the last N ms, suppress/ignore its next fn=0 notification for target==X") rather than
  byte-level, since the wire format offers no distinguishing bit.
Left as an open question for whoever designs the MX-Keys-S 0x1814 handling — this is a design/
architecture question (see CLAUDE.md: delegate design work to @software-architect), not something
resolvable from documentation alone. Recommend empirical verification (capture traffic on the
mouse's link immediately after CleverSwitch sends setCurrentHost) before shipping an 0x1814
listener without a de-dupe/guard.
