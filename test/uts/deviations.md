# Deviations

Where the derived tests depart from the Universal Test Specifications, and why.
The closing section covers how the specifications are adopted here; everything
before it records behaviour.

Entries are grouped by root cause rather than by test, so one entry covers every
test it affects, whichever specification or tier the tests came from. The four
headings are fixed, appear in order, and appear even when they hold nothing. Three
further headings follow them: **Investigated and not defects**, which records
claims raised during derivation and then refuted, so nobody re-reports them;
**Candidate issues**, which is the "Filing issues from deviations" output that
`writing-derived-tests.md` asks for — the same deviations classified into distinct
issues, ranked, for a maintainer deciding what to file; and **How the specifications
are adopted here**, which records the choices behind the harness rather than the
behaviour.

Three counts differ here, and every figure below says which of them it is. A **Test
ID** is the specification's own identifier for a test, carried in a `# UTS:` comment. A
**derived test** is a test function written under one. A **pytest case** is one run of
one function. They diverge in both directions.

One Test ID can become more than one derived test: five Test IDs in `rest/unit` — in
`error_types_test.py`, `fallback_test.py`, `rest_client_test.py` (two) and
`paginated_result_test.py` — assert several independent things under a single id, and
the derivation writes a function for each rather than one function with an unrelated
second half. That turns 1132 Test IDs into 1141 derived tests. Going the other way, one
derived test can become more than one case: five of the twelve `rest/integration`
specifications and five of the twenty `realtime/integration` ones carry a `## Protocol
Variants` section and run every one of their tests twice, once per protocol, and nine
`rest/unit` tests are parametrized over a table of fixtures the specification gives
inline. That turns 1141 derived tests into 1234 pytest cases.

Of **1132 Test IDs, derived as 1141 tests and run as 1234 pytest cases**: 905 Test IDs
(914 tests, 1002 cases) pass, 212 (212 tests, 217 cases) are gated behind
`RUN_DEVIATIONS`, and 15 (15 tests, 15 cases) cannot be run at all. The three groups are
disjoint: two Test IDs, and one parametrized test, have a gated part and a passing part,
and are counted with the gated. Every gated test has been confirmed to fail when
enabled, so none of them passes under both behaviours. 494 of the Test IDs come from
`uts/rest/unit` (503 tests, 536 cases), 481 from `uts/realtime/unit` (481, 481), 84
from `uts/rest/integration` (84, 122) and 73 from `uts/realtime/integration` (73, 95); 8
of the REST integration ids (8, 8) and 30 of the realtime ones (30, 30) come from the
`proxy` package within each. Of the gated Test IDs 122 are REST and 90 realtime, which is
126 REST cases and 91 realtime.
A further 122 pytest cases under `helpers/` cover the mock infrastructure itself and are
not derived from a specification.

The 202 gated Test IDs that record SDK non-compliance — 202 tests, 207 cases — reduce to
**71 distinct root causes**, 27 on the REST side and 44 on the realtime side. Three further
defects are recorded below with no test of their own, because the specification's test
cannot discriminate (RTP18a), has nothing to assert against (the timezone split on
synthesized LEAVE timestamps), or is worked around in the setup of every test that
would otherwise trip over it (`enterClient` on an anonymous connection), so the file
carries **74 SDK root causes** in all. The remaining 10 gated Test IDs are
specification faults, and reduce to 7.

Entries closed by a fix are removed rather than kept as history; `git log` holds that.

Run the whole suite, and then the gated tests, with:

```
uv run --frozen --extra crypto --extra dev pytest test/uts -q
RUN_DEVIATIONS=1 uv run --frozen --extra crypto --extra dev pytest test/uts -q
```

## UTS Spec Errors

Faults in the specifications themselves, found while deriving. A fault here is not an
SDK deviation, so it is recorded against the specification and not adapted to what the
SDK happens to do.

Where a specification *asserts* something `features.md` or `protocol.md` contradicts,
there is no spec-correct assertion left to write. The test is still derived faithfully
from the specification text, so that correcting the specification is all it takes to make
it pass, and it is marked `@spec_error` — a skip gated on `RUN_DEVIATIONS`, the same gate
`@deviation` uses, with a reason naming the specification rather than the SDK. The suite
stays green, a real regression still shows, and the failure is one environment variable
away. Each is filed upstream, in the issues named below. Ten tests are gated
this way:

| Test | Spec error |
|---|---|
| `test_rsl1a_publish_message_array` | RSL1c - an object payload asserted to travel unstringified |
| `test_rtl6i1_publish_message_object` | RTL6i1 - the same fault, repeated in the realtime publish spec |
| `test_rsl1k_mixed_ids_in_batch` | RSL1k - an absent id in a mixed batch asserted to be generated |
| `test_rsa4a2_expired_token_no_renewal` | RSA4a2 - local expiry detection demanded |
| `test_rsa4b1_preemptive_renewal` | RSA4b1 - local expiry detection demanded |
| `test_rsa4b_renewal_msgpack_response` | RSA4b - renewal driven through the unauthenticated `/time` |
| `test_rsa10i_authorize_preserves_key` | RSA10i - empty assertions, and a premise RSA8e contradicts |
| `test_rsp4_history_pagination` | RSP4 - wire action 4 asserted to be LEAVE |
| `test_tp3_presence_to_json` | TP3 - an outgoing action asserted as the string `"enter"` |
| `test_tp3_null_attributes_omitted` | TP3 - the same outgoing string assertion |

Where instead only a specification's *fixture*, *setup* or *label* is at fault, the
assertion it carries still stands. Those tests keep the corrected fixture (or the
corrected label in a comment), pass, and carry a `# UTS SPEC ERROR:` comment at the
site. The entries below cover both kinds and say which applies. Almost every realtime
fault is of the second kind, which is why only one realtime test is gated as a spec
error while fourteen `realtime/unit` entries appear below. The eight
`realtime/integration` faults are of that kind without exception, so none of them is
gated either.

The three sections that follow this one record SDK behaviour rather than specification
faults.

Raised upstream:

| Issue | Covers |
|---|---|
| [#523](https://github.com/ably/specification/issues/523) | `fallback.md` written against a mock API the contract does not define and the guide bans |
| [#524](https://github.com/ably/specification/issues/524) | `/time` stubbed as an object rather than an array |
| [#525](https://github.com/ably/specification/issues/525) | Spec points mislabelled across four specs |
| [#526](https://github.com/ably/specification/issues/526) | Presence actions written as strings, and wire action 4 asserted to be LEAVE |
| [#527](https://github.com/ably/specification/issues/527) | Wire encodings that contradict the features spec, and eight specs that read a body without pinning the protocol |
| [#528](https://github.com/ably/specification/issues/528) | Fixtures that cannot hold their stated values |
| [#529](https://github.com/ably/specification/issues/529) | Token expiry tests that demand optional behaviour |
| [#530](https://github.com/ably/specification/issues/530) | Token renewal driven through `/time` |
| [#531](https://github.com/ably/specification/issues/531) | `RSA10i` asserting that an API key survives `authorize()`, with no assertions |
| [#532](https://github.com/ably/specification/issues/532) | Housekeeping: a leaked local path, sections carrying no Test ID, a duplicate, misfiled tests |
| [#542](https://github.com/ably/specification/issues/542) | Two presence specifications contradicting themselves over the wildcard clientId |
| [#543](https://github.com/ably/specification/issues/543) | Tests that cannot detect what they exist to detect |
| [#544](https://github.com/ably/specification/issues/544) | Fixtures that cannot produce the condition they describe |
| [#545](https://github.com/ably/specification/issues/545) | Fixtures written against mock methods the contract does not define |
| [#546](https://github.com/ably/specification/issues/546) | Connection setups crediting a key-authenticated client with an initial token request |
| [#547](https://github.com/ably/specification/issues/547) | A device identity token hard-coded to a literal the server rejects |
| [#548](https://github.com/ably/specification/issues/548) | A restricted-key test closing the connection that owns the presence member it asserts on |
| [#549](https://github.com/ably/specification/issues/549) | A time-range test that passes when the range is ignored, under three rotated section labels |
| [#550](https://github.com/ably/specification/issues/550) | Housekeeping in the integration tier: two short headers, a JWT fixture, an empty presence array |
| [#551](https://github.com/ably/specification/issues/551) | Three sections whose heading or setup contradicts the steps and assertions below it |
| [#552](https://github.com/ably/specification/issues/552) | `proxy/connection_resume.md`: a status code neither SDK returns, a proxy substitution that does not exist, and event-log fields the proxy does not emit |
| [#553](https://github.com/ably/specification/issues/553) | A heartbeat-starvation test that closes the socket thirteen seconds inside the idle window |
| [#554](https://github.com/ably/specification/issues/554) | Two sections provoking one server response, leaving the revoked-key point uncovered |

`#527` also carries a comment on the realtime wire-format assertions, `#532` one on the
same housekeeping categories in `realtime/unit`, and
[#466](https://github.com/ably/specification/issues/466) — which is not ours — one on the
RSA4c3 contradiction, since that issue is what decides it.

`#547` to `#550` are the `uts/rest/integration` faults and `#551` to `#554` the
`uts/realtime/integration` ones. Each of them is of the second kind — a fixture, a setup
step or a header label — so the derived test keeps the corrected fixture and passes, and
none of them is among the ten gated above.

Not every entry has an issue of its own: the URL-safe base64 alphabet is recorded below
and not filed, because ably-python's own encoding settles the tests either way. Line
references in these entries are against `ably/specification@d9a04ca`.


### `/time` is stubbed as an object rather than an array

`fallback.md` (~14 setups), `rest_client.md` (6), `request_endpoint.md` (4),
`token_renewal.md` and `authorize.md` stub `/time` as `{"time": N}`. The endpoint
returns a one-element array, which is what `time.md` itself uses and what RSC16
describes. Any SDK that indexes the array raises.

### Spec points are mislabelled across four specs

The assertions are sound; the points they are filed under are not.

| Spec | Filed as | `features.md` says |
|---|---|---|
| `error_types.md` | TI2 = `statusCode`, TI3 = `message`, TI5 = `cause` | TI1 carries every attribute. TI2 is "server errors inherit from ErrorInfo", TI3 the ably-common submodule, TI5 help URLs in log entries. Only TI4 (`href`) is right |
| `token_types.md` | TD1 = token … TD5 = clientId | Every TD label is one short: TD1 is the type, TD2 = token … TD6 = clientId. TE2 and TE4 are swapped, "TE6 - nonce" names the point given to `fromJson`, and there is no TK6 at all |
| `authorize.md` | RSA10e, RSA10g, RSA10h, RSA10i | RSA10e is features RSA10g, RSA10g is RSA10f, RSA10h is RSA10j, and RSA10i maps to nothing |
| `idempotency.md` | RSL1k2 = id format, RSL1k3 = unique base | RSL1k1 is the id format, RSL1k2 client-supplied ids, RSL1k3 mixed batches. RSL1k4 and RSL1k5 are listed with no tests |

The cost is coverage: TI2, TI3 and TI5 *as specified* are untested by the suite.

### Generated message IDs are asserted to be URL-safe base64

`RSL1k2/message-id-format-0` and `RSAN1c4/idempotent-id-generated-0` assert
`[A-Za-z0-9_-]+`. `features.md` RSL1k1 requires only "base64-encoding a sequence of
at least 9 bytes" and names no alphabet, so the specification is stricter than its
source and rejects a conforming SDK's ids at random. ably-js encodes with the
standard alphabet and would fail both.

ably-python now encodes URL-safe, so both tests are derived and pass. That settles
the tests, not the specification: RSL1k1 still needs either to name the alphabet or
to let the tests accept both.

### Wire encodings contradict the features spec

- `publish.md` RSL1c asserts `body[1]["data"] == {"key": "value"}`. RSL4c3 and RSL4d3
  require an object payload to be JSON-stringified with `encoding` set to `"json"`.
  `channel_publish.md` RTL6i1 repeats it for the realtime publish, which RTL6a defers
  to `RestChannel#publish`, so the two are one fault in two files.
- `publish.md` RSL1e asserts exact equality against a whole message body, which
  cannot hold while idempotent publishing (RSL1k1, on by default) adds an `id`.
- `RSL1k/mixed-ids-in-batch-1` expects a generated id for the id-less message in a
  mixed batch. RSL1k1 generates ids only when every message lacks one, and RSL1k3
  requires ids "present or absent" to be preserved.
- `batch_publish.md` RSC22c6 asserts base64 with `encoding: "base64"` for binary
  payloads, which is the RSL4d1 JSON-protocol branch. The test never sets
  `useBinaryProtocol: false` and TO3f defaults it true, so RSL4c1 governs.
- `auth_scheme.md` asserts a raw `Bearer <token>`. RSA3b makes Base64 optional, and
  ably-python and ably-js both encode.
- `channel_delta_decoding.md` asserts a vcdiff-decoded payload equals a *string*
  literal, although the same file's transport note applies utf-8 only "if present"
  and the messages in question carry no utf-8 step, so the decoded payload is binary.
  See the Adapted entry below.

### Token expiry tests demand optional behaviour

`RSA4a2/expired-token-no-renewal-0` and `RSA4b1/preemptive-renewal-0` require local
expiry detection. RSA4b1 makes it optional *and* conditional on having persisted a
clock offset per RSA10k and judging expiry against Ably service time rather than the
local clock. Neither setup establishes that precondition.

`RSA4b/renewal-msgpack-response-4` drives a renewal flow through `client.time()`.
`/time` is unauthenticated — the same suite's `RSC16/no-auth-required-2` asserts it
carries no `Authorization` header — so it cannot return a token error or trigger
renewal in any SDK.

### `RSA10i` asserts that an API key survives `authorize()`

RSA8e says provided `AuthOptions` "are used instead of the stored values (even when
null)", and RSA10j repeats it. No features point requires key preservation, and
ably-js's own error text reads "A passed authOptions replaces the stored options
rather than merging." `RSA10k`'s setup depends on the same premise and cannot reach
`/time` without it. `RSA10i` also has an empty assertions block.

### Fixtures that cannot hold their stated values

- `RSP5/decode-cipher-channel-7`: the ciphertext is 32 bytes, an IV plus one AES-CBC
  block, but the stated plaintext `{"secret":"data"}` is 17 bytes and pads to two
  blocks. Decrypting it yields `{"example":{"jso` — a truncated copy of a longer
  fixture.
- `RSL6b/unrecognized-encoding-preserved-0`: the payload `"encrypted-data-here"` is
  not decodable base64 (17 alphabet characters), yet the test asserts base64 is
  decoded and the result is bytes.
- `RSL4/encoding-fixtures-ably-common-0` loads `encoding.json` from ably-common. No
  such file exists; RSL6a1 names `messages-encoding.json`, which has a different
  schema and runs in the decode direction.

### Presence actions are written as strings

Presence wire fixtures across `rest_presence.md` and `presence_message_types.md`
write `"action": "enter"`. `protocol.md` encodes the action as the enum ordinal, and
the suite's own TP2 asserts ordinals. `presence-to-json-2` is the sharpest case: it
asserts an *outgoing* body carries `"enter"`, which would be invalid on the wire.

`RSP4/history-pagination-1` asserts action `4` is `leave`, contradicting
`RSP4a/history-returns-paginated-1` and `RSP5/presence-action-mapping-8` in the same
file, and the protocol, which fix LEAVE at 3 and UPDATE at 4. The closing note on
`RSP_Action_1` ("3 = leave (some SDKs use 4)") invites the confusion and should go.

### Fallback tests contradict each other and the retry rules

- `RSC15f/successful-fallback-cached-0` queues a response for one named fallback and
  asserts it is chosen, which contradicts `RSC15a/fallback-random-order-0` in the
  same file.
- `RSC19d/response-status-code-0` and `response-success-indicator-1` queue a single
  500, but RSC15l3 requires a 5xx to be retried against every fallback host, so the
  first attempt consumes it.
- `RSC15l4`'s CloudFront body `{"error": "Forbidden"}` is not a valid Ably error
  shape; real CloudFront returns HTML.
- Error bodies throughout omit `message` and `statusCode` while tests assert
  `error.statusCode`. An SDK that reads the status from the payload cannot satisfy both.

### Batch response envelopes disagree between sibling specs

`batch_presence.md` states that with `X-Ably-Version >= 3` the server returns a
`BatchResult` envelope "for all batch responses" and calls the plain array legacy.
Every mock in `batch_publish.md` uses the plain array. `features.md` RSC22b backs
`batch_publish.md` — "the response will still be an array" — so `batch_presence.md`'s
claim is the one to revisit. `revoke_tokens.md` has the same internal split:
`RSA17c_1` and `TRS2_1` stub a bare array while asserting envelope fields.

`batch_publish.md` RSC22_Headers1 also pins `X-Ably-Version: 2` and
`Content-Type: application/json`; CSV2b templates the version, the sibling spec says
">= 3", and the binary protocol default makes the content type msgpack.

The revocation half of that split is settled by the server. `POST
/keys/{keyName}/revokeTokens` with `X-Ably-Version: 5` answers 201 with the
`{successCount, failureCount, results}` envelope `revoke_tokens.md`'s "Server Response
Format" section describes, for a mixed success/failure batch as well as an all-success
one, so it is the two mocks that stub a bare array that are wrong rather than the
assertions that read the envelope. Two further details of that response were measured
at the same time: an invalid target type comes back as code **40001** where the
specification's example writes 40000, though only the status code is asserted either
way; and `issuedBefore` is echoed unchanged while `allowReauthMargin: true` pushes
`appliesAt` about 30.1 seconds past server time (30089 ms in one run), which is what
RSA17e's two assertions need.

### Two presence specifications contradict themselves over the wildcard clientId

The same contradiction appears twice, mirrored, and the two should be settled together.

- `realtime_presence_enter.md`: `RTP15c/enterclient-no-side-effects-0` builds a client
  with `clientId: "*"` and expects `presence.enter()` to succeed, while
  `RTP8j/enter-wildcard-clientid-errors-1` **in the same file** requires that exact call
  to fail. No implementation can satisfy both. ably-python raises `AblyException` 40012
  (`ably/realtime/presence.py:99-104`), which is the RTP8j reading.
- `realtime_presence_reentry.md`: `RTP17g/reentry-publishes-enter-with-data-0` builds a
  client with `clientId: "admin"` and calls `enterClient("alice", …)`, noting "Use a
  concrete clientId and rely on server-side permission for enterClient". RTP15f requires
  an identified client whose `clientId` does not match the argument to indicate an error
  locally, so there is nothing for server-side permission to decide. ably-python raises
  40012 (`presence.py:229-234`), which is the RTP15f reading.

**Tests affected:** `test_rtp15c_enterclient_no_side_effects` makes its "normal" enter as
`enter_client('main-client', 'main-client')`; `test_rtp17g_reentry_publishes_enter_with_data`
holds the wildcard clientId, the only clientId RTP15f permits `enterClient` for another
user from. Both then assert everything the specification is actually about, and both pass.

### RTP18a's test cannot detect the non-compliance it targets

**Spec point:** RTP18a, `presence_sync.md`, `realtime/unit/RTP18a/new-sync-discards-previous-1`.

RTP18a requires that a new sync sequence identifier discard any in-flight sync, so that a
member delivered by the first sync but *absent* from the second is evicted. The test's two
syncs are nested rather than divergent: the map is pre-populated with `alice` and `bob`,
the first sync delivers **alice only**, and the second delivers **alice and bob**. Under
the compliant behaviour the second `startSync()` re-snapshots the residual set as
{alice, bob} and both are seen, so nothing is left over; under the non-compliant behaviour
the first sync's residual set {bob} carries across and bob is seen in the second sync, so
nothing is left over there either. Both paths give `leave_events.length == 0` and a map of
two, which is exactly what the test asserts. An SDK that ignores RTP18a entirely passes it.

The neighbouring RTP18c test shows what this one needs: its sync **omits** bob, and so it
does discriminate.

This one is worth fixing, because ably-python does ignore the requirement —
`PresenceMap.start_sync()` is guarded by `if not self._sync_in_progress`
(`ably/realtime/presencemap.py:255-262`), so a second start while a sync runs is a
complete no-op — and the test passes anyway. **To catch it, the second sync must omit a member
the first sync delivered**, and the test must then assert that member is gone.

**Tests affected:** `test_rtp18a_new_sync_discards_previous`, derived as written and
passing without discriminating. The SDK-side finding is recorded under Failing Tests as a
deviation with no test, because there is no test to gate.

### RTL2i asserts an attribute the features spec makes optional

**Spec point:** RTL2i and TH6, `channel_state_events.md`,
`realtime/unit/RTL2i/has-backlog-flag-true-0`.

Both RTL2i and TH6 word `hasBacklog` as optional — "may optionally expose", "may contain
an attribute" — and the test asserts it unconditionally, so an SDK that takes up the
option not to expose it cannot pass. The sibling `has-backlog-flag-false-1` gets this
right: its assertion is the disjunction "`hasBacklog == false` OR `hasBacklog IS null`",
which a missing attribute satisfies.

**Tests affected:** `test_rtl2i_has_backlog_flag_true` is gated as a Failing Test, since
exposing the flag is the behaviour worth having; `test_rtl2i_has_backlog_flag_false` is
derived as the disjunction and passes. The specification should either make the assertion
conditional the way its sibling does, or `features.md` should make the attribute mandatory.

### Sections carrying no Test ID were not derived

A section with no `**Test ID**` gets no test — there is nothing to name it by, and a
derived test that invents an id cannot be traced back. Three realtime specifications are
in this position:

| Spec | Sections with no Test ID |
|---|---|
| `client/realtime_client.md` | three runnable pseudocode blocks in its two trailing sections, `## Shared Options (Reference to REST Client Tests)` and `## Connection URL Query Parameters`: `#### TLS Setting (RSC18) in Realtime`, `#### useBinaryProtocol in Realtime` and `### Standard Query Parameters`. The third trailing section, `## Test Infrastructure Notes`, is prose and wants no test |
| `channels/channel_annotations.md` | RTAN3a |
| `presence/realtime_presence_history.md` | RTP12d, which the header's `Spec points` line lists |

Each has a setup and assertions, so they read as tests that lost their ids rather than as
prose never meant to carry one. `channel_detach.md`'s id-less `## [REMOVED] RTL5 - Detach
clears errorReason` is the one deliberate case, and says so in its body. RTP12d is the
exception worth arguing: `features.md`
describes it as a multi-client test made against the service, which is not a unit test, so
there it is the header reference that should go. The equivalent REST fault is recorded
above — six sections under `uts/rest/unit` also carry no Test ID.

### `channel_options.md`'s header omits seven of its own spec points

The header reads `Spec points: TB2, TB3, TB4, RTS3b, RTS3c, RTS3c1, RTS5, RTL16`, and the
file then carries sections for **TB2c, TB2d, RTL16a, RTS5a, RTS5a1, RTS5a2 and DO2a** as
well. No test is affected — the derived module docstring lists all of them — but the header
is what a reader uses to find coverage. Label fault only. The file is also the only one
under `channels/` with no `## Mock Infrastructure` section, which is consistent with the
three setups below that attach on a client that never connected.

### Fixtures that cannot produce the condition they describe

Each of these carries a sound assertion on an unreachable premise. The derived test
corrects the fixture, keeps every assertion, and carries a `# UTS SPEC ERROR:` comment at
the site.

| Spec point | Fixture | Why it cannot hold |
|---|---|---|
| RTN25 (`error_reason_test.md`), RTN14e (`connection_open_failures_test.md`) | `DEFAULT_CONNECTION_STATE_TTL = 5000` | `connectionStateTtl` defaults to 120 s (DF1a) and is otherwise a `connectionDetails` value. Neither test ever connects, so nothing can supply 5000; it is a value the fixture wishes for, and RTN14e's own comment says so — "For this test, we'll use a short default value". Both derived tests advance past the SDK's own default instead, which on notional time costs nothing |
| RTL6c4, RTN7e (`channel_publish.md`) | `ClientOptions(connectionStateTtl: 5000)` | There is no such client option. DF1a makes it a default and CD2f a `ConnectionDetails` field; `features.md` lists it under `Defaults`, not `ClientOptions`. The specification should set it in the CONNECTED `connectionDetails` — though see the RTN21 deviation, which means even that would not shorten it here |
| RTN24 (`update_events_test.md`) | the second CONNECTED changes `clientId` from `client-original` to `client-updated`, then asserts the connection is still CONNECTED | RTN24 names the details it overrides as *operational* parameters; silently re-identifying an already-identified connection is not one of them. ably-python treats it as an incompatible clientId and goes FAILED with 40102, so the fixture's two assertions cannot both hold here. Note the strict citation is RSA7b3, which governs a `connectionDetails.clientId` and mandates no FAILED transition — RSA15c is scoped to auth requests carrying a `TokenDetails` or `TokenRequest`, so whether the SDK is *right* to fail is a separate question from whether the fixture is sound. The derived test holds the clientId and asserts the operational-parameter override the test is actually about |
| RTL13b (`channel_server_initiated_detach.md`) | `realtimeRequestTimeout: 100`, `channelRetryTimeout: 200`, `ADVANCE_TIME(150)`, `ADVANCE_TIME(250)`, then `AWAIT_STATE channel.state == attaching` | The advance windows are too tight for the state they assert, in two different ways. Against ably-python, whose retry timer is the flat `channelRetryTimeout` (no RTB1 backoff or jitter), SUSPENDED is entered at t=100, the retry falls due at t=300 and its attach times out at t=400 — precisely the end of the 250 ms window, so the observed state turns on whether a timer due exactly on the boundary fires. Against a **conforming** SDK the same window is worse: RTB1's backoff and jitter put the second cycle's retry somewhere in 213–267 ms, so `ADVANCE_TIME(250)` clears it only about seven times in ten and the test is flaky by construction. The derived test asserts the specification's own `attach_count == 3` at that point instead. Upstream should widen the gap between the two timeouts, and size the windows for the jittered upper bound |
| RTL4b (`channel_attach.md`) | `channelRetryTimeout: 100` ("short timeout for testing"), then `AWAIT_STATE client.connection.state == suspended` | `channelRetryTimeout` governs channel retries, not the connection's suspend timer, which runs for `connectionStateTtl`. The test does not enable fake timers either, so on real time it would wait out two minutes. Derived with a `FakeClock`, passing the named option through unchanged |
| RTP5f, RTL11 (`realtime_presence_channel_state.md`) | `simulate_disconnect()` then `AWAIT_STATE channel.state == suspended` | A transport drop reaches DISCONNECTED. RTL3c propagates SUSPENDED to channels only from a SUSPENDED *connection*, so the awaited state never arrives. RTP5f's own note ("e.g. connection transitions to SUSPENDED") says as much; the steps do not carry it out |
| RTP5a (`realtime_presence_channel_state.md`) | detach, then `presence.get(waitForSync: false).length == 0` | RTP11e has `get` run the ensure-active-channel procedure for any state but SUSPENDED, so the read-back re-attaches the channel and the specification's own server then repopulates the very map being checked for emptiness. The derived test reads the two maps directly |
| RTS3c1, RTL16a (`channel_options.md`), RTS4a (`channels_collection.md`) | `autoConnect: false`, no mock installed, `connect()` never called, then `AWAIT channel.attach()` and assert ATTACHED | RTL4b requires `attach()` to fail unless the connection is CONNECTING, CONNECTED or DISCONNECTED, and with no mock nothing would answer the ATTACH in any case. Derived with a mock that connects and answers each ATTACH. Upstream should give these three setups a mock, as the sibling sections of the same files do |
| RTS3c1 `error-reattach-modes-1` (`channel_options.md`) | `# Put channel in attaching state (implementation detail)` | The premise the test turns on is the one step it does not give, and the setup has no mock to reach ATTACHING with |

### Fixtures written against mock methods the contract does not define

`uts/realtime/unit/helpers/mock_websocket.md` is the contract. These call members it does
not have.

| Spec point | Written | The contract offers |
|---|---|---|
| RTL5l (`channel_detach.md`) | `conn.respond_with_connected()`, and assigning `mock_ws.active_connection = conn` | `respond_with_success(connected_message: ProtocolMessage)`. `respond_with_connected` appears nowhere else in `uts/`, and is called here with no argument, so no CONNECTED would reach the client even if it existed. Assigning `active_connection` is a second fault — see the note below on members the contract never declares |
| RTN13d (`connection_ping_test.md`) | `mock_ws.active_connection.close_from_server()` | `simulate_disconnect()`, which is the server ending the connection without a protocol message |
| RTN16f, RTN16j (`connection_recovery_test.md`) | `mock_ws.events.filter(e => e.type == "ws_frame" AND e.direction == "client_to_server")` | `MESSAGE_FROM_CLIENT`. There is no `ws_frame` type and no `direction` field, and every other specification in the suite reads `MESSAGE_FROM_CLIENT` |
| RTN17f (`fallback_hosts_test.md`) | `conn.respond_with_error("Host unresolvable")`, under a comment reading "Primary domain: unresolvable (simulated)" | `respond_with_error` *establishes* the connection and has the server send an ERROR `ProtocolMessage`, and takes a message rather than a string. The condition meant is RSC15l's host-unreachable, which the contract spells `respond_with_dns_error()` |

Four further names are used across the realtime specifications without ever being
declared by the mock contract, which is a gap in `helpers/mock_websocket.md` as much as in
the tests that lean on it:

- **`mock_ws.active_connection`** is used by dozens of tests and appears in
  `mock_websocket.md` only inside two usage examples; `interface MockWebSocket` does not
  declare it. `fallback_hosts_test.md` also calls `mock_ws.active_connection.close()`,
  which is neither declared nor equivalent to anything that is.
- **`MockEvent` has no `connection` or `message` field** — only `type`, `timestamp` and
  `data` — yet `connection_recovery_test.md` reads `…find(e => e.type == CONNECTION_SUCCESS).connection`
  and `f.message.action`, and `connection_failures_test.md` does the same.
- **`MockWebSocketClient`** appears once, in `channel_history.md`; every other file uses
  `MockWebSocket`.
- **`create_realtime_client(...)`** appears in `connection_open_failures_test.md` and
  `channel_detach.md`; every other file writes `Realtime(options: …)`.

This harness implements `active_connection` and gives `MockEvent` the fields the tests
want, so none of these costs a test. They are recorded because the contract is the thing
a new SDK derives against, and four of its most-used members are not in it.

### A specification note instructs SDKs to suppress a mandatory check

`realtime_presence_enter.md`'s header note tells implementers to skip the client-side
RTP15f `enterClient` clientId-mismatch check so that the file's fixtures pass. A UTS
specification asking an SDK to drop a `features.md` requirement in order to be testable is
the wrong way round: the fixtures should change. It is the same wildcard problem as the
RTP15c/RTP8j contradiction above, and settling that settles this.

### RTN17i names a primary domain REC1 no longer produces

`RTN17i/prefer-primary-domain-0` asserts `connection_attempts[0].host == "realtime.ably.io"
OR … CONTAINS "realtime.ably"`. REC1 derives the primary domain from the endpoint, which
defaults to `main`, giving `main.realtime.ably.net`. The disjunct saves the assertion, so
the test still means what it should, but the first branch can never hold for an SDK that
implements REC1. `test_rtn17i_prefer_primary_domain` asserts equality with the REC1 domain
and passes.

### Three connection setups credit a key-authenticated client with an initial token request

**Spec points:** RTN15h2 (`token-error-renew-success-0`), RTN15c5
(`token-error-during-resume-0`), RTN14b (`token-error-with-renewal-0`).

Each sets the client up with `ClientOptions(key: "appId.keyId:keySecret")` alone, stubs
`/keys/…`, and then asserts `token_request_count == 2  # Initial + renewal`. RSA4 has a
client given only a key authenticate with basic auth; token auth is selected by
`useTokenAuth`, a `clientId`, an `authCallback`, an `authUrl` or a supplied token, and none
of the three setups does any of that. No SDK makes an initial token request here, so the
renewal is the first and only one — the assertion contradicts the specification's own
setup, not just ably-python.

All three derived tests assert `len(token_requests) == 1`, carry a `# UTS SPEC ERROR:`
comment, and pass; the assertion the specification is really making — that the token was
renewed — is preserved.

RTN14b's sibling `token-renewal-fails-1` has a second fault: its `onConnectionAttempt`
sends an ERROR `ProtocolMessage` without first calling `respond_with_success()`, and the
contract produces a `MockConnection` only once an attempt is answered, so the message can
reach nobody. Every other test in the same file establishes the connection first; the
derived test answers the attempt with `respond_with_error`, which does both.

### Two specifications assert opposite things about RSA4c3's `errorReason`

`connection_auth_test.md` (`RSA4c3/callback-error-stays-connected-0`) asserts that an
authCallback failure during an RTN22 reauth leaves `connection.errorReason` set to an
80019 whose `cause` is the callback's error. `auth_callback_errors_test.md`
(`RSA4c3/callback-error-connected-stays-0`) asserts the opposite in its own words —
"errorReason is NOT set … the auth failure is silently swallowed" — citing
[specification#466](https://github.com/ably/specification/issues/466).

`features.md` as it stands backs the first: RSA4c1 says an ErrorInfo with code 80019
"should be emitted with the state change if there is one (per RSA4c2/3) **and set as the
connection errorReason**". Both are derived as written.
`test_rsa4c3_callback_error_stays_connected` is gated as a Failing Test, because the
current `features.md` makes it the spec-correct reading, and
`test_rsa4c3_callback_error_connected_stays` passes, because ably-python happens to behave
the way #466 proposes. Neither fails fast: the contradiction is between two UTS specs and
an unlanded features change, not an assertion `features.md` flatly refutes. Whichever way
#466 lands, one of the two has to be regenerated from the corrected spec.

### RTN19a2's assertion cannot distinguish the behaviours it separates

`RTN19a2/new-serial-failed-resume-1` publishes two messages, which take `msgSerial` 0 and
1, then asserts that after a **failed** resume the resent messages carry 0 and 1 — the same
values a **successful** resume preserves, and exactly what its paired test
`RTN19a2/same-serial-on-resume-0` asserts. An SDK that ignored RTN15c7's counter reset
entirely would pass both. Publishing a third message after the reconnect and asserting
*its* `msgSerial` is what would separate them.

The test is derived as written and passes, and is not made fail-fast: the specification is
under-determined rather than contradicted by `features.md`, so there is still a correct
(if weak) assertion to make. The SDK-side finding it would have caught is real and is
recorded under Failing Tests.

### RTC12 points at a specification file that does not exist

`realtime_client.md` RTC12 `constructor-string-detection-0` says
"**See:** `uts/test/realtime/unit/client/client_options.md` - RSC1, RSC1a, RSC1c", and
"The same test cases apply". No such path exists — `uts/test/…` is not a directory — and
no RSC1, RSC1a or RSC1c test is declared anywhere under `uts/rest/unit`, so the referenced
cases cannot be reused because they were never written. The same section's second
reference, `RTC12/invalid-arguments-error-1` → `auth_scheme.md` RSC1b, does resolve.

`test_rtc12_constructor_string_detection` is derived from the three cases the specification
lists in its own body — API key string, token string, empty string — with a `# NOTE:` at
the site recording the broken reference. Either write the RSC1/RSC1a/RSC1c tests and fix
the path, or drop the reference and keep the inline cases as the definition.

### Duplicated, misfiled and mis-commented realtime tests

| Spec | Fault |
|---|---|
| `auth_callback_errors_test.md` | `RSA4e/rest-callback-error-40170-0` drives a REST client and a mocked HTTP client but takes a `realtime/unit/` Test ID. The same class of fault as `fallback.md`'s REC3a/REC3b/REC3, which drive a Realtime client from `rest/unit`. Derived where its Test ID puts it, and it passes |
| `connection_auth_test.md`, `auth_callback_errors_test.md` | RSA4c2 is the same test in both files: `callback-error-causes-disconnected-0` and `callback-error-connecting-disconnected-0` have the same authCallback, the same mock and the same four assertions, and the second adds only `useBinaryProtocol: false` and a `state_changes` listener. The closing note of `auth_callback_errors_test.md` acknowledges the overlap without removing it. Both are derived, since each has its own Test ID |
| `channel_properties.md` | `RTL15b/serial-not-updated-irrelevant-3`'s closing comment reads "RTL15b2 clears it on DETACHED/FAILED, then ATTACHED sets it fresh". The DETACHED it injects arrives while the channel is ATTACHED, so RTL13a reattaches and the DETACHED *state* is never entered. Nothing clears the serial; it is simply never written from the DETACHED message. The assertion the comment sits above is still the right one |

### `push_channels.md` hard-codes a device identity token the server rejects

**Spec points:** RSH7a, RSH7c, `rest/integration/RSH7a/subscribe-unsubscribe-device-0`.
Filed as [#547](https://github.com/ably/specification/issues/547).

The setup's own comment says "The deviceIdentityToken is obtained from the registration
response", and the pseudocode immediately beneath it writes
`deviceIdentityToken: "test-device-identity-token"`. The comment is right and the code is
not. RSH7a2 and RSH7c2 authenticate as the device, and the server refuses a token it did
not issue — `POST /push/channelSubscriptions` with `X-Ably-DeviceToken:
test-device-identity-token` answers 400/40005, "Invalid accessToken in request". The real
one comes back from `PUT /push/deviceRegistrations/{id}`, under `deviceIdentityToken` as
an object of `{token, keyName, issued, expires, capability}`, and its `token` is accepted:
the same subscribe and unsubscribe answer 201 and 204.

`test_rsh7a_subscribe_unsubscribe_device` takes the issued token, through
`issued_device_identity_token(registration)`, and would fail 40005 whatever the SDK did
if it took the literal. `test_rsh7b_subscribe_unsubscribe_client` keeps the placeholder,
because RSH7b2 and RSH7d2 subscribe by clientId and neither sends `X-Ably-DeviceToken` —
the unit tier pins that, and the server accepts the clientId subscription on the client's
ordinary credentials.

### Closing the realtime client destroys the presence the following REST read is about

**Spec points:** RSC24 and BGF2 (`batch_presence.md`,
`rest/integration/RSC24/restricted-key-channel-failure-1`). Filed as
[#548](https://github.com/ably/specification/issues/548).

`batch_presence.md`'s restricted-key test enters `member-1` on the allowed channel and
`member-2` on the denied one, puts `AWAIT realtime.close()` between that fixture and the
REST read, and then requires `success.presence.length == 1` with
`success.presence[0].clientId == "member-1"`. A presence member belongs to the connection
that entered it, so closing the connection takes it away. Measured against the sandbox,
three runs, each querying before the close and at +0, +1 and +3 seconds after: before the
close the allowed channel carries `presence: ["member-1"]`; after it, `GET
/presence?channels=channel6,denied-…` answers `{"successCount": 1, "failureCount": 1,
"results": [{"channel": "channel6"}, {…"error": {"code": 40160, "statusCode": 401}}]}`
every time, the allowed channel carrying no `presence` key at all. Not a race. The other
two tests in the same file get it right and say so — "Keep realtime open during the REST
query so the presence member persists on the server."

The close belongs in cleanup, as the sibling tests put it. The derived test omits it and
leaves the suite's autouse teardown to close every client the test built, which is what
the specification's own cleanup step amounts to. Every assertion is the specification's,
unchanged.

`presence.md`'s RSP4b2 puts the same `AWAIT realtime.close()` in the same place and is
**not** affected, which is worth recording because it looks as though it should be. The
close does add a synthesized LEAVE as the newest presence event, so
`history(direction: "backwards").items[0]` is that LEAVE rather than the last update — but
the server gives the synthesized LEAVE the member's last data, so the assertion the
specification writes, `items[0].data == "third"`, still holds. Measured: before the close
the backwards page is `[(4, "third"), (4, "second"), (2, "first")]`, and after it
`[(3, "third"), (4, "third"), (4, "second"), (2, "first")]`, unchanged at +0.5, +1.5 and
+3 seconds. The derived test keeps the close. What the assertion cannot see is that it is
reading a LEAVE at all; `items[0].action` would pin the intent, and that is a remark on
[#548](https://github.com/ably/specification/issues/548) rather than a change asked for.

### RSL2b3's assertions cannot detect an ignored time range

**Spec point:** RSL2b3, `history.md`, `rest/integration/RSL2b3/history-time-range-0`.
Filed as [#549](https://github.com/ably/specification/issues/549).

The test publishes two "early" messages, waits 2 ms, publishes two "late" ones, computes a
boundary from the server-assigned timestamps, and queries twice — once from before the
early batch up to the boundary, once from just after the boundary to beyond the late
batch. Its four assertions are that each page is non-empty, that the early page contains a
name beginning `early`, and that the late page contains one beginning `late`.

None of those discriminates. A client or a server that dropped `start` and `end` entirely
would answer both queries with all four messages, and every assertion would still hold.
The test exists to show that the range filters, and it passes when the range is ignored.
What discriminates is the converse — that each window *excludes* the other batch. The
sandbox does filter exclusively: the early window returns `early2, early1` and the late
window `late2, late1`, and widening the early query's `end` to `min_late_ts + 1000`, which
is the mutation an ignored `end` amounts to, is caught only by the exclusion check.

`test_rsl2b3_history_time_range` carries the specification's four assertions verbatim and
then the two exclusion assertions it omits, under a `# UTS SPEC ERROR:` comment at the
site. It also asserts `min_late_ts > max_early_ts` first, which is the premise the
specification's own 2 ms wait exists to establish and which its boundary arithmetic
depends on: with both batches inside one millisecond there is no side of the boundary to
put them on, and the test should fail on the stated premise rather than on an exclusion
that cannot hold. It passes.

The same section is also filed under the wrong point, as are its two siblings.
`features.md` has RSL2b1 as `start` and `end`, RSL2b2 as `direction` and RSL2b3 as
`limit`; `history.md` heads them `RSL2b1 - History direction forwards`, `RSL2b2 - History
limit parameter` and `RSL2b3 - History time range parameters`, which rotates all three by
one. The sibling `presence.md` files the identical RSP4b family correctly, so it is
`history.md` alone. The Test IDs carry the specification's labels, so the derived tests
are named for the rotated points rather than the real ones.

### `connection_lifecycle_test.md`'s RTN4b fixture contradicts its own first assertion

**Spec point:** RTN4b, `realtime/integration/RTN4b/successful-connection-0`.

The setup builds `Realtime(key, endpoint)` and leaves `autoConnect` at the library
default; the first Test Step then asserts `connection.state == initialized`. RTN3 makes
that default **true**, so there is no moment at which both hold. ably-python's constructor
calls `request_state(CONNECTING, force=True)` synchronously — measured, the state is
already CONNECTING when the constructor returns. The sibling RTN11 test in the same file
does set `autoConnect: false`, which is what this one wants too, so the derived test adds
`auto_connect=False` and keeps every assertion.

Filed as [#551](https://github.com/ably/specification/issues/551).

### `auth.md`'s RSA7 mismatched-clientId test contradicts its own assertions

**Spec point:** RSA7, `realtime/integration/RSA7/mismatched-clientid-fails-1`.

Test Steps says `EXPECT THROW creating Realtime(options: …)`. The Assertions block
immediately below it says "the key assertion is that the connection enters FAILED state
with error code 40102". Both cannot hold: a constructor has no token to compare a clientId
against, so nothing is knowable until the server answers. Measured: construction does not
raise — the client comes back INITIALIZED — and the connection reaches FAILED with
40102/401 "invalid clientId for credentials" about fifteen seconds later. The derived test
drops the throw and makes the specification's own named assertion. The fifteen seconds are
not the server's: they are the spurious `disconnected_retry_timeout` recorded under
`#### A JWT string with a matching clientId is rejected 40102` below, which is why the
test waits twenty seconds rather than the default ten.

Filed as [#551](https://github.com/ably/specification/issues/551).

### `channel_attach_test.md`'s RTL14 heading and prose contradict its own test steps

**Spec point:** RTL14, `realtime/integration/RTL14/insufficient-capability-failed-0`.

The heading reads "Insufficient capability causes channel FAILED" and the prose has the
server "responds with a channel-scoped ERROR and the channel transitions to FAILED". The
Test Steps then say "Attach succeeds (subscribe-only key can attach to any channel)" and
assert `channel.state == ATTACHED` outright, and the Assertions read the publish error
and the connection state without looking at the channel again. Measured with `keys[3]`, `{"*": ["subscribe"]}`: the attach reaches
ATTACHED, the publish raises 40160/401 "Unable to publish a message due to lacking the
required 'publish' capability", and the connection is still CONNECTED. The steps are what
the server does, so the steps are what is derived, and the heading is the fault.

Filed as [#551](https://github.com/ably/specification/issues/551).

### `proxy/connection_resume.md`'s RTN15h1 asserts a 401 where the status code is 403

**Spec point:** RTN15h1, `realtime/proxy/RTN15h1/token-error-nonrenewable-failed-0`.

The section asserts `errorReason.statusCode == 401` beside `code == 40171`, and its own
note says it follows ably-js in expecting 40171. ably-js throws that `ErrorInfo` with
`statusCode: 403` (`src/common/lib/client/auth.ts`, the "Need a new token, but authOptions
does not include any way to request one" branch), and ably-python raises
`AblyAuthException(msg, 403, 40171)` at `ably/rest/auth.py:200`. Measured end to end
through the proxy: FAILED, 40171, 403. The derived test asserts 403 and passes. The
realtime unit tier arrives at the same 40171 by a different route — see
`### A token error with no means to renew reports the renewal failure, not the server's error`.

Filed as [#552](https://github.com/ably/specification/issues/552).

### `proxy/connection_resume.md`'s RTN14h asks the proxy for a substitution it does not make

**Spec point:** RTN14h, `realtime/proxy/RTN14h/resume-after-ttl-expiry-0`.

The rule replaces the first CONNECTED and writes `"connectionKey": "__PASSTHROUGH__"` in
both the frame and its `connectionDetails`, intending the proxy to fill in the key the
server issued. uts-proxy v0.3.0 has no such sentinel and passes the literal through.
Measured: the client took `__PASSTHROUGH__` as its connection key, reconnected with
`?resume=__PASSTHROUGH__`, and the sandbox answered `{'code': 80018, 'message': 'invalid
connection key: __PASSTHROUGH__'}`. The rule is kept verbatim, because the test is gated
on the TTL defect before the connection key matters. Either the proxy grows the
substitution or the specification stops asking for it.

Filed as [#552](https://github.com/ably/specification/issues/552).

### `proxy/connection_resume.md`'s RTN19a reads log fields the proxy does not emit

**Spec point:** RTN19a, `realtime/proxy/RTN19a/unacked-resent-on-resume-0`.

It filters the event log on `e.type == "ws_frame_to_server"` and `e.message.action ==
"MESSAGE"`. The proxy emits `type: "ws_frame"` with the direction in a separate
`direction` field, and `action` as the protocol integer. The same drift is already
recorded above for `connection_recovery_test.md`. The derived test reads the real field
names through a `frames(log, direction, action)` helper defined at the top of the file,
and asserts exactly what the specification asserts.

Filed as [#552](https://github.com/ably/specification/issues/552).

### `proxy/heartbeat.md` does not exercise the spec point it is filed under

**Spec point:** RTN23a, `realtime/proxy/RTN23a/heartbeat-starvation-reconnect-0`.

The file is titled "Heartbeat starvation causes disconnect and reconnect" and quotes
RTN23a — "if no activity is received for `maxIdleInterval + realtimeRequestTimeout`, the
transport should be disconnected". Its rule is `delay_after_ws_connect: 2000` followed by
`close`, so the proxy sends a WebSocket close frame two seconds into the connection.
Measured: the sandbox advertises `maxIdleInterval: 15000` in CONNECTED, so the close lands
thirteen seconds inside the window the idle timer would have measured, and the
disconnection observed is the close frame's doing. The specification's own Integration Test
Notes admit as much. Every assertion is sound for what the test does do, and the derived
test makes all of them; the fault is that the spec point is unexercised at this tier.
Exercising it wants a `suppress_onwards` rule, a wait past twenty-five seconds, and a
session `timeoutMs` long enough to survive the idle. uts-proxy's own API reference gives
that pairing as its worked "Heartbeat starvation" example.

Two smaller notes on the same file. It describes the connection as "re-established with
**new** connection details" where the resume in fact succeeds and the connectionId is
unchanged — measured identical across both connections; the assertions require only
non-null, so they hold either way. And it captures `first_connection_key` and never uses
it: the derived test spends it on
`ws_connects[1]['queryParams']['resume'] == first_connection_key`, which is measured true
and is the only place the connection key is observable in the scenario.

Filed as [#553](https://github.com/ably/specification/issues/553).

### `connection_failures_test.md`'s RTN14a and RTN14g are the same provocation

**Spec points:** RTN14a (`realtime/integration/RTN14a/invalid-key-failed-0`) and RTN14g
(`realtime/integration/RTN14g/revoked-key-failed-0`),
`connection/connection_failures_test.md`.

They are presented as "invalid API key" and "revoked key / deleted app", but both fixtures
name an application that does not exist and the sandbox answers both identically:
40101/401 "unable to handle request; no application id found in request". Both sets of
assertions admit that code — RTN14a as one of 40005 or 40101, RTN14g as anything outside
the token-error range 40140–40149 — so both derived tests pass, and the two differ in what
they assert about one shared server response rather than in the response they provoke.
RTN14g is not exercising a revoked key. Doing so wants a key that exists and has been
revoked, which neither fixture nor the app-provisioning section produces:
`ably-common/test-resources/test-app-setup.json`'s only revocation affordance is
`{"revocableTokens": true}`, which revokes tokens and answers 40141 — inside the
40140–40149 range RTN14g excludes.

Filed as [#554](https://github.com/ably/specification/issues/554).

### Smaller faults

| Spec | Fault |
|---|---|
| `options_types.md` | The `TO/endpoint-affects-host-0` "Expected Rest Host" column uses pre-REC1 hostnames (`rest.ably.io`, `test-rest.ably.io`). No assertion reads the column, so the derived test is unaffected |
| `channels_collection.md` (rest) | Header claims RSN3b and RSN3c; neither has a test |
| `stats.md` | Fixture nests counts under `all`, which `Stats.from_dict` never reads |
| `rest_client.md` | `RSC17` has two byte-identical tests; header lists RSC7 and RSC7b with no tests |
| `rest_client.md` | `RSC18` requires constructor-time failure; RSA1/RSC18 only say "any attempt to use" |
| `request.md` | `version` is written as an integer but lands in a header |
| `fallback.md` | REC3a, REC3b and REC3 drive a Realtime client but sit in `rest/unit` |
| `message_encoding.md`, `msgpack_interop.md`, `annotations.md` | Six sections carry no Test ID; ids were inferred by sibling convention |
| `publish.md`, `rest_presence.md`, `message_encoding.md`, `history.md`, `idempotency.md` | All point at `/Users/paddy/data/worknew/dev/dart-experiments/...` for the mock contract |
| `publish.md` (integration) | The `Spec points:` header reads RSL1d, RSL1l1, RSL1m4, RSL1n, and the file carries a fifth section, `## RSL1k5 - Idempotent publish with client-supplied IDs`, with its own Test ID. The section is sound; only the header is short. `auth.md` (integration) has the same shape: its header reads RSA4, RSA8 and it carries `## RSC10` with its own Test ID. Same housekeeping class as [#532](https://github.com/ably/specification/issues/532); filed as [#550](https://github.com/ably/specification/issues/550) |
| `auth.md` (integration) | RSC10's expired-JWT fixture is `generate_jwt(expires_at: now() - 5_seconds)`, naming `exp` and leaving `iat` open. Ably reads a JWT's lifetime as `exp - iat` and rejects a negative one with 400/40003 "Invalid value for ttl" before it considers expiry, so `iat` at now produces a token that fails the wrong way and never reaches the 40140–40149 renewal path the test is about. Backdating `iat` past `exp` gives the already-expired token the test wants, answered 401/40142. An SDK signing its own Ably JWT has to choose, so the fixture should say which. Filed as [#550](https://github.com/ably/specification/issues/550) |
| `batch_presence.md` | The restricted-key setup's comment reads "only has access to \"batch-allowed\" channel" while the setup fixes `allowed_channel = "channel6"`; `batch-allowed` appears nowhere in the file. Filed with [#548](https://github.com/ably/specification/issues/548), whose fix replaces the same lines |
| `batch_presence.md` | BGR2 says a channel with no members "returns a success result with an empty `presence` array", and the unit tier's mocks all send `'presence': []`. The server sends no `presence` key at all, so an implementation has to default the field for the assertion to hold. The derived test asserts the specification's `length == 0`, with the wire shape in a comment. Filed as [#550](https://github.com/ably/specification/issues/550) |

## Failing Tests

The specification's assertion is preserved and gated behind `@deviation`. Removing
the mark is the only change needed once the SDK behaviour lands.

### Unimplemented features

Nothing to fix here, only something to build. Each row is one feature, and the count is
the number of gated Test IDs that fall with it, with the pytest case count beside it
where the two differ.

Five of these rows are gated at both tiers. `batchPresence`, `Auth#revokeTokens`, the
`PushChannel` surface and the `clientId` filter on `RestPresence#get` each carry
`uts/rest/integration` tests as well as unit ones, and connection recovery carries two
`uts/realtime/integration` ones; all are written against the spelling the unit tier
already gates on, so both tiers go green together when the API lands. Those
integration tests do all their real work first — the sandbox app, the channels, the
presence members entered over a realtime connection, the registered device and the
issued token are all real, and each test reaches the missing call before it fails, so the
assertions either side of it are known to hold against real server responses. The
`batch_presence` and `push_channels` files were additionally run against throwaway shims
— a `batch_presence` forwarding to `GET /presence`, and a `PushChannel` posting and
deleting `/push/channelSubscriptions` with `X-Ably-DeviceToken` — and pass in full
against them. The two recovery tests are a different shape: there is no missing call for
them to reach, so each runs end to end against the sandbox through `uts-proxy` and fails
on the `recover` parameter the connection never sends.

| Spec points | Missing | Test IDs |
|---|---|---|
| RSC22, RSC24, BSP2, BPR2, BPF2, BAR2, BGR2, BGF2 | `batchPublish` and `batchPresence`, and all six result types. `grep -rn batch ably/` finds nothing | 44 (47 cases) |
| RSA17, RSA17b–g, BAR2, TRS2, TRF2 | `Auth#revokeTokens`, `TokenRevocationTargetSpecifier`, `BatchResult`. Gated against `auth.revoke_tokens(targets, issued_before=, allow_reauth_margin=)` returning `success_count` / `failure_count` / `results`, with `target` / `issued_before` / `applies_at` / `error` per result. RSA17d is the one case that needs no server at all — a token-authenticated client must refuse locally with 40162/401 — so it can be satisfied before any of the wire work | 21 |
| RSH7, RSH7a–e, RSH6, RSH8 | `PushChannel`: `channel.push`, `client.device`, `LocalDevice`. The push *admin* surface (RSH1) does exist | 12 |
| RTN16, RTN16f–k, RTC1c (TO3i) | Connection recovery, entire. `recover` is in the `Options` signature, stored, and given a property and a setter (`options.py:30,111,193,196`), and read nowhere. No `Connection#createRecoveryKey`, no `recover` connect parameter, no recovery-key decoding. Measured through the proxy: a client built with a valid `recover=` opened a `ws_connect` whose query parameters were `{'accessToken': …, 'v': '5'}` — no `recover` — and was given a fresh `connectionId`. RTN16l is otherwise fully compliant, taking the proxy's `recovery-failed-new-id`, `recovery-failed-new-key` and error 80008 and staying CONNECTED; only the absent parameter fails it | 8 |
| RTL22, RTL22a–d, MFI1, MFI2a–e | `MessageFilter`. `RealtimeChannel.subscribe` (`channel.py:262-273`) accepts only a `str` or a callable, and there is no filter type of any shape to spell. Each test builds its filter through the module's `message_filter()` helper, which is the one place to repoint when the type lands | 5 |
| RTS5, RTS5a, RTS5a1, RTS5a2, DO2a | Derived channels: `DeriveOptions` and `Channels.getDerived`. `grep -r derive ably/` is empty. Each test imports `DeriveOptions` inside its body so the module still loads | 5 |
| RTB1, RTB1a, RTB1b | Retry backoff, jitter and `retryIn`. Retry timers schedule the flat configured timeout (`connectionmanager.py:753`, `channel.py:866-871`); `grep` for jitter/backoff/retry_in returns nothing, and neither `ConnectionStateChange` nor `ChannelStateChange` carries `retryIn` | 4 |
| RTL25, RTL25a, RTL25b | `RealtimeChannel#whenState`. `Connection._when_state` exists (private, awaitable), so this is a gap on the channel rather than a house style; the tests are written against a `channel.when_state(state)` matching the shape the connection already has | 4 |
| RSC2, RSC3, RSC4, TO3b, TO3c, TO3c2 | `log_handler` as a client option, and any use of `log_level` — it is stored on `Options` and read by nothing | 4 |
| RSP3a2, RSP3a3 | `clientId` and `connectionId` filters on `RestPresence#get`. `Presence.get` is `get(self, limit=None)` (`ably/types/presence.py:216`), while `Presence.history` does take its documented params. `presence.get(client_id=...)` raises `TypeError: get() got an unexpected keyword argument 'client_id'`. The absence also forces the RSP5 decoding adaptation below | 4 (5 cases) |
| TP3a, TP3d, TP3g | Presence attributes defaulted from the encapsulating ProtocolMessage. There is no ProtocolMessage type; `ably/realtime/channel.py:751-761` passes the presence array through without context. Matters for synthesized-leave detection and `memberKey` | 3 |
| TB4, RTL7h, RTP6e | `attachOnSubscribe`. `ChannelOptions.__init__` (`channeloptions.py:22-26`) takes only `cipher`, `params` and `modes`, and `subscribe()` on the channel, on presence and on annotations all end unconditionally with `await attach()`. This absence also forces the largest single adaptation in the suite, below | 3 |
| RSL7 | `RestChannel#setOptions`. The realtime channel implements it; the REST `options` setter expects the kwargs dict `Channels.get` collected, so a `ChannelOptions` raises `TypeError` | 2 |
| RTC1a (TO3h), RTL7f | `echoMessages`, in both the forms RTL7f allows. There is no `echo_messages` client option — passing one raises `TypeError` — and no `echo` connect parameter, so every message the server sends is delivered whatever its `connectionId` | 2 |
| RTP12, RTP12a, RTP12c | `RealtimePresence#history`. The realtime *channel* does delegate `history` to the REST implementation; only the presence object is missing it | 2 |
| RTN23c1, RTN23c2 | PING/PONG. `ProtocolMessageAction` stops at `ANNOTATION` (21), so PING (22) and PONG (23) are not modelled and action 22 matches no branch of `on_protocol_message` (`websockettransport.py:37-59`, `:143-199`). The message is counted as activity and discarded | 2 |
| TI4, TI1/TI5 | `href` anywhere in the SDK, and `cause` when deserialising. `AblyException.from_dict` and `raise_for_response` read only `message`, `statusCode` and `code`, so both fields are dropped from server errors | 2 |
| RTN23a | The `heartbeats` connect parameter. The full parameter set is `{key\|accessToken, v, format, resume?, …transport_params}`; `grep -r heartbeats ably/` finds nothing. RTN23a is the branch that binds ably-python, because it cannot observe ping frames | 1 |
| RTL10b | `untilAttach` on `RealtimeChannel#history`. The realtime channel does not override `history`, so the call lands on `Channel.history`, which takes only `direction`, `limit`, `start` and `end`. No `fromSerial` is ever sent, and the attach serial the channel does record is private and read nowhere | 1 |
| TB3 | `ChannelOptions.withCipherKey`. The nearest equivalent, `ably.util.crypto.get_default_params({'key': key})`, is not reachable from `ChannelOptions` | 1 |
| RTL2i, TH6 | `hasBacklog` on `ChannelStateChange`. `Flag.HAS_BACKLOG` is defined (`types/flags.py:7`) but `_on_message` reads only RESUMED and HAS_PRESENCE (`channel.py:715-721`). See the UTS Spec Error above: the features spec makes this optional | 1 |
| RTP6b | Subscribing to an *array* of presence actions. The list reaches `EventEmitter.on` and pyee uses the event as a dict key, so `presence.subscribe([ENTER, LEAVE], listener)` raises `TypeError: unhashable type: 'list'`. A fix has to fan the list out into one registration per action, and `unsubscribe` with it. `realtime/integration/presence_lifecycle_test.py::test_rtp4_bulk_enter_observed` adapts instead of gating: it registers the one listener once for `'enter'` and once for `'present'`, which is what the array form means, and the counted set is identical | 1 |
| RSL1i | REST publish never calls `validate_message_size`. The helper exists and is correct, but only `ably/realtime/channel.py:423` calls it, so an oversized REST publish goes out | 1 |
| TP5 | `size` on `PresenceMessage`. The related `maxMessageSize` gap is adapted rather than gated, below; `features.md` TM6 has no UTS test | 1 |

### Connection

#### A connection-level ERROR bypasses everything that matters on a failure — 5 tests

**Spec points:** RTL3a, RTN7e.

`ConnectionManager.on_error` ends with `enact_state_change(ConnectionState.FAILED, exception)`
(`connectionmanager.py:477`) rather than `notify_state`. Everything a connection failure
has to do lives in `notify_state`: `cancel_transition_timer` (`:664`),
`fail_queued_messages` (`:689`) and `channels._propagate_connection_interruption`
(`:690`). An ERROR `ProtocolMessage` — the commonest way a connection actually fails —
skips all three.

| Consequence | Spec point |
|---|---|
| ATTACHING and ATTACHED channels are not failed. They stay as they were, `error_reason` stays null, no state change is emitted, and a pending `attach()` never returns | RTL3a |
| Pending publishes neither resolve nor reject. The publish hangs for good | RTN7e |
| The transition and suspend timers are left running | RTN14, RTN21 |

Every *other* route to FAILED goes through `notify_state` and behaves correctly — an
incompatible `clientId` (`:422`) and the two authorize failures (`:483`, `:487`) — so this
is specific to the ERROR path. Two batches found the two halves independently; **it is one
issue, not two.**

The same shape holds against the real server. An ERROR 50000/500 injected onto an
established connection through `uts-proxy` took the connection to FAILED with the right
`error_reason` and made no further `ws_connect`, while both attached channels stayed
**ATTACHED with `error_reason is None`** and emitted no state change — the first
observation of the channel half against the sandbox rather than a mock.

The left-running timers are observable too, on any connection the server fails with an
ERROR. A client whose configured `clientId` does not match its token reaches FAILED on the
server's 40102/401 and then emits a **further** state change about ten seconds afterwards:
`DISCONNECTED, 50003/504 "Connection cancelled due to request timeout"`. The CONNECTING
transition timer started at `:579` is still running, and `on_transition_timer_expire`
(`:711-718`) calls `notify_state` when it fires. Measured sequence:

```
connecting → disconnected  80019/401 'Client configured authentication provider request failed'
connecting → failed        40102/401 'invalid clientId for credentials'
           → disconnected  50003/504 'Connection cancelled due to request timeout'
```

No test of the suite asserts that last transition, because each asserts within its own
wait, but anyone writing a test that sits on a FAILED connection for longer than
`realtimeRequestTimeout` will meet it.

**Tests affected:** `test_rtl3a_failed_attached_to_failed` and
`test_rtl3a_failed_attaching_to_failed` fail on `assert channel.state == ChannelState.FAILED`
with `attached` and `attaching`; `test_rtn7e_pending_fail_failed` and
`test_rtn7e_error_represents_reason` fail with `asyncio.TimeoutError` from the bounded await
on the publish. `test_rtl3a_other_states_unaffected` passes, but only because nothing happens
at all; it becomes a real test of RTL3a once this is fixed.
`realtime/integration/proxy/connection_resume_test.py::test_rtn15j_fatal_error_established_conn`
is the fifth, and the one that reaches the defect through a real transport: it fails on the
channel state its two attached channels never leave.

Note that `client.connection.error_reason` *is* populated correctly with the ERROR's
80019/400, so the reason RTN7e asks for is in hand at the point a fix would need it. The
code comment at `connectionmanager.py:411` also justifies omitting a `msgSerial` reset with
"we fail all pending messages on disconnect per RTN7e" — which this defect makes false.

**Status:** open bug.

#### The connection id, key and details are cleared on SUSPENDED — 2 tests

**Spec points:** RTN8d, RTN9d, RTN14h.

`features.md` makes `Connection#id` and `Connection#key` null "when the SDK is in the
`CLOSED`, `CLOSING`, or `FAILED` states". RTN8c/RTN9c, which also cleared them in
SUSPENDED, were replaced as of specification 6.1.0, because the client always attempts a
resume on reconnecting (RTN14h) and lets the server decide whether continuity survives.

`ConnectionManager.enact_state_change` (`connectionmanager.py:181-189`) clears the
connection details, the connection id, the connection key and `msg_serial` on entry to
SUSPENDED as well, under a comment citing RTN16d — which is about *recovery keys* being
invalidated, not about suppressing resume:

```python
if state == ConnectionState.SUSPENDED or state in (ConnectionState.CLOSED, ConnectionState.FAILED):
    self.__connection_details = None
    self.connection_id = None
    self.__connection_key = None
    self.msg_serial = 0
```

Because `__get_transport_params` adds `resume` only `if self.connection_details`, the
second consequence is that a suspended connection stops resuming. Measured over 72 attempts
in 150 s of notional time: 60 carried `resume`, and the 12 that did not were every attempt
made after the suspend timer fired.

**Tests affected:** `test_rtn8d_id_key_retained_in_suspended` (`assert None == 'conn-id-1'`)
and `test_rtn14h_resume_after_ttl` (`KeyError: 'resume'`). One fix — clearing only on CLOSED
and FAILED — closes both.

**Status:** open bug.

#### A DISCONNECTED carrying a 5xx with no fallback hosts stalls the connection — 2 tests

**Spec point:** RTN15h3.

A DISCONNECTED whose error is not a token error must trigger an immediate reconnect with a
resume attempt. Instead nothing happens at all: the connection stays CONNECTED, no further
attempt is made, no state change is emitted, and the client is left believing it is
connected to a socket the server has closed.

`ConnectionManager.on_disconnected` (`connectionmanager.py:437-450`) routes any
`500 <= status_code <= 504` to RTN17f1's fallback-host path. With `self.__fallback_hosts`
empty it logs "No fallback host to try for disconnected protocol message" and falls out of
the `if`/`elif` chain **without calling `notify_state`**. There is no path back to
DISCONNECTED. Any client with no fallback hosts — a custom endpoint, a local cluster, or
the empty list these unit tests use — is stranded. The specification's own fixture uses
`code: 80003, statusCode: 503`.

**Tests affected:** `test_rtn15h3_non_token_error_resume` —
`Timed out waiting for connection state connecting; it was connected` — and
`realtime/integration/proxy/connection_resume_test.py::test_rtn15h3_non_token_error_reconnects`,
which reaches the same place through a real transport. Measured there: an injected
`{action: 6, error: {code: 80003, statusCode: 500}}` followed by a socket close produces
**no state change at all**, CONNECTED being held for the whole ten-second wait with
`error_reason is None`, while the proxy log records `ws_disconnect initiator=proxy`. What
empties `__fallback_hosts` in that test is `endpoint='localhost'` (REC2c2), so the
stranding is reached from an ordinary client configuration rather than from a test fixture.

**Status:** open bug. This is the most serious connection-level defect found.

#### The UPDATE event drops the CONNECTED message's error — 1 test

**Spec point:** RTN24.

The `Connection` must emit UPDATE with a `ConnectionStateChange` whose `reason` is the
`error` member of the CONNECTED `ProtocolMessage`. The error is parsed off the wire, passed
into `on_connected` as `reason`, and then discarded on the already-connected branch
(`connectionmanager.py:425-428`):

```python
state_change = ConnectionStateChange(ConnectionState.CONNECTED, ConnectionState.CONNECTED,
                                     ConnectionEvent.UPDATE)
self._emit(ConnectionEvent.UPDATE, state_change)
```

The `reason=exception` parameter is used only on the `notify_state` branch below it.

**Tests affected:** `test_rtn24_update_event_with_error` — `assert None is not None`. It
also leaves `Connection#errorReason` unset for the RTN15c7 failed-resume case, which RTN25
lists among the errors that must set it.

**Status:** open bug, and a one-line fix: pass `reason=exception` into the
`ConnectionStateChange`.

#### `errorReason` is not cleared by a successful reconnect — 1 test

**Spec points:** RTN14b (`realtime/proxy/RTN14b/token-error-renew-reconnect-0`), and RTN25
(`realtime/unit/RTN25/error-reason-cleared-on-connect-4`).

`Connection._on_state_update` assigns `__error_reason` only when the incoming change carries
a reason, and the only place that clears it is `Connection.connect()` — which an automatic
retry, driven through `ConnectionManager.request_state`, does not go through. The connection
manager tells the same story: `on_token_error` (`connectionmanager.py:458`) assigns
`self.__error_reason`, and the only other writer, `enact_state_change` (`:168-169`), assigns
it only when `reason` is truthy. A successful CONNECTED carries no reason, so nothing
overwrites it and nothing resets it, and the error that caused the drop is still readable
once the connection is back.

RTN14b is what makes this a defect rather than a choice. It requires that after the SDK
meets a 40142 while opening a connection, renews its token and reaches CONNECTED,
`connection.errorReason` is null, and offers no alternative reading. Measured through the
proxy: `state=connected`, states `[CONNECTING, DISCONNECTED, CONNECTING, CONNECTED]`,
`auth_calls=2`, `ws_connects=2`, and `error_reason: code=40142 status=401 'Token expired'`
still in place at the end.

RTN25 is the nuance, and it stands. Its own test names `errorReason IS null` as the primary
assertion while explicitly sanctioning the alternative — "errorReason is kept but clearly
not relevant to current state (Implementation-specific behavior)" — and `features.md` RTN25
says only when `errorReason` is *set*, never when it is cleared. So
`test_rtn25_error_reason_cleared_on_connect` asserts the retained error, the
specification's option B, with option A in a comment, and is an adapted test rather than a
gated one. What settles the question is the second specification requiring the clearing
that the first merely permitted.

**Tests affected:**
`realtime/integration/proxy/connection_open_failures_test.py::test_rtn14b_token_error_renew_reconnect`
— `assert AblyAuthException() is None`.

**Status:** open bug. Clearing `__error_reason` on entry to CONNECTED closes it, and turns
the adapted RTN25 unit test round to the specification's option A, so that test's
adaptation goes with the fix.

#### `ping()` rejects DISCONNECTED instead of deferring, and charges the wait to the caller — 3 tests

**Spec points:** RTN13b, RTN13c, RTN13d.

Two defects in the same method.

- RTN13b errors only for INITIALIZED, SUSPENDED, CLOSING, CLOSED and FAILED, and RTN13d
  defers a ping requested while CONNECTING *or DISCONNECTED* until the connection is
  CONNECTED. `ConnectionManager.ping` (`connectionmanager.py:362`) admits only CONNECTED
  and CONNECTING and raises `AblyException("Cannot send ping request. Calling ping in
  invalid state", 400, 40000)` for DISCONNECTED. Note that
  `deferred-ping-error-suspended-5` would otherwise pass for the wrong reason: its only
  stated assertion is that an error arrives, and one does — just immediately, rather than
  when the connection suspends.
- RTN13c with RTN13d requires a deferred ping's timeout to run "from when the HEARTBEAT is
  actually sent, not when `ping()` is called". `ping()` enters
  `asyncio.wait_for(pending_ping.future, self.__timeout_in_secs)` (`:375`) as soon as it is
  called, so the whole CONNECTING period is charged against it and a ping requested while
  connecting can expire before its HEARTBEAT has gone out.

**Tests affected:** `test_rtn13d_ping_deferred_disconnected` and
`test_rtn13b_deferred_ping_error_suspended` fail with "the ping errored instead of waiting
for the connection"; `test_rtn13c_deferred_ping_timeout` fails with
`assert 0.096… >= (0.4 * 0.9)` — the error arrived 96 ms after CONNECTED where a 400 ms
`realtimeRequestTimeout` should have run from that point.

**Status:** open bug.

### Channels

#### `detach()` never returns when the connection is not CONNECTED — 2 tests

**Spec point:** RTL5l.

When the connection is in any state other than CONNECTED and no earlier channel-state
condition applies, the channel must transition immediately to DETACHED. Instead `detach()`
requests DETACHING, `_check_pending_state()` returns without sending anything because the
connection is not CONNECTED, and `detach()` then awaits the internal state emitter
(`channel.py:212`) for a transition nothing will produce. **The coroutine never returns**
and the channel is left in DETACHING.

**Tests affected:** `test_rtl5l_detach_not_connected_immediate` and
`test_rtl5l_detach_attached_when_disconnected`, each with a one-second `asyncio.wait_for`
so the hang is reported as a failure rather than a stuck run. Both fail with
`asyncio.exceptions.TimeoutError`. In the second, the assertions that set the scene — the
connection settling in DISCONNECTED with the channel still ATTACHED — pass first, so the
failure is unambiguously the detach.

**Status:** open bug. A hang, not a wrong value.

#### `set_options()` never returns for an already-ATTACHED channel — 1 test

**Spec point:** RTL16a.

When `params` or `modes` are supplied to `setOptions` on an attached channel, the channel
must reattach, pass through ATTACHING, return to ATTACHED, and `setOptions` must resolve.
Instead it hangs, and the root cause is a single missing call.

`set_options` (`channel.py:93-102`) calls `_attach_impl()` and then awaits
`self.__internal_state_emitter.once_async()`. `_attach_impl()` sends the ATTACH **without
going through `_request_state(ChannelState.ATTACHING)`**, so the channel is still ATTACHED
when the server's ATTACHED arrives. `_on_message` therefore takes the RTL12 branch
(`:722-726`), which emits `update` on the *public* emitter and returns. The internal state
emitter is written only by `_notify_state` (`:821`), which that branch never reaches, so
the await has nothing to wake it. Both halves of the defect — no ATTACHING transition, and
no internal event — follow from the one missing `_request_state`.

Measured: the second ATTACH is sent, the server's ATTACHED is received, the options *are*
stored, and `asyncio.wait_for(channel.set_options(...), 1.0)` raises `TimeoutError`.

**Tests affected:** `test_rtl16a_triggers_reattach`. It also constrains
`test_rtl4c1_includes_channel_serial` and `test_rtl4j_attach_resume_flag_not_set`, which run
`set_options` as a task and cancel it — recorded under Adapted Tests.

**Status:** open bug. A hang, not a wrong value.

#### A server-initiated DETACHED discards its error, and the pending call then raises `TypeError` — 2 tests

**Spec points:** RTL24, RTL4c, with RTL13a and RTL13b.

An attach rejected by a DETACHED carrying an `ErrorInfo` must fail with that error and leave
`channel.errorReason` holding it. Two faults compound:

1. `_on_message` answers a DETACHED received while ATTACHING with
   `self._notify_state(ChannelState.SUSPENDED)` (`channel.py:735`), passing **no reason**,
   so the message's error is dropped. The same shape applies to RTL13a's
   `_request_state(ATTACHING)` and RTL13b's `_notify_state(SUSPENDED)`.
2. `attach()` then reaches `raise state_change.reason` (`channel.py:150`) with `reason`
   `None`, which Python reports as `TypeError: exceptions must derive from BaseException`
   rather than as an `AblyException`. The same unguarded `raise` is at `:102` in
   `set_options` and `:219` in `detach`.

**Tests affected:** `test_rtl24_error_reason_attach_failure` and
`test_rtl4c_error_cleared_on_attach`, both `TypeError: exceptions must derive from
BaseException` at `channel.py:150`. The clearing half of RTL4c is still covered by
`test_rtl4c_error_cleared_preserved_detach`, which sets the error with an ERROR message
instead and passes. Two adapted tests — `test_rtl13a_attached_reattach_triggered` and
`test_rtl13b_attaching_detached_to_suspended` — assert `reason is None` and the `TypeError`
respectively, and will need revisiting once the reason is carried through.

**Status:** open bug, in two parts. The `raise None` is worth fixing on its own even before
the reason is plumbed through: a missing reason should give an `AblyException`, not a
`TypeError`.

#### An ATTACHED received while DETACHING or DETACHED is ignored — 2 tests

**Spec point:** RTL5k.

An ATTACHED arriving while the channel is DETACHING or DETACHED must be answered with a new
DETACH, the channel remaining in or returning to DETACHING. `_on_message` handles ATTACHED
only for the ATTACHED (RTL12) and ATTACHING cases; every other state falls through to
`log.warn("ATTACHED received while not attaching")` and nothing is sent. While DETACHING
that leaves the detach to time out, so `detach()` raises "Channel detach timed out" and the
channel returns to ATTACHED.

**Tests affected:** `test_rtl5k_attached_while_detaching`
(`AblyException: 90007 408 Channel detach timed out`) and
`test_rtl5k_attached_while_detached` (`Timed out waiting until a second DETACH`).

**Status:** open bug.

#### A detach requested while already DETACHING sends a second DETACH — 1 test

**Spec point:** RTL5i.

A detach requested while the channel is DETACHING must be performed after the pending
request completes, so only one DETACH reaches the server. `detach()` calls
`_request_state(DETACHING)` unconditionally; `_notify_state` returns early for a state the
channel already holds, but only *after* `__clear_state_timer()`, and `_request_state` then
calls `_check_pending_state()` anyway, which restarts the state timer and re-sends DETACH.

**Tests affected:** `test_rtl5i_detach_while_detaching` — `assert 2 == 1`.

**Status:** open bug.

#### The deleted RTL4j ATTACH_RESUME flag is still set on every reattach — 1 test

**Spec point:** RTL4j, deleted as of specification 6.1.0.

The client must not set the ATTACH_RESUME flag (TR3f, bit 5) on any ATTACH, the server
having taken over the resumability decision. `RealtimeChannel._notify_state` sets
`__attach_resume` on every ATTACHED, and `_encode_flags` ORs `Flag.ATTACH_RESUME` into the
flags of every subsequent ATTACH, so the reattach carries `flags: 32`.

**Tests affected:** `test_rtl4j_attach_resume_flag_not_set` —
`assert not (32 & <Flag.ATTACH_RESUME: 32>)`.

**Status:** open bug.

#### Channel serial bookkeeping is wrong in four adjacent places — 4 tests

**Spec points:** RTL15b, RTL15b2, RTL15c.

Four separate lines in `RealtimeChannel._on_message` and `_notify_state`, all about the same
two fields, all fixable in one pass.

| Fault | Site | Spec point | Test |
|---|---|---|---|
| `attachSerial` is taken from *every* ATTACHED, resumed or not, because it is assigned at `:708` before `flags` is read and `resumed` computed at `:716` | `channel.py:708` | RTL15c | `test_rtl15c_attach_serial_not_updated_resumed` (`assert 'resumed-serial' == 'initial-serial'`) |
| A PRESENCE message does not update `channelSerial`, unlike MESSAGE (`:743`) and ANNOTATION (`:772`) | `channel.py:751-755` | RTL15b | `test_rtl15b_channel_serial_from_messages` (`assert 'serial-002' == 'serial-003'`) |
| A message with **no** `channelSerial` **clears** the stored one, because `proto_msg.get('channelSerial')` is `None` and the assignment is unconditional. The ATTACHED (`:708-709`) and ANNOTATION (`:772`) branches have the same shape | `channel.py:743` | RTL15b | `test_rtl15b_serial_not_updated_empty` (`assert None == 'serial-001'`) |
| `channelSerial` is cleared on SUSPENDED as well as DETACHED and FAILED, under a comment naming the superseded RTP5a1, so the ATTACH sent after a suspend carries no serial for the server's RTL4c1 continuity decision | `channel.py:810-812` | RTL15b2 | `test_rtl15b2_serial_retained_suspended` (`assert None == 'serial-001'`) |

RTL15b's requirement is that the serial is set from a protocol message "if and only if that
field is populated"; RTL15b2, as of specification 6.1.0, clears it on DETACHED or FAILED and
explicitly *not* on SUSPENDED.

**Status:** open bug, four of them, one issue.

#### Messages are delivered to a channel that is not ATTACHED — 1 test

**Spec point:** RTL17.

"No messages should be passed to subscribers if the channel is in any state other than
`ATTACHED`." The MESSAGE branch of `_on_message` (`channel.py:738-750`) decodes the array
and emits every message with no reference to `self.state`, and
`Channels._on_channel_message` (`:1028`) only checks that the channel exists. A message
arriving while the channel is ATTACHING, DETACHING, SUSPENDED or FAILED reaches subscribers
exactly as one arriving while ATTACHED does.

**Tests affected:** `test_rtl17_no_delivery_when_not_attached` — `assert 1 == 0`.

**Status:** open bug.

#### `Channels.release` does not detach the channel — 1 test

**Spec point:** RTS4a.

Release "detaches the channel and then releases the channel resource". `Channels.release`
(`channel.py:1012-1026`) is `if name not in self.__all: return` followed by
`del self.__all[name]`, and sends nothing. An attached channel is dropped from the
collection while still attached in the Ably service, and the orphaned object stays in
ATTACHED. It overrides the REST implementation, which is correct for REST, without adding
the detach.

**Tests affected:** `test_rts4a_release_detaches_attached` — `assert 0 == 1` on the
DETACH-message count.

**Status:** open bug.

#### A decode error other than 40018 has no channel-level handling — 2 tests, 3 cases

**Spec point:** PC3.

A `vcdiff`-encoded message received by a client with no vcdiff plugin must put the channel
in FAILED with `errorReason.code == 40019`. The channel stays where it was and nothing is
reported on it. Two causes, both verified:

1. `Message.from_encoded` (`message.py:302-305`) compares `extras.delta.from` against the
   context's `last_message_id` **before** the decode pipeline runs. The specification's
   message is the first the channel receives, so the stored id is null, the comparison
   fails, and a **40018** is raised — the RTL18 recovery error, not the missing-plugin
   error. The channel goes ATTACHING instead of FAILED.
2. Even reaching the missing-decoder branch, `channel.py:744-748` gives channel-level
   handling to 40018 alone; every other decode error takes the `else` arm, which logs
   "Message processing error … Skip messages" and skips the batch silently, with no state
   change and no `error_reason`.

The second cause is what the integration tier reaches, because the server's deltas are
real: the first message on the channel is sent whole, so the decoding context is populated
and the reference check passes, and the **second** message is a genuine vcdiff delta.
`Message.from_encoded_array` then raises `AblyException(…, 40019)` from
`ably/types/mixins.py:81-83` as it should, `RealtimeChannel._on_message`
(`ably/realtime/channel.py:738-749`) takes the generic `else`, and the batch is logged and
dropped. `from_encoded_array` rolls the decoding context back as it goes, so the *next*
delta's `extras.delta.from` no longer matches `context.last_message_id`, that raises 40018,
and the channel goes round the RTL18 recovery instead. Measured: the channel stays ATTACHED
throughout and ends carrying 40018 rather than the 40019 PC3 asks for.

```
ERROR ably.types.mixins: Message cannot be decoded as no VCDiff decoder available
ERROR ably.realtime.channel: Message processing error 40019 40019 VCDiff decoder not available. Skip messages
ERROR ably.realtime.channel: VCDiff decode failure: 40018 400 Delta message decode failure - previous message not available
```

**Tests affected:** `test_pc3_no_plugin_fails` — "Timed out waiting until the channel fails
for want of a vcdiff decoder" — and
`realtime/integration/delta_decoding_test.py::test_pc3_no_plugin_causes_failed`, which is
one Test ID run once per protocol and fails both times with
`Timed out waiting for channel state failed; it was attached`.

**Status:** open bug. The delta-reference check needs to run after the decoder-availability
check, and a decode error needs to fail the channel whatever its code.

#### A message with no id in a ProtocolMessage with no id is given the id `"None:0"` — 1 test

**Spec point:** TM2a.

The `protocolMsgId:index` derivation applies only when the ProtocolMessage carries an `id`;
otherwise the message is delivered with no `id`. `Message.__update_empty_fields`
(`message.py:369-375`) writes `msg['id'] = f"{proto_msg.get('id')}:{msg_index}"` whenever
the message has no id, with no test for the parent having one, so a missing parent id is
interpolated as the literal string `None`.

**Tests affected:** `test_tm2a_no_id_without_protocol_id` — `assert 'None:0' is None`.

**Status:** open, and **already filed as ably-python#706**, which the REST suite raised for
the same line fabricating `"None:0"` for a presence message. This is the same defect reached
through the realtime `messages` array; one fix closes both. The presence-side consequence is
worth knowing: `"None:0"` does not start with the member's `connectionId`, so
`PresenceMessage.is_synthesized()` returns True and `_is_newer` takes the RTP2b1 timestamp
path instead of the RTP2b2 `msgSerial`/`index` path.

### Presence

#### `EventEmitter` keys its wrapper registry on the listener alone — 2 tests

**Spec points:** RTL8b, RTP7b.

`EventEmitter.on` stores the wrapper it built in `self.__wrapped_listeners[listener]`
(`util/eventemitter.py:85`), keyed on the **listener object alone** rather than on
`(event, listener)`. `once` does the same at `:130`. Registering one listener for a second
event overwrites the first entry, so the wrapper registered for the first event is no longer
reachable. `off(first_event, listener)` (`:166`) then hands pyee the *second* event's
wrapper for the first event, and `pyee.base.EventEmitter._remove_listener` does
`self._events[event].pop(f)`, which raises.

Two further consequences of the same line: the first registration is left live, so the
listener keeps receiving that event; and `off` sets `self.__wrapped_listeners[listener] = None`
(`:167`) rather than deleting the entry, so any **later** `off` for that listener silently
does nothing.

Reproducible in six lines with no Ably connection:

```python
e.on('alpha', listener); e.on('beta', listener); e.off('alpha', listener)
# KeyError: <function EventEmitter.on.<locals>.wrapped_listener>
```

This is an `EventEmitter` defect, not a channel or presence one. It affects `connection.on`,
`channel.on`, `channel.subscribe` and `presence.subscribe` equally, and three batches
reported it independently. It also constrains the suite: **no derived test may register one
listener function for two events**, which is why the presence helpers register a separate
function per event name.

**Tests affected:** `test_rtl8b_unsubscribe_named_listener` and
`test_rtp7b_unsubscribe_for_specific_action`, both `KeyError` out of
`pyee/base.py:262`.

**Status:** open bug. The registry needs to be keyed on `(event, listener)`, and to hold a
list per key so that a listener registered twice for one event can be removed once.

#### A LEAVE during a SYNC emits three `leave` events for one member — 1 test

**Spec points:** RTP2h2a, RTP2h2b.

A LEAVE received while a SYNC is in progress is stored as ABSENT and nothing is emitted; at
`endSync` the ABSENT entry is deleted silently, and only members never seen during the sync
earn a synthesized LEAVE. Measured instead:
`[('present', 'alice'), ('leave', 'bob'), ('leave', 'bob'), ('leave', 'bob')]`.

Three separate places:

1. `PresenceMap.remove()` (`presencemap.py:186-196`) returns `True` for the ABSENT store
   exactly as it does for a deletion, and `RealtimePresence.set_presence()`
   (`presence.py:552-554`) broadcasts on the strength of that return value with no test of
   `sync_in_progress`. That is the first LEAVE, during the sync.
2. `PresenceMap.remove()` does not take the member out of `_residual_members`, so a member
   that left during the sync is still a residual at `end_sync` (`presencemap.py:296-305`).
   That is the second.
3. `set_presence()` synthesizes a LEAVE for `residual + absent` (`presence.py:575-587`),
   where the `absent` list exists so the caller can *delete* those members, not announce
   them. That is the third.

**Tests affected:** `test_rtp2h2a_leave_during_sync_absent_cleanup` — `assert leaves(events) == []`
fails on the first of the three. The ABSENT storage itself is correct and is covered ungated
by `test_rtp2h2a_leave_during_sync_stores_absent` and `test_rtp2h2b_absent_deleted_on_endsync`.

**Status:** open bug.

#### The RTP17 map runs the newness check across connectionIds — 1 test

**Spec points:** RTP17h, with RTP2a.

The RTP17 map is keyed only by `clientId`, expressly so that "entries associated with old
`connectionId`s would never be removed" cannot happen. An ENTER for `user-1` on `conn-B`
must therefore replace the entry for `user-1` on `conn-A`. It does not: `_my_members` is a
plain `PresenceMap` with `client_id` as its key function (`presence.py:79-81`), so `put()`
runs the full RTP2b newness comparison against whatever is under that key. Both messages are
non-synthesized, so `_is_newer` takes the RTP2b2 path and compares `conn-B:0:0` against
`conn-A:0:0` by `msgSerial` then `index` — 0 against 0 — and the incoming message is
discarded.

RTP2a scopes the newness check to the *matching* member, meaning the same `connectionId`
**and** `clientId`. An entry under the same key but a different `connectionId` is not a
matching member, and `msgSerial` is ordered only within one connection, so comparing across
connections is meaningless as well as wrong. `PresenceMap.put()` has no knowledge of the key
function it was built with, so it cannot make the distinction — which is the shape of the
fix.

**Tests affected:** `test_rtp17h_keyed_by_clientid` — `assert 'first' == 'second'`.

**Status:** open bug. This is the precise failure RTP17h exists to prevent: a dead
connection's entry pinned under a clientId.

#### A presence action on a DETACHED channel re-attaches instead of failing — 1 test

**Spec points:** RTL11, RTP8g.

A presence action on a DETACHED channel must fail immediately with an `ErrorInfo`, sending
nothing. `_enter_or_update_client` groups DETACHED with INITIALIZED (`presence.py:258-264`),
so it starts an implicit `channel.attach()` and queues the message. Measured: the channel
goes back to ATTACHED and one PRESENCE protocol message leaves the client — and because the
specification's server does not ACK a PRESENCE, the `enter()` then never returns at all.
`_leave_client` does not have the same grouping; it raises for INITIALIZED and FAILED and
queues only for ATTACHING (`presence.py:332-348`), so the SDK is inconsistent with itself.

**Tests affected:** `test_rtl11_queued_presence_fail_detached` — the spec-correct
`pytest.raises(AblyException)` around a 2 s `asyncio.wait_for` fails with
`asyncio.exceptions.TimeoutError`, the enter still pending.

**Status:** open bug.

#### A failed automatic re-entry reports the NACK, not the 91004 wrapper — 1 test

**Spec point:** RTP17e.

When an automatic presence ENTER is NACKed, the channel must emit an UPDATE with `resumed`
true and a `reason` whose `code` is 91004, whose message names the clientId, and whose
`cause` is the NACK error. `_reenter_member` catches the `AblyException` and emits
`ChannelStateChange(previous=state, current=state, resumed=False, reason=e)`
(`presence.py:667-674`), so `resumed` is False and `reason` is the raw NACK error with no
91004 wrapper, no clientId in the message and no `cause`.

**Tests affected:** `test_rtp17e_failed_reentry_emits_update_error` — `assert False is True`
on `resumed`, with `auto-reenter failed: 40160 401 Presence denied` in the log.

**Status:** open bug. `AblyException` already carries a `cause`, so the fix is local to this
one method.

#### RTP17i re-entry never runs on a channel that is already ATTACHED — 1 test

**Spec points:** RTP17i, RTP17g.

RTP17i requires automatic re-entry whenever a channel receives an ATTACHED
ProtocolMessage, except where the channel is already attached **and** the RESUMED flag is
set. `RealtimePresence.on_attached()`, which carries out the RTP17g re-entry, is reached
only from `RealtimeChannel._notify_state()`, and `_on_message`
(`ably/realtime/channel.py:723-728`) sends an ATTACHED received while already ATTACHED
down the RTL12 branch, which emits an `update` event and never calls `_notify_state`. The
re-entry path is therefore unreachable on an attached channel whatever the RESUMED flag
says. Measured through `uts-proxy`: injecting
`{action: 11, flags: 0, error: {code: 91001}}` onto an attached channel holding one entered
member produces no further client→server PRESENCE frame at all — the proxy log shows the
injected frame arriving and the channel staying ATTACHED.

This is invisible to the unit tier, whose RTP17i cases all drive a dropped transport, so
the channel passes through ATTACHING first and `_notify_state` runs.

**Tests affected:**
`realtime/integration/proxy/presence_reentry_test.py::test_rtp17i_reenter_on_non_resumed` —
`Timed out after 10.0s waiting for a re-enter PRESENCE frame`. Its sibling
`test_rtp17i_reenter_after_disconnect` passes, for exactly that reason.

**Status:** open bug. A fix has to reach the re-entry from the RTL12 branch too, gated on
the RESUMED flag being clear.

#### A new sync sequence does not discard the in-flight one — no test

**Spec point:** RTP18a.

`PresenceMap.start_sync()` is guarded by `if not self._sync_in_progress:`
(`presencemap.py:255-262`), so a second call while a sync is running is a complete no-op and
the first sync's residual set carries into the second. A member delivered by the first sync
but absent from the second therefore survives, where RTP18a requires it to be evicted.
Nothing else distinguishes one sync sequence from another either: `set_presence` parses the
`channelSerial` only to decide whether the cursor is empty (`presence.py:538-546`) and never
stores the sequence identifier.

**Tests affected:** none, and that is the point. `realtime/unit/RTP18a/new-sync-discards-previous-1`
delivers both members in the second sync, which empties the residual set under either
behaviour, so `test_rtp18a_new_sync_discards_previous` passes without discriminating. The
test fault is recorded under UTS Spec Errors above; the SDK fault is recorded here so that
correcting the test does not read as a new discovery.

**Status:** open bug, untested.

#### A synthesized LEAVE's timestamp is timezone-aware; every other one is naive — no test

**Spec points:** RTP19, RTP19a, against TP3g.

`_synthesize_leaves` and `set_presence` build the LEAVE with `datetime.now(timezone.utc)`
(`presence.py:586`, `:720`), while every wire-derived presence message gets a **naive**
`datetime` from `_dt_from_ms_epoch`, which is built on `datetime.utcfromtimestamp(0)`
(`types/presence.py:12-19`, `:182-184`). Comparing the two raises
`TypeError: can't compare offset-naive and offset-aware datetimes`, verified directly.

Nothing inside the library compares them, because synthesized leaves are emitted rather than
stored, so this bites only application code — but any subscriber that sorts or compares the
timestamps of the messages it receives will hit it. Related to the deprecation work in
PR #656.

**Tests affected:** none. `test_rtp19_synth_leave_null_id_timestamp` brackets the LEAVE with
two aware `datetime.now(timezone.utc)` readings and passes.

**Status:** open bug, untested.

### Auth

#### A JWT string with a matching clientId is rejected 40102 — 1 test

**Spec point:** RSA7, `realtime/integration/RSA7/matching-clientid-succeeds-0`.

RSA7 requires that a token whose `clientId` equals the client's configured `clientId` is
accepted. `Auth._ensure_valid_auth_credentials` calls
`self._configure_client_id(self.__token_details.client_id)` after every token fetch
(`ably/rest/auth.py:126`). Where an `auth_callback` returns a **JWT string**,
`request_token` wraps it as `TokenDetails(token=<jwt>)` (`auth.py:213`) without parsing the
JWT, so `token_details.client_id` is `None`. `_configure_client_id(None)` then finds
`None != 'test-client-…'` and raises `IncompatibleClientIdException(…, 400, 40102)`
(`auth.py:345`), although the JWT's own `x-ably-clientId` claim is exactly the configured
id. Measured against the sandbox, one auth-callback invocation:

```
initialized→connecting  None
connecting→disconnected AblyAuthException 80019/401 'Client configured authentication provider request failed'
disconnected→connecting None
connecting→connected    None
```

The connection does arrive in the end, because `__token_details` is assigned before the
raise: the retry takes the cached-token branch and skips `_configure_client_id` altogether.
The observable cost is a spurious failed attempt and a full `disconnected_retry_timeout` —
fifteen seconds — on a clientId that matched.

**Tests affected:**
`realtime/integration/auth_test.py::test_rsa7_matching_clientid_succeeds` —
`AssertionError: Timed out waiting for connection state connected; it was disconnected`.
The sibling `test_rsa7_mismatched_clientid_fails` is not gated and pays the same fifteen
seconds before the server's genuine rejection arrives, which is why it waits twenty
seconds rather than the default ten.

**Status:** open bug. A fix either reads the `x-ably-clientId` claim when wrapping a bare
token string, or leaves `_configure_client_id` alone where the fetched token carries no
clientId of its own.

#### An authCallback error is always rewritten as 401/40170, so RSA4d is unreachable — 4 tests

**Spec points:** RSA4d, RSA4d1.

`ably/rest/auth.py:182-187` wraps **every** exception an authCallback raises as
`AblyException("auth_callback raised an exception", 401, 40170, cause=e)`, discarding the
original `statusCode`. `ConnectionManager.on_error_from_authorize` (`connectionmanager.py:479-491`)
then branches on `exception.status_code == 403` to reach FAILED, and that branch can never be
taken for an authCallback: the status is always 401, so a 403 goes to the `__fail_state`
(DISCONNECTED) with an 80019/401 instead. RSA4d requires FAILED with 80019/**403** and
`cause` set to the 403, both during the connect sequence and during an RTN22 reauth.

| Test | Observed |
|---|---|
| `connection_auth_test.py::test_rsa4d_callback_403_causes_failed` | `Timed out waiting for connection state failed; it was disconnected` |
| `connection_auth_test.py::test_rsa4d_callback_403_reauth_causes_failed` | `Timed out waiting for connection state failed; it was connected` |
| `auth_callback_errors_test.py::test_rsa4d_callback_403_connecting_failed` | `Timed out waiting for connection state failed; it was disconnected` |
| `auth_callback_errors_test.py::test_rsa4d_callback_403_reauth_failed` | `Timed out waiting for connection state failed; it was connected` |

**Status:** open bug. Preserving the callback error's `statusCode` — or letting an
`AblyException` from the callback through unwrapped — also restores the `cause` chain
recorded under Adapted Tests.

#### A failed RTN22 reauth leaves no trace on the connection — 1 test

**Spec points:** RSA4c1, RSA4c3.

`WebSocketTransport.on_protocol_message` (`websockettransport.py:170-175`) handles a server
AUTH by awaiting `auth.authorize()` inside a bare `except Exception` that only logs. Nothing
reaches `on_error_from_authorize`, so no 80019 is built and `connection.errorReason` stays
as it was.

**Tests affected:** `test_rsa4c3_callback_error_stays_connected` —
`Timed out waiting for errorReason to be set`.

**Status:** open bug, but see the UTS Spec Error above: specification#466 would make
ably-python's behaviour the correct one, in which case this entry closes as a spec change
rather than a fix.

#### TokenParams passed to an authCallback carry no clientId on a realtime client — 1 test

**Spec points:** RSA12a, RTN2e.

`Auth.__init__` (`ably/rest/auth.py:36-41`) sets `self.__client_id = None` when
`ably._is_realtime`, deferring the clientId to the CONNECTED `connectionDetails`.
`_ensure_valid_auth_credentials` only adds `token_params['client_id']` when
`self.client_id is not None`, so an authCallback on a realtime client is called with the
clientId missing entirely, even though `ClientOptions.clientId` was set. The REST client does
pass it, so the SDK is inconsistent with itself. The snake_case key is idiomatic translation,
not the deviation; the absent member is.

**Tests affected:** `test_rtn2e_callback_params_include_clientid` — `KeyError: 'client_id'`.

**Status:** open bug.

#### RSA4f invalid-format validation is not implemented — 1 test

**Spec points:** RSA4f, RSA4c2.

An object that is not a String, JsonObject, TokenRequest or TokenDetails is an invalid token
format, and must give DISCONNECTED with 80019/401. `Auth.request_token` matches
`TokenDetails`, `dict`, `str` and `None` in turn and then falls through to
`token_path = f"/keys/{token_request.key_name}/requestToken"`. A value of another type — the
specification uses `12345` — raises `AttributeError: 'int' object has no attribute
'key_name'`, which is not an `AblyException`, so `try_host`'s `except AblyException` does not
catch it and `connect_base`'s `except Exception` notifies DISCONNECTED with the raw
`AttributeError` as the reason. `connection.errorReason` is then an `AttributeError` with no
`code`.

**Tests affected:** `test_rsa4f_callback_invalid_type_format` —
`AttributeError: 'AttributeError' object has no attribute 'code'`.

**Status:** open bug, in two parts: no RSA4f type check, and a non-`AblyException` reaching
`Connection#errorReason`.

#### No 40171 log at instantiation with a non-renewable token — 1 test

**Spec point:** RSA4a1.

`Auth.__init__` logs "using token auth with supplied token only" at debug level when a client
is built with a token and no key, authCallback or authUrl. RSA4a1 requires an **info**-level
message carrying error code 40171 and, per TI5, the help URL
`https://help.ably.io/error/40171`. Nothing in `ably/` mentions 40171 outside `request_token`'s
raise and `on_error_from_authorize`'s branch, and `grep -rn href ably/` finds no help URLs
anywhere.

The specification collects the log through a `logHandler` client option, which ably-python
does not have (recorded above under RSC2/RSC3/RSC4/TO3b/TO3c/TO3c2); the test uses pytest's
`caplog` instead, which is idiomatic rendering rather than a second deviation.

**Tests affected:** `test_rsa4a1_non_renewable_token_logs_warning` — `assert False` on the
"an info record mentions 40171" assertion. The RSA4a2 half of the same spec — a token error
on a non-renewable token giving FAILED with 40171 and no retry — is implemented and both its
tests pass.

**Status:** open bug.

#### `Rest#request` never renews an expired token — 1 test

**Spec points:** RSC10, and RSC19 for the path it is observed on.

RSC10 requires a REST request that fails with a token error (40140–40149) to have its token
renewed and the request retried. That happens on every REST operation except the one
`rest/integration/auth.md` drives the test through: `Rest#request`.

`Http.make_request` is wrapped by `reauth_if_expired` (`ably/http/http.py:19-42`), which
renews on two triggers. The pre-emptive one is inert for a token-authenticated client:
`Auth.token_details_has_expired()` returns `False` whenever `time_offset` is unset
(`ably/rest/auth.py:139-140`), and the offset is only ever set by `query_time`, so an
`authCallback` client never has one. That leaves the reactive trigger, which fires on a
raised `AblyException`. `AblyRest.request` asks for `raise_on_error=False`
(`ably/rest/rest.py:145`) so that its `HttpPaginatedResponse` can report an error status to
the caller, per RSC19e and RSC19d3; `make_request` therefore skips
`AblyException.raise_for_response` (`http.py:233-234`) and returns the 401 as a `Response`.
Nothing raises, so the reactive branch never runs — the `authCallback` is invoked once, the
expired token is sent, and the 401 reaches the caller. The two requirements are in direct
conflict in the code as it stands: the flag that suppresses the exception also suppresses
the renewal.

`Rest#request` is the only call site in the library that passes `raise_on_error=False`, and
this is specific to it rather than a general failure of RSC10. Confirmed on one client in
one run: given the same expired JWT, `channel.publish()` renews correctly — the callback is
invoked twice and the client ends up holding the second JWT — while `client.request()`
invokes the callback once and returns 401/40142.

**Tests affected:** `test_rsc10_token_renewal_expired_jwt`, which fails on the
specification's `result.statusCode >= 200 AND < 300` as `assert 401 < 300`; the two
assertions after it, `callback_count == 2` and the check that the client holds the renewed
JWT, fall with it.

**Status:** open bug. A fix has to separate the two meanings `raise_on_error` carries —
renew and retry on a token error whatever the flag says, and only then decide whether the
final response is raised or returned.

#### A basic-auth connection records its clientId as validated and `None`, so `enterClient` can never succeed — no test

**Spec points:** RSA7b4, RTP14, RTP15.

A client built from a full-access key alone and asked to `enter_client("user-1", …)`
raises `AblyException: 40012 400 Unable to enter presence channel with clientId user-1 as
it does not match the current clientId None`.

The server tells such a connection `clientId: "*"` in CONNECTED, and
`Auth._configure_client_id` (`ably/rest/auth.py:335-353`) opens with a branch that exists
to stop a server wildcard overwriting a clientId the caller configured:

```python
if original_client_id != '*' and new_client_id == '*':
    self.__client_id_validated = True
    self.__client_id = original_client_id
    return
```

With no configured clientId, `original_client_id` is `None`, `None != '*'` holds, and the
client id is recorded as **validated and `None`**. `can_assume_client_id`
(`auth.py:356-363`) then takes the validated path and answers `None == '*' or None ==
assumed`, which is `False` for every clientId, so `enter_client` cannot succeed for any of
them. The `original_client_id is None` escape in the unvalidated branch is unreachable once
CONNECTED has arrived. The branch should apply only where a clientId was configured, and
`__client_id` should become `'*'` otherwise, which is what RSA7b4 asks for.

**Tests affected:** none, which is why this is recorded here rather than gated. The three
`batch_presence.md` tests build their realtime client with `client_id='*'` instead, in
`entering_client()`, with the diagnosis in its docstring — the repository's own presence
suite carries the same workaround for the same reason, commented "Use wildcard auth for
enterClient" (`test/ably/realtime/realtimepresence_test.py:394-396`). It is setup rather
than subject: those tests are about `batchPresence`, and nothing they assert depends on how
the members got there. A fix would let the setup halves be written exactly as the
specification writes them. Both `realtime/integration` presence specifications carry the
same workaround for the same reason — `presence_lifecycle_test.py::test_rtp4_bulk_enter_observed`
and `presence/presence_sync_test.py::test_rtp2_sync_multiple_members` each build the client
that enters members on behalf of others with `client_id='*'` — which makes five tests
across two tiers that would otherwise be written as their specifications write them.

This is distinct from the wildcard-clientId contradiction recorded under UTS Spec Errors,
which is about a client that *does* configure `clientId: "*"`.

**Status:** open bug, one line from a fix.

#### Auth behaviour on the REST client

| Spec points | Behaviour |
|---|---|
| RSA4 | With a `key` present, `auth_callback` and `auth_url` are ignored when choosing the auth scheme, so Basic is selected and the callback is never called. `Auth.__init__` considers only `use_token_auth` and `key_secret`. `AblyRest.__init__`'s credential `elif` chain compounds it by discarding `token`/`token_details` when a key is given |
| RSA15a, RSA15c | A mismatch between `ClientOptions.clientId` and a statically supplied `TokenDetails.clientId` is never detected. `Auth.__init__` only falls back to the token's clientId; `_configure_client_id`, which would raise, is reached only after a *fetched* token |
| RSA12a | A token with a **null** clientId is rejected when `ClientOptions.clientId` is set, with 40102 "Client ID cannot be changed to 'None'". RSA15a constrains only non-wildcard token clientIds. Needs a `new_client_id is not None` guard |
| RSA7, RSA16c | A clientId learned from a token is treated as immutable, so `authorize()` to a token with a different clientId raises 40102. RSA15 scopes immutability to a clientId set in `ClientOptions`. `_configure_client_id` uses `self.client_id or self.auth_options.client_id`, conflating the two. Possibly deliberate — worth a maintainer's call |
| RSA10b, RSA10h, RSA10j | `authorize()` overwrites an explicit `tokenParams.clientId`. `ably/rest/auth.py:126-127` assigns `self.client_id` unconditionally. RSA10h makes it the default "if not null" |
| RSA5c, RSA6c | `create_token_request()` ignores `default_token_params`. The merge lives in `Auth.request_token` only, so a direct call yields `ttl=None` and `capability=None`. RSA5, RSA5b, RSA5d, RSA6, RSA6b and RSA6d all pass, so the nullability requirement itself is met |
| RSA16b | `TokenDetails` built from a bare token string fabricates `expires` (now plus an hour), `issued` (0) and `capability`. RSA16b requires only `token` to be populated. The invented expiry can drive spurious renewal |
| RSA16c | No local expiry detection without a server time offset, which an authCallback client never obtains. See the RSA4b1 spec error above; here the specification asserts renewal *does* happen, so there is no green reading |
| RSA16d | A failed renewal leaves the invalidated token in place — `_ensure_valid_auth_credentials` assigns only on success |
| RSA16d | `authorize()` cannot switch a client back to basic auth: `_ensure_valid_auth_credentials` sets `Method.TOKEN` unconditionally, and `AuthOptions.replace` drops `use_token_auth`, which is stored outside the options dict |
| RSA8c1a, RSA12b | `TokenParams` reach the `auth_url` under the SDK's internal snake_case names: `Auth._ensure_valid_auth_credentials` sets `token_params['client_id']` and `token_request_from_auth_url` passes the dict straight to the query string, so an auth server sees `client_id`, not `clientId` |

### Options

| Spec points | Behaviour |
|---|---|
| TO3 | `endpoint` is left unset when none is given, per `TO/endpoint-affects-host-0`. `Options.__init__` resolves the default eagerly to the REC1a routing policy id `main`, so the attribute never reads back as null. Only the default case is gated; the two that name an endpoint are derived and pass |

#### `httpRequestTimeout` is seconds where the specification counts milliseconds — 1 test

**Spec points:** TO3l4, RSC15l2, `rest/proxy/RSC15l2/timeout-triggers-fallback-0`.

`ably/http/http.py:193` builds `timeout = (self.http_open_timeout,
self.http_request_timeout)` and hands it to `httpx`, which reads both as **seconds**.
TO3l4's `httpRequestTimeout` is milliseconds, default 10000, and
`CONNECTION_RETRY_DEFAULTS` holds `10`. So a caller passing the value the published
specification describes gets a deadline a thousand times longer than the one asked for:
`http_request_timeout=3000` is three thousand seconds. The **defaults** come out right
by coincidence — 10 seconds is TO3l4's 10000 ms, and `http_open_timeout`'s 4 is TO3l3's
4000 — which is why only a client that configures the option is affected, and why the
mismatch reads as cosmetic anywhere it is only compared against `options`.

Measured through the proxy. Against a session delaying the first `/time` by 20 seconds,
a client built with the specification's `httpRequestTimeout: 3000` sat out the whole
delay, succeeded on the primary host, and tried no fallback — one `/time` request in the
event log where the test asserts two, which is the `assert 1 >= 2` the gated run shows.
Passing `3` in its place makes the same test pass in 3.1 seconds: the timeout fires, the
retry goes to the fallback host and succeeds. So RSC15l2's fallback path is compliant and
the unit is the whole of the defect.

The same mismatch is recorded twice under *Adapted Tests*, at `TO3l1, TO3l5` and at
`RTC7 (TO3l3, TO3l4)` in *REST behaviours asserted as they are*, where it is what makes
the effective defaults unreadable from `options`. This is that defect seen from outside:
the same line of `http.py`, reached through a public client option rather than through an
attribute, so a caller is affected whether or not they ever read `options`. It is counted
as one root cause, here, because it is the only gated test on it; neither Adapted Tests
row is counted again.

**Tests affected:** `test_rsc15l2_timeout_triggers_fallback`, the one gated test in
`rest/integration/proxy`. The test is written exactly as the specification has it, with
`http_request_timeout=3000`, so removing the gate is all that is needed once the unit is
fixed.

**Status:** open bug. The fix converts at the boundary — `Http` dividing the option by
1000 before it reaches `httpx`, with `CONNECTION_RETRY_DEFAULTS` restated in
milliseconds — and has to move `http_open_timeout` (TO3l3) with it, since both halves of
the tuple are read the same way. That same line carries a second, filed defect:
[#709](https://github.com/ably/ably-python/issues/709) is that the value, in whatever
unit, bounds one socket read rather than the request, so a connection that keeps
producing frames is never timed out and `write` and `pool` are left unbounded. The two
want fixing together, since both change what one attempt may spend of the RSC15 retry
budget.

### Requests

| Spec points | Behaviour |
|---|---|
| RSC19b | Caller-supplied headers override the configured `Authorization`, because `Http.make_request` applies `headers` after `auth_headers`. RSC19b says requests "unconditionally" use the configured mechanism |
| RSH1b1 | Device ids are interpolated raw into push paths (`ably/rest/push.py` lines 82, 106, 118), so an id containing `/` addresses a different resource and `:` is unescaped. `ably/rest/channel.py` does quote channel names, so the SDK is inconsistent with itself |

## Adapted Tests

The test asserts what the SDK does, with the specification's expectation in a
comment above. These run, so they guard against regression.

### The house ruling on missing accessors

Where the SDK's *behaviour* is right but the *public accessor* is missing, the derived
test **adapts** — asserting the equivalent observable, however internal — and the missing
API is recorded here in its own right. It is not gated, because gating would take real
behavioural coverage out of the run indefinitely over a question of spelling. Only wrong
behaviour is gated. The closing section of this file carries the reasoning.

This is not the same as idiomatic naming, which is not a deviation at all and is recorded
nowhere: in each row below there is no public member to rename, so a caller has to reach
through an internal object to get at a value the specification makes public.

| Spec points | Missing accessor | What the test reads instead | Tests |
|---|---|---|---|
| RTN3, RTN8, RTN8a, RTN8b, RTN8d, RTN9, RTN9a, RTN9b, RTN9d | `Connection#id` and `Connection#key`. `Connection` exposes `state`, `error_reason`, `connection_manager` and `connection_details` only | `connection.connection_manager.connection_id` and `connection.connection_details.connection_key`, which is `None` whenever the key would be. Each file defines `connection_id(client)` / `connection_key(client)` at the top | 8 in `connection_id_key_test.py`, plus ~11 across the auth, failures and liveness suites, and eight modules of `realtime/integration` — `auth_test.py`, `auth/token_request_test.py`, `channels/channel_publish_test.py`, `connection_lifecycle_test.py` and four under `proxy/` — each defining the same file-local readers, `connection_resume_test.py` adding a `recovery_key(client)` for `createRecoveryKey()` |
| RTL15 | `RealtimeChannel#properties`, a `ChannelProperties` holding `attachSerial` and `channelSerial`. There is no `properties` attribute and no such type | the name-mangled `__attach_serial` and `__channel_serial` (`channel.py:66-67`), through `attach_serial(channel)` / `channel_serial(channel)` defined in the file | 10 in `channel_properties_test.py`, of which 4 are gated for behaviour above |
| RTN26, RTN26a, RTN26b | `Connection#whenState(state, listener)` — the SDK has `Connection._when_state(state)`, private, returning an awaitable | the awaitable, driven as a task through a `when_state(connection, state)` helper. Both branches are correct: already in the state it resolves with `None`, otherwise it is a `once` registration that resolves for the first entry only | 6 in `when_state_test.py` |
| RTL5, RTL2, RTL2d, RTL2g, RTL12, TH5 | `ChannelStateChange#event`, and a `ChannelEvent` type. `ChannelStateChange` is `(previous, current, resumed, reason)` | the event is the key a listener is registered against, so each test registers on `ChannelState.ATTACHING` / `ATTACHED` / `'update'` and receiving the change at all *is* the `event` assertion | 7 across `channel_state_events_test.py` and `channel_detach_test.py` |
| RTP17, RTP17h | a distinct `LocalPresenceMap` type keyed by `clientId` | `RealtimePresence._my_members`, the same `PresenceMap` class built with `member_key_fn=lambda msg: msg.client_id` (`presence.py:79-81`). The keying requirement is met; the newness check is not, and is gated above | all of `local_presence_map_test.py` |
| RTP2d1, RTP2h1a, and the `Interface Under Test` blocks of all three presence-map specs | `put(message) -> PresenceMessage?` and `remove(message) -> PresenceMessage?` | both return `bool` (`presencemap.py:111`, `:159`); the message to emit is the caller's own, which `set_presence` appends to `broadcast_messages` when the return is true. `IS NOT null` is read as `is True`. `put` stores a *copy* with the action rewritten to PRESENT and leaves the caller's message untouched, so RTP2d1's "emit the original action" falls out for free | all of `presence_map_test.py` |
| RTP19, and the `Interface Under Test` block of `presence_sync.md` | `endSync() -> List<PresenceMessage>`, the synthesized LEAVEs | `end_sync()` returns `(residual, absent)` of the *stored* members; the synthesis lives one level up in `RealtimePresence.set_presence` (`presence.py:575-587`). Tests reading only counts and clientIds concatenate the two lists exactly as `set_presence` does; tests reading the LEAVE itself drive a `RealtimePresence` and assert on what its subscribers receive | 4 in `presence_sync_test.py` |
| TB2, RTS3b, RTS3c, RTS3c1, RTL16 | `channel.options` as a `ChannelOptions` | a dict keyed by wire names, because `RealtimeChannel` passes `ChannelOptions.to_dict()` to the REST `Channel` constructor (`channel.py:84`). Assertions read `channel.options['params']['rewind']`. On `ChannelOptions` itself the cipher attribute is spelled `cipher`, not `cipherParams`. `set_options_without_reattach` replaces the stored mapping wholesale rather than merging, which `test_rts3c_options_updated_existing` pins | 5 |
| RTS2, RTS4a | `channels.exists(name)`, `channels.names`, and an awaitable `release()` | `name in client.channels` (`Channels.__contains__`); the collection iterates over its channels rather than their names; `release` is synchronous. Genuinely idiomatic spelling rather than an absence — recorded only because of the `__getattr__` hazard noted below | 4 |
| RSH1b1, RSH1b2, RSH1b3, RSH1b4, RSH1b5, RSH1c3 | `DevicePushDetails`. The specification builds every device as `DeviceDetails(…, push: DevicePushDetails(recipient: {…}))`; ably-python has no such type | `DeviceDetails.__init__` takes `push` as a plain dict and stores it unchanged (`ably/types/device.py:10-40`), and `DeviceDetails.push` hands that dict back, so the tests read `{'recipient': {…}}` directly. The recipient's `transportType` is still validated against `DevicePushTransportType` in the constructor, which is the only part of `DevicePushDetails` carrying behaviour | the 7 in `push_admin_test.py` that register a device, through its `apns_device()` helper |

**Status:** open bugs of the missing-API kind, not of the wrong-behaviour kind. Adding the
accessors would leave every assertion above unchanged; only the spelling would move.

### The clientId is sent on outgoing PresenceMessages where the spec requires it absent

**Spec points:** RTP8c, RTP9d, RTP10c.

`enter()`, `update()` and `leave()` use the connection's clientId implicitly, so the
`clientId` attribute of the PresenceMessage **must not be present** — the server infers it
from the connection. ably-python sends it: `_enter_or_update_client` and `_leave_client`
resolve `effective_client_id = _get_client_id(self)` when no clientId was passed
(`presence.py:239`, `:315`), and `PresenceMessage.to_encoded` writes `clientId` whenever it
is set (`types/presence.py:160-161`). The implicit case is not distinguished from the
explicit one; both go through the same `client_id` argument.

**Tests affected:** `test_rtp8a_enter_sends_presence_enter`,
`test_rtp9a_update_sends_presence_update`, `test_rtp10a_leave_sends_presence_leave`, each
asserting `clientId == 'my-client'` with the spec expectation in a comment.

**Status:** open bug, and the most substantive protocol-level non-compliance in the suite.
Adapted rather than gated because the behaviour is stable and the rest of each test —
action, channel, payload — is worth running.

### `AblyException`'s status code and code are transposed at six sites

The constructor is `AblyException(message, status_code, code)` (`util/exceptions.py:15`).
Six raises put the Ably error code in the status slot and the HTTP status in the code slot,
so the resulting exception reports each as the other:

| Site | As written | Should be |
|---|---|---|
| `realtime/channel.py:203` | `AblyException("Unable to detach; channel state = failed", 90001, 400)` | `400, 90001` |
| `realtime/channel.py:217` | `AblyException("Detach request superseded by a subsequent attach request", 90000, 409)` | `409, 90000` |
| `realtime/connectionmanager.py:343` | `AblyException("Connection failed", 80000, 500)` | `500, 80000` |
| `types/mixins.py:84` | `AblyException('VCDiff decoder not available', 40019, 40019)` | `400, 40019` |
| `types/mixins.py:88` | `AblyException('VCDiff decode failure', 40018, 40018)` | `400, 40018` |
| `types/mixins.py:111` | `AblyException('VCDiff decode failure', 40018, 40018) from e` | `400, 40018` |

The two neighbours that get it right — `channel.py:860` (`408, 90007`) and
`message.py:304` (`400, 40018`, for the sibling of the `mixins.py` errors) — make this a
repeated slip rather than a misunderstanding of the constructor.

**Tests affected:** `test_rtl5b_detach_failed_errors` and `test_rtl4h_attach_while_detaching`
assert on `status_code` with a comment recording the transposition.
`test_rtn7d_fail_disconnected_no_queue`, `test_rtn7e_pending_fail_closed` and
`test_rtn7e_multiple_pending_fail` assert only what the specification asks — that a code is
present — so they pass; the wrong value is recorded here rather than asserted.

**Status:** open bug. A mechanical fix, and a caller branching on `status_code` today gets a
five-digit number.

### A refused connection and a connect timeout reach no failure path

**Spec points:** RTN14d most directly; the same defect shapes RTN14e, RTN14f, RTN14h,
RTN17e, RTN17f, RTN17h, RTN17i, RTN17j, RTN13b, RTN16g3 and both connection tests in
`backoff_jitter_test.md`.

`WebSocketTransport.ws_connect` (`websockettransport.py:117`) catches only
`(WebSocketException, socket.gaierror)`:

```python
except (WebSocketException, socket.gaierror) as e:
    exception = AblyException(f'Error opening websocket connection: {e}', 400, 40000)
    self._emit('failed', exception)
```

`ConnectionRefusedError` is an `OSError`, not a `WebSocketException`, and
`asyncio.TimeoutError` is neither, so neither reaches `_emit('failed')`. The future
`ConnectionManager.try_host` awaits is completed only by the `connected` or `failed` events,
so it never completes; the `except` clause in `connect_base` that would enter
`connect_with_fallback_hosts` is never reached; and the attempt is ended only by the
transition timer. Measured, with `fallback_hosts=[]` and `realtime_request_timeout=1000`:

| injected | state at settle | state change | reason |
|---|---|---|---|
| `ConnectionRefusedError` (`respond_with_refused`) | still CONNECTING | at t=1000 | 50003 / 504 |
| `asyncio.TimeoutError` (`respond_with_timeout`) | still CONNECTING | at t=1000 | 50003 / 504 |
| `socket.gaierror` (`respond_with_dns_error`) | already DISCONNECTED | at t=0 | 40000 / 400, naming the cause |

Three consequences:

- A refused connection and a connect timeout are indistinguishable from each other *and*
  from a server that accepts the socket and says nothing. All three surface as the
  transition timer expiring with "Connection cancelled due to request timeout".
- **The fallback loop is unreachable for the two commonest transport failures.** Measured
  with the default fallback hosts in place: one connection attempt and no fallback host
  tried for refused and for timeout, against six attempts — primary plus all five
  fallbacks — for a DNS error. RTN17d's fallback behaviour therefore cannot happen in
  practice.
- **Every refused attempt leaks a task and a future.** `try_a_host`'s future
  (`connectionmanager.py:646`) is never settled, so each attempt leaves a
  `connect_base()` task awaiting it for good, printing `Task was destroyed but it is
  pending!` at interpreter shutdown. A long-lived client reconnecting against a refusing
  host leaks one per attempt.

**Tests affected:** `test_rtn14d_retry_recoverable_failure` is the adapted test that pins
it — it asserts that the refusal moves nothing, that DISCONNECTED arrives only when the
transition timer expires, and that the reason is the timer's 50003 rather than the
refusal's, so it fails if the defect is fixed, which is the point. Around a dozen further
tests substitute `respond_with_dns_error()` for the specification's `respond_with_refused()`
or `respond_with_timeout()`, which is RSC15l's host-unreachable condition and does reach
the fallback loop, each noted at the site: `test_rtn17f_fallback_on_error`,
`test_rtn17h_fallback_domains_from_rec2`, `test_rtn17i_prefer_primary_domain`,
`test_rtn17j_connectivity_check_before_fallback`, `test_rtn17e_http_uses_same_fallback`,
`test_rtn13b_ping_error_suspended`, `test_rtn16g3_recovery_key_null_inactive`,
`test_rtc7_disconnected_retry_timeout`. `test_rtn17g_empty_fallback_set_error` and
`test_rtl6c4_fails_conn_suspended` keep `respond_with_refused()` deliberately — the first
because it asserts that *no* fallback follows, the second because swapping it would silence
the ten `Task was destroyed` lines that are the leak showing.

**Status:** open bug. Widening the `except` to `(WebSocketException, OSError,
asyncio.TimeoutError)` — or, better, emitting `failed` from a guard no exception type can
escape — fixes all three consequences.

### The connectivity check bypasses every seam and blocks the event loop

**Spec points:** RTN17j, REC3a, REC3b, REC3.

`ConnectionManager.check_connection` (`connectionmanager.py:193`) calls module-level
`httpx.get` **synchronously**, from within the async fallback loop, once per fallback host
tried. It therefore bypasses the client's own HTTP layer entirely —
`TestOptions(http_transport=...)` cannot see it — and blocks the event loop for the duration
of the request.

**Tests affected:** the three REC3 tests are skipped stubs (below). Every test in
`fallback_hosts_test.py` that leaves the client a fallback set replaces
`ably.realtime.connectionmanager.httpx.get` with an in-process stub through pytest's
`monkeypatch`, and `test_rtn17j_connectivity_check_before_fallback` asserts on the calls
that stub recorded. The whole batch was re-run with `socket.socket.connect`,
`socket.create_connection` and `socket.getaddrinfo` blocked, with identical results, so no
test reaches the network.

**Status:** open bug — two of them: an HTTP call no client-scoped seam can reach, and a
synchronous call inside the event loop.

### The server's `connectionStateTtl` is parsed and never used

**Spec points:** RTN21, and RTN14e, RTN14f, RTN14h, RTL3c, RTL3d, RTP11d, RTL6c4, RTN7e
through their setups.

`ConnectionDetails.from_dict` parses `connectionStateTtl` (`types/connectiondetails.py:19`)
and nothing ever reads it. `ConnectionManager.start_suspend_timer`
(`connectionmanager.py:745`) uses `Defaults.connection_state_ttl` — 120000 — directly, and
no client option overrides it (`types/options.py:64` accepts the keyword and then discards
it). A server that shortens or lengthens the TTL is ignored.

**Tests affected:** every test that has to reach a SUSPENDED connection — nine across the
connection, channel and presence suites — sends the specification's `connectionStateTtl` and
then advances the `FakeClock` to the 120000 default instead, either directly or through
`advance_to_connection_state`. Because the clock is notional this costs nothing in wall
time: the three connection tests take 0.06 s, 0.09 s and 0.08 s. Each says so in a comment.

The integration tier has no clock to advance, so there the same root cause is a gated
failure rather than an adaptation.
`realtime/integration/proxy/connection_resume_test.py::test_rtn14h_resume_after_ttl_expiry`
has `uts-proxy` replace the first CONNECTED with one carrying `connectionStateTtl: 2000`,
drops the socket and refuses the retry. Measured: the replacement did reach
`connection_details.connection_state_ttl == 2000`, and SUSPENDED still did not arrive
within 45 s — the client sat DISCONNECTED and reconnected on the fifteen-second
`disconnected_retry_timeout`. Honouring the TTL will not on its own turn that test green.
`#### The connection id, key and details are cleared on SUSPENDED` means a suspended client
stops sending `resume`, which is precisely what RTN14h asserts it still does, and
`"connectionKey": "__PASSTHROUGH__"` in the fixture is not substituted by uts-proxy v0.3.0
either — see the UTS Spec Error above. The three want closing together.

**Status:** open bug. It is the reason the fake clock exists in this suite at all; see
the fake-time section at the end of this file.

### An 80019 from a failed auth carries no `cause`, and a slow callback is not attributed

**Spec points:** RSA4c, RSA4c1, RSA4c2.

Two adaptations with one underlying theme — an auth failure reaches the right state with the
wrong explanation.

- `ConnectionManager.on_error_from_authorize` builds
  `AblyException('Client configured authentication provider request failed', 401, 80019)`
  with no `cause` argument, so the error the authCallback raised survives only in the log.
  RSA4c1/RSA4c2 require `cause` to be set to the underlying error. Same root cause as the
  RSA4d entry above: `request_token`'s wrapper loses the original error's shape, and
  `on_error_from_authorize` then drops what is left. Adapted, not gated, because the state,
  code and status are all correct and worth guarding — only the `cause` link is missing.
  Tests: `test_rsa4c2_callback_error_causes_disconnected`,
  `test_rsa4c2_callback_error_connecting_disconnected`.
- RSA4c treats an auth attempt that outruns `realtimeRequestTimeout` as an auth error,
  giving DISCONNECTED with 80019/401. ably-python applies no timeout to the callback —
  `await auth_callback(token_params)` is unbounded — and the CONNECTING transition timer
  (`connectionmanager.py:699-724`) ends the attempt instead, with the generic 504/50003 it
  raises for any connect that does not complete in time. Test:
  `test_rsa4c2_callback_timeout_connecting_disconnected`, asserting 50003/504 on a
  `FakeClock`.

**Status:** open bugs, cosmetic in effect — the connection recovers either way, but the
error does not say the auth provider is at fault.

### A token error with no means to renew reports the renewal failure, not the server's error

**Spec point:** RTN15h1.

After a DISCONNECTED carrying 40142/401 that cannot be renewed, the connection is FAILED as
required, but `error_reason` is the error from the *attempted renewal*: 40171/403, "Need a
new token but auth_options does not include a way to request one".
`ConnectionManager.on_token_error` records the server's error as `__error_reason`, then calls
`Auth._ensure_valid_auth_credentials(force=True)`, which raises; `on_error_from_authorize`
then calls `notify_state(FAILED, that exception)` and `enact_state_change` overwrites
`__error_reason` with it.

**The two specifications disagree here.** `connection_open_failures_test.md`'s own RSA4a test
asserts exactly 40171 for the same situation reached through an ERROR rather than a
DISCONNECTED, citing RSA4a2, and ably-python matches that one —
`test_rsa4a_token_error_no_renewal` passes unmodified.
`test_rtn15h1_token_error_no_renew` asserts 40171/403 with the specification's expectation in
a comment.

`revoke_tokens.md` reaches the same code from a third direction, and is recorded here
rather than as an entry of its own. Its "Verification Strategy" watches a realtime client
built as `Realtime(ClientOptions(token: token_details))` — a token and nothing else — and
asserts a DISCONNECTED whose `reason.code` is 40141. The server does exactly what the
specification describes: revoking the token pushes `{'action': 6, 'error': {'message':
'token revoked', 'code': 40141, 'statusCode': 401}}`. ably-python reads that as a token
error (RTN14b, `connectionmanager.py:474`), `on_token_error` (`:456`) tries
`_ensure_valid_auth_credentials(force=True)`, a client holding only a `TokenDetails` has no
way to obtain another, and the 40171 displaces the server's 40141 as above. What differs is
that no DISCONNECTED is emitted at all: the observed result is a single state change,
`connected -> failed`, carrying 40171/403. Where the client *can* renew, `on_token_error`
reaches `notify_state(DISCONNECTED, exception, retry_immediately=True)` (`:464`) and does
report DISCONNECTED with the server's 40141, so the divergence comes from the
specification's token-only setup meeting RSA4a rather than from anything about revocation.
`test_rsa17g_revoke_token_prevents_use` and `test_rsa17c_mixed_success_failure` assert the
FAILED state change and its 40171/403 with the specification's expectation in a comment;
both are also gated for the absent `revoke_tokens`, so those assertions cannot run until
the API lands. The behaviour was established outside the suite, with a throwaway script
that provisioned a sandbox app, issued a token, connected a realtime client with it and
POSTed to `/keys/{keyName}/revokeTokens` directly, reproduced three times.

**Status:** arguably correct as it stands; the specifications should be reconciled first.
RSA4a does not say which state a token error observed mid-connection should be reported in,
and other SDKs may report DISCONNECTED first and fail afterwards.

### A pending `attach()` resolves, rather than failing, when the connection closes

**Spec points:** RTL3b, RTL4d.

RTL3b moves an ATTACHING channel to DETACHED when the connection closes, and RTL4d has the
attach's callback invoked with an `ErrorInfo` "in all other cases" than ATTACHED.
`channel_connection_state.md` spells it `AWAIT attach_future FAILS WITH error`. The RTL3b
transition is correct; the pending `attach()` then returns `None`, because `attach()` ends
with `if state_change.current in (SUSPENDED, FAILED): raise state_change.reason`
(`channel.py:148-150`) and DETACHED is in neither, so the coroutine falls through as a
success.

**Tests affected:** `test_rtl3b_closed_attaching_to_detached` asserts `await attach_future is
None`, and makes every other assertion the specification does. It fails if the SDK starts
raising, so it does guard the behaviour.

**Status:** open bug.

### An attach requested while DETACHING pre-empts the detach

**Spec point:** RTL4h.

The specification has the attach performed *after* the pending detach completes, with the
detach completing normally. `attach()` requests ATTACHING straight away, which resolves the
pending detach's wait with an ATTACHING state change, and `detach()` then raises "Detach
request superseded by a subsequent attach request". The end state and the two ATTACH
messages the specification counts are as expected.

**Tests affected:** `test_rtl4h_attach_while_detaching`, asserting the superseding error.

**Status:** open bug, minor — the observable outcome is the same, but a caller's `detach()`
raises where the specification has it return.

### Adaptations forced by the absent `attachOnSubscribe` — 21 tests

**Spec points:** RTL7a, RTL7b, RTL7f, RTL8a, RTL8b, RTL8c, RTL22a–c, RTAN4a, RTAN4c, RTAN4e,
RTAN4e1, RTAN5a, TB2, RTL16.

`RealtimeChannelOptions(attachOnSubscribe: false)` is setup scaffolding in twenty-one tests:
it keeps `subscribe` from issuing a second attach while the test counts protocol messages.
The option does not exist (gated above), so each test **attaches explicitly first**, which is
what the specification's own test steps do; on an already-ATTACHED channel `subscribe`'s
attach returns immediately without sending anything (RTL4a, `channel.py:125`). Every
assertion the specification makes is kept.

Two cases need more than that. `test_rtan4e1_no_warn_unattached` needs the channel to stay
unattached, which it cannot ask for, so it runs `subscribe` as a task against a server that
never confirms the attach and asserts both that the channel is not attached and that no
warning was logged. `test_tb2_channel_options_attributes` and
`test_rtl16_set_options_updates` drop the `attachOnSubscribe` assertion and keep the three
that the SDK can answer, each pointing at the gated `test_tb4_attach_on_subscribe_default`
which holds the spec-correct one — gating these two as well would take four working
assertions out of the run for one missing option.

**Status:** the adaptation stands until RTL7h is implemented.

### Adaptations forced by the absent `clientId` filter on `RestPresence#get` — 3 Test IDs, 6 cases

**Spec point:** RSP5.

Three of the four RSP5 decoding tests in `rest/integration/presence.md` open with
`presence.get(clientId: "client_<kind>")` and then assert `items.length == 1`. The filter
is incidental to what each test is about — it selects one of the six pre-populated fixture
members so the decoded `data` can be asserted — so rather than gate three decoding tests
behind the missing parameter recorded under Failing Tests above, each fetches the whole
member set and selects in Python through the file's `member_for(page, client_id)` helper.
The `items.length == 1` assertion becomes `member is not None`, with the specification's
expectation in a comment; every assertion about `data` is the specification's, unchanged.

`RSP3a2/get-with-clientid-filter-0` is *about* the filter, so it is gated rather than
adapted.

**Tests affected:** `test_rsp5_decode_string_data`, `test_rsp5_decode_json_data` and
`test_rsp5_decode_encrypted_data`, each run under both protocols.

**Status:** adapted; the gap itself is the open issue recorded above.

### Channel and presence behaviours asserted as they are

| Spec points | Specification | ably-python | Tests |
|---|---|---|---|
| RTL13a, RTL13b | the ATTACHING or SUSPENDED state change triggered by a server-initiated DETACHED carries that message's `error` as its `reason` | `_on_message` discards the error and calls `_request_state(ATTACHING)` / `_notify_state(SUSPENDED)` with no reason, so `reason` is null — and a pending `attach()` then hits `raise None`. Gated in its own right under RTL24/RTL4c above; these two tests assert `reason is None` and the `TypeError` | `test_rtl13a_attached_reattach_triggered`, `test_rtl13b_attaching_detached_to_suspended` |
| RTP16c | answering an ATTACH with a DETACHED puts the channel in DETACHED, and a presence operation from there errors | the channel lands in SUSPENDED (`channel.py:735`) and `attach()` raises `TypeError` on the null reason. The presence operation itself does error, with 90001 | `test_rtp16c_presence_errors_other_states` |
| RTL7g | `channel.subscribe(listener)` registers the listener even when the implicit attach is rejected | the listener *is* registered (`channel.py:279-282`), and then `subscribe` awaits `attach()`, which re-raises the failure (`:150`). So `await channel.subscribe(...)` raises where the specification's fire-and-forget call returns. The RTL7g requirement itself holds | `test_rtl7g_listener_registered_attach_fails`, `test_rtl7g_no_attach_when_attaching` |
| RTL10b | an `AblyException` when `untilAttach` is used on an unattached channel | an `AblyException`, but for the wrong reason: `history` takes no `until_attach`, and `catch_all` wraps the `TypeError` as `50000 500 Unexpected exception` whatever the channel's state. The test also asserts that no HTTP request was made | `test_rtl10b_errors_when_not_attached` |
| RTL19b, RTL19c, RTL20, RTL21, PC3 | a vcdiff-decoded payload equals a string literal | a `bytearray`. `EncodeDataMixin.decode` (`mixins.py:106`) leaves the vcdiff result binary because no further encoding step turns it back into text, which is correct — the specification's own `RTL19b/json-wire-form-base-1`, which does carry `utf-8/vcdiff`, receives a string. Five tests assert `b'second message'` where the specification writes the string | 5 in `channel_delta_decoding_test.py` |
| RTB1b | 1000 jitter samples | 40, because there is no jitter generator to sample and each sample costs a whole reconnection cycle, which must finish before the 120000 ms suspend timer moves the retries onto `suspended_retry_timeout`. The standard error of the mean is 0.009 against a ±0.05 allowance, so the test still separates a uniform generator from a degenerate one | `test_rtb1b_jitter_coefficient_range` |
| RTB1 | the channel test provokes its re-attach with a channel `ERROR`, citing RTL13b | RTL14 takes a channel ERROR straight to FAILED, which is correct (see *Investigated and not defects*), so the channel never suspends and no retry timer starts. The derived test provokes the re-attach with a server-initiated DETACHED instead, which RTL13a does answer with `_request_state(ATTACHING)`; from there the scenario runs as written | `test_rtb1_suspended_channel_retry_delay` |

### Translation notes that are not deviations

Recorded so the next reader does not rediscover them, and so the difference from the
pseudocode is not mistaken for non-compliance.

| Subject | Note |
|---|---|
| DISCONNECTED as a restable state | RTN15a retries a drop from CONNECTED through `loop.call_soon` (`connectionmanager.py:668`) with no time passing, so DISCONNECTED is left within the same turn of the event loop and a listener registered afterwards never sees it. The heartbeat specification says so itself, under "Verifying Transient States"; tests record the whole sequence with `connection.on(...)` and assert `CONTAINS_IN_ORDER`. Where a test needs the connection to *rest* in DISCONNECTED it fails the immediate retry and raises `disconnected_retry_timeout`. Correct RTN15a behaviour |
| `Channels.__getattr__` | `ably/rest/channel.py:408` answers **any** unknown attribute with `self.get(name)`, so reading an attribute that does not exist creates a channel named after it and never raises — `hasattr(channels, 'get_derived')` is `True`, and mutates the collection. Consequences: a typo becomes a phantom channel, and `client.channels.get_derived(...)` fails with `TypeError: 'RealtimeChannel' object is not callable` rather than `AttributeError`. No test loses coverage to it, because no derived test names an attribute the collection does not define; it is recorded because it silently changes what a probing test measures. `Channels.__iter__` is annotated `Iterator[str]` but yields `Channel` objects, which is a second, smaller instance |
| `RealtimeChannel.publish()` | positional-only (`*args`, `channel.py:342`). The keyword form the specifications write raises `ValueError`, although `RestChannel.publish()` accepts it. Every test uses the positional form |
| ACK `res` | every ACK in the specifications is written `res: { "serials": [...] }`, a single object. `WebSocketTransport` (`websockettransport.py:191-193`) reads `res` as a list, one entry per acknowledged ProtocolMessage, which matches the protocol definition. The specification's single object is shorthand for the one-message case |
| `subscribe` before `connect` | all eight `message_field_population.md` tests subscribe in their setup, before `client.connect()`. `subscribe` awaits `attach()`, which raises 90001 unless the connection is CONNECTING, CONNECTED or DISCONNECTED, so the derived tests connect first. Nothing they assert depends on the order |
| `EventEmitter` and bound built-ins | `connection.on(state, states.append)` raises `ValueError: EventEmitter.on(): invalid args`, because `is_callable_or_coroutine` accepts only `iscoroutinefunction`/`isfunction`/`ismethod`. Every listener in the suite is a `def` |
| `Connection#whenState`'s registration window | `_when_state`'s deferred branch is an `async def`, so its `once` registration happens when the coroutine *starts*, not when `_when_state` is called. A caller that needs the registration in place before the state can change must schedule it and yield first, which the derived tests do. A literal callback API would have no such window |
| RTP17b's synthesized-LEAVE filter | RTP17b's own implementation note allows the check to live "either inside the presence map's `remove()` method, or at the calling level". ably-python uses the calling level (`presence.py:557-558`). Compliant |
| RTP19a's route | the specification models an ATTACHED without HAS_PRESENCE as `startSync()` then `endSync()`. `on_attached(has_presence=False)` calls `_synthesize_leaves(...)` then `clear()` (`presence.py:611-618`), which is the requirement itself rather than the model of it |
| `hasNext` as a value | `push_admin.md` RSH1b2 writes `ASSERT result.hasNext == true`. In Python `has_next` is a bound method (`ably/http/paginatedresult.py:63`), truthy whatever the page holds, so the direct translation asserts nothing. `test_rsh1b2_list_devices_pagination` writes `result.has_next() is True`, confirmed to fail when inverted |
| Push `remove` return values | the specification's remove steps assert nothing about a return value ("should not throw"). `PushDeviceRegistrations.remove` / `remove_where` and `PushChannelSubscriptions.remove` / `remove_where` return the `ably.http.http.Response` from the DELETE rather than `None` (`ably/rest/push.py:112-127`, `:176-192`), so the six derived removal tests assert `response.status_code == 204`, which is stronger than the specification asks and matches what `test/ably/rest/restpush_test.py` already asserts |
| `rest/proxy/RSC15l/unreachable-endpoint-error-0` | the specification asserts only that the error carries a non-null `status_code` or `code`, leaving the values open, so the derived test asserts exactly that and is the weakest of the eight proxy tests. What this SDK produces against a refused connection is 500 / 50000 with the message "All connection attempts failed", `catch_all` having wrapped the `httpx.ConnectError`, and that is recorded here rather than asserted, since pinning it would assert more than the specification does |
| `RSL1k4`'s history read | the event log is per session, so any request the client under test makes through it is recorded — including the `history()` the test verifies deduplication with. The log is therefore read **before** the history call, and the POST count assertion made against that snapshot. The history read itself is a `wall_clock_poll_until` rather than one fetch, for the same reason every other integration verification is: a published message does not reach history at once |
| RSP4b1's time bounds | the specification records `time_before = now_millis()` before generating the presence events and `time_after = now_millis()` after, then asserts a `history(start=, end=)` over that window returns them. Read from the runner's clock the window is only as good as the skew against the sandbox, which decides the timestamps actually stored, so a runner running a little fast would exclude the very events the test generated. Both bounds come from `await client.time()` instead — the same instant on the clock that stamps the events. `Presence.history` passes an `int` straight through as milliseconds (`ably/types/presence.py:232-241`), which is what `client.time()` returns, so no conversion is involved |

### REST behaviours asserted as they are

| Spec points | Specification | ably-python | Status |
|---|---|---|---|
| RSL2 | A space in a channel name is `%20` | `+`, from `parse.quote_plus` in `Channel.__init__`. `quote_plus` is form encoding, and a `+` in a URL *path* is a literal plus, so the name reaching the server is altered | Open bug, and a genuine correctness issue |
| RSL8 | `Channel#status` URI-encodes the channel id | `status()` interpolates the name with no escaping at all. `a/b` addresses the wrong resource, `a?b` truncates the name into a query string, `a#b` becomes a fragment | Open bug |
| RSL2, RSL11b, RSL15b | `:` is `%3A` | Left literal, from `safe=':'`. RFC 3986 allows `:` in a path segment and Ably uses it for namespaces, so the server receives the same value | Intentional |
| RSC1b | Error code 40106 | A bare `ValueError` from `AblyRest.__init__` with an informative message, not an `AblyException`, so there is no code. The realtime constructor shares it — `test_rtc12_invalid_arguments_error` records the same behaviour | Open bug |
| RTC12 / RSC1, RSC1a, RSC1c | A string constructor argument is an API key when it contains `:` and a token when it does not | `AblyRest.__init__` treats its first positional argument as a key unconditionally and hands it to `AuthOptions.set_key`, which requires exactly two colon-separated parts, so a token string raises 40101/401 "key of not len 2 parameters". A token is supplied through the separate `token` or `token_details` arguments. The empty-string case is compliant | Intentional / SDK-wide: the constructor takes credentials as distinct named arguments and has no string-sniffing path to restore |
| RSC18 | The constructor rejects basic auth over HTTP | Construction succeeds; 40103 is raised from `make_request` when a request needing Basic Auth is attempted, and no request goes out. RSA1/RSC18 say only "any attempt to use" | Compliant; the UTS is stricter than its source |
| REC1b1, REC1c1 | Code 40000, or a message containing "invalid" or "conflict" | 400/40106 with a specific message. The features spec mandates no code | Cosmetic |
| RSAN1a3 | Code 40003 for a missing `Annotation.type` | 400/40000 | Cosmetic; worth aligning cross-SDK |
| RSH1a | Empty `recipient` or `data` rejected with code 40000, the error reaching the caller from the server | `PushAdmin.publish` validates its arguments itself and raises before touching the HTTP layer (`ably/rest/push.py:49-59`): a non-dict `recipient` or `data` raises `TypeError`, an empty one `ValueError`. So there is no request, no server error and no `code` to read. The "no HTTP request" half is satisfied, and the repository's own sandbox suite already pins the exception types (`test/ably/rest/restpush_test.py::test_admin_publish`). `test_rsh1a_push_publish_invalid_recipient` in the integration tier asserts `pytest.raises(ValueError)` alongside the unit-tier test | Open bug, minor — a stricter precondition rather than wrong behaviour. The specification's test would need a recipient the SDK will send and the server will reject, an unknown `transportType` say, to exercise the server-side path it describes |
| HP6 | `errorCode` is a number | The raw header string, `'40101'` | Open bug, trivial |
| HP8 | `headers` is a map | A list of `(name, value)` pairs, so the lookup the spec describes is impossible without converting, and case-insensitivity is lost | Open bug; changing the return type is breaking |
| RSC19e | An error indicated idiomatically | `httpx.ConnectError` / `ReadTimeout` reach the caller unwrapped, because `AblyRest.request` carries no `@catch_all` unlike `time()` and `stats()`. The messages do name the failure | Borderline; defensible under RSC19e |
| RSC15a | Six hosts tried | Three. `Options.__get_hosts` truncates to `http_max_retry_count`, which TO3l5 sanctions | Intentional |
| TI | `ErrorInfo` equality by attributes | No `__eq__`, so errors compare by identity. Python exceptions conventionally do, and the requirement appears nowhere in `features.md`. Adding `__eq__` without `__hash__` would make `AblyException` unhashable and break any caller that puts one in a set | Intentional |
| TD5, RSA16a | `capability` is stringified JSON | A `Capability` object, a public convenience type used throughout `auth`. Narrowing the return type to `str` would break every caller that indexes or mutates it, so it is reserved for a future major | Intentional; a breaking change to align |
| RSA6b, RSA6d | The capability literal as passed | Canonicalised by `Capability.c14n`, which RSA9f requires | Compliant; rendering only |
| RSA8d | `error.message` contains the callback's text | Wrapped as 40170 with the original in `cause`; `__str__` renders both | Rendering |
| CHM2 | Missing metrics default to 0 | `ChannelMetrics.from_dict` uses a bare `obj.get(name)`, so any omitted metric parses as `None` | Open bug, broader than CHM2g/h |
| CHM2g, CHM2h | `objectPublishers` and `objectSubscribers` on `ChannelMetrics` | Neither is modelled, so both are dropped on parsing. The test asserts their absence, and turns red once they are added | Open bug |
| TO3l8 | `maxMessageSize` is a client option, default 65536 | Rejected by `Options.__init__`. `ably/realtime/channel.py:422` reads it with `getattr(..., 65536)`, so the default holds but cannot be configured, nor overridden by `connectionDetails` (CD2c) | Open bug |
| RTN15, RTN23 | A DISCONNECTED `ErrorInfo` needs no `statusCode` | `ConnectionManager.on_disconnected` evaluates `exception.status_code >= 500` unguarded, so a DISCONNECTED whose error omits `statusCode` raises `TypeError` in a task whose exception is only logged, and the connection silently stays CONNECTED. `DISCONNECTED_MESSAGE` supplies 400 | Open bug |
| TO3l1, TO3l5 | `httpRequestTimeout` and `httpMaxRetryCount` carry their defaults on the options object | Left unset; the effective defaults are applied downstream by `Http` and by `Options.__get_hosts`. The spec's `httpRequestTimeout` is milliseconds and ably-python's `http_request_timeout` is seconds, on the value a caller passes as much as on the default — gated, with the measurement, under *`httpRequestTimeout` is seconds where the specification counts milliseconds* in Failing Tests | Intentional for where the defaults are applied; the unit is an open bug, recorded there |
| RTC7 (TO3l3, TO3l4) | `client.options.httpOpenTimeout == 4000` and `httpRequestTimeout == 10000` | Both `None` on `Options`; `Http.http_open_timeout` / `http_request_timeout` fall back to `CONNECTION_RETRY_DEFAULTS`, which holds 4 and 10 — seconds, where TO3l3 and TO3l4 count milliseconds. The three realtime timeouts the same test checks are defaulted on `Options` and match | Two faults in one row: the defaults are unreadable from `options`, and the unit reaches the wire — `rest/proxy/RSC15l2/timeout-triggers-fallback-0` measures a request outliving its configured timeout by a factor of a thousand. Both open; the unit is gated under *`httpRequestTimeout` is seconds where the specification counts milliseconds* in Failing Tests |
| RTC17 (RSA7b1) | `client.clientId == client.auth.clientId` | `AblyRealtime.client_id` reads `options.client_id` and returns the configured value, while `Auth.__init__` sets `self.__client_id = None` whenever `ably._is_realtime` (`rest/auth.py:34-41`), deferring it to whatever a CONNECTED confirms. The two disagree on a client that has not connected | Open bug. RSA12b only allows the realtime clientId to be unknown while it has not been *configured* |
| RTC1f | a `transportParams` boolean appears as `"true"` / `"false"` | `True` / `False`, because `WebSocketTransport.connect` builds the query string with `urllib.parse.urlencode`, which renders each value through `str()` (`websockettransport.py:89`). Integers are unaffected | Open bug. A caller can pass the strings directly, but a bool is what the spec's Stringifiable type admits |

## Mock Infrastructure Limitations

Tests that cannot be implemented as written, kept as skipped stubs carrying their Test
IDs so the specification's coverage is still accounted for. Fifteen in total. Two of the
entries are caused by the SDK rather than by the mock, but they land here because the
effect is the same: no test can observe the behaviour.

### WebSocket ping frames reach no library hook — 4 tests

**Spec points:** RTN23b (`ping-frame-resets-timer-2`, `any-message-resets-timer-3`,
`multiple-pings-keep-alive-6`), RTN23c (`heartbeats-bounce-query-param-0`).

`mock_websocket.md` offers `send_ping_frame()` for platforms whose websocket client
surfaces ping frame events. `WebSocketTransport` has none: the `websockets` library answers
pings inside the protocol and offers no application-level hook, `on_activity` is called only
from `on_protocol_message`, and no `ping_interval` or `ping_handler` is configured.
`send_ping_frame()` is implemented and records a `PING_FRAME` event, but nothing observable
follows — proved by
`mock_websocket_test.py::test_a_ping_frame_is_recorded_but_reaches_no_library_hook`, which
asserts the transport's `last_activity` is unmoved.

The specification's own platform note says the RTN23b tests do not apply to an SDK in this
position, and ably-python is one, so RTN23a is the branch that binds it — and the six RTN23a
tests are derived and pass, driven by `send_to_client(HEARTBEAT_MESSAGE)`. The two RTN23b
tests that do not depend on ping frames, `idle-timeout-reconnect-1` and
`timeout-triggers-reconnect-4`, plus `reconnect-uses-resume-5` and
`heartbeats-false-query-param-0`, are derived in full and pass.

`heartbeats=bounce` is the fourth stub: the specification scopes it to a client whose own
code may be suspended while the transport stays alive, which it says means browsers.
ably-python has no browser build and no equivalent environment, so there is no
configuration of it under which `bounce` is the value to send. That it sends no
`heartbeats` parameter at all is a separate matter, gated under RTN23a above.

### RTN20 has no network connectivity listener to mock — 4 tests

**Spec points:** RTN20, RTN20a, RTN20b, RTN20c.

`network_change_test.md` requires an injectable `MockNetworkListener` with
`simulate_network_lost()` and `simulate_network_available()`, installed "via the same
mechanism the SDK uses to receive real network events". There is no network connectivity
abstraction anywhere in `ably/`, no OS-event subscription, and no seam through which a mock
could be installed. `ConnectionManager.check_connection` is a one-shot HTTP probe on the
fallback-host path, not an event source.

This is **not** an SDK deviation: RTN20 is conditional on the platform, and
`network_change_test.md`'s own platform table lists Python under "Not typically available —
RTN20 may not apply", adding that "SDKs that do not implement network monitoring should skip
these tests entirely".

### The connectivity check bypasses the injected transport — 3 tests

`ConnectionManager.check_connection` is internal, synchronous, and calls `httpx.get`
directly, so `REC3a`, `REC3b` and `REC3` are skipped. These specs drive a Realtime client
and belong under `realtime/unit` in any case. The realtime fallback tests reach the same
call through `monkeypatch` instead, which is recorded under Adapted Tests; these three
assert on `mock_http` and cannot.

### A token over 128 KiB cannot reach a connection attempt — 1 test

**Spec point:** RSA4f (`callback-oversized-token-format-1`).

The authCallback returns a 131073-character token. ably-python accepts it — there is no
RSA4f size check — and puts it in the websocket URL's `accessToken` parameter, which makes
the URL longer than `httpx.URL` accepts. `PendingConnection.__init__`
(`helpers/mock_websocket.py:233`) parses every connection URL through `httpx.URL`, which
raises `InvalidURL: URL too long` above 64 KiB, and it does so inside `_MockConnect.__aenter__`
**before the attempt is recorded**, so the failure is invisible in `events`, `handler_errors`
is empty, and the client simply stays in CONNECTING.

The SDK deviation behind it is real — no 128 KiB check on a token from an authCallback — but
the mock cannot show it. Letting `RecordedUrl` fall back to a hand-parsed URL when
`httpx.URL` refuses one would make this test derivable.

### `fallbackHostsUseDefault` is not implemented — 3 tests

Optional per TO3k7, and `REC1b1` and `REC2a1` scope their checks to libraries that
support it, so these are skipped as not applicable rather than recorded as
deviations.

## Investigated and not defects

Claims raised during derivation, investigated, and found not to be SDK faults. They are
kept so that nobody reaches the same first conclusion again.

### A channel ERROR going straight to FAILED is correct — **retracted**

One batch reported that "a channel ERROR goes straight to FAILED instead of prompting a
re-attach (`channel.py:775`, RTL13b)". A second batch refuted it and the refutation was
verified. **RTL14 requires FAILED.** RTL13b's re-attach is scoped to a *server-initiated
DETACHED* and enumerates its triggers, which do not include ERROR; RTL4e, which might have
been read the other way, was deleted as redundant to RTL14.

ably-python is right here: `ConnectionManager.on_error` routes a channel-scoped ERROR to the
channel (`connectionmanager.py:469-471`, RTN15i) and `channel.py:775-777` sets FAILED with
the error as both the state change's `reason` and the channel's `error_reason`, leaving
other channels and the connection alone and cancelling the RTL13b retry timer on the way.
All five RTL14 tests in `channel_error_test.py` pass unmodified, with no deviations at all.

The one real consequence is on the RTB1 channel-retry test, whose fixture uses a channel
ERROR to provoke the re-attach it needs. That fixture is wrong, not the SDK; the derived
test provokes it with a server-initiated DETACHED instead, and is recorded under Adapted
Tests.

### RTP17b's filter placement is compliant

RTP17b requires that a synthesized LEAVE not be applied to the RTP17 map, and its own
implementation note allows the check to live "either inside the presence map's `remove()`
method, or at the calling level". ably-python uses the calling level
(`presence.py:557-558`). Within the licence the note gives, this is compliant.

### `PresenceMap` getting RTP19's residual removal right

`put()` removes the member from `_residual_members` **before** the newness check
(`presencemap.py:140-142`), which is what RTP19 needs. The three RTP19 cases the
specification distinguishes all come out right.

### RTL18 delta recovery matches the specification exactly

Verified end to end: the recovery ATTACH carries the `channelSerial` of the last batch that
*decoded* rather than the failing one, `reason.code == 40018`, the failed message is not
delivered, recovery completes to ATTACHED, and `__decode_failure_recovery_in_progress`
correctly suppresses a second recovery. RTL19b's json-wire-form chaining is right too:
`last_payload` is advanced only by the `base64` and `vcdiff` steps, never by `json` or
`utf-8`, matching ably-js.

### RTN15a's immediate retry is correct, and is why DISCONNECTED cannot be awaited

Several specifications write `AWAIT_STATE connection == disconnected` between a drop and the
reconnection. RTN15a requires the retry to be immediate after a drop from CONNECTED, and
ably-python does it with `loop.call_soon` (`connectionmanager.py:668`), so DISCONNECTED is
left within the same turn of the event loop. The awaited state is unreachable because the
SDK is compliant, not because it is not. Recorded under Adapted Tests as a translation note.

### Push admin filter keys have to be camelCase, and the snake_case form filters nothing

**Spec points:** RSH1b2, RSH1b5, RSH1c1, RSH1c4, RSH1c5, RSH7a, RSH7b.

`PushDeviceRegistrations.list` / `remove_where` and `PushChannelSubscriptions.list` /
`list_channels` build their query string with `format_params(params)` — the collected
`**params` dict passed *positionally*, so it bypasses the `snake_to_camel` conversion
`format_params` applies only to its own `**kw` (`ably/rest/push.py:94,127,147,158`,
`ably/http/paginatedresult.py:18-25`). `list(client_id=x)` therefore sends `?client_id=x`,
which the server does not recognise.

Measured against the sandbox with three devices registered, two of them sharing a
clientId: `list(clientId=cid)` returned 2, `list(client_id=cid)` returned 3, and `list()`
returned 3. So the snake_case form does not match *nothing*, it matches *everything* — the
unknown query parameter is dropped and the response is the unfiltered page. That is the
more dangerous of the two failure modes, because a test asserting `items.length >= 1`, or
asserting that a subscription it just created is present, passes with the filter doing
nothing at all. `PushChannelSubscriptions.remove_where` is the one exception — it spreads
its params (`format_params(**params)`), so both spellings work there — which makes the
surface inconsistent with itself.

Not a compliance failure, since the specifications name the filters in camelCase and the
derived tests write them that way. Every filtered list in `push_admin_test.py` and
`push_channels_test.py` carries a control assertion proving the filter narrowed: a decoy
registration the `deviceId` filter must exclude, a count before the `limit` is applied, a
second channel the `channel` filter must exclude, and a surviving `clientId` that
`removeWhere` must leave alone. An inconsistency worth tidying — the four positional calls
could spread their params like the fifth does — rather than a defect.

### Device deletion is asynchronous on the server

**Spec points:** RSH1b5, RSH1c4, RSH1c5.

`removeWhere` answers 204 before the rows are gone, so the specification's immediate
`ASSERT result.items.length == 0` is racy. `test/ably/rest/restpush_test.py` already
carries the same observation — "Deletion is async: wait up to a few seconds before giving
up" — and the derived tests poll with `wall_clock_poll_until(..., timeout=20.0)` rather
than asserting straight away. Server behaviour, not the SDK.

### RSL1m4's clientId mismatch is rejected by the server, not locally

`Channel.__publish_request_body` does carry a local clientId check that raises
`IncompatibleClientIdException` 400/40012 (`ably/rest/channel.py:73-77`), so there was a
question of whether `rest/integration/publish.md`'s RSL1m4 test verifies a local check
rather than the server interop it describes. It does not. The specification builds its
client with `token: token_details.token` — the bare token string — so `auth.client_id` is
`None`, the library cannot tell which clientId the token carries, `can_assume_client_id`
allows the publish, and the message goes to the wire. The sandbox rejects it with
`AblyException 40012 400 "Malformed message; invalid clientId"`, which is the code and
status the specification asserts, raised from the response rather than locally. The test
is genuine server interop under both protocols.

Passing `token_details=token_details` instead would hand the library the clientId and move
the rejection client-side, to the same 400/40012, before any request left. The test notes
this at the site so that nobody "simplifies" it into a local check.

### The presence fixture channel returns all six members, and the cipher has to go in first

`rest/integration/presence.md` allows for `>= 5` members on `persisted:presence_fixtures`
and warns that `client_encoded` may not decode. Against a real provision all six are
returned on both protocols, and with `fixture_cipher_params()` supplied at `channels.get`
time `client_encoded` decodes to `{'example': {'json': 'Object'}}` — the same payload
`client_decoded` carries in the clear. `test_rsp5_decode_encrypted_data` asserts that value
rather than the specification's `IS NOT null`, which would also hold for the raw ciphertext
bytes the same call returns without a cipher.

The cipher has to go in on the **first** `channels.get` for a client: `Presence.__init__`
snapshots `channel.cipher` (`ably/types/presence.py:207-212`) and `Channels.get` caches the
channel, so setting the option afterwards leaves the presence object decrypting with
nothing and silently yielding the ciphertext. Each test builds its own client, so the order
is not shared between them.

`RSP3/full-pagination-3` is sound on the same fixture: presence `get` paginates at
`limit=2`, walks three pages of two and recovers exactly the six fixture clientIds with no
duplicates, on both protocols. The test asserts the full set rather than only the
specification's `>= 5`, since the fixture is fixed.

## Candidate issues

`writing-derived-tests.md` asks for the deviations above to be classified into distinct
issues grouped by root cause, "not one issue per test", each with the spec points, the
spec-versus-actual, and a reproduction command. That is this section. It is a shortlist for
a maintainer, not a work plan: nothing here has been filed unless it says so.

**Ranking.** Tier 1 stops a running application dead. Tier 2 raises the wrong kind of error,
or an error where none should be raised, so a caller cannot handle it. Tier 3 puts wrong
data on the wire or in front of the application, silently. Tier 4 is absent features. Tier 5
is missing accessors over correct behaviour. Within a tier the order is blast radius.

**Already filed, do not re-file:**

| Issue | Covers | Rows below it answers |
|---|---|---|
| [#706](https://github.com/ably/ably-python/issues/706) | the fabricated `"None:0"` message id | 3.3 |
| [#658](https://github.com/ably/ably-python/issues/658) | presence messages sent on reconnection before reattach | adjacent to 3.14, which is the other half of RTP17 automatic re-entry |
| [#656](https://github.com/ably/ably-python/issues/656) | `utcfromtimestamp` deprecation | adjacent to 2.4 |
| [#709](https://github.com/ably/ably-python/issues/709)–[#712](https://github.com/ably/ably-python/issues/712) | REST request timeout, token-request nonce reuse, single-host retry, `dispose()` teardown | adjacent to I.3, which is a second defect on the line #709 is about and is not covered by it; otherwise none, these having been filed from the REST derivation |

Every reproduction below is prefixed by:

```
RUN_DEVIATIONS=1 uv run --frozen --extra crypto --extra dev pytest
```

### Tier 1 — the application stops

**1.1 A DISCONNECTED carrying a 5xx strands a client that has no fallback hosts.**
RTN15h3. The spec requires an immediate reconnect with a resume; the SDK does nothing at
all — no state change, no retry, and the client goes on believing it is connected to a
socket the server has closed. `on_disconnected` (`connectionmanager.py:437-450`) routes
500–504 to the fallback path and, with an empty fallback list, logs and falls out of the
`if`/`elif` chain without calling `notify_state`. Any client with a custom endpoint, a local
cluster, or `fallback_hosts=[]` is affected, and there is no way back. Confirmed against
the sandbox through `uts-proxy`, where the stall is reached from `endpoint='localhost'`
alone: CONNECTED held for the whole wait, `error_reason is None`, no retry.
`test/uts/realtime/unit/connection/connection_failures_test.py -k rtn15h3`
`test/uts/realtime/integration/proxy/connection_resume_test.py -k rtn15h3`

**1.2 A connection-level ERROR skips every failure action.** RTL3a, RTN7e.
`on_error` ends with `enact_state_change(FAILED, …)` (`connectionmanager.py:477`) instead of
`notify_state`, so `cancel_transition_timer` (`:664`), `fail_queued_messages` (`:689`) and
`channels._propagate_connection_interruption` (`:690`) are all skipped. Channels are left
ATTACHED or ATTACHING with a null `error_reason` and no state change; a pending `attach()`
never returns; pending publishes never resolve **or** reject; the transition and suspend
timers keep running. Every other route to FAILED goes through `notify_state` and is correct,
so the fix is one line. Two batches found the two halves independently; it is one issue.
Confirmed end to end against the sandbox: an injected ERROR 50000/500 left both attached
channels ATTACHED with a null `error_reason` and no state change, and the left-running
transition timer surfaces as a spurious `DISCONNECTED 50003/504` about ten seconds after a
connection fails.
`test/uts/realtime/unit/channels/channel_connection_state_test.py -k rtl3a`
`test/uts/realtime/unit/channels/channel_publish_pending_test.py -k rtn7e`
`test/uts/realtime/integration/proxy/connection_resume_test.py -k rtn15j`

**1.3 `detach()` never returns when the connection is not CONNECTED.** RTL5l.
RTL5l requires an immediate transition to DETACHED. `detach()` requests DETACHING,
`_check_pending_state()` sends nothing because the connection is not CONNECTED, and
`detach()` then awaits the internal state emitter (`channel.py:212`) for a transition
nothing will produce. The coroutine never returns and the channel is stuck in DETACHING.
`test/uts/realtime/unit/channels/channel_detach_test.py -k rtl5l`

**1.4 `set_options()` never returns for an already-ATTACHED channel.** RTL16a.
`_attach_impl()` (`channel.py:99`) sends the ATTACH without going through
`_request_state(ATTACHING)`, so the channel is still ATTACHED when the server's ATTACHED
arrives; `_on_message` takes the RTL12 branch (`:722-726`), which emits `update` on the
*public* emitter, while `set_options` awaits the *internal* one, written only by
`_notify_state`. The options are stored; the call never resolves. Adding the
`_request_state` fixes both halves.
`test/uts/realtime/unit/channels/channel_options_test.py -k rtl16a`

**1.5 A presence action on a DETACHED channel re-attaches and then hangs.** RTL11, RTP8g.
Both require an immediate error with nothing sent. `_enter_or_update_client` groups DETACHED
with INITIALIZED (`presence.py:258-264`), starts an implicit attach and queues the message,
so a PRESENCE goes out and — with no ACK — `enter()` never returns. `_leave_client` does not
have the grouping, so the SDK is inconsistent with itself.
`test/uts/realtime/unit/presence/realtime_presence_channel_state_test.py -k rtl11_queued_presence_fail_detached`

### Tier 2 — the wrong error, or an error where there should be none

**2.1 `raise state_change.reason` raises `TypeError` when the reason is `None`.** RTL24,
RTL4c, RTL13b, RTP16c. Three sites — `channel.py:102` (`set_options`), `:150` (`attach`),
`:219` (`detach`) — raise whatever the state change carries, and the state change often
carries nothing, because a server-initiated DETACHED's error is discarded at `:735`,
`_request_state(ATTACHING)` and `_notify_state(SUSPENDED)` being called with no reason. The
caller gets `TypeError: exceptions must derive from BaseException` instead of an
`AblyException`, and `channel.errorReason` stays null. Two fixes, worth doing separately:
guard the `raise`, and carry the DETACHED's error onto the state change.
`test/uts/realtime/unit/channels/channel_attributes_test.py -k "rtl24 or rtl4c_error_cleared_on_attach"`

**2.2 `EventEmitter` keys its wrapper registry on the listener alone.** RTL8b, RTP7b.
`util/eventemitter.py:85` (and `:130`, for `once`) stores the wrapper under the listener
object rather than under `(event, listener)`, so registering one listener for a second event
overwrites the first entry and `off` for the first event hands pyee the wrong wrapper —
`KeyError` out of `pyee/base.py:262`. The first registration is also left live, and `off`
writes `None` rather than deleting (`:167`), so every later `off` for that listener silently
no-ops. It affects `connection.on`, `channel.on`, `channel.subscribe` and
`presence.subscribe` equally, and three batches found it independently. Reproducible in six
lines with no Ably connection:
```python
e.on('alpha', listener); e.on('beta', listener); e.off('alpha', listener)
# KeyError: <function EventEmitter.on.<locals>.wrapped_listener>
```
The registry needs an `(event, listener)` key holding a list per key.
`test/uts/realtime/unit/channels/channel_subscribe_test.py -k rtl8b`
`test/uts/realtime/unit/presence/realtime_presence_subscribe_test.py -k rtp7b`

**2.3 `Channels.__getattr__` answers any unknown attribute by creating a channel.**
`ably/rest/channel.py:408` is `return self.get(name)`, so `hasattr(client.channels, 'x')`
is always `True` **and creates a channel called `x`**. A typo becomes a phantom channel,
`client.channels.get_derived(...)` raises `TypeError: 'RealtimeChannel' object is not
callable` rather than `AttributeError`, and any code that probes the collection mutates it.
No derived test loses coverage to it, because none names an attribute the collection does
not define — that constraint is itself the evidence. `Channels.__iter__` is annotated
`Iterator[str]` and yields `Channel` objects, which is the same carelessness one size down.
No gated test; reproduce with:
```python
len(client.channels)            # 0
hasattr(client.channels, 'foo') # True
len(client.channels)            # 1
```

**2.4 Synthesized LEAVE timestamps are timezone-aware; every other one is naive.** RTP19,
RTP19a, TP3g. `presence.py:586` and `:720` use `datetime.now(timezone.utc)`, while every
wire-derived `PresenceMessage.timestamp` comes from `_dt_from_ms_epoch`, built on
`datetime.utcfromtimestamp(0)` (`types/presence.py:12-19`). Comparing them raises
`TypeError: can't compare offset-naive and offset-aware datetimes`. Nothing inside the
library compares them, so it bites only application code — but any subscriber that sorts the
timestamps of the messages it receives will hit it. Related to #656. No gated test.

**2.5 `Channels._on_channel_message` subscripts before it checks.** `channel.py:1038-1045`
does `channel = self.__all[channel_name]` and only then `if not channel:`, so a message for
an unknown channel raises `KeyError` inside the protocol task — swallowed and logged — and
the "non-existent channel" branch is dead code. No gated test.

**2.6 `ws_connect` catches too little, so two of the three commonest transport failures
vanish.** RTN14d, RTN17d, RTN17e. `websockettransport.py:117` catches only
`(WebSocketException, socket.gaierror)`, so a `ConnectionRefusedError` (an `OSError`) and an
`asyncio.TimeoutError` never reach `_emit('failed')`, the future `try_host` awaits is never
settled, and the attempt is ended only by the transition timer with a generic 50003/504.
Three consequences: refused, timed-out and silently-accepted connections are
indistinguishable; **the fallback loop is unreachable** for refused and timeout (measured:
one attempt and no fallback tried, against six for a DNS error); and each attempt leaks a
`connect_base()` task and its future (`connectionmanager.py:646`), printing `Task was
destroyed but it is pending!` at shutdown. Widening the `except`, or emitting `failed` from a
guard no exception can escape, fixes all three.
`test/uts/realtime/unit/connection/connection_failures_test.py -k rtn14d` (this one is
adapted, so it **passes** today and fails when the defect is fixed — read it as the pin, not
the proof)

**2.7 `check_connection` is a synchronous `httpx.get` inside the event loop.** RTN17j,
REC3a–c. `connectionmanager.py:193` calls module-level `httpx.get` synchronously from the
async fallback loop, once per fallback host, so it blocks the event loop for the duration of
each request and bypasses the client's own HTTP layer entirely — no client-scoped seam can
observe or stub it. Two issues in one line. The derived tests reach it only through
`monkeypatch`; the three REC3 tests are skipped stubs.

**2.8 An authCallback error is always rewritten as 401/40170, so RSA4d is unreachable.**
RSA4d, RSA4d1. `rest/auth.py:182-187` wraps every callback exception as
`AblyException(…, 401, 40170, cause=e)`, discarding the original status, and
`on_error_from_authorize` branches on `status_code == 403` to reach FAILED — a branch an
authCallback can never take. A 403 from an auth provider therefore gives DISCONNECTED with
80019/401 where the spec requires FAILED with 80019/403. The same wrapper is why the 80019
carries no `cause`, and why RSA4f's non-`AblyException` (`AttributeError: 'int' object has
no attribute 'key_name'`) reaches `Connection#errorReason` with no `code` at all. One issue,
three symptoms.
`test/uts/realtime/unit/auth -k "rsa4d or rsa4f_callback_invalid_type_format"`

**2.9 `AblyException`'s status code and code are transposed at six sites.** The constructor
is `(message, status_code, code)`. `channel.py:203` (`90001, 400`), `channel.py:217`
(`90000, 409`), `connectionmanager.py:343` (`80000, 500`), `mixins.py:84` (`40019, 40019`),
`mixins.py:88` and `:111` (`40018, 40018`). `channel.py:860` (`408, 90007`) and
`message.py:304` (`400, 40018`) are right, so it is a repeated slip rather than a
misunderstanding. A caller branching on `status_code` today gets a five-digit number.
Mechanical fix. No gated test — three adapted tests assert the wrong values deliberately
(`channel_detach_test.py -k "rtl5b or rtl4h"`), so they turn red when it is fixed, which is
the signal wanted.

### Tier 3 — silently wrong data

**3.1 The clientId is sent on outgoing PresenceMessages where the spec requires it absent.**
RTP8c, RTP9d, RTP10c. `enter()`, `update()` and `leave()` must leave `clientId` off the
message so the connection's own is implied; `presence.py:239`/`:315` resolve
`effective_client_id` and `types/presence.py:160-161` writes it whenever set. The implicit
case is not distinguished from the explicit one. **The most substantive protocol-level
non-compliance in the suite.** Adapted rather than gated, so the three tests pass today:
`test/uts/realtime/unit/presence/realtime_presence_enter_test.py -k "rtp8a_enter_sends or rtp9a_update_sends or rtp10a_leave_sends"`

**3.2 A LEAVE during a SYNC emits three `leave` events for one member.** RTP2h2a, RTP2h2b.
Measured `[('present','alice'), ('leave','bob'), ('leave','bob'), ('leave','bob')]` where the
spec requires none. Three causes: `remove()` reports the ABSENT store with the same `True`
as a deletion and `set_presence` broadcasts on it without testing `sync_in_progress`;
`remove()` leaves the key in `_residual_members`; and `set_presence` synthesizes a LEAVE for
`residual + absent`, where `absent` exists so the caller can *delete* those members, not
announce them. An application counting members from events gets it wrong.
`test/uts/realtime/unit/presence/presence_sync_test.py -k rtp2h2a_leave_during_sync_absent_cleanup`

**3.3 A message with no id in a ProtocolMessage with no id is given the id `"None:0"`.**
TM2a. **Already filed as #706**, from the REST side; this is the same line
(`message.py:369-375`) reached through the realtime `messages` array, and one fix closes
both. Worth adding to #706 that the presence consequence is worse than a wrong id: `"None:0"`
does not start with the member's `connectionId`, so `is_synthesized()` returns True and the
RTP2b newness check silently takes the timestamp path instead of the msgSerial path.
`test/uts/realtime/unit/channels/message_field_population_test.py -k tm2a_no_id_without_protocol_id`

**3.4 Channel serial bookkeeping is wrong in four adjacent places.** RTL15b, RTL15b2, RTL15c.
`attachSerial` is taken from a *resumed* ATTACHED (`:708`, assigned before `resumed` is
computed at `:716`); a PRESENCE does not update `channelSerial` (`:751-755`), unlike MESSAGE
and ANNOTATION; a message with **no** `channelSerial` **clears** the stored one (`:743`, and
the same shape at `:708-709` and `:772`); and `channelSerial` is cleared on SUSPENDED
(`:810-812`) under a comment naming the superseded RTP5a1, so the ATTACH after a suspend
carries no serial for the server's RTL4c1 continuity decision. Four lines, one pass, one
issue. The last one loses message continuity on every channel suspend.
`test/uts/realtime/unit/channels/channel_properties_test.py -k "rtl15b or rtl15c"`

**3.5 The connection id, key and details are cleared on SUSPENDED, so a suspended connection
stops resuming.** RTN8d, RTN9d, RTN14h. `enact_state_change` (`connectionmanager.py:181-189`)
clears them for SUSPENDED as well as CLOSED and FAILED, citing RTN16d — which is about
recovery keys, not resume. RTN8c/RTN9c were replaced in specification 6.1.0 precisely
because the client should always attempt a resume and let the server decide. Measured over
72 attempts: the 12 that carried no `resume` were every attempt after the suspend timer
fired. Clearing only on CLOSED and FAILED fixes both symptoms.
`test/uts/realtime/unit/connection -k "rtn8d or rtn14h_resume_after_ttl"`

**3.6 The RTP17 map runs the newness check across connectionIds.** RTP17h. `_my_members` is a
plain `PresenceMap` keyed by `client_id`, so `put()` compares `conn-B:0:0` against
`conn-A:0:0` by `msgSerial` and index and discards the newer entry — pinning a dead
connection's member under a clientId, which is the precise failure RTP17h exists to prevent.
`msgSerial` is ordered only within one connection, so the comparison is meaningless as well
as wrong. `PresenceMap.put()` has no knowledge of its key function, so the fix has to reach
the map's construction.
`test/uts/realtime/unit/presence/local_presence_map_test.py -k rtp17h`

**3.7 Messages are delivered to a channel that is not ATTACHED.** RTL17. The MESSAGE branch
of `_on_message` (`channel.py:738-750`) has no state guard, and `_on_channel_message`
(`:1028`) only checks the channel exists, so a message arriving while the channel is
ATTACHING, DETACHING, SUSPENDED or FAILED reaches subscribers exactly as one arriving while
ATTACHED does.
`test/uts/realtime/unit/channels/channel_subscribe_test.py -k rtl17`

**3.8 A duplicate `msgSerial` is issued after a failed resume.** RTN7b, found while deriving
RTN19a2. `msg_serial` is reset to 0 (`connectionmanager.py:411`) when the connectionId
changes, but `_send_protocol_message_on_connected_state` resends each requeued message with
its **original** serial, so after a failed resume two messages go out as 0 and 1 and the next
*new* publish also goes out as 0 — a duplicate serial on one connection, which RTN7b forbids.
The code comment at `:411` justifies omitting the reset with "we fail all pending messages on
disconnect per RTN7e", which issue 1.2 above proves false. No gated test: the UTS test for
this cannot distinguish the behaviours (recorded under UTS Spec Errors), so the finding is
the output.

**3.9 `Channels.release` does not detach the channel.** RTS4a. `channel.py:1012-1026` deletes
the entry and sends nothing, so the channel is dropped from the collection while still
attached in the Ably service — the application goes on being billed for and delivered to a
channel it believes it released.
`test/uts/realtime/unit/channels/channels_collection_test.py -k rts4a_release_detaches_attached`

**3.10 The UPDATE event drops the CONNECTED message's error.** RTN24. `on_connected`
(`connectionmanager.py:425-428`) builds the `ConnectionStateChange` without the `reason` it
was handed, so an application never sees the error a CONNECTED carries — including the
RTN15c7 failed-resume error, which RTN25 lists among those that must set
`Connection#errorReason`. A one-line fix.
`test/uts/realtime/unit/connection/update_events_test.py -k rtn24_update_event_with_error`

**3.11 Detach protocol faults.** RTL5i — a detach requested while already DETACHING sends a
**second** DETACH, because `_request_state` calls `_check_pending_state()` even after
`_notify_state` returns early. RTL5k — an ATTACHED arriving while DETACHING or DETACHED is
ignored instead of answered with a new DETACH, so the detach times out and the channel
returns to ATTACHED. Same method, one issue.
`test/uts/realtime/unit/channels/channel_detach_test.py -k "rtl5i or rtl5k"`

**3.12 The deleted RTL4j ATTACH_RESUME flag is still set on every reattach.** RTL4j, deleted
in specification 6.1.0. `_notify_state` sets `__attach_resume` on every ATTACHED and
`_encode_flags` ORs it in, so every reattach carries `flags: 32` and tells the server
something the server now decides for itself.
`test/uts/realtime/unit/channels/channel_attach_test.py -k rtl4j`

**3.13 A decode error other than 40018 never fails the channel.** PC3. `channel.py:744-748`
gives channel-level handling to 40018 alone; every other decode error is logged and the batch
**silently skipped**, with no state change and no `error_reason`, so a vcdiff message with no
decoder is simply lost. Compounding it, `message.py:302-305` checks the delta's `from` id
*before* the decode pipeline, so the first-message case raises 40018 and never reaches the
missing-decoder branch at all.
`test/uts/realtime/unit/channels/channel_delta_decoding_test.py -k pc3_no_plugin_fails`

**3.14 A failed automatic re-entry reports the NACK, not the 91004 wrapper.** RTP17e.
`_reenter_member` (`presence.py:667-674`) emits the UPDATE with `resumed=False` and the raw
NACK as `reason`, where the spec requires `resumed` true and a 91004 naming the clientId with
the NACK as `cause`. Local to one method.
`test/uts/realtime/unit/presence/realtime_presence_reentry_test.py -k rtp17e`

**3.15 `ping()` rejects DISCONNECTED, and charges the connect wait to the caller's timeout.**
RTN13b, RTN13c, RTN13d. `ConnectionManager.ping` (`:362`) admits only CONNECTED and
CONNECTING where RTN13d requires a ping from DISCONNECTED to be deferred; and `:375` enters
`asyncio.wait_for` as soon as `ping()` is called, so a ping requested while CONNECTING can
expire before its HEARTBEAT has gone out.
`test/uts/realtime/unit/connection/connection_ping_test.py -k "rtn13b_deferred or rtn13c or rtn13d"`

**3.16 A failed RTN22 reauth leaves no trace on the connection.** RSA4c1, RSA4c3.
`websockettransport.py:170-175` awaits `auth.authorize()` inside a bare `except Exception`
that only logs, so nothing reaches `on_error_from_authorize` and `errorReason` stays as it
was. **Hold this one**: specification#466 would make the current behaviour correct, and the
two UTS specs disagree about it today.
`test/uts/realtime/unit/auth/connection_auth_test.py -k rsa4c3_callback_error_stays_connected`

**3.17 TokenParams passed to an authCallback carry no clientId on a realtime client.**
RSA12a, RTN2e. `Auth.__init__` nulls `client_id` for a realtime client (`rest/auth.py:36-41`)
and `_ensure_valid_auth_credentials` only adds it when non-null, so an auth server never
learns the configured clientId. The REST client does pass it. The same nulling is why
`client.client_id` and `client.auth.client_id` disagree before CONNECTED (RTC17).
`test/uts/realtime/unit/auth/connection_auth_test.py -k rtn2e`

**3.18 No 40171 log at instantiation with a non-renewable token.** RSA4a1. Requires an
info-level record carrying 40171 and the TI5 help URL; the SDK logs at debug with no code,
and `grep -rn href ably/` finds no help URLs at all. Small, and the TI5 half is a gap of its
own.
`test/uts/realtime/unit/auth/token_expiry_non_renewable_test.py -k rsa4a1`

### Tier 4 — absent features

Each row is one feature and one issue. None is a bug in existing code.

| Feature | Spec points | Tests | Reproduction (`-k` against `test/uts/realtime/unit/`) |
|---|---|---|---|
| Connection recovery, entire — `createRecoveryKey`, the `recover` connect parameter, recovery-key decoding. `recover` is stored on `Options` and read nowhere. Measured through the proxy: a client given a valid `recover=` sends no `recover` query parameter and is issued a fresh `connectionId` | RTN16, RTN16f–k, RTC1c | 8 | `connection/connection_recovery_test.py`, `client/realtime_client_test.py -k rtc1c`, and `test/uts/realtime/integration/proxy/connection_resume_test.py -k "rtn16d or rtn16l"` |
| `MessageFilter` and filtered subscriptions | RTL22, RTL22a–d, MFI1, MFI2a–e | 5 | `channels/channel_subscribe_test.py -k rtl22` |
| Derived channels — `DeriveOptions`, `Channels.getDerived` | RTS5, RTS5a, RTS5a1, RTS5a2, DO2a | 5 | `channels/channel_options_test.py -k "rts5 or do2a"` |
| Retry backoff, jitter and `retryIn` on both state-change types | RTB1, RTB1a, RTB1b | 4 | `connection/backoff_jitter_test.py` |
| `RealtimeChannel#whenState` (the connection has a private equivalent) | RTL25, RTL25a, RTL25b | 4 | `channels/channel_when_state_test.py` |
| `attachOnSubscribe` on `ChannelOptions`. Also forces the suite's largest adaptation — 21 tests attach explicitly to work around it | TB4, RTL7h, RTP6e | 3 | `channels/channel_subscribe_test.py -k rtl7h`, `channels/channel_options_test.py -k tb4`, `presence/realtime_presence_subscribe_test.py -k rtp6e` |
| `echoMessages`, in both the client-filter and `echo`-parameter forms | RTC1a, RTL7f | 2 | `client/realtime_client_test.py -k rtc1a`, `channels/channel_subscribe_test.py -k rtl7f` |
| `RealtimePresence#history` (the realtime *channel* does delegate `history`) | RTP12, RTP12a, RTP12c | 2 | `presence/realtime_presence_history_test.py` |
| PING/PONG handling — actions 22 and 23 are not modelled | RTN23c1, RTN23c2 | 2 | `connection/heartbeat_test.py -k rtn23c1` |
| The `heartbeats` connect parameter. Binding on ably-python, which cannot observe ping frames | RTN23a | 1 | `connection/heartbeat_test.py -k rtn23a_heartbeats_true` |
| `untilAttach` on `RealtimeChannel#history` | RTL10b | 1 | `channels/channel_history_test.py -k rtl10b_adds_from_serial` |
| `ChannelOptions.withCipherKey` | TB3 | 1 | `channels/channel_options_test.py -k tb3` |
| `hasBacklog` on `ChannelStateChange`. `Flag.HAS_BACKLOG` exists and is never read — but the features spec makes the attribute optional, so this is a "should we" rather than a "must" | RTL2i, TH6 | 1 | `channels/channel_state_events_test.py -k rtl2i_has_backlog_flag_true` |
| Subscribing to an **array** of presence actions — the list reaches pyee as a dict key and raises `TypeError: unhashable type: 'list'` | RTP6b | 1 | `presence/realtime_presence_subscribe_test.py -k rtp6b` |

### Tier 5 — missing accessors over correct behaviour

One issue, or four small ones. In each case the value exists and behaves exactly as the
specification requires; there is simply no public member, so a caller has to reach through
an internal object. None is gated, per the house ruling at the end of this file, so
none of these shows up as a failure — which is why they are easy to lose.

| Missing | Reachable today as | Spec points |
|---|---|---|
| `Connection#id`, `Connection#key` | `connection.connection_manager.connection_id`, `connection.connection_details.connection_key` | RTN3, RTN8, RTN9 |
| `RealtimeChannel#properties` (`ChannelProperties`, with `attachSerial` and `channelSerial`) | the name-mangled `__attach_serial` / `__channel_serial` | RTL15 |
| `ChannelStateChange#event`, and a `ChannelEvent` type | the key the listener was registered against | RTL2, RTL5, RTL12, TH5 |
| A public `Connection#whenState` | the private `Connection._when_state`, which `test/ably/realtime/realtimepresence_test.py` already reaches for in two places | RTN26 |

### From the integration tier

The five tiers above classify the realtime unit derivation; the REST unit derivation's
candidates went upstream as [#709](https://github.com/ably/ably-python/issues/709)–[#712](https://github.com/ably/ably-python/issues/712).
Six further defects came out of the two integration tiers, and none of them is filed. I.1
and I.2 are tier 2 by the ranking above — an error where there should be none — and I.3 is
tier 1 for a client that configures the option it concerns, since the call does not come
back when the caller asked for it to. I.4 and I.6 are tier 2 as well; I.5 is tier 3, a
presence member silently leaving the set with nothing to report it.

The realtime integration tier also put four defects the unit tier had already recorded in
front of the real server, and those extend the entries above rather than opening issues of
their own: the RTN15h3 stall (1.1), the connection-level ERROR (1.2), the unused
`connectionStateTtl`, and connection recovery (tier 4). A fifth, the missing channel-level
handling for a decode error other than 40018, is reached there through a genuine
server-sent delta rather than through the specification's unreachable fixture.

**I.1 `Rest#request` never renews an expired token.** RSC10, RSC19. Every other REST
operation renews and retries on a 40140–40149; `Rest#request` returns the 401 to the
caller. It is the only call site passing `raise_on_error=False` (`ably/rest/rest.py:145`),
so `make_request` skips `raise_for_response`, nothing raises, and the reactive branch of
`reauth_if_expired` (`ably/http/http.py:19-42`) never runs; the pre-emptive branch is
separately inert, because `token_details_has_expired()` returns `False` with no time
offset. The same expired token renews correctly through `publish()`. A fix has to separate
the two meanings `raise_on_error` carries.
`test/uts/rest/integration/auth_test.py -k rsc10`

**I.2 `enterClient` cannot succeed on a basic-auth connection.** RSA7b4, RTP14, RTP15. A
connection built from a key alone is told `clientId: "*"`, and the branch of
`Auth._configure_client_id` (`ably/rest/auth.py:335-353`) that guards a configured clientId
against a server wildcard fires when there is no configured clientId, recording it as
validated and `None`. `can_assume_client_id` then refuses every clientId. One line from a
fix, and `enter_client` is unusable without one. No test gates on it — the three tests that
would hit it pass `client_id='*'` in setup instead, as the repository's own presence suite
does — so it will not show up as a failure.

**I.3 `httpRequestTimeout` is applied as seconds where the specification counts
milliseconds.** TO3l4, TO3l3, RSC15l2. `ably/http/http.py:193` hands
`(http_open_timeout, http_request_timeout)` to `httpx`, which reads seconds, so a client
built with the specification's `httpRequestTimeout: 3000` waits three thousand seconds.
Measured through `uts-proxy` against a session delaying `/time` by 20 seconds: the
request sat out the whole delay, succeeded on the primary host and attempted no
fallback, where `http_request_timeout=3` timed out at 3.1 seconds and the fallback retry
succeeded. The defaults are unaffected, 4 and 10 seconds being TO3l3's and TO3l4's 4000
and 10000 ms, so this reaches only a client that sets the option — but such a client gets
no timeout and no fallback at all. Distinct from
[#709](https://github.com/ably/ably-python/issues/709), which is about the same value
bounding a single socket read rather than the request; a fix wants to settle both.
`test/uts/rest/integration/proxy/rest_fallback_test.py -k rsc15l2`

**I.4 A JWT string whose clientId matches the configured one is rejected 40102.** RSA7.
An `auth_callback` returning an Ably JWT gets wrapped as `TokenDetails(token=<jwt>)`
without the JWT being parsed (`ably/rest/auth.py:213`), so `token_details.client_id` is
`None`; `_configure_client_id(None)` (`:126`, raising at `:345`) then reads that as a
clientId change and raises 40102 although the JWT's `x-ably-clientId` claim is the
configured id exactly. The connection recovers on the retry, which takes the cached-token
branch, so the cost is a spurious failed attempt and a full `disconnected_retry_timeout` —
fifteen seconds — on every such client. Affects anyone whose auth provider returns a JWT
and who also configures `clientId`, which is the ordinary shape of a JWT deployment.
`test/uts/realtime/integration/auth_test.py -k rsa7_matching`

**I.5 RTP17i re-entry never runs on a channel that is already ATTACHED.** RTP17i, RTP17g.
`RealtimePresence.on_attached()` is reached only from `RealtimeChannel._notify_state()`, and
an ATTACHED arriving on an already-attached channel takes the RTL12 branch
(`ably/realtime/channel.py:723-728`), which emits `update` and never calls `_notify_state`.
So a server that re-attaches a channel without the RESUMED flag — the case RTP17i exists
for — gets no re-entry, and the member is gone from the presence set with nothing raised
anywhere. The unit tier cannot see it, because its RTP17i cases all pass through ATTACHING.
Adjacent to [#658](https://github.com/ably/ably-python/issues/658), which is the other half
of RTP17 automatic re-entry.
`test/uts/realtime/integration/proxy/presence_reentry_test.py -k rtp17i_reenter_on_non_resumed`

**I.6 `errorReason` survives a successful reconnect, which RTN14b forbids.** RTN14b, RTN25.
Nothing clears `Connection#errorReason` on entry to CONNECTED: `enact_state_change`
(`connectionmanager.py:168-169`) writes it only when the state change carries a reason, and
a successful CONNECTED carries none. After the SDK meets a 40142 opening a connection,
renews its token and connects, the 40142 is still there. RTN25 permits either reading and
the unit tier adapts to that; RTN14b does not, which is what makes this a defect rather
than a choice.
`test/uts/realtime/integration/proxy/connection_open_failures_test.py -k rtn14b`

## How the specifications are adopted here

Choices about the approach, as against the behaviour recorded above.

### Tests are derived against the async API only

`ably/sync` is generated from `ably/` by `ably/scripts/unasync.py`, a token
rewriter driven by hand-maintained literal-string maps. Those maps name mock
targets individually, so every patch target in a derived test would need an
entry, and a missed entry produces a test that runs against the async class
while appearing to cover the sync one.

The specifications describe client-side behaviour — request formation, response
parsing, state transitions — which is the same code in both variants. Running
the suite twice would establish that the rewriter works, which is a different
question and deserves its own much smaller test.

Derived tests therefore live at `test/uts/`, outside both unasync source globs.

### A mock is an httpx transport, supplied as a client option

`mock_http.md` leaves injection open: "The mechanism for injecting the mock is
implementation-specific and not part of the public API."

The seam is `TestOptions(http_transport=...)`, consumed in `Http.__create_client`.
Serving requests at the transport layer keeps URL construction, header merging,
the host fallback loop and response decoding in the path, which is what the
specifications assert on. It also carries the distinction between a failed
connection and a failed request directly, as httpx raises `ConnectError`,
`ConnectTimeout` and `ReadTimeout` separately.

The alternative, replacing the whole client, would stub out the code under test.

### A websocket mock is a connect callable, supplied as a client option

The seam is `TestOptions(websocket_connect=...)`, read by `WebSocketTransport`
and called in place of `websockets.connect`. It is called as
`connect(url, additional_headers=headers)`, or with `extra_headers=headers` if
that raises `TypeError`, and returns an async context manager yielding an object
supporting `__aiter__`, `send` and `close` — the whole surface the transport
uses.

Replacing the connect call keeps the URL and query parameter construction, the
host fallback loop, frame decoding, the idle timer and the `ConnectionManager`
state machine in the path. Injecting a replacement transport, the alternative,
would stub out all of it, which is what the specifications assert on.

A connect callable that raises reaches the library's failure handling exactly
where a real one does, so a refused connection, a DNS error and a timeout are
simulated by the exception the callable raises.

### Fake time is a timer factory, and a last resort

Every delayed callback in the realtime library is a `ably.util.helper.Timer`,
constructed at six sites across the transport, the channel and the connection
manager. `TestOptions(timer=...)` replaces it at all six, selected once per
consumer by `select_timer(options)`. `test/uts/helpers/clock.py` is the fake:
`await clock.advance(ms)` fires what has fallen due, in due order, and lets the
event loop settle so the effects have landed when it returns. It is the
`enable_fake_timers()` / `ADVANCE_TIME(ms)` pair of `mock_websocket.md`.

The option is client-scoped for the same reason the HTTP mock is: a
module-level factory would outlive the test that set it and be shared by every
client the suite builds.

A derived test reaches for it only where nothing else reaches the behaviour.
`realtime_request_timeout`, `disconnected_retry_timeout`,
`suspended_retry_timeout` and `channel_retry_timeout` are client options, and
`maxIdleInterval` arrives in the CONNECTED message's `connectionDetails` and is
honoured, so a real short value drives those and the test stays free of the
interaction between faked time and the real `await`s around it. What has no
such handle is `connection_state_ttl`: it is not a constructor parameter, and
the suspend timer reads `Defaults.connection_state_ttl` directly, which costs
120 real seconds. That is what the fake clock is for.

### Injected frames are encoded for the protocol the client asked for

`send_to_client(CONNECTED_MESSAGE)` leaves the encoding open, and
`use_binary_protocol` defaults to `True`, so a mock that always fed JSON would
make `decode_raw_websocket_frame` raise. `ws_read_loop` catches that with a
broad `except Exception` and logs it, so the test would simply hang to its
timeout with nothing to go on.

A message given as a dict is therefore msgpack-packed or JSON-encoded to match
the `format` query parameter of the connection it is going to, exactly as the
HTTP mock encodes a native response body to match the request's `Accept`
header. A message given as `bytes` or `str` is passed through untouched, so a
specification that is about the wire format can still pin it.

A message is deep-copied before it is encoded, so the shared templates survive
being sent. The templates are still plain dictionaries, and
`connected_message(...)` builds a variant rather than mutating one.

### `realtime_client` defaults `auto_connect` off

`AblyRealtime` connects from its constructor when `auto_connect` is true, which
is the option's own default. Derived tests get the opposite default, for three
reasons.

The await-based mock API needs a waiter registered before the event it is
waiting for. A client that connects during construction has already made its
first attempt by the time the test's next statement runs, so
`await_connection_attempt()` could only ever catch a retry.

A realtime client built for a REST-over-realtime specification is given no
websocket mock, because the specification is about HTTP. With `auto_connect`
true that client opens a real websocket to the internet.

And the specifications themselves overwhelmingly pass `autoConnect: false` and
call `connect()`. The ones that are about the default — the three in
`connection/auto_connect_test.md` — name `auto_connect=True` explicitly, which
is what a test of a default should do anyway.

### `realtime_client` defaults the fallback hosts empty

`ConnectionManager.check_connection` calls `httpx.get` directly, module level
and synchronously, on every host of the fallback loop. No seam reaches it: it
is not the client's HTTP layer, so `TestOptions(http_transport=...)` does not
serve it either.

Measured, a client with the default fallback hosts and a connect that fails
makes six connection attempts and one real request to
`internet-up.ably-realtime.com` per host, blocking the event loop for each.
With `socket.create_connection` blocked it makes one attempt, because the
connectivity check raises and `connect_with_fallback_hosts` swallows it per
host. Either way a unit test has reached the network.

`fallback_hosts=[]` keeps the loop out of the path entirely. A specification
that is about the fallback loop passes its own `fallback_hosts`, and has to
accept that the connectivity check goes to the real internet; the three REC3
tests are skipped for that reason already.

### A DISCONNECTED template carries a status code the specification omits

`mock_websocket.md` writes `DISCONNECTED_MESSAGE` with an `ErrorInfo` of
`code` and `message` only. `ConnectionManager.on_disconnected` reads
`exception.status_code` and compares it against 500 without guarding, so a
DISCONNECTED with no `statusCode` raises `TypeError` inside a task whose
exception is only logged — the same silent hang as a frame that will not
decode.

The template supplies `statusCode: 400`, the status Ably sends with 80003. The
unguarded comparison is recorded above; a
specification that is about a DISCONNECTED without a status code sends its own
message rather than the template.

### A mock serves one client rather than being installed globally

The specifications write `install_mock(mock_http)` and warn against passing a
mock to a client, because the SDKs they were first written against hold HTTP
behind a platform singleton. This client builds its HTTP client during
construction and holds it, so a mock is passed as a client option instead.

Derived tests construct the mock first, and `uninstall_mock()` has no
counterpart — `test/uts/conftest.py` closes clients after each test, so a test
whose assertions fail still releases its client.

### A native response body is encoded to match the request

`respond_with(200, {...})` leaves the encoding open. Encoding it as JSON
unconditionally, as the reference implementation does, breaks against this SDK,
where `use_binary_protocol` defaults to `True` and `Response.to_native()`
dispatches on the response content type.

A body given as a dict or list is therefore encoded to match the request's
`Accept` header, and carries the matching `Content-Type`. A body given as
`bytes` or `str` is passed through untouched, so a specification can still pin
the encoding itself.

This keeps the binary protocol on its default setting for the specifications
that exercise it, rather than turning it off across the suite.

### The superseded `queue_*` mock API is implemented

`writing-test-specs.md` lists `mock_http.queue_response()` under "Common
Mistakes to Avoid" in favour of the `onRequest` handler. The specifications have
not followed: `fallback.md`, `request.md` and `rest_client.md` use it heavily.

Implementing it costs little and keeps those three translations literal.
Rewriting each call into a handler and a counter would be the kind of invention
that derived tests exist to avoid.

Stubs are matched by URL, then by host, then consumed first-in-first-out, and a
URL is normalised before matching so that a default port may be given or
omitted.

### Test names carry the spec point, and the Test ID sits above them

A specification's Test ID, `rest/unit/RSC16/returns-server-time-0`, becomes
`test_rsc16_time_returns_server_time`, with the full ID in a `# UTS:` comment
immediately above the function. The comment is the identifier that survives
renaming; the function name makes failures readable without it.

### Timing is driven by client options rather than a fake clock

`enable_fake_timers()` and `ADVANCE_TIME(ms)` have no counterpart here, as there
is no clock seam — `ably/http/http.py` calls `time.time()` directly. Where a
specification advances time, the derived test shortens the interval through a
client option instead, which is what the specifications themselves do for
`fallback_retry_timeout`. The realtime specifications do get a timer seam,
for the one interval no option reaches; see the fake time section above.

### A TokenDetails payload is recognised by its `token`, not only by `issued`

RSA8c admits "a `TokenRequest` or `TokenDetails` object" from an `authUrl` without
saying how to tell them apart. ably-python discriminated on `issued`, as ably-js
still does, so the `{"token": ..., "expires": ...}` that seven specifications
return was read as a `TokenRequest` and rejected as 40170.

`token` is now accepted as a second discriminator. A `TokenRequest` never carries
one — TE2 makes `keyName`, `nonce` and `mac` its required fields — so this only
widens what is accepted, and the existing `issued` branch is untouched.

It is a deliberate divergence from ably-js, whose derived suite avoids the
question by returning a `text/plain` token string in place of the specification's
JSON body.

### A missing public accessor is adapted around, never gated

`writing-derived-tests.md` separates three situations, and only the last two are
deviations: a differently *spelled* public API is ordinary translation and is
recorded nowhere; a different public *value or effect* is a deviation; and an
internal API whose *shape* differs is a deviation at the unit tier only, to be
adapted while preserving the coverage.

A fourth situation came up repeatedly in the realtime derivation and sits between
them: the behaviour is exactly what the specification requires, the value exists and
has the right lifecycle, but there is **no public member at all** — not a
differently named one, none. `Connection#id` and `Connection#key`,
`RealtimeChannel#properties`, `ChannelStateChange#event`, a public
`Connection#whenState`, a distinct `LocalPresenceMap` type.

The ruling is: **adapt, and record the missing API separately.** The test asserts
the equivalent observable, however internal — `connection.connection_manager.connection_id`,
the name-mangled `__channel_serial`, the event key a listener was registered
against — with a comment at the first site and the reason in the module docstring.
Each file defines a small reader at the top (`connection_id(client)`,
`attach_serial(channel)`) so the adaptation is in one place and the assertions read
as the specification writes them.

It is not gated, for a reason worth stating plainly: gating would take real
behavioural coverage out of the run indefinitely over a question of spelling. The
RTL15 serial tests are the clearest case — ten tests about when a channel serial is
written and cleared, four of which found genuine defects. Gating all ten because
`properties` does not exist would have found none of them.

The cost is that a missing accessor never shows up as a failure, so it is easy to
lose. That is what the *missing accessor* table
above is for, and why the candidate-issue list gives them a
tier of their own rather than folding them into the features that are absent
outright.

Only wrong behaviour is gated.

### Each integration tier runs against a provisioned sandbox app of its own, once per protocol

`uts/rest/integration` and `uts/realtime/integration` are the tiers with a server behind
them, and three harness choices follow from that.

Each tier provisions one app for itself and deletes it at the end, which is the
specifications' `BEFORE ALL TESTS` / `AFTER ALL TESTS` pair; a fresh app per test would
make the tiers several times slower and invite the sandbox's rate limiting. The REST tier's
app arrives as the `sandbox` fixture and the realtime tier's as `realtime_sandbox`, each
provisioned and named separately, so a realtime test entering presence or publishing to a
channel cannot be seen by a REST test reading the same channel name. `key(0)` is the
full-access key the specifications call `api_key`, and the other indices are the
capabilities each specification's app-provisioning section names.

A specification carrying a `## Protocol Variants` section runs each of its Test IDs twice,
through a `use_binary_protocol` fixture parametrized `[False, True]` with the ids `json`
and `msgpack`; each tier defines its own. Five of the twelve REST specifications carry that
section, so 38 of the 84 REST integration Test IDs are two pytest cases each, and five of
the twenty realtime ones do — `channel_history_test.md`, `channels/channel_publish_test.md`,
`delta_decoding_test.md`, `mutable_messages_test.md` and `presence_lifecycle_test.md` — so
22 of the 73 realtime Test IDs are. The rest are json only and take the default their
tier's `sandbox_rest_client` or `sandbox_realtime_client` applies. This is why the counts
in this file give Test IDs and cases separately.

An autouse fixture closes every client a test built, whether or not its assertions held
(`test/uts/conftest.py`, `close_open_clients`). The specifications write
`AWAIT realtime.close()` inline, which is redundant against that fixture and in two
places actively destroys what the following REST read is about — see the UTS Spec Error
above. Tests omit the inline close and leave it to teardown.

### The proxy package runs against a pinned proxy, with a session per test

`uts/docs/proxy.md` puts `ably/uts-proxy` between the client and the sandbox for the
specifications under `rest/integration/proxy` and `realtime/integration/proxy`, and three
harness choices follow from having to supply the proxy itself. The two packages share
`test/uts/helpers/proxy.py` and each repeats the `proxy_control` / `proxy_session` pair,
including the `append=False` on the timeout marker that keeps the package's 300 seconds
ahead of its parent's 120.

The release is pinned and verified rather than built or assumed present. The archive for
the machine is downloaded on first use, checked against the sha256 the release publishes,
and extracted into `~/.cache/uts-proxy/<version>/`, under a lock file so that the several
Python versions CI runs fetch it once between them. `UTS_PROXY_LOCAL_PATH` substitutes a
locally built binary or distributive, and `UTS_PROXY_CONTROL_URL` substitutes a control
API a developer is already running, which the suite then leaves alone. One control
process is started per test run on a free port, rather than a fixed one, so two suites on
a machine do not collide, and it is reaped at the end of the run and again at interpreter
exit.

A session is per test and the `proxy_session` fixture closes every one it handed out,
which is the specifications' `AFTER EACH TEST: IF session IS NOT null: session.close()`
without each test having to carry it. The session's `timeoutMs` is set to 120000 against
the proxy's own 30000, because it is an idle timer and one of these tests sits through a
twenty-second delay before it reads anything; the package's per-test pytest timeout is
300 seconds against the tier's 120, for the delay and for the download the first test may
wait on. Every client in the package authenticates through an `authCallback` whose own
request goes straight to the sandbox: the session speaks plain HTTP, RSC18 refuses basic
auth over it, and a token request routed through the session would be counted by the
assertions that count requests. A realtime connection carries its credentials in the
WebSocket's query string rather than in an Authorization header, so a `key=` does reach the
session over plain `ws://`; the realtime modules still prefer a locally signed Ably JWT
wherever the scenario is not about authentication, because signing one costs no round trip
and so leaves nothing in the event log beside the frames a test counts.

A realtime client reaches its session exactly as a REST one does — `endpoint='localhost'`,
`port=session.proxy_port`, `tls=False`, `use_binary_protocol=False` — and that rests on
`WebSocketTransport` interpolating `Defaults.get_port(self.options)` into the URL it opens,
so that the `port` and `tlsPort` client options (TO3k4, TO3k5) the REST layer honours reach
the websocket too. Without it a realtime client can be pointed at no port but the default,
and the realtime half of this tier cannot run at all. That is a fix in the SDK rather than
a deviation, so it has no entry above — entries closed by a fix are removed rather than
kept as history — but it is what the tier stands on.

### A hedged integration setup is provisioned so its guarded assertions bite

`time_stats.md` hedges its setup in a way that lets both its tests pass without testing
anything, and the harness removes the hedge rather than the assertion. It allows for an empty result — "stats may be empty for a new sandbox app" —
and guards its assertions on an interval's shape behind `IF result.items.length > 0`. A
freshly provisioned app has no stats at all, verified, so against one that branch never
runs and both RSC6 tests assert only that the call returned something. The module-scoped
`app_with_stats` fixture records a minute of traffic against the app through the sandbox's
`POST /stats` injection endpoint — the mechanism the repository's own
`test/ably/rest/reststats_test.py` uses — and the tests then make the guarded assertions
unconditionally. Injection rather than real traffic is deliberate: real traffic is
aggregated on the server's own schedule, so there is no bounded wait after which a
published message is certainly counted, whereas an injected interval is queryable at once.
With traffic in place `test_rsc6_stats_with_parameters` also asserts that every returned
interval has `unit == 'hour'`; the specification asserts only `items.length <= 5`, which an
empty page satisfies whether or not the query reached the server. Both tests were confirmed
to fail with `assert 0 > 0` when the injection is removed, so neither passes vacuously.

One further setup departs from the pseudocode, for latency rather than coverage.
`pagination.md`'s five setups are each `FOR i IN 1..N: AWAIT channel.publish(...)` — 15,
12, 10, 25 and 3 messages, a round trip apiece. The tests publish the same messages as one
list through `channel.publish([Message(...), ...])`, which `Channel._publish` accepts
(`ably/rest/channel.py:97,105`): the resulting message set, names and data are identical
and each message still gets a distinct id, so only the setup latency differs. Each test
then polls history until the expected count is visible before paginating, which is the
specifications' own `poll_until`, because history is not immediately consistent.

### Deviation records are consolidated, not accumulated

Each round of derivation runs a specification area per agent, and each writes its own
`deviations-<area>.md`. Those files are scaffolding and are not kept:
`writing-derived-tests.md` requires one entry per **root cause**, and a per-area file
cannot see that two areas found the same defect. In the realtime round three defects
were in fact reported by more than one area — the `on_error` bypass, the transposed
`AblyException` arguments, and the `EventEmitter` wrapper registry — and one was
reported as a defect and then refuted. The integration round found four gaps the unit
tier had already recorded, which extend the rows they belong to rather than opening
new ones: `Auth#revokeTokens`, `Rest#batchPresence`, the `PushChannel` surface and the
`clientId` filter on `RestPresence#get`. The revoked-token 40171 it observed is the
same root cause as RTN15h1's, and sits in that entry. The realtime integration round did
the same for five more: the RTN15h3 stall, the connection-level ERROR bypass, the unused
`connectionStateTtl`, connection recovery, and the missing channel-level handling for a
decode error other than 40018.

A verdict can change the same way, when a second specification reaches a behaviour the
first was content with. `errorReason` surviving a successful reconnect is permitted by
RTN25, whose test names either reading, and forbidden by RTN14b, which names one; so the
entry sits under *Failing Tests* and the RTN25 unit test that asserts the retained error
stays an adaptation. Where two specifications differ in strength, the entry follows the
stronger.

So the per-area files are merged into this file and deleted, and the comments in
the tests that pointed at them point here instead.
A refuted claim is kept, under *Investigated and not defects*, because the reason a
reader needs it is precisely that it looks like a defect.

### This file carries its own counts, and they are measured

The header states how many derived tests there are, how many pass, how many are
gated and how many cannot run. Those numbers are the check that the file is still
true: in pytest cases, the gated count must equal the number of failures under
`RUN_DEVIATIONS=1`, and gated plus unrunnable must equal the number of skips without
it. As of this writing that is 217 failures and 15 skips with the variable set, and
232 skips and 1124 passes without it, the 1124 being 1002 derived cases and 122
`helpers/` ones.

The other two counts are measured from the source rather than from a run. The number of
**derived tests** is the number of `# UTS:` comments, 1141. The number of **Test IDs** is
the number of *distinct* ids in them, 1132 — not the same figure, because five ids in
`rest/unit` are carried by more than one test function. Counting the comments and calling
the result Test IDs is the easy mistake here, and it overstates the specification coverage
by nine.

Anyone changing the suite should re-run both and update the header, rather than copying
the previous numbers forward. Keep the three units apart while doing it: one Test ID is
one or more derived tests, and one derived test is one or more pytest cases.
