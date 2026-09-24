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
rest/        specifications under uts/rest
realtime/    specifications under uts/realtime
```

Every directory needs an `__init__.py`, because `test` is a package.

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
| [helpers/deviations.py](helpers/deviations.py) | the `@deviation` and `@spec_error` gates |

`SKILL.md` lists every name in each. The helpers have their own tests
(`helpers/*_test.py`), which are not derived from a specification and are not counted
in the derived-test totals.

## Running

```
uv run --frozen --extra crypto --extra dev pytest test/uts -q
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
