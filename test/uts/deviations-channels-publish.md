# Deviations — `uts/realtime/unit/channels/channel_publish.md`

Derived into `test/uts/realtime/unit/channels/channel_publish_test.py` (RTL6, 23 tests)
and `test/uts/realtime/unit/channels/channel_publish_pending_test.py` (RTN7d, RTN7e,
RTN19a, RTN19a2, RTN19b, 12 tests). 35 tests for the specification's 35 Test IDs.

Categories and their conventions follow `uts/docs/writing-derived-tests.md` and the
house reading of it in [deviations.md](deviations.md): `@spec_error` and `@deviation`
are both skips gated on `RUN_DEVIATIONS`, the first naming the specification and the
second the SDK.

## UTS Spec Errors

### RTL6i1 — an object payload asserted to travel unstringified

*Specification:* `channel_publish.md:1062` (`realtime/unit/RTL6i1/publish-message-object-1`)
asserts `captured_messages[0].messages[0].data == {"key": "value"}` for
`Message(name: "custom", data: {"key": "value"})`.

*Source of truth:* RTL6a defers a realtime publish's encoding to `RestChannel#publish`,
and `features.md:331` (RSL4c3) and `:336` (RSL4d3) both require a JSON-encodable object
to be stringified and carry `encoding: "json"`. The decoded ProtocolMessage therefore
holds the string `'{"key": "value"}'`, never the object.

*What the SDK does:* sends `{'name': 'custom', 'data': '{"key": "value"}', 'encoding':
'json'}` — correct.

*Tests affected:* `test_rtl6i1_publish_message_object`, marked `@spec_error`. Enabled, it
fails with `assert '{"key": "value"}' == {'key': 'value'}`.

*Status:* the same fault is already recorded against the REST specification at
`rest/unit/channel/publish.md:129` in [deviations.md](deviations.md)
(upstream [ably/specification#527](https://github.com/ably/specification/issues/527));
the realtime specification repeats it. Fix the specification, then re-derive.

### RTL6c4, RTN7e — `connectionStateTtl` passed as a `ClientOption`

*Specification:* `channel_publish.md:629` and `:1362` build the client with
`ClientOptions(..., connectionStateTtl: 5000)` so that SUSPENDED is reached inside the
15 × 2000ms advance loop the test then runs.

*Source of truth:* `features.md:2085` (DF1a) makes `connectionStateTtl` a **default**,
and `:1760` (CD2f) makes it a `ConnectionDetails` field that overrides that default.
`features.md:2527` lists it under `Defaults`, not `ClientOptions`. There is no such
client option to set.

*What the SDK does:* `ably/types/options.py:64` accepts the keyword and then discards it
(`connection_state_ttl = Defaults.connection_state_ttl`, unconditionally), and the
suspend timer reads `Defaults.connection_state_ttl` directly
(`ably/realtime/connectionmanager.py:745`) rather than either the option or
`ConnectionDetails`. So neither the specification's route nor the spec-correct one would
shorten it.

*Tests affected:* `test_rtl6c4_fails_conn_suspended` and
`test_rtn7e_pending_fail_suspended`, adapted — they advance the fake clock to the real
120s default (`advance_until_suspended`) rather than fail fast, because the assertions
the tests exist for are still spec-correct and still made; only the setup shortcut is
unavailable. The `ConnectionDetails` half of this is the RTN21 deviation already recorded
in [deviations.md](deviations.md).

*Status:* open — the specification should set `connectionStateTtl` in the CONNECTED
`connectionDetails`, not in `ClientOptions`.

### RTN19a2 — the failed-resume assertion cannot distinguish the behaviours it separates

*Specification:* `realtime/unit/RTN19a2/new-serial-failed-resume-1` publishes two
messages, which take `msgSerial` 0 and 1, then asserts that after a **failed** resume the
resent messages carry `msgSerial` 0 and 1 — the same values a **successful** resume would
preserve. `realtime/unit/RTN19a2/same-serial-on-resume-0`, the test it is paired with,
asserts exactly those values too.

*Why it matters:* an SDK that ignored RTN15c7's counter reset entirely would pass both
tests. The pair proves nothing about the distinction. Publishing a third message after
the reconnect, and asserting its `msgSerial`, is what would separate them.

*What the SDK does:* `ably/realtime/connectionmanager.py:411` resets `msg_serial` to 0
when the connectionId changes, but `_send_protocol_message_on_connected_state` resends
`pending_message.message` unaltered, so a requeued message keeps the serial it was first
given. Measured: after a failed resume the two resent messages go out as 0 and 1, and a
**new** publish then also goes out as `msgSerial` 0 — a duplicate serial on one
connection, which RTN7b forbids. Out of this specification's scope, but worth a look.

*Tests affected:* `test_rtn19a2_new_serial_failed_resume`, derived as written and passing.
Not made fail-fast: the specification is under-determined rather than contradicted by
`features.md`, so there is still a correct (if weak) assertion to make.

*Status:* open against the specification.

## Failing Tests

### RTN7e — a connection-level ERROR reaches FAILED without failing pending messages

*Specification:* RTN7e — "If a connection enters the SUSPENDED, CLOSED or FAILED state,
and an ACK or NACK has not yet been received for a message submitted to the connection,
the client should consider the delivery of those messages as failed, meaning their
callback should be called with an error representing the reason for the state change".

*What the SDK does:* nothing. The publish never resolves and never rejects; awaiting it
times out.

*Root cause:* `ConnectionManager.notify_state` does call `fail_queued_messages(reason)`
for CLOSING, CLOSED, SUSPENDED and FAILED
(`ably/realtime/connectionmanager.py:682-690`), but a connection-level ERROR does not go
through `notify_state`. `ConnectionManager.on_error` ends at
`self.enact_state_change(ConnectionState.FAILED, exception)`
(`ably/realtime/connectionmanager.py:477`), which emits the state change and nothing
else. The other three states are all reached through `notify_state`, which is why
`pending-fail-closed-1`, `multiple-pending-fail-3` and `pending-fail-suspended-0` pass
and only the ERROR path does not.

*Tests affected:* `test_rtn7e_pending_fail_failed` and
`test_rtn7e_error_represents_reason`, both `@deviation`. Enabled, both fail with
`asyncio.exceptions.TimeoutError` from the bounded await on the publish.

*Status:* open bug. `client.connection.error_reason` is populated correctly with the
ERROR's 80019/400, so the reason RTN7e asks for is available at the point the fix would
need it.

## Adapted Tests

### RTN7d, RTN7e — `AblyException`'s status code and code are transposed on the failure path

*Specification:* `ASSERT error.code IS NOT null`.

*What the SDK does:* `fail_queued_messages` builds its fallback error as
`AblyException("Connection failed", 80000, 500)`
(`ably/realtime/connectionmanager.py:343`), but the constructor is
`AblyException(message, status_code, code)` (`ably/util/exceptions.py:15`). The resulting
exception reports `status_code == 80000` and `code == 500` — an error code where the
status code belongs and vice versa.

*Tests affected:* `test_rtn7d_fail_disconnected_no_queue`,
`test_rtn7e_pending_fail_closed` and `test_rtn7e_multiple_pending_fail` assert only what
the specification asks — that a code is present — so they pass. Recorded here because
the value is wrong, not merely differently spelled.

*Status:* open bug, out of scope for these tests to assert.

### RTL6c2 — DISCONNECTED is not a state the connection rests in

*Specification:* `realtime/unit/RTL6c2/queued-when-disconnected-1` simulates a disconnect,
waits for DISCONNECTED, and publishes into it.

*What the SDK does:* RTN15a retries a drop from CONNECTED through
`loop.call_soon(request_state, CONNECTING)` (`ably/realtime/connectionmanager.py:668`),
with no time passing, so the connection is CONNECTING or CONNECTED again before a test
can publish into DISCONNECTED. This is correct RTN15a behaviour, not a defect; the
specification's step is simply not reachable as written.

*Tests affected:* `test_rtl6c2_queued_when_disconnected` — the immediate retry is failed
(`respond_with_dns_error` on the second attempt) and `disconnected_retry_timeout` is set
to 60000, which holds the connection in DISCONNECTED for the publish. The reconnect is
then driven by an explicit `client.connect()`. The specification's own assertions are
unchanged.

*Status:* a specification refinement rather than an SDK bug.

### RTL6c4 — a refused connection leaks a connect task per attempt

*What the SDK does:* `ws_connect` catches only `(WebSocketException, socket.gaierror)`,
so a `ConnectionRefusedError` escapes and `try_a_host`'s future
(`ably/realtime/connectionmanager.py:646`) is never settled. Every refused attempt leaves
a `ConnectionManager.connect_base()` task awaiting that future for good.

*Tests affected:* `test_rtl6c4_fails_conn_suspended` reaches SUSPENDED over ten refused
attempts, as the specification's `respond_with_refused()` asks, and the run therefore
prints ten `Task was destroyed but it is pending!` lines at interpreter shutdown. The
test passes; the noise is the defect showing. Swapping to `respond_with_dns_error()`
would silence it and hide the leak, so it is left as the specification writes it.

*Status:* open bug — a long-lived client reconnecting against a refusing host leaks a
task and a future per attempt. This is the connect-error-handling defect already recorded
in the harness notes, with a resource-leak consequence attached.

### RTL6 — the publish signature and `attachOnSubscribe`

Two translation notes, neither a behavioural deviation, recorded so the next reader does
not rediscover them:

- `RealtimeChannel.publish()` takes its arguments positionally (`*args`,
  `ably/realtime/channel.py:342`). The keyword form the specifications write —
  `publish(name: ..., data: ...)` — raises `ValueError` here, although
  `RestChannel.publish()` does accept it. Every test uses the positional form.
- `RealtimeChannelOptions(attachOnSubscribe: false)`, which every setup in this
  specification passes, has no counterpart in `ably.types.channeloptions.ChannelOptions`.
  It exists in the specifications to stop `subscribe()` attaching implicitly; no test
  here subscribes, so the option is simply omitted and nothing is lost.

## Mock Infrastructure Limitations

*(none)*
