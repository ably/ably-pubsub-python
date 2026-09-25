# Universal Test Specifications

Tests here are derived from the pseudocode specifications in the
[ably/specification](https://github.com/ably/specification) repository under `uts/`.
They are mechanical translations: each one names the spec point it covers and
carries a `# UTS: <id>` comment identifying the specification it came from.

Read `uts/docs/writing-derived-tests.md` in the specification repository before
adding or changing tests here, alongside `.claude/skills/uts-to-python/SKILL.md`,
which covers what is particular to this SDK and lists every helper below.

Record anything that departs from a specification in [deviations.md](deviations.md),
which also covers the faults found in the specifications themselves and raised
upstream, and the choices behind how the specifications are adopted here.

## Layout

```
helpers/     shared infrastructure the specifications assume, and its own tests
assets/      fixtures the specifications name, vendored from elsewhere
rest/        specifications under uts/rest
realtime/    specifications under uts/realtime
```

Every directory holding tests needs an `__init__.py`, because `test` is a package.

Unit tests serve every request from a mock and reach no network — neither the REST
suite nor the realtime one. Integration tests run against a sandbox app.

## Installing the mocks

The specifications express mock installation as a global `install_mock(mock_http)`.
Here a mock is passed to the client it serves, through `TestOptions`. There are three
seams, all client-scoped; [deviations.md](deviations.md) says why.

```python
mock_http = MockHttpClient(
    on_connection_attempt=lambda conn: conn.respond_with_success(),
    on_request=lambda req: req.respond_with(200, {'result': 'ok'}),
)
ably = AblyRest(key=key, test_options=TestOptions(http_transport=mock_http.as_transport()))
```

A realtime client takes its websocket mock the same way, through
`TestOptions(websocket_connect=...)`, and its timers through `TestOptions(timer=...)`:

```python
mock_ws = MockWebSocket(
    on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
)
ably = AblyRealtime(key=key, auto_connect=False,
                    test_options=TestOptions(websocket_connect=mock_ws.as_connect(),
                                             timer=FakeClock().timer))
```

`rest_client(mock_http, ...)` and `realtime_client(mock_ws, ...)` in
[helpers/client.py](helpers/client.py) wrap all three, defaulting the credentials
and registering the client for teardown:

```python
realtime_client(mock_websocket=None, mock_http=None, clock=None, **kwargs)
```

`mock_http=` gives a realtime client an HTTP mock for the specifications that drive
REST over a realtime client; `clock=` installs a `FakeClock`. `realtime_client`
defaults `auto_connect` to **false** and `fallback_hosts` to **empty** — both
deliberate, and both explained in [deviations.md](deviations.md).

The client builds its HTTP client once and reads its websocket hook once, so
construct the mocks first. Teardown is automatic: `conftest.py` closes every
registered client after each test, which stands in for `uninstall_mock()`. **Do not
close clients in a test** — the fixture survives every connection state, and a test
that closes its own leaves nothing to clean up if it fails first.

## What the helpers offer

| Module | Holds |
|---|---|
| [helpers/mock_http.py](helpers/mock_http.py) | `MockHttpClient`, matching `uts/rest/unit/helpers/mock_http.md`, including the superseded `queue_*` family |
| [helpers/mock_websocket.py](helpers/mock_websocket.py) | `MockWebSocket`, matching `uts/realtime/unit/helpers/mock_websocket.md`, plus the protocol-message templates and builders the specifications assume |
| [helpers/client.py](helpers/client.py) | client constructors, and the `AWAIT_STATE` / `AWAIT UNTIL` equivalents |
| [helpers/clock.py](helpers/clock.py) | `FakeClock`, `settle()` and `advance_to_connection_state()` — `enable_fake_timers()` and `ADVANCE_TIME(ms)` |
| [helpers/presence.py](helpers/presence.py) | the presence-map stubs and wire-message builders the presence specifications share |
| [helpers/sandbox.py](helpers/sandbox.py) | the sandbox app the integration tier provisions, the presence-fixture cipher, `random_id()` and the JWT signing the auth specification asks a library for |
| [helpers/deviations.py](helpers/deviations.py) | the `@deviation` and `@spec_error` gates |

`SKILL.md` lists every name in each. The helpers have their own tests
(`helpers/*_test.py`), which are not derived from a specification and are not counted
in the derived-test totals.

## The integration tier

`rest/integration/` runs against the real Ably sandbox, so it needs network access;
nothing there is served from a mock. Each specification's `BEFORE ALL TESTS` block
provisions an app from the canonical `test-resources/test-app-setup.json` in
[ably/ably-common](https://github.com/ably/ably-common), vendored at
[assets/test-app-setup.json](assets/test-app-setup.json), and deletes it afterwards.
One app serves the whole session, since an app per test would be slow and would invite
the sandbox's rate limiting. Provisioning goes over plain `httpx` rather than through
`AblyRest`: it is infrastructure, and a client that cannot form a request should fail a
test rather than look like a broken fixture. Teardown is best effort — a sandbox app
expires on its own, so a failed delete is logged and nothing more.

The app arrives as the `sandbox` fixture, which is a specification's `app_config`:

```python
async def test_rsl1n_publish_returns_serials(sandbox):
    channel = sandbox_rest_client(sandbox.key(0).key_str).channels.get('test-serials-' + random_id())
```

`sandbox.key(i)` is the specifications' `app_config.keys[i]`, carrying `key_str`,
`key_name`, `key_secret` and `capability`. The index means what it means in a
specification — `keys[0]` full access, `keys[1]` push admin, `keys[2]` the per-channel
capabilities, `keys[3]` subscribe-only, `keys[4]` revocable tokens — which is why the
asset is the `ably-common` file and not `test/assets/testAppSpec.json`, whose keys sit
at other indices. `sandbox.app_id` and `sandbox.key_str`, the full-access key, are
there too.

`sandbox_rest_client(key, ...)` and `sandbox_realtime_client(key, ...)` in
[helpers/client.py](helpers/client.py) build the clients. They set the endpoint to the
sandbox, carry no `test_options`, and register the client for the same teardown the
mock-backed constructors use. A specification that authenticates some other way leaves
the key out and passes `token=`, `auth_callback=` or `auth_url=`. The protocol defaults
to JSON; the realtime client keeps `auto_connect` and the fallback hosts at the library
defaults, since connecting is the point.

Waits are wall-clock here, which is the opposite of the unit tier: `poll_until` spins on
the event loop, so the integration tier uses `wall_clock_poll_until(condition, timeout,
description)`, which sleeps the specifications' interval between attempts and returns
whatever the condition answered with. Its condition may be sync or async. Nothing waits
on a fixed sleep for something that can be polled for.

The five specifications carrying a `## Protocol Variants` section — `publish`,
`history`, `presence`, `batch_presence` and `mutable_messages` — run once per protocol.
A test asks for that by taking the `use_binary_protocol` fixture and passing it on; a
test that does not take it runs json only.

```python
async def test_rsl1d_publish_failure(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key(2).key_str, use_binary_protocol=use_binary_protocol)
```

Tests here are given 120 seconds each, per `uts/docs/integration-testing.md`, rather
than the 30 seconds `pyproject.toml` sets for the suite as a whole. The marker covers
the integration package alone.

`rest/integration/proxy/` routes its traffic through
[ably/uts-proxy](https://github.com/ably/uts-proxy), a programmable proxy standing
between the client and the sandbox. Those specifications are about what the SDK does
when a request goes wrong — a connection dropped mid-request, a 503, a CloudFront 403,
a response held past the request timeout — and the sandbox answers correctly, so the
fault is injected in front of it. The proxy binds a port per session, takes plain HTTP
on it and speaks TLS onwards to the sandbox, applies the rules the session was opened
with, and records every request and response that crosses it.

The binary is a pinned `uts-proxy` release. The first run that needs it fetches the
release archive for the machine, checks it against the sha256 the release publishes,
and extracts the binary into `~/.cache/uts-proxy/<version>/`, where every run
afterwards finds it; the download is serialised on a lock file, so several Python
versions starting at once on an empty cache fetch it once between them.
`UTS_PROXY_LOCAL_PATH` names a locally built binary, or a `.tar.gz` holding one, to be
used in place of the release, and `UTS_PROXY_CONTROL_URL` names a control API someone
is already running, which the suite uses as it stands and leaves running. Otherwise one
control process is started for the test session on a free port and reaped at the end of
it; it serves every session the run opens.

`proxy_session` is a specification's `create_proxy_session(...)`, and closes every
session it hands out when the test ends. A client reaches its session by naming
`localhost` and the session's port with TLS off, which disables fallback hosts (REC2c2);
a scenario about a retry names the same session again as its fallback, so both attempts
arrive at the one port and appear in the one event log, which `session.get_log()`
returns:

```python
async def test_rsc15l_connection_drop_fallback(sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'http_request', 'pathContains': '/time'},
        'action': {'type': 'http_drop'},
        'times': 1,
    }])
    client = sandbox_rest_client(
        auth_callback=token_auth_callback(sandbox.key_str),
        endpoint='localhost', fallback_hosts=['localhost'],
        port=session.proxy_port, tls=False, use_binary_protocol=False)
```

A plain connection rules basic auth out, since RSC18 refuses it, so every client here
authenticates through a callback whose own request goes straight to the sandbox and
stays out of the event log.

Tests in this package are given 300 seconds each: a cold cache downloads the binary
before the first of them runs, and a specification that provokes a timeout sits through
the delay it asked the proxy for.

`realtime/integration/` runs against the same sandbox over a real WebSocket — twenty
specifications, thirteen of them straight to the sandbox and seven under `proxy/`. It
provisions an app of its own, which arrives as the `realtime_sandbox` fixture, so that a
realtime test entering presence or publishing to a channel cannot be seen by a REST test
reading the same channel name. The app carries the same `key(i)`, `key_str` and `app_id`
members the `sandbox` fixture does.

```python
async def test_rtl7a_subscribe_all_messages(realtime_sandbox):
    client = sandbox_realtime_client(realtime_sandbox.key_str)
    channel = client.channels.get('test-rtl7a-' + random_id())
```

Five specifications carry a `## Protocol Variants` section — `channel_history`,
`channels/channel_publish`, `delta_decoding`, `mutable_messages` and `presence_lifecycle` —
and take the tier's own `use_binary_protocol` fixture, passing it to every client they
build. The other fifteen are json only.

The connections are real, so the waits are wall-clock here too.
`await_connection_state(client, state, timeout)` and `await_channel_state(channel, state,
timeout)` are the specifications' `AWAIT_STATE`, and ten seconds is the figure the
specifications give for reaching CONNECTED over a network, against the five those helpers
default to for a mock. A state the client passes through in a millisecond cannot be waited
for after the fact — DISCONNECTED after a drop from CONNECTED is one, the retry being a
`loop.call_soon` — so a test that needs it registers a `connection.on(...)` recorder before
connecting and waits on the recorded list.

Tests here are given 120 seconds each, from the package's own `conftest.py`, as in the REST
integration tier.

`realtime/integration/proxy/` puts the same pinned `uts-proxy` between the client and the
sandbox, with the same `proxy_control` and `proxy_session` fixtures and the same two
environment variables, `UTS_PROXY_LOCAL_PATH` and `UTS_PROXY_CONTROL_URL`, that
[helpers/proxy.py](helpers/proxy.py) documents. What these specifications fault is the
WebSocket rather than an HTTP request — a frame suppressed, replaced or injected, a socket
closed, an upgrade refused — and the event log is read for the frames that crossed:

```python
async def test_rtn15a_disconnect_triggers_resume(realtime_sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'delay_after_ws_connect', 'delayMs': 1000},
        'action': {'type': 'close'},
        'times': 1,
    }])
    client = sandbox_realtime_client(
        auth_callback=jwt_auth_callback(realtime_sandbox.key_str),
        endpoint='localhost', port=session.proxy_port, tls=False,
        use_binary_protocol=False, auto_connect=False)
```

`endpoint='localhost'` disables the fallback hosts by itself (REC2c2), so every attempt
lands on the one session port and appears in the one event log. A realtime connection
carries its credentials in the WebSocket's query string, so a plain `key=` does work over
the session; the modules here sign an Ably JWT locally instead, through a file-local
`jwt_auth_callback` built on `generate_jwt`, because it costs no round trip and so adds
nothing to the log a test is counting. Tests in this package are given 300 seconds each,
as in the REST proxy package.

## Running

```
uv run --frozen --extra crypto --extra dev pytest test/uts -q
```

The offline tiers alone, which need no network:

```
uv run --frozen --extra crypto --extra dev pytest test/uts/rest/unit test/uts/realtime/unit test/uts/helpers -q
```

Either integration tier alone, each of which provisions a sandbox app and needs network
access:

```
uv run --frozen --extra crypto --extra dev pytest test/uts/rest/integration -q
uv run --frozen --extra crypto --extra dev pytest test/uts/realtime/integration -q
```

`--frozen` is required: without it dependency resolution reaches past the
environment's cutoff. `--extra dev` carries pytest.

Tests that record a deviation or a specification fault are skipped by default and run
under an environment variable:

```
RUN_DEVIATIONS=1 uv run --frozen --extra crypto --extra dev pytest test/uts -q
```

Every gated test is confirmed to fail when enabled — none passes under both
behaviours — so the two runs are the check that the record in
[deviations.md](deviations.md) is still true. The counts either run should produce are
in that file's header.

Both seams are installed per client, so a test that forgets one, or that lets the host
fallback loop run, reaches the real internet; see the fallback host note in
[deviations.md](deviations.md).

Linting is `ruff`, line length 115:

```
uv run --frozen --extra crypto --extra dev ruff check ably/ test/
```
