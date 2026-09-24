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

### Templates and protocol-message builders

All in `test.uts.helpers.mock_websocket`. Templates are plain dicts with wire names
(camelCase), **shared at module level** — build a variant with the builder rather
than mutating one.

| Name | Is |
|---|---|
| `CONNECTED_MESSAGE` | action 4, `connectionId 'test-connection-id'`, `connectionDetails{connectionKey 'test-connection-key', clientId None, connectionStateTtl 120000, maxIdleInterval 15000}` |
| `CONNECTED_MESSAGE_NO_IDLE` | the same with `maxIdleInterval: 0`, so the transport never schedules the idle timer. **Every `FakeClock` test should connect with this** — see trap 6 |
| `CLOSED_MESSAGE`, `DISCONNECTED_MESSAGE`, `HEARTBEAT_MESSAGE` | actions 8, 6 (with a `statusCode`; see trap 9) and 0 |
| `connected_message(connection_id='test-connection-id', **connection_details)` | a CONNECTED variant |
| `ERROR_MESSAGE(code, message, status_code=None)` | action 9. Defaults 8xxxx to status 500; 4xxxx/5xxxx follow the spec formula (40142 -> 401) |
| `PING_MESSAGE(id)` | action 22 |
| `attached_message(channel, **fields)`, `detached_message(channel, **fields)` | actions 11 and 13 |
| `server_detached_message(channel, code, message, status_code=None)` | a DETACHED carrying an error, for RTL13 |
| `channel_error_message(channel, code, message, status_code=None)` | a channel-scoped ERROR. Routes through `on_error` -> `on_channel_message` (RTN15i) and fails the **channel**, which is the cheapest way into a FAILED channel |
| `message_protocol_message(channel, messages, **fields)` | action 15 |
| `annotation_protocol_message(channel, annotations, **fields)` | action 21 |
| `ack(message, serials=None, count=1)`, `nack(message, code, description, status_code=None, count=1)` | actions 1 and 2, built against a captured outgoing message |
| `PING_ACTION`, `PONG_ACTION`, `NORMAL_CLOSURE`, `MSGPACK_PROTOCOL`, `JSON_PROTOCOL` | constants |

A message given as a dict is encoded for the connection's protocol, deep-copied
first, and unknown keys survive to the wire — so `send_to_client` with a plain dict
already **is** the specifications' `send_to_client_raw`, and forwards-compatibility
specs need no new mock method. Pass `bytes` or `str` to control the wire format
yourself.

### Waiting on what the client sent

| Helper | Is |
|---|---|
| `await_protocol_messages(mock, action, count=1, timeout=5.0)` | the primitive: waits until `count` messages of that action have left the client, and returns them |
| `await_published(mock, count=1, timeout=5.0)` | the MESSAGE wrapper |
| `await_presence_sent(mock, count=1, timeout=5.0)` | the PRESENCE wrapper |
| `contains_in_order(observed, expected)` | the specifications' `CONTAINS_IN_ORDER` |

### Client and state helpers

All in `test.uts.helpers.client`.

| Helper | Is |
|---|---|
| `rest_client(mock_http, **kwargs)` | a REST client on the HTTP seam, registered for teardown |
| `realtime_client(mock_websocket=None, mock_http=None, clock=None, **kwargs)` | a realtime client on up to three seams. Defaults `key`, `auto_connect=False`, `fallback_hosts=[]` |
| `connected_client(mock_websocket, **kwargs)` | awaitable; a client already CONNECTED. Was copied into sixteen test files before it was promoted |
| `await_connection_state(client, state, timeout=5.0)` | `AWAIT_STATE`. Registers synchronously; **returns at once if the state is already current** — see trap 0 |
| `next_connection_state(client, state, timeout=5.0)` | waits for the *next fresh* entry into a state. The antidote to trap 0 for a reconnection |
| `await_channel_state(channel, state, timeout=5.0)` | the channel equivalent, with the same trap-0 hazard |
| `poll_until(condition, timeout=5.0, description='condition')` | `AWAIT UNTIL`, for a premise no state captures. Spins on **real** loop time, so it cannot wait for anything a `FakeClock` drives |
| `drop_transport(client, mock_websocket)` | stalls the attempt handler, disconnects, polls until DISCONNECTED is recorded, settles. Returns the recorded states. The cheap `FakeClock`-free way to hold DISCONNECTED |
| `reconnect_transport(client, mock_websocket, connected_message=None)` | drops and waits for a **fresh** CONNECTED |

### Presence helpers

All in `test.uts.helpers.presence`. The three white-box presence specifications drive a
`PresenceMap` and a `RealtimePresence` directly; the channel-state and `get`
specifications build presence wire messages by hand.

| Helper | Is |
|---|---|
| `presence_map()` | the specification's `PresenceMap()`, keyed by memberKey (TP3h) |
| `presence_message(action, client_id, connection_id, id, timestamp, data=None)` | a `PresenceMessage` as the specification's test steps construct one. Always give it an explicit `connId:serial:index` id — see trap 15 |
| `subscribed_presence(connection_id='conn-1', name='presence-test')` | a `RealtimePresence` over a `SimpleNamespace` stub channel, plus the list of `(event_name, message)` pairs its subscribers receive. Registers one listener **per event name**, to dodge trap 12 |
| `present_member(client_id, connection_id, id, **fields)` | one entry of a PRESENCE or SYNC message's `presence` array |
| `sync_message(channel_name, channel_serial, presence)` | a SYNC protocol message |

A stub channel is enough to drive `RealtimePresence` end to end: `set_presence` needs
only `channel.ably.connection.connection_manager.connection_id`, and `on_attached` a
running loop.

### Timing helpers

All in `test.uts.helpers.clock`.

| Helper | Is |
|---|---|
| `FakeClock(settle_passes=20)`, passed as `realtime_client(mock, clock=clock)` | `enable_fake_timers()`. Notional only — it patches nothing onto `time`, `Date` or the loop clock, so real safety timeouts still work |
| `await clock.advance(ms)` | `ADVANCE_TIME(ms)`: fires what has fallen due, in due order, and lets the loop settle |
| `clock.now`, `clock.pending`, `clock.fired` | inspection. **`clock.now` inside a callback equals that timer's due time**, which makes a delay measurement exact rather than sampled |
| `settle(passes=20)` | `process_pending_events()`: twenty yields, because the realtime paths chain `create_task` several levels deep |
| `advance_to_connection_state(client, clock, state, step, limit=60)` | the specifications' `LOOP up to N: ADVANCE_TIME(x)`, for driving the connection to SUSPENDED |

## Traps that cost the most time

Ordered by how much they cost, not by subject. Every one was hit for real while
deriving the realtime unit specifications; the first three account for most of the
lost time.

**0. `await_connection_state` returns immediately when the state is already held**, so
it silently no-ops and the assertions after it run against stale state. It looks like
it passed. Two shapes, both reported independently by two batches:

- *"Drop the connection and reconnect"* — the target is CONNECTED and the client is
  **still** CONNECTED when you call it. One batch lost five tests to false passes this
  way, asserting `connection_key == 'key-1'` where `'key-1-updated'` was the point.
  Use `next_connection_state(client, CONNECTED)`, or `reconnect_transport(...)`.
- *"An attempt is in flight"* — `client.connect()` sets CONNECTING **synchronously**,
  so `connect(); await await_connection_state(CONNECTING)` returns before
  `connect_base` has been scheduled. Poll for the **attempt**, never for the state:
  `poll_until(lambda: len(mock_ws.connection_attempts) == 1, description='...')`.

The same applies to `await_channel_state`: `send_to_client(DETACHED)` then
`await await_channel_state(channel, ATTACHED)` asserts nothing, because the channel
still *is* attached at that instant. Poll for the second ATTACH message first.

**1. A registered `await_*` waiter takes precedence over the handler.** So the
specifications' commonest shape — build the mock with an `on_connection_attempt` that
responds, *and* then `pending = await mock_ws.await_connection_attempt()` — leaves the
attempt unanswered, and teardown waits the full five seconds on a dangling connect.
When you capture with `await_*`, respond manually afterwards. Conversely, a
`MockWebSocket()` with **no** `on_connection_attempt` auto-answers with
`respond_with_success()` and no CONNECTED message: the connection sits in CONNECTING,
which looks like what you wanted, but the attempt is already answered and a later
`respond_with_success(CONNECTED_MESSAGE)` is silently a no-op. To withhold a response,
spell it `MockWebSocket(on_connection_attempt=lambda conn: None)`.

**2. `use_binary_protocol` defaults to True.** A mock feeding JSON strings must pass
`use_binary_protocol=False` or msgpack-pack its frames. Otherwise
`decode_raw_websocket_frame` raises, `ws_read_loop`'s broad `except Exception`
swallows it with a log line, and the test hangs to timeout with no clue.

**3. Keep `TypeError` out of the mock's handlers.** `ws_connect`'s `except TypeError`
wraps the whole `async with` body, so a `TypeError` raised anywhere inside — including
in a listener — silently triggers a **second** connect call. Give any connect callable
a `**kwargs` signature.

**4. A transient state cannot be polled for.** RTN15a retries immediately after a drop
from CONNECTED (`loop.call_soon`, not a timer), so DISCONNECTED is gone before the next
`await` returns and `await_connection_state(client, DISCONNECTED)` times out. Record
the sequence with `connection.on(...)` and assert on the list, as `mock_websocket.md`
says. To *rest* in DISCONNECTED, use `drop_transport(...)`, or fail the immediate retry
and raise `disconnected_retry_timeout`.

**5. Deadlock: `await connection.once_async(SUSPENDED)` before calling `advance()`
hangs forever** — nothing fires timers but `advance`. Record with `connection.on(...)`,
advance, then assert. If a real await is needed, start it as a task **first** and
advance second. And put `await settle()` between `simulate_disconnect()` and
`clock.advance(...)`, or the transport's idle timer is still pending and `advance`
fires it before the disconnect is processed.

**6. Do not install `FakeClock` for heartbeat or `maxIdleInterval` tests.**
`on_idle_timer_expire` compares `unix_time_ms()` (the real wall clock) against
`max_idle_interval` but schedules through the timer seam, so advancing fires the idle
timer while no real time has passed and it reschedules itself forever. Drive those with
a small `maxIdleInterval` in `connected_message(...)`, on real time. For every *other*
`FakeClock` test, connect with `CONNECTED_MESSAGE_NO_IDLE`.

**7. `ping()`'s timeout is real loop time, not the seam.**
`connectionmanager.py:375` is `asyncio.wait_for(pending_ping.future, timeout)`, so
`advance()` will not move it. Use a short real `realtime_request_timeout`.

**8. `clock.settle()` is twenty event-loop yields, not true quiescence.** The
disconnect path chains `create_task` several levels deep. If a derived test shows a
timer scheduled one interval off, raise `FakeClock(settle_passes=...)` before
suspecting the library.

**9. Send DISCONNECTED with a `statusCode`.** `on_disconnected` compares
`exception.status_code >= 500` unguarded, so a DISCONNECTED without one raises
`TypeError` in a task whose exception is only logged, and the test hangs with no clue.
The template has one.

**10. A refused connection and a connect timeout are indistinguishable, and skip the
fallback loop.** `ws_connect` catches only `WebSocketException` and `socket.gaierror`,
so `ConnectionRefusedError` and `asyncio.TimeoutError` never reach `_emit('failed')`:
the attempt hangs until the transition timer fires with a generic 50003/504, and each
one leaks a `connect_base` task. `respond_with_dns_error()` is the only fast, caught
failure — 40000/400 with the real cause — so **prefer it** whenever you just need "the
connect failed", and note the substitution at the site. Keep
`realtime_request_timeout` short in any test that does wait a refusal out.

**11. Keep the fallback hosts empty** unless the spec is about them.
`check_connection()` is a module-level, **synchronous** `httpx.get` that no seam
reaches, so it blocks the event loop and goes to the real internet, once per host. A
test that must exercise the fallback loop has to `monkeypatch`
`ably.realtime.connectionmanager.httpx.get`.

**12. Do not register one listener function for two events.** `EventEmitter` keys its
wrapper registry on the listener alone, so the second registration overwrites the
first and `off` for the first event raises `KeyError`. Use a separate `def` per event.
Relatedly, `connection.on(state, states.append)` raises
`ValueError: EventEmitter.on(): invalid args` — a bound built-in is not accepted, so
every listener must be a `def`.

**13. Never name an attribute the channel collection does not define, and never use
`hasattr` on it.** `Channels.__getattr__` answers any unknown attribute with
`self.get(name)`, so probing it **creates a channel** and mutates what you are
measuring.

**14. A publish hangs without an ACK.** `RealtimeChannel.publish()` is
`await send_protocol_message(...)` under RTL6b, and PRESENCE, ANNOTATION and OBJECT are
`ack_required` too. Most specifications write the publish un-awaited and never ACK:
read that as a promise the spec is eliding and **add the ACK** with `ack(msg)`, unless
the spec says in as many words not to — then drive the publish as a task. State which
you did in the module docstring.

**15. Give every PresenceMessage an explicit `connId:serial:index` id.** A missing id
becomes the literal string `"None:0"`, which does not start with the member's
`connectionId`, so `is_synthesized()` returns True and the newness check silently takes
the RTP2b1 timestamp path instead of the RTP2b2 msgSerial path. The test then passes
while exercising the opposite branch from the one it names.

**16. A server-sent CLOSED does nothing.** `on_closed` disposes the transport without
notifying a state, so the connection stays CONNECTED. CLOSED is reached only through
`client.close()`. Similarly, after `send_to_client_and_close()` the mock leaves
`active_connection` set, so a later `send_to_client` injects into a dead connection and
is silently swallowed rather than raising.

**17. A spec's `mock_ws.active_connection.close()` means the *server* closing.**
Translate it to `simulate_disconnect()`. `MockConnection.close()` is the library's own
side.

**18. `connection.id` does not exist**, nor `connection.key`. Read
`client.connection.connection_manager.connection_id` and
`client.connection.connection_details.connection_key`.
`client.connection.connection_details` and `connection.error_reason` **are** public.

**19. Two noisy-but-harmless teardown messages.** `Task exception was never retrieved`
for a client whose connect failed — `WebSocketTransport.send` raises a bare
`Exception()` when `self.websocket is None`. And `Task was destroyed but it is
pending!`, one per refused attempt, which is trap 10's leak showing. Neither is a
failure; do not chase them.

**20. A channel needs a SUSPENDED *connection* to reach SUSPENDED.**
`_propagate_connection_interruption` fires only for CLOSING/CLOSED/FAILED/SUSPENDED, so
a bare `simulate_disconnect()` leaves the channel ATTACHED. And RTL4f's channel attach
timeout and the connection's transition timeout are the **same option** (TO3l11), so a
test that needs the connection to suspend before the channel does must set
`realtime_request_timeout` very high.

**21. `presence.subscribe()` and `annotations.subscribe()` are coroutines that
attach.** They must be awaited, and they cannot run before `connect()`. `unsubscribe()`
is not a coroutine. Presence event names are the lowercase action names from
`PresenceAction._action_name`, which is monkey-patched onto `PresenceAction` at the
bottom of `presence.py` and exists only once that module is imported.

**22. `RecordedUrl` cannot survive a URL httpx rejects.** `httpx.URL` caps at 64 KiB
and raises inside `PendingConnection.__init__` **before** the attempt is recorded, so
the failure is invisible in `events`, `handler_errors` is empty, and the client hangs
in CONNECTING. Only matters if a spec drives an oversized query parameter.

**23. A single `await settle()` after `send_to_client(...)` is provably enough** for
message delivery, so `poll_until(positive); await settle(); assert negative` is a sound
pattern for "and nothing else arrived".

**24. RTN23b ping-frame and RTN23c1 PING/PONG tests are unimplementable.** The SDK has
no ping/pong handling and sends no `heartbeats` query parameter; the `websockets`
library answers pings inside the protocol and surfaces no event. Record as a Mock
Infrastructure Limitation. RTN23a via `send_to_client(HEARTBEAT_MESSAGE)` works.

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

**A missing public accessor is adapted, never gated.** Where the behaviour is right
and only the public member is absent — `Connection#id`, `RealtimeChannel#properties`,
`ChannelStateChange#event` — assert the equivalent observable however internal it is,
define a reader at the top of the file so the adaptation is in one place, and record
the missing API in its own entry. Gating would take real behavioural coverage out of
the run indefinitely over a question of spelling. `test/uts/deviations.md` has the
ruling in full.

**Group by root cause, not by test or by spec file.** Five tests failing for one
reason are one entry naming all five. If you are deriving one area of a larger effort,
check whether a neighbouring area has already recorded your finding before writing it
up again — three of the realtime defects were reported two or three times over.

**Record a refuted claim too.** If you investigate something that looks like a defect
and it turns out the SDK is right, put it under *Investigated and not defects* with
the reasoning. The next reader will otherwise reach the same first conclusion.

## Checks

```bash
uv run --frozen --extra crypto --extra dev ruff check ably/ test/
uv run --frozen --extra crypto --extra dev pytest test/uts -q
RUN_DEVIATIONS=1 uv run --frozen --extra crypto --extra dev pytest test/uts -q
```

`--frozen` is required — without it dependency resolution reaches past the
environment's cutoff — and `--extra dev` carries pytest. Line length is 115. If
`uv.lock` changes, `git checkout -- uv.lock`.

The first two must pass. The third is the check that the deviations record is still
true: **every gated test must fail when enabled**, so gated + unimplementable under the
third run must equal the skip count under the second, and nothing may pass under both
behaviours. The expected counts are in the header of `test/uts/deviations.md`; update
them from a measured run rather than copying them forward.
