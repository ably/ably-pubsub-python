# Universal Test Specifications

Tests here are derived from the pseudocode specifications in the
[ably/specification](https://github.com/ably/specification) repository under `uts/`.
They are mechanical translations: each one names the spec point it covers and
carries a `# UTS: <id>` comment identifying the specification it came from.

Read `uts/docs/writing-derived-tests.md` in the specification repository before
adding or changing tests here, alongside `.claude/skills/uts-to-python/SKILL.md`,
which covers what is particular to this SDK. Record anything that departs from a
specification in [deviations.md](deviations.md), which also covers how the
specifications are adopted here and why.

## Layout

```
helpers/     shared infrastructure the specifications assume
rest/        specifications under uts/rest
realtime/    specifications under uts/realtime
```

Unit tests serve every request from a mock and reach no network. Integration
tests run against a sandbox app.

## Installing the mock

The specifications express mock installation as a global `install_mock(mock_http)`.
Here a mock is passed to the client it serves:

```python
mock_http = MockHttpClient(
    on_connection_attempt=lambda conn: conn.respond_with_success(),
    on_request=lambda req: req.respond_with(200, {'result': 'ok'}),
)
ably = AblyRest(key=key, test_options=TestOptions(http_transport=mock_http.as_transport()))
```

A realtime client takes its websocket mock the same way, through
`TestOptions(websocket_connect=...)`:

```python
mock_ws = MockWebSocket(
    on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
)
ably = AblyRealtime(key=key, auto_connect=False,
                    test_options=TestOptions(websocket_connect=mock_ws.as_connect()))
```

`rest_client(mock_http, ...)` and `realtime_client(mock_ws, ...)` in
[helpers/client.py](helpers/client.py) wrap both, defaulting the credentials
and registering the client for teardown. `realtime_client` also takes
`mock_http=` for a realtime client whose HTTP calls a specification drives, and
`clock=` for a `FakeClock`.

The client builds its HTTP client once and reads its websocket hook once, so
construct the mocks first. Teardown is `await ably.close()`, which stands in for
`uninstall_mock()`.

## Running

```
uv run --extra crypto pytest test/uts
```

Realtime unit tests reach no network at all. Both seams are installed per
client, so a test that forgets one, or that lets the host fallback loop run,
reaches the real internet; see the fallback host note in
[deviations.md](deviations.md).
