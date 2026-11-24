# InfoTask design

`InfoTask` (`subscriber/task/info_task.py`) is abstract, `Thread`, and `Subscriber`:
- Subscribes to `hid_event`; `notify()` filters on `slot + pid + sw_id` plus the feature index and function of the call `_send_request` last sent (peer apps such as Logi Options+ reuse our sw_ids), and enqueues matching `HidppResponseEvent` / `HidppErrorEvent`
- `_send_request(*params)` drains the response queue, then builds a long-format HID++ message and publishes a `WriteEvent`. The drain matters: anything already queued predates the request, so without it a late reply would be handed to the *next* `_wait_response`, and the chunked name reads and the `getCidInfo` sweep would splice it in at the wrong offset and silently record wrong data. A clean timeout is the honest outcome. Tests must therefore deliver responses **on publish** (`tests/task_helpers.py:deliver_on_request`), not by pre-loading `_response_queue`
- `_wait_response(timeout=2.0)` blocks on the private queue; returns `None` on timeout
- **Aborts on its own device's disconnect** (`DeviceConnectedEvent(link_established=False)` for its wpid, or `TransportDisconnectedEvent` for its pid): the wait returns `None` at once, later replies are ignored and no more requests are sent. Without it a task still waiting across a quick drop/reconnect takes the reply meant for the copy the reconnection starts — two `getDeviceName` reads spliced the name into `MX Keys WirelessMX Keys W`. The progress event carries `aborted=True` and the orchestrator does not retry it; the reconnection path restarts the still-pending step
- `run()` checks `step_name in device.pending_steps`; skips `doTask()` if already complete; always publishes `InfoTaskProgressEvent` — after waiting `ERROR_RETRY_DELAY` when it failed and `_wait_response` returned an error reply (a disconnect ends the wait and marks it aborted); releases the `hid_event` subscription in a `finally` — a subclass overriding `run()` must preserve that

Task dependency chain:
- `CidReportingFeatureTask` → fires `FindESCidsFlagsTask`
- `NameAndTypeFeatureTask` → fires `GetDeviceTypeTask` + `GetDeviceNameTask`
- `FriendlyNameFeatureTask` → fires `GetDeviceFriendlyNameTask`
- `ChangeHostFeatureTask` has no dependents

A keyboard must never be cached without `FEATURE_REPROG_CONTROLS_V4` (0x1B04), or it is never armed:
- `GetDeviceTypeTask` keeps its step pending on an error reply. Its dependents drop the CID steps only when the role is known and not `"keyboard"`; with the role unknown they stay pending, so the device is not cached
- `CidReportingFeatureTask` treats a "not supported" getFeature reply for a keyboard as suspect (a peer app's reply on a shared sw_id can look like one) and keeps the step pending; the orchestrator's cap bounds the retries
- `FeatureTask` checks `available_features` keys (feature codes), not values (indexes), to skip an already-resolved feature

Each task type has an `sw_id` constant in `subscriber/task/constants.py`. The sw_id is a 4-bit nibble whose bit 3 must be set (`SW_ID_MASK`), so **8–15 is the entire space and every value is already allocated** — including `SW_ID = 0x08`, `SW_ID_DIVERT = 0x0E` and `SW_ID_HOST_CHANGE = 0x0F` in `hidpp/constants.py`. Two are already double-booked: `SW_ID_DIVERT` equals `FEATURE_DEVICE_FRIENDLY_NAME_SW_ID`, and `SW_ID_HOST_CHANGE` equals `GET_DEVICE_FRIENDLY_NAME_SW_ID`. A shared sw_id is survivable because `Topic.publish` copies each event into *every* subscriber's own queue: a collision can only put noise in the wrong task's queue, never steal a response from the right one. Filter precisely (by function code where needed), and rely on `_send_request`'s drain for the rest.
