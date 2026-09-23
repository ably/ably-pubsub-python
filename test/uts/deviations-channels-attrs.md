# Deviations: channels-attrs batch

Covers the tests derived from `uts/realtime/unit/channels/channel_options.md`,
`channel_properties.md`, `channels_collection.md` and `channel_attributes.md`.

41 tests derived: 26 pass and 15 are gated behind `RUN_DEVIATIONS`. Every gated
test has been confirmed to fail when enabled.

## UTS Spec Errors

### Three setups attach a channel on a client that was never connected

- **Spec points**: RTS3c1, RTL16a (`channel_options.md`), RTS4a (`channels_collection.md`).
- **What the spec says**: `realtime/unit/RTS3c1/error-reattach-params-0`,
  `realtime/unit/RTL16a/triggers-reattach-0` and
  `realtime/unit/RTS4a/release-detaches-attached-2` each build a client with
  `autoConnect: false`, install no mock, never call `connect()`, and then
  `AWAIT channel.attach()` followed by `ASSERT channel.state == attached`.
- **The problem**: RTL4b requires `attach()` to fail unless the connection is CONNECTING,
  CONNECTED or DISCONNECTED. With `autoConnect: false` and no `connect()` the connection is
  INITIALIZED, so a conforming SDK must raise rather than attach. Even were the state
  right, nothing would answer the ATTACH, so the attach would time out into SUSPENDED.
- **Tests affected**: `test_rts3c1_error_reattach_params`, `test_rtl16a_triggers_reattach`,
  `test_rts4a_release_detaches_attached`.
- **Status**: derived with a `MockWebSocket` that connects and answers each ATTACH with an
  ATTACHED, and with `connect()` called before the attach. The assertions the specification
  makes are unchanged. Upstream should give these three setups a mock, as the sibling
  sections of the same specs do.

### `realtime/unit/RTS3c1/error-reattach-modes-1` leaves its premise unwritten

- **Spec point**: RTS3c1.
- **What the spec says**: "`# Put channel in attaching state (implementation detail)`".
- **The problem**: the premise the test turns on is the one step it does not give, and the
  setup has no mock to reach ATTACHING with.
- **Tests affected**: `test_rts3c1_error_reattach_modes`.
- **Status**: derived by connecting through a mock that leaves the ATTACH unanswered and
  starting `attach()` as a task, which holds the channel in ATTACHING. The assertion is
  unchanged.

### `realtime/unit/RTL15b/serial-not-updated-irrelevant-3` misdescribes its own path

- **Spec point**: RTL15b, RTL15b2.
- **What the spec says**: the closing comment reads "RTL15b2 clears it on DETACHED/FAILED,
  then ATTACHED sets it fresh".
- **The problem**: the DETACHED the test injects arrives while the channel is ATTACHED, so
  RTL13a reattaches and the channel never enters the DETACHED *state*. Nothing clears the
  serial; it is simply never written from the DETACHED message. The assertion the comment
  sits above is still the right one.
- **Tests affected**: `test_rtl15b_serial_not_updated_irrelevant`.
- **Status**: derived as written and passing; only the explanatory comment is wrong.

### `channel_options.md` header omits five of its own spec points

- **Spec points**: RTL16a, RTS5a, RTS5a1, RTS5a2, DO2a.
- **What the spec says**: "Spec points: `TB2`, `TB3`, `TB4`, `RTS3b`, `RTS3c`, `RTS3c1`,
  `RTS5`, `RTL16`".
- **The problem**: the file goes on to carry sections for RTL16a, RTS5a, RTS5a1, RTS5a2 and
  DO2a, none of which the header lists.
- **Tests affected**: none; the derived module docstring lists all of them.
- **Status**: label fault only.

## Failing Tests

### `setOptions` never returns for an attached channel — 1 test

- **Spec point**: RTL16a.
- **What the spec says**: when `params` or `modes` are supplied to `setOptions` on an
  attached channel, the channel reattaches, passes through ATTACHING, returns to ATTACHED,
  and `setOptions` resolves.
- **What the SDK does**: `set_options` hangs. Measured with
  `asyncio.wait_for(channel.set_options(ChannelOptions(params={'rewind': '1'})), 1.0)` on a
  channel attached through a mock that answers every ATTACH: the second ATTACH is sent, the
  server's ATTACHED is received, and the call raises `asyncio.TimeoutError`. No ATTACHING
  state change is emitted; the only event the channel emits is `update`, carrying
  `current == ATTACHED`. The options themselves *are* stored, so `channel.options` holds
  the new params even though the call never returns.
- **Root cause**: `set_options` (`ably/realtime/channel.py:93-102`) calls `_attach_impl()`
  and then `await self.__internal_state_emitter.once_async()`. `_attach_impl()` sends the
  ATTACH without going through `_request_state(ChannelState.ATTACHING)`, so the channel is
  still ATTACHED when the server's ATTACHED arrives. `_on_message` therefore takes the RTL12
  branch (`:722-726`), which emits `update` on the *public* emitter and returns. The
  internal state emitter is written only by `_notify_state` (`:821`), which that branch
  never reaches, so the await has nothing to wake it. Both halves of the defect follow from
  the one missing `_request_state`: no ATTACHING transition, and no internal event.
- **Tests affected**: `test_rtl16a_triggers_reattach`. It also constrains
  `test_rtl4c1_includes_channel_serial` and `test_rtl4j_attach_resume_flag_not_set` in the
  channels-attach batch, which run `set_options` as a task and cancel it.
- **Also on this path**: `raise state_change.reason` at `:102` raises whatever the state
  change carries, which may be `None` — the same defect as `:150` and `:219` recorded by the
  channels-attach batch.
- **Status**: gated. `RUN_DEVIATIONS=1` gives
  `FAILED test_rtl16a_triggers_reattach - asyncio.exceptions.TimeoutError`. The
  specification's unbounded `AWAIT` is derived with a 1 s deadline, which is what turns the
  hang into a failure rather than a stuck run.

### `attachOnSubscribe` is not implemented — 2 tests

- **Spec points**: TB4, RTS5.
- **What the spec says**: `ChannelOptions` carries `attachOnSubscribe`, a boolean defaulting
  to true, which suppresses the implicit attach `subscribe()` performs.
- **What the SDK does**: `ChannelOptions(attach_on_subscribe=False)` raises
  `TypeError: __init__() got an unexpected keyword argument 'attach_on_subscribe'`.
- **Root cause**: `ChannelOptions.__init__` (`ably/types/channeloptions.py:22-26`) accepts
  only `cipher`, `params` and `modes`. `subscribe()` attaches unconditionally.
- **Tests affected**: `test_tb4_attach_on_subscribe_default`,
  `test_rts5_get_derived_with_options`. Two further tests, `test_tb2_channel_options_attributes`
  and `test_rtl16_set_options_updates`, drop the `attachOnSubscribe` assertion and are
  recorded under Adapted Tests.
- **Status**: gated. `RUN_DEVIATIONS=1` gives
  `FAILED test_tb4_attach_on_subscribe_default - TypeError: __init__() got an unexpected keyword argument 'attach_on_subscribe'`.

### `ChannelOptions.withCipherKey` is absent — 1 test

- **Spec point**: TB3.
- **What the spec says**: `RealtimeChannelOptions.withCipherKey(key)` builds options whose
  `cipherParams` has algorithm `aes` and the key's length.
- **What the SDK does**: `ChannelOptions.with_cipher_key` does not exist.
- **Root cause**: `ably/types/channeloptions.py` offers only the constructor and
  `from_dict`. The nearest equivalent, `ably.util.crypto.get_default_params({'key': key})`,
  is not reachable from `ChannelOptions`.
- **Tests affected**: `test_tb3_with_cipher_key`.
- **Status**: gated. `RUN_DEVIATIONS=1` gives
  `FAILED test_tb3_with_cipher_key - AttributeError: type object 'ChannelOptions' has no attribute 'with_cipher_key'`.

### Derived channels are not implemented — 5 tests

- **Spec points**: RTS5, RTS5a, RTS5a1, RTS5a2, DO2a.
- **What the spec says**: `channels.getDerived(name, deriveOptions, channelOptions?)` returns
  a channel named `[filter=<base64 JMESPath>]name`, with any channel params appended to the
  qualifier after a `?`, and `DeriveOptions` carries the `filter` string.
- **What the SDK does**: neither `DeriveOptions` nor `Channels.get_derived` exists.
  `from ably import DeriveOptions` raises `ImportError`, and `grep -r derive ably/` finds
  nothing.
- **Root cause**: the feature is absent. Note that `hasattr(client.channels, 'get_derived')`
  answers `True`: `Channels.__getattr__` (`ably/rest/channel.py:408`) returns a channel named
  after any unknown attribute, so the call would raise
  `TypeError: 'RealtimeChannel' object is not callable` rather than `AttributeError`.
- **Tests affected**: `test_rts5a_creates_derived_channel`,
  `test_rts5a1_filter_base64_encoded`, `test_rts5a2_derived_with_params`,
  `test_rts5_get_derived_with_options`, `test_do2a_filter_attribute`.
- **Status**: gated. Each imports `DeriveOptions` inside the test body so that the module
  still loads. `RUN_DEVIATIONS=1` gives, for all five,
  `ImportError: cannot import name 'DeriveOptions' from 'ably'`.

### A server-initiated DETACHED discards its error, and the attach then raises TypeError — 2 tests

- **Spec points**: RTL24, RTL4c.
- **What the spec says**: an attach rejected by a DETACHED carrying an `ErrorInfo` fails with
  that error and leaves `channel.errorReason` holding it.
- **What the SDK does**: `error_reason` stays `None` and the attach raises
  `TypeError: exceptions must derive from BaseException`.
- **Root cause**: `_on_message` answers a DETACHED received while ATTACHING with
  `self._notify_state(ChannelState.SUSPENDED)` (`ably/realtime/channel.py:735`), passing no
  reason, so the error on the message is dropped. `attach()` then reaches
  `raise state_change.reason` (`:150`) with `reason` `None`. The channels-attach batch
  recorded both halves; these two tests are further instances.
- **Tests affected**: `test_rtl24_error_reason_attach_failure`,
  `test_rtl4c_error_cleared_on_attach`.
- **Status**: gated. `RUN_DEVIATIONS=1` gives, for both,
  `TypeError: exceptions must derive from BaseException` at `ably/realtime/channel.py:150`.
  The clearing half of RTL4c is still covered, by
  `test_rtl4c_error_cleared_preserved_detach`, which sets the error with an ERROR message
  instead and passes.

### `attachSerial` is overwritten by a resumed ATTACHED — 1 test

- **Spec point**: RTL15c.
- **What the spec says**: `attachSerial` is updated from each ATTACHED whose `resumed`
  attribute is false, so an ATTACHED with the RESUMED flag must leave it unchanged.
- **What the SDK does**: it takes the serial from every ATTACHED, resumed or not.
- **Root cause**: `_on_message` assigns `self.__attach_serial = channel_serial`
  (`ably/realtime/channel.py:708`) at the top of the ATTACHED branch, before `flags` has
  been read and `resumed` computed at `:716`.
- **Tests affected**: `test_rtl15c_attach_serial_not_updated_resumed`.
- **Status**: gated. `RUN_DEVIATIONS=1` gives
  `AssertionError: assert 'resumed-serial' == 'initial-serial'`.

### A PRESENCE message does not update `channelSerial` — 1 test

- **Spec point**: RTL15b.
- **What the spec says**: `channelSerial` is updated for MESSAGE, PRESENCE, ANNOTATION,
  OBJECT and ATTACHED actions alike.
- **What the SDK does**: MESSAGE, ANNOTATION and ATTACHED update it; PRESENCE does not.
- **Root cause**: the PRESENCE branch of `_on_message`
  (`ably/realtime/channel.py:751-755`) hands the members to the presence map and never
  touches `__channel_serial`, unlike the MESSAGE branch at `:743` and the ANNOTATION branch
  at `:772`.
- **Tests affected**: `test_rtl15b_channel_serial_from_messages`. Its MESSAGE half passes;
  the PRESENCE half is what fails.
- **Status**: gated. `RUN_DEVIATIONS=1` gives
  `AssertionError: assert 'serial-002' == 'serial-003'`.

### A message with no `channelSerial` clears the stored one — 1 test

- **Spec point**: RTL15b.
- **What the spec says**: `channelSerial` is set from a protocol message "if and only if that
  field is populated".
- **What the SDK does**: a MESSAGE with no `channelSerial` sets the channel's serial to
  `None`.
- **Root cause**: `channel_serial = proto_msg.get('channelSerial')` (`:697`) is `None` when
  the field is absent, and the MESSAGE branch assigns it unconditionally
  (`ably/realtime/channel.py:743`). The ATTACHED branch (`:708-709`) and the ANNOTATION
  branch (`:772`) have the same shape, so an ATTACHED or ANNOTATION without the field clears
  it too.
- **Tests affected**: `test_rtl15b_serial_not_updated_empty`.
- **Status**: gated. `RUN_DEVIATIONS=1` gives `AssertionError: assert None == 'serial-001'`.

### `channelSerial` is cleared on SUSPENDED — 1 test

- **Spec point**: RTL15b2.
- **What the spec says**: as of specification 6.1.0 the channel clears `channelSerial` when
  it enters DETACHED or FAILED, and explicitly *not* when it enters SUSPENDED, so that the
  serial can travel on the next ATTACH for the server's continuity decision (RTL4c1).
- **What the SDK does**: it clears the serial on SUSPENDED as well, so the ATTACH sent after
  a suspend carries no `channelSerial`.
- **Root cause**: `_notify_state` (`ably/realtime/channel.py:810-812`) clears it for
  `(DETACHED, SUSPENDED, FAILED)`, under a comment naming RTP5a1 — the superseded RTL15b1
  behaviour.
- **Tests affected**: `test_rtl15b2_serial_retained_suspended`.
- **Status**: gated. `RUN_DEVIATIONS=1` gives `AssertionError: assert None == 'serial-001'`.

### `Channels.release` does not detach the channel — 1 test

- **Spec point**: RTS4a.
- **What the spec says**: release "detaches the channel and then releases the channel
  resource".
- **What the SDK does**: it deletes the entry and sends nothing. An attached channel is
  dropped from the collection while still attached in the Ably service, and the orphaned
  object stays in ATTACHED.
- **Root cause**: `Channels.release` (`ably/realtime/channel.py:1012-1026`) is
  `if name not in self.__all: return` followed by `del self.__all[name]`. It overrides the
  REST implementation, which is correct for REST, without adding the detach.
- **Tests affected**: `test_rts4a_release_detaches_attached`.
- **Status**: gated. `RUN_DEVIATIONS=1` gives `assert 0 == 1` on the DETACH-message count.

## Adapted Tests

### RTL15's `properties` object is absent — 10 tests

- **Spec point**: RTL15.
- **What the spec says**: `RealtimeChannel#properties` is a `ChannelProperties` object
  holding `attachSerial` and `channelSerial`.
- **What the SDK does**: there is no `properties` attribute and no `ChannelProperties` type.
  The two serials are kept as private fields, `__attach_serial` and `__channel_serial`
  (`ably/realtime/channel.py:66-67`), with no public accessor of any spelling.
- **Tests affected**: every test in `channel_properties_test.py`.
- **Status**: adapted rather than gated, because what RTL15b and RTL15c actually require of
  the serials is testable and worth running. The file defines `attach_serial(channel)` and
  `channel_serial(channel)`, which read the name-mangled fields, and the module docstring
  says why. Four of the ten are gated for behaviour, above; the other six pass. Adding the
  `properties` object would leave the assertions unchanged, only the accessors.

### Channel options are stored as a mapping — 5 tests

- **Spec points**: TB2, RTS3b, RTS3c, RTS3c1, RTL16.
- **What the spec says**: `channel.options` is a `ChannelOptions`, so
  `channel.options.params["rewind"]`, and the cipher attribute is `cipherParams`.
- **What the SDK does**: `RealtimeChannel` passes `ChannelOptions.to_dict()` to the REST
  `Channel` constructor (`ably/realtime/channel.py:84`), so `channel.options` is a dict
  keyed by wire names — `{}` for default options, `{'params': …, 'modes': […], 'cipher': …}`
  otherwise. On `ChannelOptions` itself the cipher attribute is spelled `cipher`.
- **Tests affected**: `test_tb2_channel_options_attributes`, `test_rts3b_options_set_on_new`,
  `test_rts3c_options_updated_existing`, `test_rts3c1_error_reattach_params`,
  `test_rtl16_set_options_updates`.
- **Status**: adapted. Assertions read `channel.options['params']['rewind']` and
  `options.cipher`; nothing else changes. `set_options_without_reattach` replaces the stored
  mapping wholesale rather than merging, which `test_rts3c_options_updated_existing` pins
  with `'modes' not in channel.options`.

### `attachOnSubscribe` assertions dropped from two otherwise-passing tests — 2 tests

- **Spec points**: TB2, RTL16.
- **What the spec says**: `realtime/unit/TB2/channel-options-attributes-0` asserts
  `options.attachOnSubscribe == true` alongside the three attributes that do exist, and
  `realtime/unit/RTL16/set-options-updates-0` sets it to false and reads it back.
- **What the SDK does**: the option does not exist; see the Failing Tests entry above.
- **Tests affected**: `test_tb2_channel_options_attributes`, `test_rtl16_set_options_updates`.
- **Status**: adapted. Each keeps the assertions the SDK can answer and carries a comment
  pointing at `test_tb4_attach_on_subscribe_default`, which is gated and holds the
  spec-correct assertion. Gating these two as well would take four working assertions out of
  the run for one missing option.

### `exists()`, `names` and an awaitable `release()` are spelled differently — 4 tests

- **Spec point**: RTS2, RTS4a.
- **What the spec says**: `channels.exists(name)`, `channels.names`, and
  `AWAIT channels.release(name)`.
- **What the SDK does**: existence is `name in client.channels` (`Channels.__contains__`),
  the collection iterates over its channels rather than their names, and `release` is
  synchronous and returns `None`.
- **Tests affected**: `test_rts2_channel_exists_check`, `test_rts2_iterate_channels`,
  `test_rts4a_release_removes_channel`, `test_rts4a_release_nonexistent_noop`, and the
  existence assertions in the other `channels_collection_test.py` tests.
- **Status**: adapted as idiomatic spelling, not recorded as non-compliance. One hazard is
  worth flagging to maintainers even though it costs no test: `Channels.__getattr__`
  (`ably/rest/channel.py:408`) answers *any* unknown attribute with
  `self.get(name)`, so `client.channels.exists` silently creates and returns a channel
  called `exists`, and `client.channels.names` one called `names`. Reading an attribute
  that does not exist mutates the collection and never raises. These tests therefore never
  name an attribute the collection does not define. `Channels.__iter__` is annotated
  `Iterator[str]` but yields `Channel` objects, which is a second, smaller instance of the
  same carelessness.

## Mock Infrastructure Limitations

*(none)*
