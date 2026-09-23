# Deviations: channels-attach batch

Covers the tests derived from `uts/realtime/unit/channels/channel_attach.md`,
`channel_detach.md`, `channel_server_initiated_detach.md` and
`channel_additional_attached.md`.

## UTS Spec Errors

### `realtime/unit/RTL5l/detach-attached-when-disconnected-1` uses mock methods that do not exist

- **Spec point**: RTL5l.
- **What the spec says**: the setup calls `conn.respond_with_connected()` and assigns
  `mock_ws.active_connection = conn` from inside `onConnectionAttempt`.
- **The mock specification** (`uts/realtime/unit/helpers/mock_websocket.md`) names the
  method `respond_with_success(connected_message)`, and `active_connection` is a
  read-only property the mock maintains itself.
- **Tests affected**: `test_rtl5l_detach_attached_when_disconnected`.
- **Status**: translated to `respond_with_success(CONNECTED_MESSAGE)`; no test consequence.
  Worth correcting upstream.

### `realtime/unit/RTL13b/repeated-failure-cycle-2` advances onto an exact timer boundary

- **Spec point**: RTL13b.
- **What the spec says**: with `realtimeRequestTimeout: 100` and `channelRetryTimeout: 200`,
  after `ADVANCE_TIME(150)` takes the channel to SUSPENDED, `ADVANCE_TIME(250)` is followed
  by `AWAIT_STATE channel.state == ChannelState.attaching`.
- **What actually happens**: SUSPENDED is entered at t=100, so the retry falls due at t=300
  and the attach it sends times out at t=400 — precisely the end of the 250ms window. The
  channel is therefore back in SUSPENDED when the advance returns, and whether it reads
  ATTACHING or SUSPENDED depends on whether the fake clock fires a timer due exactly on the
  window boundary.
- **Tests affected**: `test_rtl13b_repeated_failure_cycle`.
- **Status**: the boundary-dependent state assertion is replaced by the specification's own
  `attach_count == 3` assertion at the same point; the ordered state sequence the test ends
  with is unaffected. Upstream should widen the gap between the two timeouts.

### `realtime/unit/RTL4b/fails-connection-suspended-2` cannot reach SUSPENDED as written

- **Spec point**: RTL4b.
- **What the spec says**: set `channelRetryTimeout: 100` ("short timeout for testing"),
  refuse every connection, and `AWAIT_STATE client.connection.state == suspended`.
- **The problem**: `channelRetryTimeout` governs channel retries, not the connection's
  suspend timer, which runs for `connectionStateTtl` (two minutes). The test does not
  enable fake timers, so on real time it would wait out that full two minutes.
- **Tests affected**: `test_rtl4b_fails_connection_suspended`.
- **Status**: derived with a `FakeClock` advanced until the connection suspends. The option
  the specification names is passed through unchanged so the setup still matches.

## Failing Tests

### RTL4j: the deprecated ATTACH_RESUME flag is still set on a reattach

- **Spec point**: RTL4j (deleted as of specification 6.1.0).
- **What the spec says**: the client must not set the ATTACH_RESUME flag (TR3f, bit 5) on
  any ATTACH, the server having taken over the resumability decision.
- **What the SDK does**: `RealtimeChannel._notify_state` sets `__attach_resume` on every
  ATTACHED (`channel.py`, "RTL4j1"), and `_encode_flags` ORs `Flag.ATTACH_RESUME` into the
  flags of every subsequent ATTACH. The reattach carries `flags: 32`.
- **Tests affected**: `test_rtl4j_attach_resume_flag_not_set` (`@deviation`).
- **Status**: gated. Confirmed failing with `RUN_DEVIATIONS=1`:
  `AssertionError: assert not (32 & <Flag.ATTACH_RESUME: 32>)`.

### RTL5i: detach while already DETACHING sends a second DETACH

- **Spec point**: RTL5i.
- **What the spec says**: a detach requested while the channel is DETACHING is performed
  after the pending request completes, so only one DETACH reaches the server.
- **What the SDK does**: `detach()` calls `_request_state(DETACHING)` unconditionally.
  `_notify_state` returns early for a state the channel already holds, but only after
  `__clear_state_timer()`, and `_request_state` then calls `_check_pending_state()` anyway,
  which restarts the state timer and re-sends DETACH.
- **Tests affected**: `test_rtl5i_detach_while_detaching` (`@deviation`).
- **Status**: gated. Confirmed failing with `RUN_DEVIATIONS=1`: `AssertionError: assert 2 == 1`.

### RTL5l: detach with the connection not CONNECTED never completes

- **Spec point**: RTL5l.
- **What the spec says**: when the connection is in any state other than CONNECTED and no
  earlier channel-state condition applies, the channel transitions immediately to DETACHED.
- **What the SDK does**: `detach()` requests DETACHING, `_check_pending_state()` returns
  without sending anything because the connection is not CONNECTED, and `detach()` then
  awaits the internal state emitter for a transition that nothing will produce. The
  coroutine never returns and the channel is left in DETACHING.
- **Tests affected**: `test_rtl5l_detach_not_connected_immediate`,
  `test_rtl5l_detach_attached_when_disconnected` (both `@deviation`).
- **Status**: gated, each with a one-second `asyncio.wait_for` so the hang is reported as a
  failure. Confirmed failing with `RUN_DEVIATIONS=1`: `asyncio.exceptions.TimeoutError` for
  both. In the second, the assertions that set the scene — the connection settling in
  DISCONNECTED with the channel still ATTACHED — pass first, so the failure is the detach.

### RTL5k: an ATTACHED received while DETACHING or DETACHED is ignored

- **Spec point**: RTL5k.
- **What the spec says**: an ATTACHED arriving while the channel is DETACHING or DETACHED
  must be answered with a new DETACH, the channel remaining in or returning to DETACHING.
- **What the SDK does**: `RealtimeChannel._on_message` handles ATTACHED only for the
  ATTACHED (RTL12) and ATTACHING cases; every other state falls through to
  `log.warn("ATTACHED received while not attaching")` and nothing is sent. While DETACHING
  that leaves the detach to time out, so `detach()` raises "Channel detach timed out" and
  the channel returns to ATTACHED.
- **Tests affected**: `test_rtl5k_attached_while_detaching`,
  `test_rtl5k_attached_while_detached` (both `@deviation`).
- **Status**: gated. Confirmed failing with `RUN_DEVIATIONS=1`:
  `ably.util.exceptions.AblyException: 90007 408 Channel detach timed out` and
  `AssertionError: Timed out waiting until a second DETACH`.

## Adapted Tests

### RTL4h: an attach requested while DETACHING pre-empts the detach

- **Spec point**: RTL4h.
- **What the spec says**: an attach requested while the channel is DETACHING is performed
  after the pending detach completes; the detach itself completes normally.
- **What the SDK does**: `attach()` requests ATTACHING straight away, which resolves the
  pending detach's wait with an ATTACHING state change; `detach()` then raises "Detach
  request superseded by a subsequent attach request". The end state and the two ATTACH
  messages the specification counts are as expected.
- **Tests affected**: `test_rtl4h_attach_while_detaching`.
- **Status**: adapted — the test asserts the superseding error, with the specification's
  expectation in a comment above it.

### RTL13a and RTL13b: the DETACHED message's error is not carried onto the state change

- **Spec points**: RTL13a, RTL13b.
- **What the spec says**: the ATTACHING (RTL13a) or SUSPENDED (RTL13b) state change
  triggered by a server-initiated DETACHED carries the `error` member of that DETACHED as
  its `reason`.
- **What the SDK does**: `_on_message` discards the error and calls `_request_state(ATTACHING)`
  or `_notify_state(SUSPENDED)` with no reason, so `ChannelStateChange.reason` is null.
- **Tests affected**: `test_rtl13a_attached_reattach_triggered`,
  `test_rtl13b_attaching_detached_to_suspended`.
- **Status**: adapted — each asserts `reason is None` with the specification's expectation
  in a comment above. Every other assertion in both tests is the specification's own.

### RTL13b: a pending attach raises TypeError when the channel is suspended with no reason

- **Spec point**: RTL13b (consequence of the deviation above).
- **What the SDK does**: `attach()` ends with
  `if state_change.current in (SUSPENDED, FAILED): raise state_change.reason`
  (`channel.py:102`). With the reason dropped, this is `raise None`, which Python reports as
  `TypeError: exceptions must derive from BaseException` rather than an `AblyException`.
- **Tests affected**: `test_rtl13b_attaching_detached_to_suspended`.
- **Status**: adapted — the test asserts the `TypeError` with an explanatory comment. It
  will need revisiting once the reason is carried through.

### RTL5b and RTL4h: `status_code` and `code` are transposed on two channel errors

- **Spec points**: RTL5b, RTL4h.
- **What the SDK does**: `AblyException` takes `(message, status_code, code)`, but
  `channel.py:203` raises `AblyException("Unable to detach; channel state = failed", 90001, 400)`
  and `channel.py:217` raises
  `AblyException("Detach request superseded by a subsequent attach request", 90000, 409)`.
  Both put the Ably error code in `status_code` and the HTTP status in `code`.
- **Tests affected**: `test_rtl5b_detach_failed_errors`, `test_rtl4h_attach_while_detaching`.
- **Status**: adapted — each asserts on `status_code`, with a comment recording the
  transposition. `__timeout_pending_state` (`channel.py:860`) passes them the right way
  round, so this is local to those two raises.

### RTL4c1 and RTL4j: `set_options` never returns for a channel that is already ATTACHED

- **Spec point**: RTL16a, used by both tests to trigger a reattach that keeps the channel
  serial (RTL15b2 clears it on DETACHED).
- **What the SDK does**: `set_options` calls `_attach_impl()` — which sends ATTACH without a
  state change — and then awaits the internal state emitter. The server's ATTACHED arrives
  while the channel is ATTACHED, so `_on_message` takes the RTL12 branch and emits only
  `update` on the public emitter. The internal emitter never fires and the coroutine hangs.
  Verified directly: `asyncio.wait_for(channel.set_options(...), 1.0)` raises `TimeoutError`.
- **Tests affected**: `test_rtl4c1_includes_channel_serial`, `test_rtl4j_attach_resume_flag_not_set`.
- **Status**: adapted — both run `set_options` as a task, assert on the two ATTACH messages
  the specification cares about, and cancel the task. Neither asserts that `set_options`
  returns. This is a separate SDK defect from the two the tests are about.

### RTL5 and RTL12: `ChannelStateChange` has no `event` attribute

- **Spec points**: RTL5, RTL12.
- **What the spec says**: assertions on `state_change.event`.
- **What the SDK offers**: `ChannelStateChange` is `(previous, current, resumed, reason)`.
  The event is the key a listener is registered against, so a test that wants it registers
  `channel.on(ChannelState.DETACHING, ...)` instead.
- **Tests affected**: `test_rtl5_detach_state_change_events`, `test_rtl12_update_emits_with_error`,
  `test_rtl5d_normal_detach_flow`.
- **Status**: adapted — the `event` assertions are expressed through the registration key
  where that is possible and noted in a comment where it is not. Recorded here as a missing
  API rather than wrong behaviour.

## Mock Infrastructure Limitations

*(none)*
