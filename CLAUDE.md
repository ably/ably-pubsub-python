- after making any code changes, run `uv ruff check` to make sure linting passes
- use `uv` to run any other necessary tasks such as `pytest`

# Time

Production code in `ably/` reads the current time and schedules delayed callbacks through
the clock, never through `time`, `datetime.now` or `asyncio.sleep`:

- `select_clock(options)` in the constructor, from `ably.util.clock`
- `now_ms()` for the time of day
- `monotonic_ms()` for a duration
- `timer(timeout_ms, callback)` for a delayed callback

A test replaces it with `TestOptions(clock=...)`. Converting a caller-supplied value, and
arithmetic on the unix epoch, are not clock readings and stay as they are.

`asyncio.wait_for` in `ConnectionManager.ping` is the one delay that runs on the event
loop's clock rather than this one; a test which waits it out sets a short real
`realtime_request_timeout_seconds`.

The timing client options are seconds, named `*_seconds`, where the clock counts
milliseconds. `Options` converts them in one place, `seconds_to_ms`, behind a private
`_<option>_ms` property for each, and code scheduling on the clock reads those.

`Auth._timestamp` signs a token request the server validates, so a client which reads a
fake clock talks to a mock rather than to the sandbox.
