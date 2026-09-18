# Deviations

Where the derived tests depart from the Universal Test Specifications, and why.
[decisions.md](decisions.md) covers how the specifications are adopted here;
this file records behaviour.

Entries are grouped by root cause rather than by test, so one entry covers every
test it affects. Headings are fixed and appear even when they hold nothing.

Of 581 derived tests, 474 pass, 100 are gated behind `RUN_DEVIATIONS` and 7 cannot
be run at all. Every gated test has been confirmed to fail when enabled, so none of
them passes under both behaviours.

Entries closed by a fix are removed rather than kept as history; `git log` holds that.

Run the gated tests with:

```
RUN_DEVIATIONS=1 uv run --extra crypto pytest test/uts
```

## UTS Spec Errors

Faults in the specifications themselves, found while deriving. Each is asserted
against the correct behaviour with a `# UTS SPEC ERROR:` comment naming the point,
so the suite stays green; converting any of them to a fail-fast placeholder is a
one-line change at the marked site.

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

### Smaller faults

| Spec | Fault |
|---|---|
| `options_types.md` | TO3 table uses pre-REC1 hostnames (`rest.ably.io`, `test-rest.ably.io`) |
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
| RSC22, RSC24, BSP2, BPR2, BPF2, BAR2, BGR2, BGF2 | `batchPublish` and `batchPresence`, and all six result types. `grep -rn batch ably/` finds nothing | 41 |
| RSA17, RSA17b–g, BAR2, TRS2, TRF2 | `Auth#revokeTokens`, `TokenRevocationTargetSpecifier`, `BatchResult` | 17 |
| RSH7, RSH7a–e, RSH6, RSH8 | `PushChannel`: `channel.push`, `client.device`, `LocalDevice`. The push *admin* surface (RSH1) does exist | 10 |
| RSL7 | `RestChannel#setOptions`. The realtime channel implements it; the REST `options` setter expects the kwargs dict `Channels.get` collected, so a `ChannelOptions` raises `TypeError` | 2 |
| RSP3a2, RSP3a3 | `clientId` and `connectionId` filters on `RestPresence#get`. `Presence.get` takes only `limit`, while `Presence.history` does take its documented params | 3 |
| TP5 | `size` on `PresenceMessage`. The related `maxMessageSize` gap is adapted rather than gated, below; `features.md` TM6 has no UTS test | 1 |
| RSL1i | REST publish never calls `validate_message_size`. The helper exists and is correct, but only `ably/realtime/channel.py:423` calls it, so an oversized REST publish goes out | 1 |
| RSC2, RSC3, RSC4, TO3b, TO3c, TO3c2 | `log_handler` as a client option, and any use of `log_level` — it is stored on `Options` and read by nothing | 4 |
| TI4, TI1/TI5 | `href` anywhere in the SDK, and `cause` when deserialising. `AblyException.from_dict` and `raise_for_response` read only `message`, `statusCode` and `code`, so both fields are dropped from server errors | 2 |
| TP3a, TP3d, TP3g | Presence attributes defaulted from the encapsulating ProtocolMessage. There is no ProtocolMessage type; `ably/realtime/channel.py:751-761` passes the presence array through without context. Matters for synthesized-leave detection and `memberKey` | 3 |

### Auth

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

### Requests

| Spec points | Behaviour |
|---|---|
| RSC19b | Caller-supplied headers override the configured `Authorization`, because `Http.make_request` applies `headers` after `auth_headers`. RSC19b says requests "unconditionally" use the configured mechanism |
| RSH1b1 | Device ids are interpolated raw into push paths (`ably/rest/push.py` lines 82, 106, 118), so an id containing `/` addresses a different resource and `:` is unescaped. `ably/rest/channel.py` does quote channel names, so the SDK is inconsistent with itself |

## Adapted Tests

The test asserts what the SDK does, with the specification's expectation in a
comment above. These run, so they guard against regression.

| Spec points | Specification | ably-python | Status |
|---|---|---|---|
| RSL2 | A space in a channel name is `%20` | `+`, from `parse.quote_plus` in `Channel.__init__`. `quote_plus` is form encoding, and a `+` in a URL *path* is a literal plus, so the name reaching the server is altered | Open bug, and a genuine correctness issue |
| RSL8 | `Channel#status` URI-encodes the channel id | `status()` interpolates the name with no escaping at all. `a/b` addresses the wrong resource, `a?b` truncates the name into a query string, `a#b` becomes a fragment | Open bug |
| RSL2, RSL11b, RSL15b | `:` is `%3A` | Left literal, from `safe=':'`. RFC 3986 allows `:` in a path segment and Ably uses it for namespaces, so the server receives the same value | Intentional |
| RSC1b | Error code 40106 | A bare `ValueError` from `AblyRest.__init__` with an informative message, not an `AblyException`, so there is no code | Open bug |
| RSC18 | The constructor rejects basic auth over HTTP | Construction succeeds; 40103 is raised from `make_request` when a request needing Basic Auth is attempted, and no request goes out. RSA1/RSC18 say only "any attempt to use" | Compliant; the UTS is stricter than its source |
| REC1b1, REC1c1 | Code 40000, or a message containing "invalid" or "conflict" | 400/40106 with a specific message. The features spec mandates no code | Cosmetic |
| RSAN1a3 | Code 40003 for a missing `Annotation.type` | 400/40000 | Cosmetic; worth aligning cross-SDK |
| RSH1a | Empty `recipient` or `data` rejected with code 40000 | `TypeError` / `ValueError`, not an `AblyException`. The "no HTTP request" half is satisfied | Open bug, minor |
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
