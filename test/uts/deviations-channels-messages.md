# Deviations — the channel message specifications

Derived into six suites under `test/uts/realtime/unit/channels/`:

| Specification | Test file | Test IDs |
|---|---|---|
| `uts/realtime/unit/channels/channel_annotations.md` | `channel_annotations_test.py` | 14 |
| `uts/realtime/unit/channels/channel_delta_decoding.md` | `channel_delta_decoding_test.py` | 12 |
| `uts/realtime/unit/channels/channel_update_delete_message.md` | `channel_update_delete_message_test.py` | 9 |
| `uts/realtime/unit/channels/channel_history.md` | `channel_history_test.py` | 3 |
| `uts/realtime/unit/channels/channel_get_message.md` | `channel_get_message_test.py` | 1 |
| `uts/realtime/unit/channels/channel_message_versions.md` | `channel_message_versions_test.py` | 1 |

40 tests for the six specifications' 40 Test IDs. 38 run; 2 are gated on
`RUN_DEVIATIONS`.

Categories and their conventions follow `uts/docs/writing-derived-tests.md` and the house
reading of it in [deviations.md](deviations.md): `@spec_error` and `@deviation` are both
skips gated on `RUN_DEVIATIONS`, the first naming the specification and the second the SDK.

## UTS Spec Errors

*(none)*

## Failing Tests

### RTL10b — the `untilAttach` history parameter does not exist

*Specification:* `channel_history.md:29`
(`realtime/unit/RTL10b/adds-from-serial-0`) calls `channel.history(untilAttach: true)` on
an attached channel and requires the request to carry a `fromSerial` query parameter set
to the channel's `attachSerial`.

*What the SDK does:* `RealtimeChannel` does not override `history`, so the call reaches
`Channel.history` (`ably/rest/channel.py:46`), whose only parameters are `direction`,
`limit`, `start` and `end`. There is no `until_attach`, no `fromSerial` is ever sent, and
the attach serial the channel does record (`ably/realtime/channel.py:66,708`) is private
and read nowhere — there is no `properties` object exposing it either.

*Root cause:* RTL10b is unimplemented; the realtime channel reuses the REST `history`
unchanged.

*Tests affected:* `test_rtl10b_adds_from_serial`, marked `@deviation`. Enabled, it fails
with `ably.util.exceptions.AblyException: 50000 500 Unexpected exception: TypeError:
history() got an unexpected keyword argument 'until_attach'`.

*Status:* open. The same absence forces the adaptation of
`test_rtl10b_errors_when_not_attached` recorded below.

### PC3 — a vcdiff message with no decoder registered never fails the channel

*Specification:* `channel_delta_decoding.md:851`
(`realtime/unit/PC3/no-plugin-fails-1`): a `vcdiff`-encoded message received by a client
with no vcdiff plugin must put the channel in FAILED with `errorReason.code == 40019`.

*What the SDK does:* the channel stays where it was and nothing is reported on it. Two
separate causes, both verified:

1. `Message.from_encoded` (`ably/types/message.py:302-305`) compares
   `extras.delta.from` against the context's `last_message_id` **before** the decode
   pipeline runs. The specification's message is the first the channel receives, so the
   stored id is null, the comparison fails and a **40018** is raised — the RTL18 recovery
   error, not the missing-plugin error. The channel goes ATTACHING instead of FAILED.
2. Even reaching the missing-decoder branch, the 40019
   (`ably/types/mixins.py:82-84`) is not 40018, so `RealtimeChannel._on_message`
   (`ably/realtime/channel.py:744-749`) takes its `else` arm, which only logs
   `Message processing error … Skip messages`. Driving a delta whose `from` id *does*
   match the stored id leaves the channel in its previous state with
   `error_reason is None`.

*Root cause:* the delta-reference check runs ahead of the decoder-availability check, and
a decode error other than 40018 has no channel-level handling at all.

*Tests affected:* `test_pc3_no_plugin_fails`, marked `@deviation`. Enabled, it fails with
`AssertionError: Timed out waiting until the channel fails for want of a vcdiff decoder`,
with `ERROR ably.realtime.channel: VCDiff decode failure: 40018 400 Delta message decode
failure - previous message not available. Message id = msg-1:0` in the captured log.

*Status:* open.

## Adapted Tests

### RTL10b — the error raised when `untilAttach` is used unattached is a signature error

*Specification:* `channel_history.md:87`
(`realtime/unit/RTL10b/errors-when-not-attached-1`) requires an `AblyException` when
`untilAttach` is requested on a channel that is not attached.

*What the SDK does:* it raises an `AblyException`, but for the wrong reason. `history`
takes no `until_attach` parameter at all, and the `catch_all` decorator
(`ably/util/exceptions.py:93-100`) wraps the resulting `TypeError` as
`50000 500 Unexpected exception`, whatever the channel's state — an attached channel
raises exactly the same error.

*Root cause:* as for the gated RTL10b test above, the parameter does not exist.

*Tests affected:* `test_rtl10b_errors_when_not_attached` asserts the `AblyException` the
specification requires and, in addition, that no HTTP request was made. A comment records
that the error does not come from the state check the specification is about.

*Status:* open, and will be satisfied properly once RTL10b is implemented.

### RTAN4a, RTAN4c, RTAN4e, RTAN4e1, RTAN5a — `attachOnSubscribe: false` does not exist

*Specification:* five annotation tests build the channel with
`RealtimeChannelOptions(attachOnSubscribe: false)` so that `annotations.subscribe` can
register a listener without attaching.

*What the SDK does:* `ChannelOptions` (`ably/types/channeloptions.py`) takes only
`cipher`, `params` and `modes`, and `RealtimeAnnotations.subscribe`
(`ably/realtime/annotations.py:168`) always `await`s `self.__channel.attach()` before
registering. This is the same absence the subscribe batch recorded for RTL7h in
[deviations-channels-subscribe.md](deviations-channels-subscribe.md); it is not
re-gated here.

*Root cause:* the channel option is unimplemented, so the RTL7g/RTAN4d implicit attach is
unconditional rather than opt-out.

*Tests affected:* `test_rtan4a_subscribe_delivers_annotations`,
`test_rtan4c_subscribe_type_filter`, `test_rtan4e_subscribe_warns_no_mode` and the two
`test_rtan5a_*` tests attach the channel first, which makes the attach `subscribe` awaits
a no-op and leaves each test's own subject untouched.

`test_rtan4e1_no_warn_unattached` needs the channel to stay unattached, which it cannot
ask for. It runs `subscribe` as a task against a server that never confirms the attach,
so the channel is ATTACHING rather than ATTACHED when the mode check would run; the test
asserts both that the channel is not attached and that no `ANNOTATION_SUBSCRIBE` warning
was logged.

*Status:* open, tracked by the RTL7h entry.

### RTL19b, RTL19c, RTL20, RTL21, PC3 — a delta result with no `utf-8` step is binary

*Specification:* the delta tests send messages whose `encoding` is `vcdiff` and then
assert the delivered `data` equals a string literal, for example
`received_messages[1].data == "second message"` (`channel_delta_decoding.md:116`). The
same document's transport note (`:15-23`) says the pipeline applies base64, then vcdiff,
"then decode utf-8 **if present**" — and these messages have no `utf-8` step, so the
delta result is binary.

*What the SDK does:* the correct thing. `EncodeDataMixin.decode`
(`ably/types/mixins.py:106`) leaves the vcdiff result as a `bytearray` and delivers it,
since no further encoding step turns it back into text. The specification's own
`RTL19b/json-wire-form-base-1` test, which does use `utf-8/vcdiff`, receives a string and
asserts one.

*Root cause:* the specification compares a binary payload against a string literal; this
is a looseness in the pseudo-code rather than an SDK fault.

*Tests affected:* `test_rtl21_ascending_index_order`, `test_rtl19b_stores_base_payload`,
`test_rtl19c_delta_result_becomes_base`, `test_rtl20_last_id_updated_on_decode` and
`test_pc3_vcdiff_plugin_decodes` assert the bytes the SDK delivers
(`== b'second message'`) where the specification writes the string. The payload compared
is otherwise exactly the one the specification names, and
`test_rtl19b_json_wire_form_base` and `test_rtl19a_base64_decoded_before_store` assert the
specification's values unchanged.

*Status:* worth raising upstream so the assertions state the expected form.

### RTL32d — the ACK's `res` field is an array

*Specification:* every ACK in `channel_update_delete_message.md` is written
`ACK(msgSerial: …, count: 1, res: { "serials": [...] })`, a single object.

*What the SDK does:* `WebSocketTransport` (`ably/transport/websockettransport.py:191-193`)
reads `res` as a list, one entry per acknowledged ProtocolMessage, and
`MessageQueue.complete_messages` zips it against the pending messages. This matches the
protocol definition; the specification's single object is shorthand for the one-message
case.

*Root cause:* specification shorthand, not an SDK difference.

*Tests affected:* every test in `channel_update_delete_message_test.py` and the ACKing
tests in `channel_annotations_test.py` send `res: [{'serials': [...]}]`.

*Status:* no action; recorded so the shape is not mistaken for a defect later.

## Mock Infrastructure Limitations

*(none)* — `uts/realtime/unit/helpers/mock_vcdiff.md` is fully implementable here. The
encoder, the base-validating decoder and the always-failing decoder are defined in
`channel_delta_decoding_test.py`, which is the only suite that uses them. Only the binary
form is built: ably-python's plugin seam is the binary-only `VCDiffDecoder` of VD2a, so
the string overloads the mock specification offers as a test-setup convenience have
nothing to attach to.
