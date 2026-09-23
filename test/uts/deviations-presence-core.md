# Deviations — presence core

Recorded while deriving `uts/realtime/unit/presence/realtime_presence_enter.md`,
`realtime_presence_subscribe.md` and `realtime_presence_get.md` into
`test/uts/realtime/unit/presence/`.

## UTS Spec Errors

### RTP15c contradicts RTP8j

- **Spec point:** RTP15c, against RTP8j.
- **What the spec says:** `realtime/unit/RTP15c/enterclient-no-side-effects-0` builds a
  client with `clientId: "*"`, calls `presence.enter(data: "main-client")` and expects it
  to succeed alongside `enterClient`/`leaveClient` for another user.
- **Why it cannot hold:** RTP8j requires `enter()` to fail immediately when the clientId
  is the wildcard, and the same specification file asserts exactly that in
  `realtime/unit/RTP8j/enter-wildcard-clientid-errors-1`. No implementation can satisfy
  both. RTP15f rules out the other way round — a client with a concrete clientId cannot
  `enterClient` for a different one.
- **What the SDK does:** `enter()` on a wildcard client raises `AblyException` 40012
  (`ably/realtime/presence.py:99-104`), which is RTP8j-correct.
- **Tests affected:** `test_rtp15c_enterclient_no_side_effects`.
- **Status:** Adapted and running. The specification's own note invites adaptation where
  the wildcard is not workable, so the "normal" enter is made as
  `enter_client('main-client', 'main-client')` and the rest of the test — that
  `enterClient`/`leaveClient` for another user leave the first member's message
  untouched — is asserted as written. Worth raising upstream.

## Failing Tests

### RTP6b — an array of actions cannot be subscribed to

- **Spec point:** RTP6b ("The action argument may also be an array of actions").
- **What the spec says:** `presence.subscribe([ENTER, LEAVE], listener)` delivers only
  those two actions.
- **What the SDK does:** `RealtimePresence.subscribe()` passes any two-argument form
  straight to `EventEmitter.on(event, listener)` (`ably/realtime/presence.py:480`), which
  hands the event to pyee as a dictionary key. A list is unhashable, so the call raises
  `TypeError: unhashable type: 'list'` (`pyee/base.py:162`).
- **Root cause:** neither `RealtimePresence.subscribe` nor `EventEmitter.on` has any
  notion of a list of events; a fix has to fan the list out into one registration per
  action, and `unsubscribe` with it.
- **Tests affected:** `test_rtp6b_subscribe_filtered_multiple_actions` (`@deviation`).
- **Status:** Gated. With `RUN_DEVIATIONS=1`:
  `TypeError: unhashable type: 'list'`.

### RTP6e — `attachOnSubscribe` does not exist

- **Spec point:** RTP6e.
- **What the spec says:** with the `attachOnSubscribe` channel option false,
  `presence.subscribe()` must not implicitly attach; the channel stays INITIALIZED and
  no ATTACH is sent.
- **What the SDK does:** `ChannelOptions` takes only `cipher`, `params` and `modes`
  (`ably/types/channeloptions.py:22-26`), and `attach_on_subscribe` appears nowhere in
  `ably/`. Constructing the options raises
  `TypeError: __init__() got an unexpected keyword argument 'attach_on_subscribe'`, and
  `RealtimePresence.subscribe` attaches unconditionally from INITIALIZED, DETACHED or
  DETACHING (`ably/realtime/presence.py:485`).
- **Root cause:** the option is unimplemented, in `ChannelOptions` and in both
  `RealtimeChannel.subscribe` and `RealtimePresence.subscribe`.
- **Tests affected:** `test_rtp6e_subscribe_no_attach_option` (`@deviation`).
- **Status:** Gated. With `RUN_DEVIATIONS=1`:
  `TypeError: __init__() got an unexpected keyword argument 'attach_on_subscribe'`.

### RTP7b — one listener cannot hold registrations for two actions

- **Spec point:** RTP7b ("Unsubscribe with an action argument and a listener
  unsubscribes the listener for that action only").
- **What the spec says:** subscribe the same listener for ENTER and for LEAVE,
  unsubscribe it for ENTER, and it still receives LEAVE.
- **What the SDK does:** `channel.presence.unsubscribe('enter', listener)` raises
  `KeyError` out of pyee and the listener is left registered for both actions.
- **Root cause:** `EventEmitter` keeps one `__wrapped_listeners[listener]` entry per
  listener object, not per (event, listener) pair (`ably/util/eventemitter.py:85`). The
  second `subscribe` overwrites the first's wrapper, so `off('enter', listener)` looks
  up the wrapper made for `'leave'` and asks pyee to remove it from `'enter'`, where
  `_remove_listener` does an undefaulted `pop` (`pyee/base.py:262`). The same bug means
  `off` can only ever remove the most recent registration of a listener, and it sets the
  map entry to `None` rather than deleting it, so a re-subscribe-then-unsubscribe
  sequence silently no-ops.
- **Tests affected:** `test_rtp7b_unsubscribe_for_specific_action` (`@deviation`).
- **Status:** Gated. With `RUN_DEVIATIONS=1`:
  `KeyError: <function EventEmitter.on.<locals>.wrapped_listener at 0x1037ef700>`.

## Adapted Tests

### RTP8c, RTP9d, RTP10c — the clientId is sent on the PresenceMessage

- **Spec point:** RTP8c, RTP9d, RTP10c.
- **What the spec says:** `enter()`, `update()` and `leave()` use the connection's
  clientId implicitly, so the `clientId` attribute of the PresenceMessage must not be
  present.
- **What the SDK does:** `_enter_or_update_client` and `_leave_client` resolve
  `effective_client_id = _get_client_id(self)` when no clientId was passed
  (`ably/realtime/presence.py:239` and `:315`), and `PresenceMessage.to_encoded` writes
  `clientId` whenever it is set (`ably/types/presence.py:161`). So a
  `clientId: "my-client"` goes on the wire where the specification wants the field
  absent.
- **Root cause:** the implicit-clientId case is not distinguished from the explicit one;
  both go through the same `client_id` argument.
- **Tests affected:** `test_rtp8a_enter_sends_presence_enter`,
  `test_rtp9a_update_sends_presence_update`,
  `test_rtp10a_leave_sends_presence_leave`.
- **Status:** Adapted — each asserts `clientId == 'my-client'` with the RTP8c/RTP9d/RTP10c
  expectation in a comment above it. The behaviour is stable and the rest of each test
  (action, channel, payload) is worth running.

### RTP16c — the channel reaches SUSPENDED, not DETACHED

- **Spec point:** RTP16c.
- **What the spec says:** answering an ATTACH with a DETACHED puts the channel in
  DETACHED, and a presence operation from there errors.
- **What the SDK does:** a DETACHED received while ATTACHING calls
  `_notify_state(ChannelState.SUSPENDED)` with no reason (`ably/realtime/channel.py:735`),
  so the channel lands in SUSPENDED and `attach()` then evaluates
  `raise state_change.reason` on a `None`, raising `TypeError` rather than an
  `AblyException` (`ably/realtime/channel.py:149`). Both are already recorded in
  `deviations-channels-attach.md`. The presence operation itself does error, with
  `AblyException` 90001 from the catch-all branch of `_enter_or_update_client`.
- **Tests affected:** `test_rtp16c_presence_errors_other_states`.
- **Status:** Adapted — the test expects the `TypeError` and the SUSPENDED state, and
  keeps the specification's real assertion, that `presence.enter()` errors.
- **Related, not exercised by any test here:** RTP8g also requires an immediate error
  from a DETACHED channel, but `_enter_or_update_client` groups DETACHED with
  INITIALIZED and implicitly attaches (`ably/realtime/presence.py:260-264`). The
  operation still fails when the reattach fails, through
  `_fail_pending_presence`, so it errors by a different route. `_leave_client` does
  not have the same grouping — it raises for INITIALIZED and FAILED and queues only
  for ATTACHING (`ably/realtime/presence.py:332-348`).

### RTP11d — `connectionStateTtl` from the CONNECTED is ignored

- **Spec point:** RTP11d, and the specification's note on reaching SUSPENDED.
- **What the spec says:** put `connectionStateTtl: 5000` in the CONNECTED's
  `connectionDetails` and advance past it to reach a SUSPENDED connection.
- **What the SDK does:** `ConnectionDetails.connection_state_ttl` is parsed and read
  nowhere; the suspend timer uses `Defaults.connection_state_ttl` (120000)
  (`ably/realtime/connectionmanager.py:745`). Already recorded as an RTN21 deviation in
  `deviations.md`.
- **Tests affected:** `test_rtp11d_get_suspended_errors_default`,
  `test_rtp11d_get_suspended_no_wait_returns`.
- **Status:** Adapted — the CONNECTED still carries the specification's
  `connectionStateTtl`, and `advance_to_connection_state` steps the `FakeClock` until the
  connection actually reaches SUSPENDED rather than assuming 5 s.

## Mock Infrastructure Limitations

*(none)*
