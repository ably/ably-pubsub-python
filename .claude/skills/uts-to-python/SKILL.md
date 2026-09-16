---
description: Translate Universal Test Specifications from ably/specification into ably-python tests. Use when deriving, updating or evaluating tests under test/uts.
allowed-tools: Bash, Read, Edit, Write, WebFetch
---

# Translating UTS specs into ably-python tests

## Sources

Fetch both fresh at the start of every run; do not work from memory.

```bash
gh api repos/ably/specification/contents/uts/docs/writing-derived-tests.md --jq '.content' | base64 -d
gh api repos/ably/specification/contents/uts/rest/unit/<spec>.md --jq '.content' | base64 -d
```

`writing-derived-tests.md` governs. This file covers only what is particular to ably-python.

## Layout

A spec at `uts/<tier path>/<name>.md` becomes `test/uts/<tier path>/<name>_test.py`, so
`uts/rest/unit/auth/token_renewal.md` becomes `test/uts/rest/unit/auth/token_renewal_test.py`.
Every directory needs an `__init__.py`, as `test` is a package.

`test/uts/rest/unit/time_test.py` is the reference example. Follow its shape.

## Anatomy of a derived test

```python
"""Derived from uts/rest/unit/time.md in ably/specification.

Spec points: RSC16
"""

# UTS: rest/unit/RSC16/returns-server-time-0
async def test_rsc16_time_returns_server_time():
    captured_requests = []

    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, [SERVER_TIME_MS])

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http)

    result = await client.time()

    assert result == SERVER_TIME_MS
```

- The `# UTS:` comment carries the spec's Test ID verbatim, immediately above the function.
- The function name is the spec point plus the Test ID slug: `rest/unit/RSC16/returns-server-time-0`
  becomes `test_rsc16_time_returns_server_time`. Drop the trailing index.
- `pytest` runs with `asyncio_mode = "auto"`, so async tests take no decorator.
- Keep `captured_requests` a local list appended from the handler, as the specs do. Do not
  reach for `mock_http.captured_requests`.
- Always pass `on_connection_attempt`, even where it only succeeds.
- Do not close clients. `test/uts/conftest.py` closes them after every test.

## Mapping pseudocode to ably-python

| Pseudocode | ably-python |
|---|---|
| `install_mock(m)` + `Rest(options: ClientOptions(...))` | `rest_client(m, ...)` from `test.uts.helpers.client` |
| `uninstall_mock()` | nothing; the fixture closes clients |
| `ClientOptions(key: "app.key:secret")` | the default in `rest_client`; pass nothing |
| `useBinaryProtocol` / `useTokenAuth` / `tls` | `use_binary_protocol` / `use_token_auth` / `tls` |
| `AWAIT client.time()` | `await client.time()` |
| `... FAILS WITH error` | `with pytest.raises(AblyException) as excinfo:` |
| `error.code` / `error.statusCode` / `error.message` | `excinfo.value.code` / `.status_code` / `.message` |
| `request.url.queryParams` / `queryParameters` | `request.url.query_params` (spec drift; one concept) |
| `parse_json(request.body)` | `json.loads(request.body)` |
| `msgpack_decode(x)` / `msgpack_encode(x)` | `msgpack.unpackb(x)` / `msgpack.packb(x, use_bin_type=False)` |
| `process_pending_events()` | `await asyncio.sleep(0)` |
| `enable_fake_timers()` / `ADVANCE_TIME(ms)` | no equivalent; see Timers below |

Client options are snake_case throughout. Check the actual signature in
`ably/types/options.py` before assuming an option exists.

## The mock

`test/uts/helpers/mock_http.py`, matching `uts/rest/unit/helpers/mock_http.md`. Read it.
Names match the pseudocode exactly.

Every call raises a `PendingConnection`, then a `PendingRequest` only if the connection
succeeded. A failed connection records nothing in `captured_requests`.

`PendingConnection`: `host`, `port`, `tls`, `timestamp`; `respond_with_success()`,
`respond_with_refused()`, `respond_with_timeout()`, `respond_with_dns_error()`.

`PendingRequest`: `method`, `url` (`scheme`, `host`, `port`, `path`, `query_params`),
`path`, `headers` (case-insensitive), `body` (raw bytes), `timestamp`;
`respond_with(status, body, headers)`, `respond_with_delay(ms, status, body, headers)`,
`respond_with_timeout()`.

`MockHttpClient` also carries `captured_requests`, `await_request(timeout)`,
`await_connection_attempt(timeout)`, `reset()`, and the queue family
(`queue_response`, `queue_responses`, `queue_timeout`, `queue_delayed_response`,
`queue_response_for_host`, `queue_response_for_url`). Handlers are reassignable.

A response body given as a dict or list is encoded to match what the client asked for,
so specs that exercise the binary protocol need no special handling. Pass `bytes` to
control the encoding yourself, alongside an explicit `Content-Type`.

## ably-python traits that catch translations out

- **The binary protocol is the default.** `use_binary_protocol` defaults to `True`, so
  requests carry `Accept: application/x-msgpack` and bodies are msgpack. Decode request
  bodies with `msgpack.unpackb` unless the spec sets `use_binary_protocol=False`.
- **5xx and CloudFront responses retry across every host.** A handler that always answers
  500 is called once per host, not once. Count requests accordingly, or branch on a counter.
- **`client.request()` requires `version`.** It is not optional.
- **`client.time()` returns milliseconds as a number**, not a datetime. The spec requirement
  admits "a DateTime or timestamp", so this is idiomatic, not a deviation.
- **`AblyException` carries `code`, `status_code` and `message`**, and `@catch_all` wraps
  several public methods, so a transport error surfaces as `AblyException` with code 50000.
- **A response with no `Content-Type` raises** `ValueError` from `Response.to_native()`, and
  `PaginatedResult` reads the header unguarded. Set `Content-Type` on any body passed as
  `bytes` or `str` that the client is meant to decode.

## Timers

There is no clock seam. `ably/http/http.py` calls `time.time()` directly. Where a spec calls
`enable_fake_timers()` / `ADVANCE_TIME(ms)`, prefer short real timeouts driven by client
options (`fallback_retry_timeout=100`), which is what the specs themselves do. The global
pytest timeout is 30 seconds, so keep waits well under it.

## Deviations

Diagnose per the decision tree in `writing-derived-tests.md`, then apply one of:

- **Env-gated skip**, for non-compliance expected to be fixed:
  ```python
  from test.uts.helpers.deviations import deviation

  @deviation
  async def test_rsa7b_client_id_from_token_details():
      ...
  ```
  Reproduce with `RUN_DEVIATIONS=1 uv run --extra crypto pytest -k rsa7b`.
- **Adapted assertion**, preferred where the behaviour is stable: assert what the SDK does,
  with the spec's expectation in a comment above.
- **Spec-error fail-fast**, only where the spec contradicts the features spec:
  `pytest.fail('UTS spec error <point> - fix the spec first; see deviations.md')`.

Never write a test that passes under either behaviour.

Record every one in `test/uts/deviations.md` under its heading, keeping all four headings
present and in order: UTS Spec Errors, Failing Tests, Adapted Tests, Mock Infrastructure
Limitations. Each entry needs the spec point, what the spec says, what the SDK does, root
cause where known, which tests are affected, and status.

A differently spelled API is not a deviation. Record only wrong behaviour.

## Checks

```bash
uv run ruff check ably/ test/
uv run --extra crypto pytest test/uts -q
```

Both must pass. Line length is 115.
