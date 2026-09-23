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
gh api repos/ably/specification/contents/uts/realtime/unit/<spec>.md --jq '.content' | base64 -d
```

`writing-derived-tests.md` governs. This file covers only what is particular to ably-python.

## Layout

A spec at `uts/<tier path>/<name>.md` becomes `test/uts/<tier path>/<name>_test.py`, so
`uts/rest/unit/auth/token_renewal.md` becomes `test/uts/rest/unit/auth/token_renewal_test.py`.
Every directory needs an `__init__.py`, as `test` is a package.

`test/uts/rest/unit/time_test.py` is the reference example for REST, and
`test/uts/realtime/unit/connection/auto_connect_test.py` for realtime. Follow their shape.

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
| `enable_fake_timers()` / `ADVANCE_TIME(ms)` | `FakeClock` on a realtime client, nothing on REST; see Timers below |
| `install_mock(m)` + `Realtime(options: ...)` | `realtime_client(m, ...)` from `test.uts.helpers.client` |
| `AWAIT_STATE client.connection.state == X` | `await await_connection_state(client, ConnectionState.X)` |
| `mock_ws.active_connection` | the same, on `MockWebSocket` |

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

## The websocket mock

`test/uts/helpers/mock_websocket.py`, matching `uts/realtime/unit/helpers/mock_websocket.md`.
Read it. Names match the pseudocode, transliterated to snake_case.

A realtime client comes from `realtime_client(mock_ws, ...)` in
`test.uts.helpers.client`. It defaults the credentials to a key, `auto_connect` to
**false** and `fallback_hosts` to **empty**, and registers the client for teardown.
Pass `auto_connect=True` where the spec is about the default, and `mock_http=` or
`clock=` where a spec needs HTTP or controlled time on a realtime client.

```python
mock_ws = MockWebSocket(
    on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
)
client = realtime_client(mock_ws)

client.connect()
await await_connection_state(client, ConnectionState.CONNECTED)
```

### `MockWebSocket`

`MockWebSocket(on_connection_attempt=None, on_message_from_client=None,
on_text_data_frame=None, on_binary_data_frame=None)`. Every handler is reassignable.

- `as_connect()` — the callable for `TestOptions(websocket_connect=...)`.
- `events` — the unified timeline, a list of `MockEvent(type, timestamp, data)`.
- `connection_attempts` / `messages_from_client` — the timeline filtered to the
  `PendingConnection`s and the decoded messages the client sent.
- `events_of_type(MockEventType.X)` — the timeline filtered by type.
- `connections` / `active_connection` — the `MockConnection`s established, and the
  most recent one. `active_connection` is `None` before the first connection and
  after the client closes it.
- `handler_errors` — whatever a test's handler raised. The mock keeps those out of
  the library rather than letting them escape.
- `send_to_client(message)`, `send_to_client_and_close(message)`,
  `simulate_disconnect(error=None)`, `send_ping_frame()` — against
  `active_connection`; they raise if there is none.
- `await_connection_attempt(timeout=5)`, `await_next_message_from_client(timeout=5)`,
  `await_client_close(timeout=5)` — each **registers its waiter when called** and
  returns an awaitable, so the next event can be awaited before the current one is
  answered. Timeouts are seconds. A timeout raises `AssertionError`.
- `reset()` — clears the timeline, the waiters and the recorded connections, and
  leaves the handlers and any live connection alone.

`MockEventType`: `CONNECTION_ATTEMPT`, `CONNECTION_SUCCESS`, `CONNECTION_FAILURE`,
`MESSAGE_FROM_CLIENT`, `MESSAGE_TO_CLIENT`, `PING_FRAME`, `SERVER_DISCONNECT`,
`CLIENT_CLOSE`.

### `PendingConnection`

What a connection handler and `await_connection_attempt()` receive.

- `url` — a `RecordedUrl`: `scheme`, `host`, `port`, `path`, `query_params`, `str(url)`.
- `protocol` — `'application/x-msgpack'` or `'application/json'`, from the `format`
  query parameter.
- `headers` — the handshake headers, case-insensitive (`headers['Ably-Agent']`).
- `timestamp`, and `connection`, the `MockConnection` it will yield.
- `respond_with_success(connected_message=None)` — completes the connection, then
  delivers the message behind it.
- `respond_with_refused()`, `respond_with_timeout()`, `respond_with_dns_error()`.
- `respond_with_error(error_message, then_close=True)` — connects, then has the
  server send an ERROR.
- `send_to_client`, `send_to_client_and_close`, `simulate_disconnect`,
  `send_ping_frame` — the server side of the connection it produces, so a handler
  can call `respond_with_success()` and then `send_to_client(...)`.

### `MockConnection`

`send_to_client`, `send_to_client_and_close`, `simulate_disconnect(error=None)`,
`send_ping_frame`, plus `protocol`, `closed` and `close_event`. Its `__aiter__`,
`send` and `close` are the library's side; a test does not call them.

`ClientCloseEvent` carries `code` and `reason`.

### Templates

`CONNECTED_MESSAGE`, `CLOSED_MESSAGE`, `DISCONNECTED_MESSAGE`, `HEARTBEAT_MESSAGE`,
`ERROR_MESSAGE(code, message)`, `PING_MESSAGE(id)`, and
`connected_message(connection_id='test-connection-id', **connection_details)` for a
variant. Templates are plain dicts, so build a variant rather than mutating one.
Keys are wire names, camelCase.

A message given as a dict is encoded for the connection's protocol. Pass `bytes` or
`str` to control the wire format yourself.

### Timing helpers

- `await_connection_state(client, state, timeout=5)` from `test.uts.helpers.client`
  is `AWAIT_STATE`. It registers its listener synchronously and returns at once if the
  state is already current.
- `settle()` from `test.uts.helpers.clock` is `process_pending_events()`: twenty
  yields, because the realtime paths chain `create_task` several levels deep.
- `FakeClock` from `test.uts.helpers.clock`, passed as `realtime_client(mock, clock=clock)`,
  is `enable_fake_timers()`; `await clock.advance(ms)` is `ADVANCE_TIME(ms)`.

## Traps found while building the websocket mock

- **A transient state cannot be polled for.** RTN15a retries immediately after a drop
  from CONNECTED (`loop.call_soon`, not a timer), so DISCONNECTED is gone before the
  next `await` returns. Record the sequence with `connection.on(...)` and assert on it,
  as `mock_websocket.md` says. `await_connection_state(client, DISCONNECTED)` after a
  drop will time out.
- **`connection.id` does not exist**, nor `connection.key` or `recovery_key`. Read
  `client.connection.connection_manager.connection_id` and
  `client.connection.connection_details`.
- **A refused connection and a connect timeout are indistinguishable.** `ws_connect`
  catches only `WebSocketException` and `socket.gaierror`, so a
  `ConnectionRefusedError` or `asyncio.TimeoutError` never reaches
  `_emit('failed')`: the attempt hangs until the transition timer fires and the state
  change carries a generic 50003/504. Keep `realtime_request_timeout` short in any
  test that waits one out. `respond_with_dns_error()` is the only fast failure, and
  it carries 40000/400 with the real cause.
- **A server-sent CLOSED does nothing.** `on_closed` disposes the transport without
  notifying a state, so the connection stays CONNECTED. CLOSED is only reached
  through `client.close()`.
- **A DISCONNECTED error needs a `statusCode`** — see the deviations entry. The
  template has one.
- **Action 22 (PING) matches no branch** of `on_protocol_message`, so `PING_MESSAGE`
  draws no PONG. RTN23c1 is unimplemented.
- **A ping frame is unobservable.** See the Mock Infrastructure Limitation.
- **`ping()`'s own timeout is real time.** `connectionmanager.py` uses
  `asyncio.wait_for(..., realtime_request_timeout / 1000)` on the loop clock, not the
  timer seam, so `advance()` will not move it.
- **`Task exception was never retrieved` on teardown is expected** for a client whose
  connect failed. `close_impl` creates a task for `transport.close()`, and
  `WebSocketTransport.send` raises a bare `Exception()` when `self.websocket` is
  `None`. It is log noise, not a failure.
- **Do not install `FakeClock` for heartbeat or `maxIdleInterval` tests.**
  `on_idle_timer_expire` compares `unix_time_ms()` against `max_idle_interval` but
  schedules through the timer seam, so advancing fires the timer while no real time
  has passed and it reschedules itself forever. Drive those with a small
  `maxIdleInterval` in `connected_message(...)` on real time.
- **Keep the fallback hosts empty** unless the spec is about them. The connectivity
  check is a synchronous `httpx.get` no seam reaches.

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

## Traps found while deriving the REST unit specs

- **`/time` returns an array.** Several specs stub it as `{"time": N}`; the endpoint
  and `time.md` both use `[N]`, and `AblyRest.time()` indexes it. Stub `[N]`.
- **A single queued response is consumed by the first host.** A 5xx or CloudFront
  response sends the client to the next fallback, so queue one response per host
  (`queue_responses(3, ...)`) or answer from a handler.
- **`"encoding": null` crashes decoding** in `Message`, `PresenceMessage` and
  `Annotation` — `obj.get('encoding', '')` returns `None` when the key is present
  and null. Expect `AttributeError: 'NoneType' object has no attribute 'strip'`.
- **`msgpack.packb(..., use_bin_type=True)`** is required for a payload that must
  arrive as msgpack `bin` rather than `str`. The mock's automatic encoding uses
  `use_bin_type=False`, so encode such a body yourself with an explicit
  `Content-Type`.
- **`auth_url` requests go through the injected transport.**
  `Auth.token_request_from_auth_url` uses the client's own HTTP layer, so a spec driving
  `auth_url` is observed through the mock like any other request.
- **`PaginatedResult` reads `Content-Type` unguarded**, so anything it paginates over
  needs one. A native dict or list body gets one automatically.
- **The mock enforces the client's read timeout**, so `respond_with_delay` beyond
  `http_request_timeout` raises rather than arriving late.
- **Several client options are missing entirely** — `max_message_size` and
  `log_handler` among them — and raise `TypeError` rather than being ignored. Check
  `ably/types/options.py` first.

## Timers

The realtime client has a timer seam; the REST client does not.
`ably/http/http.py` calls `time.time()` directly. Where a REST spec calls
`enable_fake_timers()` / `ADVANCE_TIME(ms)`, prefer short real timeouts driven by client
options (`fallback_retry_timeout=100`), which is what the specs themselves do. The global
pytest timeout is 30 seconds, so keep waits well under it.

On a realtime client, prefer a short real interval through a client option
(`realtime_request_timeout`, `disconnected_retry_timeout`, `suspended_retry_timeout`,
`channel_retry_timeout`) or through `connected_message(maxIdleInterval=...)`, and reach
for `FakeClock` only for `connection_state_ttl`, which no option sets and whose default
costs 120 real seconds. See the fake-time section of `test/uts/deviations.md`.

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
