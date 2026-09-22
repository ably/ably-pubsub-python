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


## Failing Tests

The specification's assertion is preserved and gated behind `@deviation`. Removing
the mark is the only change needed once the SDK behaviour lands.

## Adapted Tests

The test asserts what the SDK does, with the specification's expectation in a
comment above. These run, so they guard against regression.

## Mock Infrastructure Limitations

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
