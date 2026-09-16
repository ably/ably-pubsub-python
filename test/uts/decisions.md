# Decisions

The reasoning behind how the Universal Test Specifications are adopted here.
Deviations from a specification's expected *behaviour* belong in
[deviations.md](deviations.md); this file covers choices about the approach.

## Tests are derived against the async API only

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

## A mock is an httpx transport, supplied as a client option

`mock_http.md` leaves injection open: "The mechanism for injecting the mock is
implementation-specific and not part of the public API."

The seam is `TestOptions(http_transport=...)`, consumed in `Http.__create_client`.
Serving requests at the transport layer keeps URL construction, header merging,
the host fallback loop and response decoding in the path, which is what the
specifications assert on. It also carries the distinction between a failed
connection and a failed request directly, as httpx raises `ConnectError`,
`ConnectTimeout` and `ReadTimeout` separately.

The alternative, replacing the whole client, would stub out the code under test.

## A mock serves one client rather than being installed globally

The specifications write `install_mock(mock_http)` and warn against passing a
mock to a client, because the SDKs they were first written against hold HTTP
behind a platform singleton. This client builds its HTTP client during
construction and holds it, so a mock is passed as a client option instead.

Derived tests construct the mock first, and `uninstall_mock()` has no
counterpart — `test/uts/conftest.py` closes clients after each test, so a test
whose assertions fail still releases its client.

## A native response body is encoded to match the request

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

## The superseded `queue_*` mock API is implemented

`writing-test-specs.md` lists `mock_http.queue_response()` under "Common
Mistakes to Avoid" in favour of the `onRequest` handler. The specifications have
not followed: `fallback.md`, `request.md` and `rest_client.md` use it heavily.

Implementing it costs little and keeps those three translations literal.
Rewriting each call into a handler and a counter would be the kind of invention
that derived tests exist to avoid.

Stubs are matched by URL, then by host, then consumed first-in-first-out, and a
URL is normalised before matching so that a default port may be given or
omitted.

## Test names carry the spec point, and the Test ID sits above them

A specification's Test ID, `rest/unit/RSC16/returns-server-time-0`, becomes
`test_rsc16_time_returns_server_time`, with the full ID in a `# UTS:` comment
immediately above the function. The comment is the identifier that survives
renaming; the function name makes failures readable without it.

## Timing is driven by client options rather than a fake clock

`enable_fake_timers()` and `ADVANCE_TIME(ms)` have no counterpart here, as there
is no clock seam — `ably/http/http.py` calls `time.time()` directly. Where a
specification advances time, the derived test shortens the interval through a
client option instead, which is what the specifications themselves do for
`fallback_retry_timeout`. Adding a clock seam is left until the realtime specs,
which need one for reconnection timing.

## A TokenDetails payload is recognised by its `token`, not only by `issued`

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
