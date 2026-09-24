# Deviations — presence channel state, re-entry and history

Recorded while deriving `uts/realtime/unit/presence/realtime_presence_channel_state.md`,
`realtime_presence_reentry.md` and `realtime_presence_history.md` into
`test/uts/realtime/unit/presence/`.

## UTS Spec Errors

### RTP17g enters another client from an identified client, against RTP15f

- **Spec point:** RTP17g, against RTP15f.
- **What the spec says:** `realtime/unit/RTP17g/reentry-publishes-enter-with-data-0` builds a
  client with `clientId: "admin"` and calls `enterClient("alice", ...)` and
  `enterClient("bob", ...)`, with a note reading "Use a concrete clientId and rely on
  server-side permission for enterClient".
- **Why it cannot hold:** RTP15f (features.md:961) requires that "if the client is identified
  and has a valid `clientId`, and the `clientId` argument does not match the client's
  `clientId`, then it should indicate an error". A conforming library must reject
  `enterClient("alice")` from an `admin` client locally; there is nothing for server-side
  permission to decide. The note's premise is wrong, not the SDK.
- **What the SDK does:** `_enter_or_update_client` calls `auth.can_assume_client_id()` and
  raises `AblyException` 40012 (`ably/realtime/presence.py:229-234`), which is RTP15f-correct.
- **Tests affected:** `test_rtp17g_reentry_publishes_enter_with_data`.
- **Status:** Adapted and running. The client holds the wildcard `clientId` instead, which is
  the only clientId RTP15f permits `enterClient` for another user from. Everything RTP17g is
  actually about — that both members are re-entered with an ENTER carrying their original
  clientId and data — is asserted as written. This mirrors the RTP15c entry in
  `deviations-presence-core.md`, which is the same contradiction the other way round; worth
  raising upstream together.

### RTP5f and RTL11 reach SUSPENDED with a step that only reaches DISCONNECTED

- **Spec point:** RTP5f, RTL11, against RTL3c.
- **What the spec says:** `realtime/unit/RTP5f/suspended-maintains-presence-map-0` and
  `realtime/unit/RTL11/queued-presence-fail-suspended-1` both do
  `mock_ws.active_connection.simulate_disconnect()` followed by
  `AWAIT_STATE channel.state == ChannelState.suspended`.
- **Why it cannot hold:** a transport drop takes the connection to DISCONNECTED, and RTL3c
  only propagates SUSPENDED to channels when the *connection* becomes SUSPENDED. A channel
  is ATTACHED (RTL3e) or ATTACHING throughout a DISCONNECTED, so the awaited state never
  arrives. RTP5f's own note ("e.g. connection transitions to SUSPENDED") says as much; the
  steps do not carry it out.
- **What the SDK does:** exactly RTL3c — `_propagate_connection_interruption`
  (`ably/realtime/channel.py:1047-1065`) maps only CLOSING/CLOSED/FAILED/SUSPENDED onto
  channel states.
- **Tests affected:** `test_rtp5f_suspended_maintains_presence_map`,
  `test_rtl11_queued_presence_fail_suspended`.
- **Status:** Adapted and running. Each test drops the transport, leaves every reconnection
  attempt unanswered and runs a `FakeClock` past the connection state TTL, which is the
  recipe `deviations-presence-core.md` records for RTP11d. `realtime_request_timeout` is set
  beyond the TTL in the RTL11 test so the channel follows the connection to SUSPENDED rather
  than timing its own ATTACH out first (RTL4f and the connection transition timeout are the
  same option, TO3l11). The assertions are the specification's.

### RTP5a reads the cleared map back with a call that re-attaches

- **Spec point:** RTP5a, against RTP11e.
- **What the spec says:** `realtime/unit/RTP5a/detached-clears-presence-maps-0` detaches the
  channel and then asserts `channel.presence.get(waitForSync: false).length == 0`.
- **Why it cannot hold:** RTP11e (features.md:937) has `get` run the ensure-active-channel
  procedure for any state but SUSPENDED, so calling it on a DETACHED channel re-attaches it.
  The specification's own server then answers the ATTACH with an ATTACHED plus a SYNC
  carrying alice, so the read-back repopulates the very map it is checking is empty.
- **What the SDK does:** `RealtimePresence.get` awaits `channel.attach()` for INITIALIZED and
  DETACHED (`ably/realtime/presence.py:414-415`), which is RTP11e-correct.
- **Tests affected:** `test_rtp5a_detached_clears_presence_maps`.
- **Status:** Adapted and running. The test reads `presence.members` and
  `presence._my_members` directly, which is what RTP5a is about — both maps cleared — without
  bringing the channel back up. The LEAVE assertion is the specification's.

### RTP12d is named but has no test

- **Spec point:** RTP12d.
- **What the spec says:** `realtime_presence_history.md` lists RTP12d in its `Spec points`
  header, but the file contains no `**Test ID**` for it.
- **Status:** No test derived, following the ruling already taken for the trailing sections of
  `realtime_client.md`. features.md:948 describes RTP12d as a multi-client test made against
  the service, which is not a unit test; the header reference looks like a leftover.

## Failing Tests

### RTP12a, RTP12c — `RealtimePresence` has no `history`

- **Spec point:** RTP12, RTP12a, RTP12c.
- **What the spec says:** `RealtimePresence#history` delegates to `RestPresence#history`,
  supports the same parameters and returns a `PaginatedResult`.
- **What the SDK does:** `RealtimePresence` exposes `enter`, `update`, `leave`, the
  `*_client` forms, `get`, `subscribe` and `unsubscribe`, and nothing else
  (`ably/realtime/presence.py`). `channel.presence.history` raises
  `AttributeError: 'RealtimePresence' object has no attribute 'history'`. Note the realtime
  channel itself does delegate `history` to the REST implementation, so only the presence
  object is missing it.
- **Root cause:** the method was never implemented; `grep -n history ably/realtime/presence.py`
  is empty.
- **Tests affected:** `test_rtp12a_history_supports_rest_params`,
  `test_rtp12c_history_returns_paginated_result` (both `@deviation`).
- **Status:** Gated. With `RUN_DEVIATIONS=1`:
  `AttributeError: 'RealtimePresence' object has no attribute 'history'`.

### RTL11, RTP8g — a DETACHED channel implicitly re-attaches instead of failing

- **Spec point:** RTL11, and RTP8g behind it.
- **What the spec says:** a presence action on a DETACHED channel must fail immediately with
  an `ErrorInfo`, sending nothing.
- **What the SDK does:** `_enter_or_update_client` groups DETACHED with INITIALIZED
  (`ably/realtime/presence.py:258-264`), so it starts an implicit `channel.attach()` and
  queues the message. Measured: the channel goes back to ATTACHED and one PRESENCE
  protocol message leaves the client. The specification's server does not ACK a PRESENCE, so
  the `enter()` then never returns at all.
- **Root cause:** the DETACHED branch of the RTP8d/RTP8g dispatch. `_leave_client` does not
  have the same grouping. Already noted in passing in `deviations-presence-core.md` under
  RTP16c; this is the first test to exercise it.
- **Tests affected:** `test_rtl11_queued_presence_fail_detached` (`@deviation`).
- **Status:** Gated. With `RUN_DEVIATIONS=1`, the spec-correct
  `pytest.raises(AblyException)` around a 2 s `asyncio.wait_for` fails with
  `asyncio.exceptions.TimeoutError`, the enter still pending.

### RTP17e — a failed re-entry reports the NACK, not the 91004 wrapper

- **Spec point:** RTP17e (features.md:884).
- **What the spec says:** when an automatic presence ENTER is NACKed, emit an UPDATE on the
  channel with `resumed` true and `reason` an `ErrorInfo` whose `code` is 91004, whose
  message names the clientId, and whose `cause` is the NACK error.
- **What the SDK does:** `_reenter_member` catches the `AblyException` and emits an UPDATE
  built as `ChannelStateChange(previous=state, current=state, resumed=False, reason=e)`
  (`ably/realtime/presence.py:667-674`). So `resumed` is False and `reason` is the raw NACK
  error — 40160 in this test — with no 91004 wrapper, no clientId in the message and no
  `cause`.
- **Root cause:** the error is passed straight through rather than wrapped. `ErrorInfo`/
  `AblyException` does have a `cause` to populate, so the fix is local to this one method.
- **Tests affected:** `test_rtp17e_failed_reentry_emits_update_error` (`@deviation`).
- **Status:** Gated. With `RUN_DEVIATIONS=1`:
  `AssertionError: assert False is True` — `+ where False =
  ChannelStateChange(previous=<ChannelState.ATTACHED: 'attached'>,
  current=<ChannelState.ATTACHED: 'attached'>, resumed=False,
  reason=AblyAuthException()).resumed`, with the log line
  `RealtimePresence._reenter_member(): auto-reenter failed: 40160 401 Presence denied`.

## Adapted Tests

*(none beyond the three recorded under UTS Spec Errors, each of which is adapted and
running.)*

## Mock Infrastructure Limitations

*(none)*
