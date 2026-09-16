# Universal Test Specifications

Tests here are derived from the pseudocode specifications in the
[ably/specification](https://github.com/ably/specification) repository under `uts/`.
They are mechanical translations: each one names the spec point it covers and
carries a `# UTS: <id>` comment identifying the specification it came from.

Read `uts/docs/writing-derived-tests.md` in the specification repository before
adding or changing tests here, alongside `.claude/skills/uts-to-python/SKILL.md`,
which covers what is particular to this SDK. Record anything that departs from a
specification in [deviations.md](deviations.md); [decisions.md](decisions.md)
covers how the specifications are adopted here and why.

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

The client builds its HTTP client once, so construct the mock first. Teardown is
`await ably.close()`, which stands in for `uninstall_mock()`.

## Running

```
uv run --extra crypto pytest test/uts
```
