# Deviations — channel state specifications

Derived from four specifications in `uts/realtime/unit/channels/`, 35 tests for their
35 Test IDs:

| Specification | Derived into | Tests |
|---|---|---|
| `channel_connection_state.md` | `test/uts/realtime/unit/channels/channel_connection_state_test.py` | 13 |
| `channel_state_events.md` | `test/uts/realtime/unit/channels/channel_state_events_test.py` | 13 |
| `channel_error.md` | `test/uts/realtime/unit/channels/channel_error_test.py` | 5 |
| `channel_when_state_test.md` | `test/uts/realtime/unit/channels/channel_when_state_test.py` | 4 |

Categories and their conventions follow `uts/docs/writing-derived-tests.md` and the house
reading of it in [deviations.md](deviations.md): `@deviation` is a skip gated on
`RUN_DEVIATIONS`, naming the SDK.

`channel_error.md` (RTL14) is derived with no deviations at all: a channel-scoped ERROR
reaches the channel through `ConnectionManager.on_error`'s RTN15i branch
(`ably/realtime/connectionmanager.py:469`) and `RealtimeChannel._on_message`
(`ably/realtime/channel.py:775-777`) transitions the channel to FAILED with the error as
both the state change's `reason` and the channel's `error_reason`, leaving other channels
and the connection alone, and cancelling the RTL13b retry timer on the way. All five
tests pass unmodified.

Two translation notes which are not deviations:

- `realtime/unit/RTL3c/suspended-attaching-to-suspended-1` is built with
  `realtime_request_timeout=300000`. The channel's RTL4f attach timeout and the
  connection's transition timeout are the same option (TO3l11), so at any ordinary value
  RTL4f suspends the ATTACHING channel on its own long before the connection reaches
  SUSPENDED, and the RTL3c transition the test exists for never happens. Raising the
  option past the connection state TTL leaves the connection's suspend timer as the only
  thing that fires.
- The specifications' `AWAIT_STATE connection == disconnected` (both RTL3e tests) is an
  assertion on a recorded sequence rather than a wait. RTN15a reconnects immediately after
  a drop from CONNECTED, so DISCONNECTED is passed through rather than settled in; the
  tests leave the following attempt unanswered so that nothing re-attaches the channel
  behind the assertions.

## UTS Spec Errors

*(none)*

## Failing Tests

### RTL3a: a connection-level ERROR fails the connection without touching its channels

- **Spec point**: RTL3a.
- **What the spec says**: when the connection enters FAILED, an ATTACHING or ATTACHED
  channel transitions to FAILED and `RealtimeChannel#errorReason` is set.
- **What the SDK does**: nothing. After an ERROR `ProtocolMessage` takes the connection to
  FAILED, an ATTACHED channel is still ATTACHED and an ATTACHING channel still ATTACHING,
  with `error_reason` null and no state change emitted. A pending `attach()` never returns.
- **Root cause**: `ConnectionManager.on_error` (`ably/realtime/connectionmanager.py:468`)
  ends with `self.enact_state_change(ConnectionState.FAILED, exception)` at `:477`, which
  only sets the state and emits it. The call to
  `self.ably.channels._propagate_connection_interruption(state, reason)` lives in
  `notify_state` (`:690`), which this path never reaches. The same bypass also skips
  `cancel_transition_timer`, `check_suspend_timer` and the RTN7e `fail_queued_messages`.
  Every other route to FAILED — an incompatible `clientId` (`:422`) and the two authorize
  failures (`:483`, `:487`) — goes through `notify_state` and does propagate, so this is
  specific to the ERROR message.
- **Tests affected**: `test_rtl3a_failed_attached_to_failed`,
  `test_rtl3a_failed_attaching_to_failed`, both `@deviation`. Enabled, each fails on
  `assert channel.state == ChannelState.FAILED` with `attached` and `attaching`
  respectively.
  `test_rtl3a_other_states_unaffected` passes, but only because nothing happens at all; it
  will become a real test of RTL3a once this is fixed.
- **Status**: open bug.

### RTL25: RealtimeChannel has no whenState

- **Spec points**: RTL25, RTL25a, RTL25b.
- **What the spec says**: `features.md:821` and the type listing at `:2299`
  (`whenState(ChannelState, (ChannelStateChange?) ->)`) put `whenState` on
  RealtimeChannel: a `null` argument if the channel already holds the state (RTL25a),
  otherwise a `once` for it (RTL25b).
- **What the SDK does**: `RealtimeChannel` has no such member.
  `channel.when_state(...)` raises
  `AttributeError: 'RealtimeChannel' object has no attribute 'when_state'`. The connection
  equivalent does exist as `Connection._when_state` (`ably/realtime/connection.py:90`), so
  this is a gap on the channel rather than a house style. Note the connection's is private
  and awaitable rather than listener-taking, which
  `test/uts/realtime/unit/connection/when_state_test.py` records as idiomatic rather than
  a deviation; there is nothing on the channel to be idiomatic about.
- **Tests affected**: all four in `channel_when_state_test.py` —
  `test_rtl25a_resolves_immediately_current`, `test_rtl25b_waits_for_state_change`,
  `test_rtl25b_fires_once_only`, `test_rtl25a_past_state_does_not_resolve` — all
  `@deviation`. Enabled, each fails with the AttributeError above.
- **Status**: open bug. The tests are written against a `channel.when_state(state)`
  returning an awaitable, matching the shape `Connection._when_state` already has.

### RTL2i, TH6: ChannelStateChange does not expose hasBacklog

- **Spec points**: RTL2i, TH6.
- **What the spec says**: `ChannelStateChange` may expose a boolean `hasBacklog`, true if
  and only if the state change corresponds to an ATTACHED carrying the `HAS_BACKLOG` flag.
- **What the SDK does**: `ChannelStateChange` is `(previous, current, resumed, reason)`
  (`ably/types/channelstate.py:18-23`), so there is no `has_backlog` to read.
  `Flag.HAS_BACKLOG` is defined (`ably/types/flags.py:7`) but `_on_message` reads only
  `RESUMED` and `HAS_PRESENCE` out of the ATTACHED flags (`ably/realtime/channel.py:715-721`).
- **Tests affected**: `test_rtl2i_has_backlog_flag_true`, `@deviation`. Enabled, it fails
  with `AttributeError: 'ChannelStateChange' object has no attribute 'has_backlog'`.
  `test_rtl2i_has_backlog_flag_false` passes: its spec assertion is the disjunction
  "`hasBacklog == false` OR `hasBacklog IS null`", which a missing attribute satisfies, and
  it is derived that way.
- **Status**: open, but note that both RTL2i and TH6 word the property as optional ("may
  optionally expose", "may contain an attribute"), so omitting it is not strictly
  non-compliance. `realtime/unit/RTL2i/has-backlog-flag-true-0` cannot be passed by a
  conforming SDK that takes up the option not to expose it; that is worth raising against
  the UTS specification.

## Adapted Tests

### RTL3b and RTL4d: a pending attach resolves, rather than failing, when the connection closes

- **Spec points**: RTL3b (the transition), RTL4d (the outcome of the pending attach).
- **What the spec says**: RTL3b moves an ATTACHING channel to DETACHED when the connection
  closes. RTL4d has the attach's callback invoked for whichever of ATTACHED, DETACHED,
  SUSPENDED or FAILED comes next, and "in all other cases" than ATTACHED it is called with
  an `ErrorInfo` "to indicate that the attach has failed". `channel_connection_state.md`
  spells this out as `AWAIT attach_future FAILS WITH error`.
- **What the SDK does**: the RTL3b transition is correct — the channel reaches DETACHED
  from ATTACHING and emits the state change. The pending `attach()` then returns `None`:
  `attach()` ends with `if state_change.current in (ChannelState.SUSPENDED,
  ChannelState.FAILED): raise state_change.reason` (`ably/realtime/channel.py:148-150`),
  and DETACHED is in neither, so the coroutine falls through as a success.
- **Tests affected**: `test_rtl3b_closed_attaching_to_detached`, adapted — it asserts
  `await attach_future is None` with the specification's expectation in a comment above,
  and makes every other assertion the specification does. Would fail if the SDK started
  raising, so it does guard the behaviour.
- **Status**: open bug.

### RTL2, RTL2d, TH5: ChannelStateChange has no event attribute

- **Spec points**: RTL2, RTL2d, RTL2g, TH5.
- **What the spec says**: assertions on `state_change.event` — `ChannelEvent.attaching`,
  `ChannelEvent.attached`, `ChannelEvent.update`.
- **What the SDK offers**: `ChannelStateChange` is `(previous, current, resumed, reason)`
  and there is no `ChannelEvent` type at all; the event is the key a listener is
  registered against. Already recorded for the neighbouring specifications in
  [deviations-channels-attach.md](deviations-channels-attach.md); repeated here for the
  tests it touches.
- **Tests affected**: `test_rtl2d_state_change_object_structure`,
  `test_rtl2_filtered_event_subscription`, `test_rtl2g_update_event_condition_change`,
  `test_rtl2g_no_duplicate_state_events`. Each registers against the event the
  specification names — `ChannelState.ATTACHING`, `ChannelState.ATTACHED`, `'update'` —
  so that receiving the change at all is the `event` assertion.
  `test_rtl2g_no_duplicate_state_events` needs this twice over: the specification counts
  `all_events` filtered on `event == attached` to tell the RTL12 UPDATE apart from a
  duplicate ATTACHED state event, and the derived test counts what arrives on the
  `ChannelState.ATTACHED` key instead.
- **Status**: a missing API rather than wrong behaviour; the RTL2g and RTL12 behaviour
  underneath is correct.

### RTN21: the connectionStateTtl in connectionDetails is ignored

- **Spec point**: RTN21, as used by the RTL3c and RTL3d setups.
- **What the spec says**: the three tests that drive the connection to SUSPENDED send a
  CONNECTED whose `connectionDetails.connectionStateTtl` is 120000 and comment that the
  advance must exceed "connectionStateTtl (from connectionDetails, per RTN21)".
- **What the SDK does**: `ConnectionDetails.connection_state_ttl` is parsed and read
  nowhere; the suspend timer uses `Defaults.connection_state_ttl`
  (`ably/realtime/connectionmanager.py:745`). Already recorded in
  [deviations.md](deviations.md).
- **Tests affected**: `test_rtl3c_suspended_attached_to_suspended`,
  `test_rtl3c_suspended_attaching_to_suspended`,
  `test_rtl3d_reattach_suspended_channels`. Each advances the fake clock to the 120000
  default, which happens to be the value the specification sends, so the loop bounds the
  specification gives are unchanged and every assertion is the specification's own.
- **Status**: cited, not re-reported.

## Mock Infrastructure Limitations

*(none)*
