# Deviations — connection-core batch

Covers `uts/realtime/unit/connection/when_state_test.md`,
`connection_id_key_test.md`, `error_reason_test.md` and `update_events_test.md`.
To be merged into [deviations.md](deviations.md).

25 tests derived: 23 pass, 2 are gated behind `RUN_DEVIATIONS`, none is unimplementable.
Both gated tests were confirmed to fail when enabled.

## UTS Spec Errors

### RTN25 `error-reason-suspended-2` assumes a 5 s `connectionStateTtl`

**Spec point** RTN25 / RTN14e, `error_reason_test.md`,
`realtime/unit/RTN25/error-reason-suspended-2`.

**What the UTS spec says** The setup declares `DEFAULT_CONNECTION_STATE_TTL = 5000 # 5
seconds` and advances time by `DEFAULT_CONNECTION_STATE_TTL + 100` to reach SUSPENDED.

**What the authority says** `features.md` DF1a: "`connectionStateTtl` integer - default
120s". No client in this test ever connects — every attempt is refused — so no
`connectionDetails` arrives to override the default, and the 5 s value can only come from
the fixture being wrong.

**What the SDK does** Suspends after `Defaults.connection_state_ttl`, 120000 ms, which is
correct. Advancing 5100 ms leaves the connection DISCONNECTED and the test fails on the
state, not on `errorReason`.

**Test impact** Only the fixture is at fault; the assertions it carries still stand. The
derived test advances 120100 ms and carries a `# UTS SPEC ERROR:` comment at the site.
`test_rtn25_error_reason_suspended` passes.

**Status** Fix in the UTS spec: the fixture constant should be 120000, or the setup should
send a CONNECTED carrying a short `connectionStateTtl`.

### RTN24 `connection-details-override-2` changes `clientId` mid-connection

**Spec point** RTN24, `update_events_test.md`,
`realtime/unit/RTN24/connection-details-override-2`.

**What the UTS spec says** The second CONNECTED's `connectionDetails` changes `clientId`
from `"client-original"` to `"client-updated"`, and the test then asserts
`client.connection.state == ConnectionState.connected`.

**What the authority says** RTN24 names the details it overrides as operational
parameters, and the same UTS file twice stresses that a field is not overridden for an
in-progress connection where the server never changes it. `features.md` RSA15c requires a
realtime client to transition to FAILED on an incompatible `clientId`, so a CONNECTED that
changes an already-established `clientId` cannot also leave the connection CONNECTED. The
two assertions in the spec's own test contradict each other.

**What the SDK does** `Auth._configure_client_id` raises `IncompatibleClientIdException`,
`ConnectionManager.on_connected` calls `notify_state(FAILED)`, and the connection ends
FAILED with 40102 "Client ID is immutable once configured for a client". That is RSA15c
behaviour, not a defect.

**Test impact** Only the fixture is at fault. The derived test holds `clientId` at
`"client-original"` and asserts the override the test is actually about — the operational
parameters — with a `# UTS SPEC ERROR:` comment at the site.
`test_rtn24_connection_details_override` passes.

**Status** Fix in the UTS spec: drop the `clientId` change from the second message.

## Failing Tests

### RTN8d / RTN9d — the connection id and key are cleared in SUSPENDED

**Spec point** RTN8d, RTN9d.

**What the spec says** `features.md`: `Connection#id` and `Connection#key` are "`Null` when
the SDK is in the `CLOSED`, `CLOSING`, or `FAILED` states". RTN8c/RTN9c, which also cleared
them in SUSPENDED, were replaced as of specification version 6.1.0, because the client
always attempts a resume on reconnecting (RTN14h) and lets the server decide whether
continuity can be preserved.

**What the SDK does** Clears the connection id, the connection key and the connection
details on entering SUSPENDED as well as on CLOSED and FAILED.

**Root cause** `ConnectionManager.enact_state_change` (`connectionmanager.py:181-189`),
under a comment citing RTN16d:

```python
if state == ConnectionState.SUSPENDED or state in (ConnectionState.CLOSED, ConnectionState.FAILED):
    self.__connection_details = None
    self.connection_id = None
    self.__connection_key = None
    self.msg_serial = 0
```

**Test impact** `test_rtn8d_id_key_retained_in_suspended` keeps the spec-correct assertion
and is gated with `@deviation`. Confirmed failing when enabled:

```
>       assert at_suspended['id'] == 'conn-id-1'
E       AssertionError: assert None == 'conn-id-1'
```

**Status** Open bug. The clause moved with specification version 6.1.0 and the library has
not followed; `enact_state_change` should clear only on CLOSED and FAILED.

### RTN24 — the UPDATE event drops the CONNECTED message's error

**Spec point** RTN24.

**What the spec says** The `Connection` emits an UPDATE event with a `ConnectionStateChange`
whose `previous` and `current` are both CONNECTED "and the `reason` attribute set to the
`error` member of the `CONNECTED` `ProtocolMessage` (if any)".

**What the SDK does** Emits the UPDATE with `reason` always `None`. The error is parsed off
the wire, passed into `on_connected` as `reason`, and then discarded on the
already-connected branch.

**Root cause** `ConnectionManager.on_connected` (`connectionmanager.py:425-428`) builds the
change without the reason it was given:

```python
state_change = ConnectionStateChange(ConnectionState.CONNECTED, ConnectionState.CONNECTED,
                                     ConnectionEvent.UPDATE)
self._emit(ConnectionEvent.UPDATE, state_change)
```

The `reason=exception` parameter is used only on the `notify_state` branch below it.

**Test impact** `test_rtn24_update_event_with_error` keeps the spec-correct assertion and is
gated with `@deviation`. Confirmed failing when enabled:

```
>       assert update_change.reason is not None
E       AssertionError: assert None is not None
E        +  where None = ConnectionStateChange(previous=<ConnectionState.CONNECTED: 'connected'>,
E            current=<ConnectionState.CONNECTED: 'connected'>,
E            event=<ConnectionEvent.UPDATE: 'update'>, reason=None).reason
```

**Status** Open bug, and a one-line fix: pass `reason=exception` into the
`ConnectionStateChange`. It also leaves `Connection#errorReason` unset for the RTN15c7
failed-resume case, which RTN25 lists among the errors that must set it.

## Adapted Tests

### RTN8 / RTN9 — `Connection#id` and `Connection#key` do not exist

**Spec point** RTN8, RTN8a, RTN8b, RTN8d, RTN9, RTN9a, RTN9b, RTN9d.

**What the spec says** `Connection#id` and `Connection#key` are attributes of the public
`Connection` type.

**What the SDK does** `ably.realtime.connection.Connection` has neither. The id is a public
attribute of the connection manager, `connection.connection_manager.connection_id`, and the
key is reached through `connection.connection_details.connection_key`, which is `None`
whenever the key would be. Both values, and their whole lifecycle, are otherwise exactly
what the spec describes.

This is more than a differently spelled accessor — there is no public member to rename —
but the observable is intact, so the derived tests read it through the connection manager
rather than being dropped. Each file defines `connection_id(client)` and
`connection_key(client)` at the top and uses them wherever the spec writes `connection.id`
and `connection.key`. The pilot, `auto_connect_test.py`, already does the same for the id.

**Test impact** All eight tests in `connection_id_key_test.py`, plus
`test_rtn24_connected_emits_update` and `test_rtn24_connection_details_override`. All pass
apart from the gated RTN8d/RTN9d SUSPENDED test above.

**Status** Open bug of the missing-API kind, not of the wrong-behaviour kind: `Connection`
should expose `id` and `key` properties delegating to the connection manager. Until it
does, a user cannot reach either value without touching an internal object.

### RTN26 — `whenState` is a private awaitable rather than a public listener call

**Spec point** RTN26, RTN26a, RTN26b.

**What the spec says** `Connection#whenState(state, listener)` calls `listener` with a
`null` argument if the connection is already in `state` (RTN26a), and otherwise calls
`#once` with the state and listener (RTN26b).

**What the SDK does** `Connection._when_state(state)` — private, and returning an awaitable
instead of taking a listener. Both branches behave as the spec requires: already in the
state it returns a future already resolved with `None`, and otherwise it returns
`once_async(state)`, which resolves with the `ConnectionStateChange` that enters the state
and, being a `once` registration, resolves only for the first entry.

Returning an awaitable is the idiomatic async-Python rendering of a one-shot callback, and
carries the same two observables — whether the listener has been called, and with what — so
the derived tests drive it as a task through a `when_state(connection, state)` helper.

One consequence is worth knowing: the deferred branch is an `async def`, so its `once`
registration happens when the coroutine *starts*, not when `_when_state` is called. A
caller that wants the registration in place before the state can change must schedule it
and yield to the event loop first, which the derived tests do with
`asyncio.ensure_future(...)` followed by `settle()`. A literal callback API would have no
such window.

**Test impact** All six tests in `when_state_test.py`. All pass.

**Status** Open bug of the missing-API kind. The behaviour is right; what is missing is a
public `Connection#when_state`. A caller today has to reach for a private method, which
`test/ably/realtime/realtimepresence_test.py` already does in two places.

### RTN25 — `errorReason` is not cleared by a successful reconnect

**Spec point** RTN25, `realtime/unit/RTN25/error-reason-cleared-on-connect-4`.

**What the spec says** The test's primary assertion is
`ASSERT client.connection.errorReason IS null` after a failed attempt is followed by a
successful one — while explicitly sanctioning the alternative, "errorReason is kept but
clearly not relevant to current state (Implementation-specific behavior)". `features.md`
RTN25 itself only says when `errorReason` is *set*, never when it is cleared, so there is no
authority making either reading wrong.

**What the SDK does** Keeps the last error. `Connection._on_state_update` assigns
`__error_reason` only when the incoming change carries a reason, and the only place that
clears it is `Connection.connect()` — which an automatic retry, driven through
`ConnectionManager.request_state`, does not go through. So the DISCONNECTED error is still
readable after the connection comes back.

**Test impact** `test_rtn25_error_reason_cleared_on_connect` asserts the retained error, the
spec's option B, with the option-A expectation in a comment above. It passes.

**Status** Intentional / SDK-wide: the behaviour is one the specification permits, and
asserting it guards the surprising half — that a reconnect does not clear the error but an
explicit `connect()` does. Worth raising against the UTS spec instead, which should pick one
reading rather than offering two; a test that accepts either provides no signal.

## Mock Infrastructure Limitations

*(none)*
