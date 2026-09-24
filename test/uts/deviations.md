# Deviations

Where the derived tests depart from the Universal Test Specifications, and why.
The closing section covers how the specifications are adopted here; everything
before it records behaviour.

Entries are grouped by root cause rather than by test, so one entry covers every
test it affects. Headings are fixed and appear even when they hold nothing.

Entries closed by a fix are removed rather than kept as history; `git log` holds that.

Run the gated tests with:

```
RUN_DEVIATIONS=1 uv run --extra crypto pytest test/uts
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
away. Each is filed upstream, in the issues named below.

The tests gated this way:

| Test | Spec error |
|---|---|

| `test_rsp4_history_pagination` | RSP4 - wire action 4 asserted to be LEAVE |
| `test_tp3_presence_to_json` | TP3 - an outgoing action asserted as the string `"enter"` |
| `test_tp3_null_attributes_omitted` | TP3 - the same outgoing string assertion |

Where instead only a specification's *fixture*, *setup* or *label* is at fault, the
assertion it carries still stands. Those tests keep the corrected fixture (or the
corrected label in a comment), pass, and carry a `# UTS SPEC ERROR:` comment at the
site. The entries below cover both kinds and say which applies.

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

### Smaller faults

| Spec | Fault |
|---|---|
| `options_types.md` | The `TO/endpoint-affects-host-0` "Expected Rest Host" column uses pre-REC1 hostnames (`rest.ably.io`, `test-rest.ably.io`). No assertion reads the column, so the derived test is unaffected |
| `channels_collection.md` | Header claims RSN3b and RSN3c; neither has a test |
| `stats.md` | Fixture nests counts under `all`, which `Stats.from_dict` never reads |
| `rest_client.md` | `RSC17` has two byte-identical tests; header lists RSC7 and RSC7b with no tests |
| `rest_client.md` | `RSC18` requires constructor-time failure; RSA1/RSC18 only say "any attempt to use" |
| `request.md` | `version` is written as an integer but lands in a header |
| `fallback.md` | REC3a, REC3b and REC3 drive a Realtime client but sit in `rest/unit` |
| `message_encoding.md`, `msgpack_interop.md`, `annotations.md` | Six sections carry no Test ID; ids were inferred by sibling convention |
| `publish.md`, `rest_presence.md`, `message_encoding.md`, `history.md`, `idempotency.md` | All point at `/Users/paddy/data/worknew/dev/dart-experiments/...` for the mock contract |

## Failing Tests

The specification's assertion is preserved and gated behind `@deviation`. Removing
the mark is the only change needed once the SDK behaviour lands.

### Unimplemented features

| Spec points | Missing | Tests |
|---|---|---|

| RSP3a2, RSP3a3 | `clientId` and `connectionId` filters on `RestPresence#get`. `Presence.get` takes only `limit`, while `Presence.history` does take its documented params | 3 |
| TP5 | `size` on `PresenceMessage`. The related `maxMessageSize` gap is adapted rather than gated, below; `features.md` TM6 has no UTS test | 1 |

| RSC2, RSC3, RSC4, TO3b, TO3c, TO3c2 | `log_handler` as a client option, and any use of `log_level` — it is stored on `Options` and read by nothing | 4 |
| TI4, TI1/TI5 | `href` anywhere in the SDK, and `cause` when deserialising. `AblyException.from_dict` and `raise_for_response` read only `message`, `statusCode` and `code`, so both fields are dropped from server errors | 2 |
| TP3a, TP3d, TP3g | Presence attributes defaulted from the encapsulating ProtocolMessage. There is no ProtocolMessage type; `ably/realtime/channel.py:751-761` passes the presence array through without context. Matters for synthesized-leave detection and `memberKey` | 3 |

### Options

| Spec points | Behaviour |
|---|---|
| TO3 | `endpoint` is left unset when none is given, per `TO/endpoint-affects-host-0`. `Options.__init__` resolves the default eagerly to the REC1a routing policy id `main`, so the attribute never reads back as null. Only the default case is gated; the two that name an endpoint are derived and pass |

### Requests

| Spec points | Behaviour |
|---|---|
| RSC19b | Caller-supplied headers override the configured `Authorization`, because `Http.make_request` applies `headers` after `auth_headers`. RSC19b says requests "unconditionally" use the configured mechanism |

## Adapted Tests

The test asserts what the SDK does, with the specification's expectation in a
comment above. These run, so they guard against regression.

| Spec points | Specification | ably-python | Status |
|---|---|---|---|

| RSC1b | Error code 40106 | A bare `ValueError` from `AblyRest.__init__` with an informative message, not an `AblyException`, so there is no code | Open bug |
| RSC18 | The constructor rejects basic auth over HTTP | Construction succeeds; 40103 is raised from `make_request` when a request needing Basic Auth is attempted, and no request goes out. RSA1/RSC18 say only "any attempt to use" | Compliant; the UTS is stricter than its source |
| REC1b1, REC1c1 | Code 40000, or a message containing "invalid" or "conflict" | 400/40106 with a specific message. The features spec mandates no code | Cosmetic |

| HP6 | `errorCode` is a number | The raw header string, `'40101'` | Open bug, trivial |
| HP8 | `headers` is a map | A list of `(name, value)` pairs, so the lookup the spec describes is impossible without converting, and case-insensitivity is lost | Open bug; changing the return type is breaking |
| RSC19e | An error indicated idiomatically | `httpx.ConnectError` / `ReadTimeout` reach the caller unwrapped, because `AblyRest.request` carries no `@catch_all` unlike `time()` and `stats()`. The messages do name the failure | Borderline; defensible under RSC19e |
| RSC15a | Six hosts tried | Three. `Options.__get_hosts` truncates to `http_max_retry_count`, which TO3l5 sanctions | Intentional |
| TI | `ErrorInfo` equality by attributes | No `__eq__`, so errors compare by identity. Python exceptions conventionally do, and the requirement appears nowhere in `features.md`. Adding `__eq__` without `__hash__` would make `AblyException` unhashable and break any caller that puts one in a set | Intentional |
| TD5, RSA16a | `capability` is stringified JSON | A `Capability` object, a public convenience type used throughout `auth`. Narrowing the return type to `str` would break every caller that indexes or mutates it, so it is reserved for a future major | Intentional; a breaking change to align |

| TO3l8 | `maxMessageSize` is a client option, default 65536 | Rejected by `Options.__init__`. `ably/realtime/channel.py:422` reads it with `getattr(..., 65536)`, so the default holds but cannot be configured, nor overridden by `connectionDetails` (CD2c) | Open bug |
| TO3l1, TO3l5 | `httpRequestTimeout` and `httpMaxRetryCount` carry their defaults on the options object | Left unset; the effective defaults are applied downstream by `Http` and by `Options.__get_hosts`. The spec's values are milliseconds, while ably-python's `http_request_timeout` is seconds | Intentional |

## Mock Infrastructure Limitations

Tests that cannot be implemented as written. The first is caused by the SDK, not by
the mock, but it lands here because the effect is the same: no test can observe the
behaviour.

### The connectivity check bypasses the injected transport — 3 tests

`ConnectionManager.check_connection` is internal, synchronous, and calls
`httpx.get` directly. `REC3a`, `REC3b` and `REC3` are skipped. These specs drive a
Realtime client and belong under `realtime/unit` in any case.

### `fallbackHostsUseDefault` is not implemented — 3 tests

Optional per TO3k7, and `REC1b1` and `REC2a1` scope their checks to libraries that
support it, so these are skipped as not applicable rather than recorded as
deviations.

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
`fallback_retry_timeout`. Adding a clock seam is left until the realtime specs,
which need one for reconnection timing.

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
