---
description: Translate Universal Test Specifications from ably/specification into ably-python tests. Use when deriving, updating or evaluating tests under test/uts.
allowed-tools: Bash, Read, Edit, Write, WebFetch
---

# Translating UTS specs into ably-python tests

## Sources

Fetch the governing doc and the spec fresh at the start of every run; do not work from
memory.

```bash
gh api repos/ably/specification/contents/uts/docs/writing-derived-tests.md --jq '.content' | base64 -d
gh api repos/ably/specification/contents/uts/docs/integration-testing.md --jq '.content' | base64 -d
gh api repos/ably/specification/contents/uts/rest/unit/<spec>.md --jq '.content' | base64 -d
gh api repos/ably/specification/contents/uts/realtime/unit/<spec>.md --jq '.content' | base64 -d
gh api repos/ably/specification/contents/uts/rest/integration/<spec>.md --jq '.content' | base64 -d
gh api repos/ably/specification/contents/uts/docs/proxy.md --jq '.content' | base64 -d
gh api repos/ably/specification/contents/uts/rest/integration/proxy/<spec>.md --jq '.content' | base64 -d
```

`writing-derived-tests.md` governs, and `integration-testing.md` alongside it for
`uts/rest/integration`, with `proxy.md` governing the proxy package within it. This
file covers only what is particular to ably-python.

## Layout

A spec at `uts/<tier path>/<name>.md` becomes `test/uts/<tier path>/<name>_test.py`, so
`uts/rest/unit/auth/token_renewal.md` becomes `test/uts/rest/unit/auth/token_renewal_test.py`
and `uts/rest/integration/history.md` becomes `test/uts/rest/integration/history_test.py`.
Every directory needs an `__init__.py`, as `test` is a package.

There are two kinds of tier. `rest/unit` and `realtime/unit` serve every request from a
mock and reach no network; `rest/integration` and `realtime/integration` run against the
real Ably sandbox and have no mock at all. See **The integration tier** below.

`test/uts/rest/unit/time_test.py` is the reference example for REST unit,
`test/uts/realtime/unit/connection/auto_connect_test.py` for realtime unit,
`test/uts/rest/integration/history_test.py` for REST integration and
`test/uts/realtime/integration/channels/channel_publish_test.py` for realtime
integration — two clients, protocol variants, a state wait and a `connection_id` reader,
which is most of what a realtime integration module needs. Follow their shape.

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
| `Rest(ClientOptions(key: api_key, endpoint: "nonprod:sandbox"))` | `sandbox_rest_client(key)`; `sandbox_realtime_client(key)` for realtime |
| `app_config.keys[i]` / `BEFORE ALL TESTS` app setup | the `sandbox` fixture and `sandbox.key(i)` |
| `poll_until(interval: 500ms, timeout: 10s)` in an integration spec | `await wall_clock_poll_until(condition, description='...')`, **not** `poll_until` |

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

## The integration tier

`uts/rest/integration/<name>.md` becomes `test/uts/rest/integration/<name>_test.py`, and
`uts/realtime/integration/<name>.md` becomes
`test/uts/realtime/integration/<name>_test.py`. Both run against the real Ably sandbox —
twelve REST specifications, 84 tests, and twenty realtime ones, 73 tests, each tier with a
proxy package the section below covers. There is no mock and no `test_options`: the
client reaches the network. `test/uts/README.md` covers the same ground for someone
reading the suite; this is what someone writing a test needs.

What differs from the mock-backed tiers:

- **Nothing sits in front of the client.** No `install_mock`, no captured request to
  assert on, no way to make the server answer a chosen way. A spec point that can only
  be shown through a stubbed response belongs in the unit tier.
- **One sandbox app serves each tier**, standing in for `BEFORE ALL TESTS` — `sandbox`
  for REST, `realtime_sandbox` for realtime, provisioned separately so that neither
  tier's channels, presence members or devices are visible to the other. Within a tier
  the app is shared, so every channel name, client id and device id takes a
  `random_id()` suffix, and anything a test registers it removes in a `finally`.
- **Waits are wall-clock**, the inverse of the unit tier's rule. See Timers below.
- **The per-test timeout is 120 seconds**, set by the package's own `conftest.py`, not
  the 30 `pyproject.toml` gives the rest of the suite.

| Name | Is |
|---|---|
| `sandbox` fixture, in `rest/integration/conftest.py` | a specification's `app_config`. Session-scoped: provisioned once from the vendored `assets/test-app-setup.json` and deleted afterwards |
| `realtime_sandbox` fixture, in `realtime/integration/conftest.py` | the same for the realtime tier, and a separate app. Same `key(i)`, `key_str` and `app_id` |
| `sandbox.key(i)` | `app_config.keys[i]`, carrying `key_str`, `key_name`, `key_secret` and `capability`. The index means what it means in a spec — 0 full access, 1 push admin, 2 per-channel capabilities, 3 subscribe-only, 4 revocable tokens. `sandbox.key_str` (the full-access key) and `sandbox.app_id` are shorthands |
| `use_binary_protocol` fixture | runs the test once per protocol; each tier's `conftest.py` defines its own. **Only a spec carrying a `## Protocol Variants` section takes it** — in REST `publish`, `history`, `presence`, `batch_presence`, `mutable_messages`; in realtime `channel_history`, `channels/channel_publish`, `delta_decoding`, `mutable_messages`, `presence_lifecycle`. A test that does not take it runs json only, which is the clients' default here |
| `await_connection_state(client, state, timeout=5)`, `await_channel_state(channel, state, timeout=5)` | the specifications' `AWAIT_STATE`. Pass `timeout=10` in this tier: five is the budget a mock-backed test needs, and `channel_history_test.md` spells out ten for a connect that opens a real socket |
| `sandbox_rest_client(key=None, **kwargs)` | `Rest(ClientOptions(key: api_key, endpoint: "nonprod:sandbox"))`. Registered for the same teardown as `rest_client`. Leave `key` out and pass `token=`, `auth_callback=` or `auth_url=` where the spec authenticates some other way |
| `sandbox_realtime_client(key=None, **kwargs)` | the same for realtime, for the REST specs that need presence members or presence history a connection has to produce. Unlike `realtime_client` it keeps `auto_connect` and the fallback hosts at the **library** defaults |
| `wall_clock_poll_until(condition, timeout=10.0, description='condition', interval=0.5)` | this tier's `poll_until`. Sleeps `interval` between attempts, takes a sync or async condition, and **returns whatever the condition answered with**, so a condition that fetches a page saves fetching it again |
| `random_id(length=6)` | the specifications' `random_id()`, url-safe base64 over `secrets` bytes |
| `fixture_cipher_params()` | the `CipherParams` the app setup encrypted the `client_encoded` presence fixture with. The asset holds key and IV base64; this decodes them |
| `PRESENCE_FIXTURES_CHANNEL` | `'persisted:presence_fixtures'`, the channel the app setup pre-populates with members the presence specs read rather than write |
| `generate_jwt(key_name, key_secret, ttl=3600000, client_id=None, capability=None, expires_at=None)` | the auth specification's `generate_jwt`. Signed HS256 here rather than pulling in a JWT library the locked environment does not carry |
| `extract_key_name(api_key)` / `extract_key_secret(api_key)` | the two halves of `app_id.key_id:secret` |

`sandbox_rest_client` and `sandbox_realtime_client` are in `test.uts.helpers.client`
alongside the mock-backed constructors; everything else is in `test.uts.helpers.sandbox`.

```python
# UTS: rest/integration/RSL2a/history-returns-messages-0
async def test_rsl2a_history_returns_messages(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)
    channel = client.channels.get('history-test-RSL2a-' + random_id())

    await channel.publish(name='event1', data='data1')

    async def one_message():
        page = await channel.history()
        return page if len(page.items) == 1 else None

    history = await wall_clock_poll_until(one_message, description='the message to reach history')
```

## The proxy tier

`uts/rest/integration/proxy/<name>.md` becomes
`test/uts/rest/integration/proxy/<name>_test.py` and `uts/realtime/integration/proxy/<name>.md`
becomes `test/uts/realtime/integration/proxy/<name>_test.py`, and each routes its traffic through
[ably/uts-proxy](https://github.com/ably/uts-proxy) on the way to the sandbox. The
proxy binds a port per session, takes plain HTTP on it, speaks TLS onwards, applies the
session's rules and records what crosses it. `uts/docs/proxy.md` governs the tier and
is worth reading in full before deriving one of these; fetch it the same way as the
other governing docs.

What differs from the rest of the integration tier:

- **The client points at the session, not at the sandbox.** `endpoint='localhost'`,
  `port=session.proxy_port`, `tls=False`, `use_binary_protocol=False`. `endpoint` and
  `port` set the primary host, and `fallback_hosts=['localhost']` sets the fallback to
  the same session, so both attempts land in one event log. Leave `fallback_hosts` out
  where the spec does: `endpoint='localhost'` disables fallbacks by itself (REC2c2). A
  realtime client takes the same four and adds `auto_connect=False`, so that a state
  recorder can be registered before the connection opens.
- **The event log's field names are the proxy's, not the specification's.** `ws_connect`
  carries `queryParams`. `ws_frame` carries `direction` — `server_to_client` or
  `client_to_server` — a `message` whose `action` is an **integer**, and `ruleMatched`
  holding the rule's `comment` string verbatim. `ws_disconnect` carries `initiator`. A
  `replace`d frame is logged as the frame the server sent, not as the replacement, and a
  `suppress`ed frame is logged too, so both are still countable. An imperative
  `trigger_action` appears as an `action` event followed by the `ws_frame` it produced.
  A specification writing `e.type == "ws_frame_to_server"` or `action == "MESSAGE"` is
  reading fields that do not exist: derive against the real names, through a filter
  defined once at the top of the file, and record the drift in `deviations.md`.
- **Authentication is a callback.** A plain connection cannot carry basic auth, so
  every client takes `auth_callback=`; see the traps below.
- **A fault is a rule, and everything else passes through.** `times: 1` faults the
  first request that matches and lets the retry reach the sandbox, which is the shape
  every fallback scenario wants.
- **The proxy is the second witness.** The SDK's own result answers half the question
  and `session.get_log()` the other half — how many requests were made, in what order,
  and what the proxy answered them with.
- **The per-test timeout is 300 seconds**, set by the package's own `conftest.py`.

| Name | Is |
|---|---|
| `proxy_session` fixture, in `rest/integration/proxy/conftest.py` | a specification's `create_proxy_session(...)`, together with its `AFTER EACH TEST: session.close()`. `session = await proxy_session(rules=[...])`, as many times as a test needs, and every session is closed afterwards |
| `proxy_control` fixture | the running control API, session-scoped. `proxy_session` asks for it, so a test does not have to |
| `create_proxy_session(endpoint=SANDBOX_ENDPOINT, port=None, rules=None, timeout_ms=SESSION_TIMEOUT_MS)` | the function itself, in `test.uts.helpers.proxy`, for the rare case that wants a session the fixture will not close |
| `session.session_id`, `session.proxy_host`, `session.proxy_port` | what a spec reads off its `session`. The host is always `localhost` |
| `session.add_rules(rules, position='append')` | rules added while the session runs. `position='prepend'` puts them ahead of the ones already there, which is how a spec faults traffic only once the client has reached some state |
| `session.trigger_action(action)` | the imperative half — `{'type': 'disconnect'}`, `{'type': 'close', 'closeCode': 1000}`, `inject_to_client`. 409 from the control API when no connection is open |
| `session.get_log()` | every event, in order, as the dictionaries the control API sends: `type`, `method`, `path`, `status`, `direction`, `queryParams`, `message`, `ruleMatched`. The field names are the ones a specification's assertions are written against, so they are not renamed |
| `session.close()` | best effort and never raises; the fixture calls it for you |
| `ensure_proxy()` / `stop_proxy()` | start the control process and reap it. Only the `proxy_control` fixture should need them |
| `PROXY_VERSION`, `ARCHIVE_CHECKSUMS`, `RELEASE_URL` | the pinned release and the sha256 of each platform's archive. Moving the pin means new checksums, copied from the release's own `checksums.txt` |
| `SESSION_TIMEOUT_MS` (120000) | the session's **idle** auto-cleanup timer, passed as `timeoutMs` |
| `SUITE_TIMEOUT` (300) in the package `conftest.py` | the per-test timeout for this package |
| `UTS_PROXY_LOCAL_PATH` | a locally built binary, or a `.tar.gz` holding one, in place of the pinned release |
| `UTS_PROXY_CONTROL_URL` | a control API already running, which is then neither started nor stopped by the suite |

Everything but the two fixtures is in `test.uts.helpers.proxy`. `http_requests` and
`http_responses` in the example below are the derived file's own log filters, defined
at the top of it, because every test in the file reads the log the same two ways.

```python
# UTS: rest/proxy/RSC15l4/cloudfront-header-fallback-0
async def test_rsc15l4_cloudfront_header_fallback(sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'http_request', 'pathContains': '/time'},
        'action': {
            'type': 'http_respond',
            'status': 403,
            'body': {'error': {'message': 'Forbidden', 'code': 40300, 'statusCode': 403}},
            'headers': {'Server': 'CloudFront'},
        },
        'times': 1,
        'comment': 'RSC15l4: CloudFront 403 on first /time request',
    }])

    client = sandbox_rest_client(
        auth_callback=token_auth_callback(sandbox.key_str),
        endpoint='localhost',
        fallback_hosts=['localhost'],
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
    )

    result = await client.time()
    assert isinstance(result, (int, float))

    log = await session.get_log()
    assert len(http_requests(log, '/time')) >= 2
    assert http_responses(log)[0]['status'] == 403
```

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

## Traps found while deriving the REST integration specs

Each was established by measurement against the sandbox. Most of them produce a test
that **passes while proving nothing**, rather than one that fails.

- **Push admin filter parameters must be camelCase, and the server drops an
  unrecognised query parameter rather than rejecting it.** Measured against one app:
  `device_registrations.list(clientId=x)` returned 2, `list(client_id=x)` returned 3,
  and the unfiltered list returned 3 — the snake_case filter was silently the whole
  page. A test that asserts only that the row it just created is present therefore
  passes with the filter doing nothing, so **a filtered list needs a control proving it
  narrowed**: a decoy row under another id, or an unfiltered count to compare against.
  The cause is that `list`, `list_channels` and `DeviceRegistrations.remove_where` hand
  their dict to `format_params` positionally, and `format_params` camel-cases only its
  own `**kw` (`ably/http/paginatedresult.py:18`).
  `PushChannelSubscriptions.remove_where` is the one call that spreads
  (`format_params(**params)`), so it does accept snake_case — do not generalise from it.
- **A `PaginatedResult` is always truthy and defines no `__len__`.** So a poll
  condition that answers with the page straight from `history()` or `list()` is
  satisfied by the first empty one and the assertions then run against nothing. Return
  `None` until the page holds what is wanted, and read `len(page.items)`. `has_next()`
  is a method too, and a bound method is truthy whatever the page holds.
- **Nothing is consistent immediately after a write.** History and presence lag a
  publish or an enter, and device deletion is asynchronous — `remove_where` answers 204
  while the rows are still listed. Any count that follows a write goes through
  `wall_clock_poll_until`; a fixed sleep either flakes or spends the budget.
- **`Message.timestamp` is a raw int of milliseconds, `PresenceMessage.timestamp` is a
  `datetime`.** `PresenceMessage.from_dict` converts and `Message` does not, so a
  history time boundary is integer arithmetic, a presence one is not, and comparing the
  two raises. Derive a boundary from server-assigned timestamps rather than from a
  client-side `now()`, which can land inside the same millisecond as the messages.
- **A channel captures its cipher and its protocol when it is constructed**, and
  `Channels.get` caches by name. A cipher passed on a later `get` reaches
  `channel.cipher` but never `channel.presence`, which snapshotted it in
  `Presence.__init__` (`ably/types/presence.py:207`). Pass the cipher on the **first**
  `get` for that client.
- **A fresh sandbox app has no stats.** A spec guarding its assertions on there being
  stats to read is vacuous against a new app — the guarded branch never runs and the
  test asserts nothing. Inject an interval first through the sandbox's own
  `POST /stats`, as `time_stats_test.py`'s `app_with_stats` fixture does.
- **An Ably JWT's lifetime is read as `exp - iat`, and a negative one is rejected 40003
  before expiry is ever considered.** An already-expired JWT cannot be made by leaving
  `iat` at now and putting `exp` in the past; that is a malformed token, not an expired
  one, and a renewal test would be exercising the wrong rejection. `generate_jwt`
  backdates `iat` by `ttl` when given `expires_at`, for exactly this.
- **`enter_client` fails on an anonymous connection.** The server answers basic auth
  with `clientId: "*"`, `Auth._configure_client_id` records that as validated while
  leaving the client id `None` (`ably/rest/auth.py:335`), and `can_assume_client_id`
  then refuses every id with 40012. Pass `client_id='*'` to `sandbox_realtime_client`.
  Await CONNECTED before entering, too — an enter on a CONNECTING connection is queued.
- **Waits here are wall-clock, the inverse of the unit tier's rule.** `poll_until`
  yields to the event loop, which against a real server spins a core on a network wait.
  Use `wall_clock_poll_until`, and no `FakeClock`. `writing-derived-tests.md` has a
  section on this ("Integration timeouts are wall-clock").

## Traps found while deriving the proxy tier

Established against the real proxy and the real sandbox while deriving
`rest/integration/proxy/rest_fallback.md`.

- **Basic auth cannot be used through the proxy at all.** The session speaks plain
  HTTP, and `tls=False` makes the SDK raise `40103 "Cannot use Basic Auth over non-TLS
  connections"` (RSC18) before a request is written, so a client built with `key=`
  never reaches a rule. `client.time()` is the one call that works, because it is
  `skip_auth`. Every test in the specification therefore authenticates with
  `authCallback`, including the `/time` ones, and a derived test should keep that even
  where it looks unnecessary.
- **The token callback's own client must go straight to the sandbox.** A callback that
  asks for a token through a client pointed at the session puts a request in front of
  the waiting rule and an extra `http_request` in the log, which breaks every
  assertion that counts requests exactly (`== 1` for RSC15l's 4xx test, `>= 2` for the
  fallback ones). Build an inner `AblyRest(key=api_key, endpoint=SANDBOX_ENDPOINT)`,
  request the token through that, and close it.
- **`http_response` events carry no `path`.** They have `status` and `ruleMatched`
  only, so "the injected response fired" is read off the response events **in order**
  — `http_responses(log)[0]['status'] == 403` — rather than by filtering to an
  endpoint. `http_request` events do carry `method` and `path`. A rule with no
  `comment` appears as `ruleMatched: "rule-0"`.
- **The parent package's timeout marker wins unless the subpackage prepends its
  own.** `pytest-timeout` reads the first of an item's own markers, and
  `rest/integration/conftest.py` marks everything beneath it with 120 seconds. The
  proxy package's `pytest_collection_modifyitems` adds its 300 with
  `append=False`; without that the marker order decides the timeout and a test that
  waits out a twenty-second delay on a cold cache is cut off. Anyone adding a further
  sub-tier under `test/uts/rest/integration/` hits this.
- **A session-scoped async fixture runs on a different event loop from the tests.**
  pytest-asyncio 0.23 gives the session fixture its own loop, so an object bound to
  the loop that created it — an `httpx.AsyncClient`, say — must not be held across the
  yield: reusing it from a test raises `RuntimeError: Event loop is closed` or attaches
  to the wrong loop. `helpers/proxy.py` opens a client per control call for exactly
  this reason, the way `sandbox.py` does.
- **The session's `timeoutMs` is an idle timer, not a deadline.** The proxy's default
  is 30000, measured from the last traffic through the session, and a test that has
  the proxy delay a response by twenty seconds and then reads the log spends longer
  than that idle, which is long enough for the session to be collected out from under
  the test. The harness passes 120000.
- **Every request the test's client makes lands in the same log.** The log is
  per-session, not per-endpoint, so a verification step that reads history through the
  same client adds its own `http_request` events. In `RSL1k4` the log is read
  **before** the history call, and the history read is a `wall_clock_poll_until` rather
  than a single fetch, because a published message does not reach history at once.
- **`httpRequestTimeout` is milliseconds in the specification and seconds in
  ably-python.** `ably/http/http.py:193` hands `(http_open_timeout,
  http_request_timeout)` to `httpx`, which reads seconds, so the specification's
  `http_request_timeout=3000` is a 3000-second deadline: measured, the request sat out
  the proxy's whole 20-second delay and then succeeded on the primary host, and no
  fallback was attempted. Passing `3` makes the same test pass in 3.1s, so only the
  unit is wrong. The test is written as the specification has it and gated with
  `@deviation`; `test/uts/deviations.md` carries the entry.

## Traps found while deriving the realtime integration tier

Each was established against the sandbox, or against the sandbox behind `uts-proxy`.

- **`RealtimeChannel.publish()` takes name and data positionally only.**
  `publish(name='x', data='y')` raises `ValueError: publish() expects either (name, data)
  or a message object or array of messages` before anything reaches the server
  (`ably/realtime/channel.py:394`), where `RestChannel.publish()` accepts the keyword
  form. The specifications write the keyword form throughout, so every realtime publish
  is translated positionally.
- **A binary payload comes back as `bytearray`, not `bytes`**, under both protocols. It
  compares equal to the `bytes` that was published, so only the type assertion is
  affected: `ASSERT data IS Binary` has to read `isinstance(data, (bytes, bytearray))`.
- **DISCONNECTED is transient after a drop from CONNECTED.** The retry is a
  `loop.call_soon`, not a timer, so DISCONNECTED and CONNECTING land in the same
  millisecond and `await_connection_state(client, DISCONNECTED)` is a coin toss. Register
  a `connection.on(...)` recorder before connecting and wait on the recorded list, which
  is also what a specification reading `state_changes` wants.
- **An `AWAIT_STATE` for a state the channel already holds asserts nothing** — it returns
  at once. `channel_faults.md`'s RTL13a and RTL3d both re-attach an already-attached
  channel, so both are taken on the recorded sequence instead: ATTACHING followed by
  ATTACHED, which is what their `CONTAINS_IN_ORDER` assertion checks anyway.
- **`refuse_connection` through the proxy is a caught failure**, unlike the mock tier's
  `respond_with_refused`. The proxy answers the upgrade with HTTP 502, `websockets`
  raises, and the SDK reports `40000/400 'Error opening websocket connection: server
  rejected WebSocket connection: HTTP 502'` at once. No timeout shortening is needed.
- **`realtime_request_timeout` is milliseconds at the client option**, and `Timer`
  divides by 1000, so a specification's `realtimeRequestTimeout: 3000` maps straight
  across. That is the opposite of `http_request_timeout`, which the REST proxy tier found
  is applied as seconds; the defect does not generalise, so do not carry it over.
- **The proxy's event timestamps are RFC 3339 with a variable number of fractional
  digits.** Comparing them as strings is wrong, and `datetime.fromisoformat` will not
  take the trailing `Z` on Python 3.9. Order the log by position rather than by timestamp
  wherever that will do.
- **A locally signed Ably JWT is the cheapest credential for a proxy test.** It costs no
  round trip, so nothing extra lands in the event log beside the frames a test counts.
  `test/uts/helpers/sandbox.py`'s `generate_jwt` signs one, and each proxy module wraps it
  in a small `jwt_auth_callback` of its own.
- **`wall_clock_poll_until`'s `description` is evaluated eagerly**, so it cannot report
  state a test accumulated while waiting. `connection_resume_test.py` wraps it to re-raise
  with the recorded states appended, which is what makes its timeouts self-explanatory;
  copy that wherever the wait is on a state machine.
- **Server-initiated reauth is fully implemented.** Injecting `{'action': 17}` on a live
  connection re-invokes the authCallback, leaves the state CONNECTED and the connectionId
  unchanged, and the sandbox answers with a second CONNECTED — frame actions `[4, 17, 4]`.
  A test written expecting a disturbance will not find one.
- **`close` and `disconnect` are indistinguishable to the client.** Both give
  CONNECTING → CONNECTED → DISCONNECTED → CONNECTING → CONNECTED in about 1.2 s.
  `disconnect` leaves `error_reason` set to "no close frame received or sent" and `close`
  leaves it `None`, which is the only way to tell them apart from inside the SDK.

## Timers

Three regimes; pick by tier.

**REST unit.** No clock seam reaches it: `TestOptions(timer=...)` is read by the
realtime connection alone, and `ably/http/http.py` calls `time.time()` directly. Where
a REST spec calls `enable_fake_timers()` / `ADVANCE_TIME(ms)`, drive it with short real
timeouts through client options (`fallback_retry_timeout=100`), which is what the specs
themselves do.

**Realtime unit.** The `timer` seam exists, and `realtime_client(mock, clock=clock)`
installs a `FakeClock` on it. Still prefer a short real interval through a client option
(`realtime_request_timeout`, `disconnected_retry_timeout`, `suspended_retry_timeout`,
`channel_retry_timeout`) or through `connected_message(maxIdleInterval=...)`, and reach
for `FakeClock` only for `connection_state_ttl`, which no option sets and whose default
costs 120 real seconds. See the fake-time section of `test/uts/deviations.md`.

**Integration, REST and realtime.** Real time, deliberately. There is no seam to install
in front of a server the tests exist to talk to, and shortening a timeout would only make
the tier flaky. Poll with `wall_clock_poll_until` rather than sleeping a guess, and wait on
states with `await_connection_state` / `await_channel_state`. Where a specification sets
`realtimeRequestTimeout`, `disconnectedRetryTimeout` or `suspendedRetryTimeout`, pass it
through as the client option of the same name: those drive real timers against a real
server, and they are milliseconds on both sides.

The pytest timeout is 30 seconds for the suite, 120 for each integration tier and 300 for
the `proxy` package inside each, so keep waits well under whichever applies.

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
uv run --frozen --extra crypto --extra dev pytest test/uts/rest/unit test/uts/realtime/unit test/uts/helpers -q
uv run --frozen --extra crypto --extra dev pytest test/uts/rest/integration test/uts/realtime/integration -q
RUN_DEVIATIONS=1 uv run --frozen --extra crypto --extra dev pytest test/uts -q
```

`--frozen` is required — without it dependency resolution reaches past the
environment's cutoff — and `--extra dev` carries pytest. Line length is 115. If
`uv.lock` changes, `git checkout -- uv.lock`.

The second command is the offline tiers, which need no network. The third is the two
integration tiers, each of which provisions a sandbox app of its own and does need the
network; `pytest test/uts -q` runs everything together, so run the tiers separately when
only one is in question. All three must pass.

The fourth is the check that the deviations record is still true, across both tiers:
**every gated test must fail when enabled**, so gated + unimplementable under it must
equal the skip count under the other runs, and nothing may pass under both behaviours.
It reaches the network for the same reason the third does. The expected counts are in
the header of the deviations record; update them from a measured run rather than
copying them forward.
