# Deviations — `uts/realtime/unit/channels/channel_subscribe.md`, `uts/realtime/unit/channels/message_field_population.md`

Derived into `test/uts/realtime/unit/channels/channel_subscribe_test.py` (RTL7, RTL7a,
RTL7b, RTL7f, RTL7g, RTL7h, RTL8, RTL8a, RTL8b, RTL8c, RTL17, RTL22, RTL22a–d, MFI1,
MFI2a–e, 21 tests) and
`test/uts/realtime/unit/channels/message_field_population_test.py` (TM2a, TM2c, TM2f,
8 tests). 29 tests for the two specifications' 29 Test IDs.

Categories and their conventions follow `uts/docs/writing-derived-tests.md` and the house
reading of it in [deviations.md](deviations.md): `@spec_error` and `@deviation` are both
skips gated on `RUN_DEVIATIONS`, the first naming the specification and the second the SDK.

## UTS Spec Errors

*(none)*

## Failing Tests

### RTL7h — the `attachOnSubscribe` channel option does not exist

*Specification:* `channel_subscribe.md:499` (`realtime/unit/RTL7h/no-attach-on-subscribe-0`)
builds `client.channels.get(name, RealtimeChannelOptions(attachOnSubscribe: false))` and
requires `subscribe` to leave the channel INITIALIZED with no ATTACH sent.

*What the SDK does:* `ably/types/channeloptions.py:21` takes only `cipher`, `params` and
`modes`, so the option cannot be requested, and `RealtimeChannel.subscribe`
(`ably/realtime/channel.py:285`) ends unconditionally with `await self.attach()`. There
is no way to register a listener without attaching.

*Root cause:* the channel option is unimplemented; the RTL7g implicit attach is
unconditional rather than opt-out.

*Tests affected:* `test_rtl7h_no_attach_on_subscribe`, marked `@deviation`. Enabled, it
fails with `TypeError: __init__() got an unexpected keyword argument
'attach_on_subscribe'`.

*Status:* open. The same absence forces the setup adaptation recorded under *Adapted
Tests* below, which touches thirteen further tests.

### RTL17 — messages are delivered to a channel that is not ATTACHED

*Specification:* `channel_subscribe.md:650`
(`realtime/unit/RTL17/no-delivery-when-not-attached-0`): "No messages should be passed to
subscribers if the channel is in any state other than `ATTACHED`." The test leaves the
channel ATTACHING and asserts the subscriber sees nothing.

*What the SDK does:* delivers the message. `RealtimeChannel._on_message`
(`ably/realtime/channel.py:738-750`) decodes the `messages` array and emits every message
to the subscriber emitter with no reference to `self.state`; `Channels._on_channel_message`
(`:1028`) only checks that the channel exists. A message arriving while the channel is
ATTACHING, DETACHING, SUSPENDED or FAILED reaches subscribers exactly as one arriving
while ATTACHED does.

*Root cause:* the MESSAGE branch of `_on_message` has no channel-state guard.

*Tests affected:* `test_rtl17_no_delivery_when_not_attached`, marked `@deviation`.
Enabled, it fails with `assert 1 == 0`.

*Status:* open.

### RTL7f — `echoMessages` does not exist, in either form the specification allows

*Specification:* `channel_subscribe.md:708` (`realtime/unit/RTL7f/no-echo-messages-0`)
requires that with `echoMessages: false` a message carrying this connection's
`connectionId` is not delivered. Its implementation note also accepts server-side
delegation, i.e. an `echo` connection parameter, as the thing to assert instead.

*What the SDK does:* neither. `ably/types/options.py` has no `echo_messages` keyword, so
the client cannot be built; and grepping `ably/` for `echo` finds only heartbeat-echo
comments, so no `echo` connect parameter is sent either. Every message the server sends
is delivered, whatever its `connectionId`.

*Root cause:* the client option is unimplemented.

*Tests affected:* `test_rtl7f_no_echo_messages`, marked `@deviation`. Enabled, it fails
with `TypeError: __init__() got an unexpected keyword argument 'echo_messages'`
(`ably/types/options.py:40`). The test is written in the client-side-filtering form,
because with no `echo` parameter sent there is nothing for the server-side-delegation
form to assert.

*Status:* open. Already noted as a confirmed-absent feature by earlier batches; recorded
here because RTL7f is the specification point that requires it.

### RTL8b — unsubscribing one name of a listener subscribed to two raises `KeyError`

*Specification:* `channel_subscribe.md:872`
(`realtime/unit/RTL8b/unsubscribe-named-listener-0`) subscribes one listener to `"alpha"`
and to `"beta"`, then calls `unsubscribe("alpha", listener)` and requires the `"beta"`
subscription to survive.

*What the SDK does:* raises `KeyError` out of `channel.unsubscribe`.

*Root cause:* `EventEmitter` (`ably/util/eventemitter.py`) wraps each listener in a
try/except closure and remembers it in `self.__wrapped_listeners[listener]`, keyed on the
listener **alone** (`:85`). Subscribing the same listener to a second name overwrites the
entry, so the wrapper registered for `"alpha"` is no longer reachable. `off("alpha",
listener)` (`:166`) then hands pyee the `"beta"` wrapper for the `"alpha"` event, and
`pyee.base.EventEmitter._remove_listener` does `self._events[event].pop(f)`, which raises.
Two further consequences of the same line: the `"alpha"` registration is left live, so the
listener would keep receiving `"alpha"` messages; and `off` sets
`self.__wrapped_listeners[listener] = None` (`:167`), so any later `off` for that listener
silently does nothing.

*Tests affected:* `test_rtl8b_unsubscribe_named_listener`, marked `@deviation`. Enabled,
it fails with `KeyError: <function EventEmitter.on.<locals>.wrapped_listener ...>` raised
at `.venv/.../pyee/base.py:262` from `ably/realtime/channel.py:336`.

*Status:* open. The registry needs to be keyed on `(event, listener)`, and to hold a list
per key so that a listener registered twice for one event can be removed once.

### RTL22, RTL22a, RTL22b, RTL22c, RTL22d, MFI1, MFI2a–e — no `MessageFilter`

*Specification:* five tests, `channel_subscribe.md:1084`, `:1176`, `:1272`, `:1371` and
`:1480`, subscribe with a `MessageFilter` over `name`, `refTimeserial`, `isRef`, `refType`
and `clientId`, and require only matching messages to reach the listener (RTL22c: all
criteria must hold).

*What the SDK does:* there is no filter type anywhere in `ably/` and
`RealtimeChannel.subscribe` (`ably/realtime/channel.py:262-273`) accepts only a `str`
event name or a callable, raising `ValueError('invalid subscribe arguments')` for anything
else. RTL22d allows an idiomatic spelling, but there is no filtered-subscribe surface of
any shape to spell.

*Root cause:* filtered subscriptions are unimplemented.

*Tests affected:* `test_rtl22a_filter_matching_name`,
`test_rtl22a_filter_matching_ref_timeserial`, `test_rtl22b_filter_isref_false`,
`test_rtl22c_filter_multiple_criteria` and `test_rtl22a_filter_matching_clientid`, all
marked `@deviation`. Each builds its filter through the module's `message_filter()`
helper, which imports `ably.types.messagefilter`; enabled, each fails with
`ModuleNotFoundError: No module named 'ably.types.messagefilter'`. The helper is the one
place to repoint when the type lands, and the rest of each test body is the
specification's, so the assertions become live unchanged.

*Status:* open.

### TM2a — a message with no id in a ProtocolMessage with no id is given the id `"None:0"`

*Specification:* `message_field_population.md:172`
(`realtime/unit/TM2a/no-id-without-protocol-id-2`) requires that the `protocolMsgId:index`
derivation apply only when the ProtocolMessage carries an `id`; otherwise the message is
delivered with no `id` (`:228`).

*What the SDK does:* delivers `id == 'None:0'`. `Message.__update_empty_fields`
(`ably/types/message.py:369-375`) writes `msg['id'] = f"{proto_msg.get('id')}:{msg_index}"`
whenever the message has no id, with no test for the ProtocolMessage having one, so a
missing parent id is interpolated as the string `None`.

*Root cause:* the guard on `proto_msg.get('id')` is missing.

*Tests affected:* `test_tm2a_no_id_without_protocol_id`, marked `@deviation`. Enabled, it
fails with `AssertionError: assert 'None:0' is None`.

*Status:* open, and already filed — the REST suite found the same line fabricating
`"None:0"` for a presence message with no id, reported as ably-python issue #706. This is
the same defect reached through the realtime `messages` array rather than `presence`; one
fix closes both.

## Adapted Tests

### RTL7a, RTL7b, RTL7f, RTL8a, RTL8b, RTL8c, RTL22a–c — `attachOnSubscribe: false` replaced by attaching first

*Specification:* sixteen of the twenty-one subscribe tests build the channel with
`RealtimeChannelOptions(attachOnSubscribe: false)` and then `AWAIT channel.attach()`
themselves. The option is setup scaffolding there: it keeps `subscribe` from issuing a
second attach while the test counts protocol messages.

*What the SDK does:* the option does not exist (see the RTL7h entry above), and
`subscribe` always awaits `attach()`. On an already-ATTACHED channel that attach returns
immediately without sending anything (RTL4a, `ably/realtime/channel.py:125`).

*Root cause:* missing channel option; the behaviour the tests depend on is reachable
another way.

*Tests affected:* `test_rtl7a_subscribe_all_messages`,
`test_rtl7a_multiple_messages_per_protocol`, `test_rtl7b_name_filtered_subscribe`,
`test_rtl7b_multiple_name_subscriptions`, `test_rtl8a_unsubscribe_specific_listener`,
`test_rtl8b_unsubscribe_named_listener`, `test_rtl8c_unsubscribe_all_listeners`,
`test_rtl8a_unsubscribe_noop_not_subscribed`, `test_rtl22a_filter_matching_name`,
`test_rtl22a_filter_matching_ref_timeserial`, `test_rtl22b_filter_isref_false`,
`test_rtl22c_filter_multiple_criteria` and `test_rtl22a_filter_matching_clientid`. Each
attaches explicitly before subscribing, which is what the specification's own test steps
do; only the option is dropped. Every assertion the specification makes is kept.

*Status:* the adaptation stands until RTL7h is implemented. The three remaining
specification tests that set the option — `test_rtl7h_no_attach_on_subscribe`,
`test_rtl17_no_delivery_when_not_attached` and `test_rtl7f_no_echo_messages` — are gated
under *Failing Tests* rather than adapted, so the gap the adaptation works around is
recorded in its own right.

### RTL7g — the implicit attach's failure is raised by `subscribe`

*Specification:* `channel_subscribe.md:426`
(`realtime/unit/RTL7g/listener-registered-attach-fails-2`) calls
`channel.subscribe(listener)`, lets the attach be rejected, and requires the listener to
be registered all the same.

*What the SDK does:* registers the listener (`ably/realtime/channel.py:279-282`) and then
awaits `attach()`, which re-raises the channel's failure reason (`:150`). So
`await channel.subscribe(...)` raises `AblyException` where the specification's
fire-and-forget call returns.

*Root cause:* `subscribe` is a coroutine that resolves on attach, so an attach failure has
nowhere to go but the caller. The RTL7g requirement itself — that the listener survives —
holds.

*Tests affected:* `test_rtl7g_listener_registered_attach_fails`, which wraps the subscribe
in `pytest.raises(AblyException)` and then makes the specification's assertions unchanged:
the channel reaches FAILED, a later `attach()` succeeds, and the listener registered
before the failure receives the message. The same shape covers
`test_rtl7g_no_attach_when_attaching` and `test_rtl17_no_delivery_when_not_attached`,
where `subscribe` is started as a task because the attach it awaits is deliberately never
answered.

*Status:* not an SDK defect; recorded so the difference from the pseudocode is not read as
one. Worth resolving in the specification by saying what `subscribe` returns when the
implicit attach fails.

### TM2a, TM2c, TM2f — subscribing after connecting

*Specification:* all eight `message_field_population.md` tests call
`channel.subscribe(...)` in their setup, before `client.connect()`.

*What the SDK does:* `subscribe` awaits `attach()`, and `attach()` raises 90001 unless the
connection is CONNECTING, CONNECTED or DISCONNECTED (`ably/realtime/channel.py:133-138`),
so it cannot be called on a client that has not been asked to connect.

*Root cause:* the ordering the pseudocode uses depends on a `subscribe` that registers and
returns; this one attaches.

*Tests affected:* all eight, through the shared `subscribed_channel()` helper. The
connect, the attach and the subscribe all still happen before the first ProtocolMessage is
injected, so nothing the tests assert depends on the order.

*Status:* idiomatic; no SDK change wanted.

## Mock Infrastructure Limitations

*(none)*
