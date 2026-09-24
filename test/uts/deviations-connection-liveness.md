# Deviations — connection liveness batch

Covers the tests derived from four specifications:

| Spec | Derived tests | File |
|---|---|---|
| `uts/realtime/unit/connection/heartbeat_test.md` | 17 | `realtime/unit/connection/heartbeat_test.py` |
| `uts/realtime/unit/connection/connection_ping_test.md` | 14 | `realtime/unit/connection/connection_ping_test.py` |
| `uts/realtime/unit/connection/fallback_hosts_test.md` | 8 | `realtime/unit/connection/fallback_hosts_test.py` |
| `uts/realtime/unit/connection/connection_recovery_test.md` | 6 | `realtime/unit/connection/connection_recovery_test.py` |

45 tests: 30 pass, 11 are gated behind `RUN_DEVIATIONS` and 4 cannot be run at all.
Every gated test was confirmed to fail when enabled.

```
RUN_DEVIATIONS=1 uv run --frozen --extra crypto --extra dev pytest \
  test/uts/realtime/unit/connection/heartbeat_test.py \
  test/uts/realtime/unit/connection/connection_ping_test.py \
  test/uts/realtime/unit/connection/fallback_hosts_test.py \
  test/uts/realtime/unit/connection/connection_recovery_test.py -q
```

Two conventions of the suite carry the specifications' `enable_fake_timers()` here and
are not deviations; see the fake-time section of [deviations.md](deviations.md). The heartbeat tests run the idle
timer on real time with a small `maxIdleInterval`, because
`WebSocketTransport.on_idle_timer_expire` measures against the real clock while
scheduling through the timer seam, so an advance fires the timer with no time elapsed
and it merely reschedules. `ping()`'s own timeout is `asyncio.wait_for` on the loop
clock rather than a `Timer`, so the ping tests shorten `realtime_request_timeout`
instead of advancing. The fake clock is still used for the one interval no option
reaches, `connection_state_ttl`.

## UTS Spec Errors

### `close_from_server()` is not part of the mock websocket contract

**Spec point:** RTN13d (`ping-deferred-disconnected-1`).

**What the spec says:** `mock_ws.active_connection.close_from_server()`.

**Why it is wrong:** `uts/realtime/unit/helpers/mock_websocket.md` gives a
`MockConnection` `send_to_client`, `send_to_client_and_close`, `simulate_disconnect` and
`send_ping_frame`. There is no `close_from_server`, and `simulate_disconnect()` is what
the helper spec names for a server ending the connection without a protocol message.

**Tests affected:** the test is gated for an unrelated reason (below) and reaches
DISCONNECTED another way; the derivation reads the call as `simulate_disconnect()`.

**Status:** fault in the specification; raise upstream.

### Two recovery tests assert on a `ws_frame` event the mock does not emit

**Spec point:** RTN16f (`recover-initializes-msgserial-0`), RTN16j
(`recover-channel-serials-0`).

**What the spec says:** `mock_ws.events.filter(e => e.type == "ws_frame" AND
e.direction == "client_to_server")`.

**Why it is wrong:** the mock's event types are enumerated in `mock_websocket.md` and a
message the client sent is `MESSAGE_FROM_CLIENT`. Neither a `ws_frame` type nor a
`direction` field exists, and every other specification in the suite reads
`MESSAGE_FROM_CLIENT`.

**Tests affected:** both are gated for an unrelated reason (below); both read
`MESSAGE_FROM_CLIENT` messages.

**Status:** fault in the specification; raise upstream.

### RTN17i names a primary domain that REC1 no longer produces

**Spec point:** RTN17i (`prefer-primary-domain-0`).

**What the spec says:** `ASSERT connection_attempts[0].host == "realtime.ably.io" OR
connection_attempts[0].host CONTAINS "realtime.ably"`.

**Why it is wrong:** REC1 derives the primary domain from the endpoint, which defaults to
`main`, giving `main.realtime.ably.net`. `realtime.ably.io` is the superseded host. The
disjunct saves the assertion, so the test still means what it should, but the first
branch can never hold for an SDK that implements REC1.

**Tests affected:** `test_rtn17i_prefer_primary_domain` asserts equality with the domain
REC1 gives, and passes.

**Status:** fault in the specification; raise upstream.

### RTN17f fails the primary host with a server ERROR message

**Spec point:** RTN17f (`fallback-on-error-0`).

**What the spec says:** `conn.respond_with_error("Host unresolvable")`, under the comment
`# Primary domain: unresolvable (simulated)`.

**Why it is wrong:** `respond_with_error` in the mock contract *establishes* the
connection and has the server send an ERROR `ProtocolMessage`; it takes a protocol
message, not a string, and an established connection is not an unresolvable host. The
condition the test means to simulate is RSC15l's "host unreachable", which the contract
spells `respond_with_dns_error()`.

**Tests affected:** `test_rtn17f_fallback_on_error` fails the primary with
`respond_with_dns_error()` and carries the note at the site. It passes, and the
assertions the specification makes are unchanged.

**Status:** fault in the specification; raise upstream.

## Failing Tests

### No `heartbeats` connect parameter is sent

**Spec point:** RTN23a (`heartbeats-true-query-param-0`), RTN23b.

**What the spec says:** a client that cannot observe websocket ping frames must send
`heartbeats=true` so that the server sends HEARTBEAT protocol messages instead.

**What the SDK does:** sends no `heartbeats` parameter in any form. The complete connect
parameter set is `{key|accessToken, v, format, resume?, …transport_params}`.

**Root cause:** `ConnectionManager.__get_transport_params` (`connectionmanager.py:204`)
never adds one; `grep -r heartbeats ably/` finds nothing.

**Tests affected:** `test_rtn23a_heartbeats_true_query_param` is gated and fails with
`assert None == 'true'`. `test_rtn23b_heartbeats_false_query_param` passes, because
RTN23b permits the parameter to be omitted — but ably-python cannot observe ping frames
(the `websockets` library answers them inside the protocol and surfaces no event), so
RTN23a is the branch that binds it and `true` is the value it owes.

**Status:** open bug.

### A PING is never answered with a PONG

**Spec point:** RTN23c1 (`ping-pong-echo-id-0`,
`pong-regardless-of-heartbeats-param-1`), RTN23c2.

**What the spec says:** every client, whatever `heartbeats` value it sent, must answer a
PING with a PONG on the same transport, echoing the PING's `id` when it has one and
carrying no `msgSerial`.

**What the SDK does:** nothing. `ProtocolMessageAction` stops at `ANNOTATION` (21), so
PING (22) and PONG (23) are not modelled at all, and action 22 matches no branch of
`WebSocketTransport.on_protocol_message`. The message is counted as activity and
discarded.

**Root cause:** `websockettransport.py:37-59` and `:143-199`.

**Tests affected:** both gated tests fail with
`AssertionError: Timeout waiting for message from client`. Note that the PING *is*
handled correctly as far as RTN23a is concerned:
`test_rtn23a_ping_resets_timer` passes, because `on_activity()` runs before the action is
looked at.

**Status:** open bug.

### `ping()` rejects DISCONNECTED instead of deferring

**Spec point:** RTN13d (`ping-deferred-disconnected-1`), RTN13b
(`deferred-ping-error-suspended-5`).

**What the spec says:** RTN13b errors only for INITIALIZED, SUSPENDED, CLOSING, CLOSED
and FAILED; RTN13d defers a ping requested while CONNECTING *or DISCONNECTED* and
executes it once the connection is CONNECTED.

**What the SDK does:** `ConnectionManager.ping` (`connectionmanager.py:362`) admits only
CONNECTED and CONNECTING and raises `AblyException("Cannot send ping request. Calling
ping in invalid state", 400, 40000)` for DISCONNECTED.

**Tests affected:** both gated tests assert that the ping is still pending immediately
after the call and fail with
`AssertionError: RTN13d: the ping errored instead of waiting for the connection`.
Note that `deferred-ping-error-suspended-5` would otherwise pass for the wrong reason:
the specification's only stated assertion is that an error arrives, and one does — just
immediately, rather than when the connection suspends.

The setup is also adapted. The specification reaches DISCONNECTED in
`ping-deferred-disconnected-1` by dropping an established connection, which RTN15a
retries with no delay, so the state cannot be held long enough to ping from; the derived
test fails the *first* attempt instead, which settles in DISCONNECTED behind the retry
timer.

**Status:** open bug.

### A deferred ping's timeout runs from the call, not from the HEARTBEAT

**Spec point:** RTN13c with RTN13d (`deferred-ping-timeout-1`).

**What the spec says:** a ping deferred from CONNECTING "still times out based on
`realtimeRequestTimeout` after the connection becomes CONNECTED (the timeout starts when
the HEARTBEAT is actually sent, not when `ping()` is called)".

**What the SDK does:** `ping()` enters `asyncio.wait_for(pending_ping.future,
self.__timeout_in_secs)` (`connectionmanager.py:375`) as soon as it is called, so the
whole of the CONNECTING period is charged against the timeout. A ping requested while
connecting can expire before its HEARTBEAT has gone out at all.

**Tests affected:** `test_rtn13c_deferred_ping_timeout` is gated and fails with
`assert 0.096… >= (0.4 * 0.9)`: the error arrived 96 ms after CONNECTED where the 400 ms
`realtime_request_timeout` should have run from that point.

**Status:** open bug.

### Connection recovery (RTN16) is absent

**Spec point:** RTN16f, RTN16g, RTN16g1, RTN16g3, RTN16i, RTN16j, RTN16k.

**What the spec says:** `Connection#createRecoveryKey` returns a serialisation of the
connection key, the current `msgSerial` and the channel serials of every attached
channel, and null in CLOSING, CLOSED, FAILED or before a first connection. A client given
the `recover` option sends the key's connection key as a `recover` connect parameter on
its first attempt only, initialises `msgSerial` from the key, and instantiates each
channel in the key with its channel serial.

**What the SDK does:** none of it. `recover` is in the `Options` signature, stored, and
given a property and a setter (`options.py:30,111,193,196`), and is read nowhere else in
the library: `grep -r recover ably/` finds only those four lines and the unrelated
channel decode-failure recovery. There is no `create_recovery_key`, no `recover` connect
parameter and no recovery-key decoding.

**Tests affected:** five gated tests.

| Test | Failure with `RUN_DEVIATIONS=1` |
|---|---|
| `test_rtn16g_recovery_key_structure` | `AttributeError: 'Connection' object has no attribute 'create_recovery_key'` |
| `test_rtn16g3_recovery_key_null_inactive` | `AttributeError: 'Connection' object has no attribute 'create_recovery_key'` |
| `test_rtn16k_recover_query_param` | `assert None == 'recovered-key-xyz'` |
| `test_rtn16f_recover_initializes_msgserial` | `assert 0 == 42` |
| `test_rtn16j_recover_channel_serials` | `assert None == 'serial-1-abc'` |

`test_rtn16f1_malformed_recovery_key` is the sixth, and passes: RTN16f1 asks that a
recovery key which cannot be deserialized be logged and otherwise ignored, and a client
given `recover: "this-is-not-valid-json!!!"` does connect normally with no `recover`
parameter. It satisfies the requirement only because the option is never read, and the
error the specification's implementation note asks to be logged is not logged.

**Status:** open bug — one issue covering the whole feature.

## Adapted Tests

### A refused or timed-out connection starts no fallback attempt

**Spec point:** RTN17f, RTN17h, RTN17i, RTN17j (`prefer-primary-domain-0`,
`fallback-domains-from-rec2-0`, `connectivity-check-before-fallback-0`,
`fallback-random-order-1`), RTN17e (`http-uses-same-fallback-0`), RTN13b
(`ping-error-suspended-1`), RTN16g3 (`recovery-key-null-inactive-0`).

**What the spec says:** each of these fails the primary host with
`conn.respond_with_refused()` or `conn.respond_with_timeout()` and expects the client to
move on to a fallback host, or to DISCONNECTED.

**What the SDK does:** `WebSocketTransport.ws_connect` catches only
`(WebSocketException, socket.gaierror)` (`websockettransport.py:119`), so a
`ConnectionRefusedError` or an `asyncio.TimeoutError` emits no `failed`,
`ConnectionManager.try_host`'s future is never settled, and `connect_base` never reaches
its fallback branch. The connection sits in CONNECTING until the transition timer ends
it with a generic 50003/504. This was measured by the connection-failures batch and is
already recorded in `deviations-connection-failures.md`.

**Tests affected:** every test above fails the primary host with
`respond_with_dns_error()` instead, which is RSC15l's "host unreachable" condition and
does reach the fallback loop. The assertions each specification makes are unchanged and
all of these tests pass. `test_rtn17g_empty_fallback_set_error` keeps
`respond_with_refused()`, since it asserts that *no* fallback follows, and waits out the
transition timer with a short `realtime_request_timeout`.

**Status:** open bug, already filed against the connection-failures batch — not a second
issue.

### The RTN17j connectivity check is a blocking call no seam reaches

**Spec point:** RTN17j (`connectivity-check-before-fallback-0`).

**What the spec says:** the connectivity check is a `GET` to `connectivityCheckUrl` which
the test serves from `mock_http`, alongside the client's other HTTP traffic.

**What the SDK does:** `ConnectionManager.check_connection` (`connectionmanager.py:193`)
calls module-level `httpx.get` **synchronously**, from within the async fallback loop.
It therefore bypasses the client's own HTTP layer entirely —
`TestOptions(http_transport=...)` cannot see it — and blocks the event loop for the
duration of the request, once per fallback host tried.

**Tests affected:** every test in `fallback_hosts_test.py` that leaves the client a
fallback set replaces `ably.realtime.connectionmanager.httpx.get` with an in-process stub
through pytest's `monkeypatch`, and `test_rtn17j_connectivity_check_before_fallback`
asserts on the calls that stub recorded rather than on `mock_http.captured_requests`. The
whole batch was run with `socket.socket.connect`, `socket.create_connection` and
`socket.getaddrinfo` blocked, with identical results, so no test reaches the network.

**Status:** open bug — two of them, really: an HTTP call that no client-scoped seam can
reach, and a synchronous call inside the event loop.

### `connection.id`, `connection.key` and a channel's `properties` are not exposed

**Spec point:** RTN23a (`idle-timeout-reconnect-1`, `timeout-triggers-reconnect-4`),
RTN23b (`idle-timeout-reconnect-1`, `timeout-triggers-reconnect-4`), RTN16f1
(`malformed-recovery-key-0`), RTN16j (`recover-channel-serials-0`).

**What the spec says:** `client.connection.id`, `client.connection.key` and
`channel.properties.channelSerial`.

**What the SDK does:** `Connection` exposes `state`, `error_reason`, `connection_manager`
and `connection_details` only; the connection id lives at
`connection.connection_manager.connection_id` and the connection key at
`connection.connection_details.connection_key`. `RealtimeChannel` has no RTL15
`properties` object and keeps the serial privately as `__channel_serial`.

**Tests affected:** the tests above read the equivalent values. This follows the ruling
taken by the connection-core and channels-attrs batches: where the behaviour is right and
only the accessor is missing, adapt and record the missing API rather than gating real
coverage on a question of spelling.

**Status:** open bug — missing public API, no behavioural difference.

### DISCONNECTED cannot be waited on between a drop and the reconnection

**Spec point:** RTN23a and RTN23b (every test that disconnects), RTN17i
(`prefer-primary-domain-0`).

**What the spec says:** the heartbeat specification says so itself, in "Verifying
Transient States", and asks for the state sequence to be recorded and asserted at the
end. RTN17i still writes `AWAIT_STATE client.connection.state ==
ConnectionState.disconnected` between the drop and the reconnection.

**What the SDK does:** RTN15a's immediate retry is `loop.call_soon`
(`connectionmanager.py:668`), so DISCONNECTED is left within the same turn of the event
loop and a listener registered afterwards never sees it.

**Tests affected:** the heartbeat tests record the whole sequence with
`connection.on(...)` and assert `CONTAINS_IN_ORDER` at the end, as the specification
directs. `test_rtn17i_prefer_primary_domain` drops the intermediate wait and waits for
the reconnection instead, which is what the assertion is about.

**Status:** not an SDK fault — correct RTN15a behaviour, recorded because the derivation
departs from the pseudocode.

## Mock Infrastructure Limitations

### Websocket ping frames cannot reach the library

**Spec point:** RTN23b (`ping-frame-resets-timer-2`, `any-message-resets-timer-3`,
`multiple-pings-keep-alive-6`).

**What the spec says:** on a platform whose websocket client surfaces ping frame events,
a ping frame is activity and resets the idle timer.

**Why it cannot be implemented:** the `websockets` library answers pings inside the
protocol and offers no application-level hook, so `WebSocketTransport` cannot observe
one. `MockConnection.send_ping_frame()` records a `PING_FRAME` event and reaches no
library code. The specification's own platform note says the RTN23b tests do not apply to
an SDK in this position, and ably-python is one: RTN23a is the branch that binds it, and
the six RTN23a tests are derived and pass.

**Tests affected:** three skipped stubs. The two RTN23b tests that do not depend on ping
frames — `idle-timeout-reconnect-1` and `timeout-triggers-reconnect-4`, plus
`reconnect-uses-resume-5` and `heartbeats-false-query-param-0` — are derived in full and
pass.

### `heartbeats=bounce` has no applicable configuration

**Spec point:** RTN23c (`heartbeats-bounce-query-param-0`).

**What the spec says:** a client whose own code may be suspended while the transport
stays alive and keeps answering transport-level liveness checks — the specification
scopes this to browsers — should send `heartbeats=bounce`.

**Why it cannot be implemented:** ably-python has no browser build and no equivalent
environment, so there is no configuration of it under which `bounce` is the value to
send. That it sends no `heartbeats` parameter at all is a separate matter, recorded
against RTN23a above. RTN23c1, which the specification binds on every platform whatever
`heartbeats` value it sent, is derived and gated.

**Tests affected:** one skipped stub.
