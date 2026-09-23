# Deviations — connection failures batch

Covers the tests derived from six specifications:

| Spec | Derived tests | File |
|---|---|---|
| `uts/realtime/unit/connection/connection_failures_test.md` | 12 | `realtime/unit/connection/connection_failures_test.py` |
| `uts/realtime/unit/connection/connection_open_failures_test.md` | 9 | `realtime/unit/connection/connection_open_failures_test.py` |
| `uts/realtime/unit/connection/backoff_jitter_test.md` | 4 | `realtime/unit/connection/backoff_jitter_test.py` |
| `uts/realtime/unit/connection/network_change_test.md` | 4 | `realtime/unit/connection/network_change_test.py` |
| `uts/realtime/unit/connection/forwards_compatibility_test.md` | 3 | `realtime/unit/connection/forwards_compatibility_test.py` |
| `uts/realtime/unit/connection/server_initiated_reauth_test.md` | 3 | `realtime/unit/connection/server_initiated_reauth_test.py` |

35 tests: 25 pass, 6 are gated behind `RUN_DEVIATIONS` and 4 cannot be run at all.
Every gated test was confirmed to fail when enabled.

```
RUN_DEVIATIONS=1 uv run --frozen --extra crypto --extra dev pytest \
  test/uts/realtime/unit/connection -q
```

## UTS Spec Errors

### A key-authenticated client is credited with an initial token request

**Spec point:** RTN15h2 (`token-error-renew-success-0`), RTN15c5
(`token-error-during-resume-0`), RTN14b (`token-error-with-renewal-0`).

**What the spec says:** each of the three sets the client up with
`ClientOptions(key: "appId.keyId:keySecret")`, stubs `/keys/…` in `mock_http`, and then
asserts `token_request_count == 2  # Initial + renewal`.

**Why it is wrong:** `features.md` RSA4 has a client given only a key authenticate with
basic auth; token auth is used when `useTokenAuth` is set, or when a `clientId`,
`authCallback`, `authUrl` or token is supplied. None of the three setups does any of
that, so no SDK makes an initial token request here — the renewal is the first and only
one. The assertion contradicts the specification's own setup, not just ably-python.

**What the SDK does:** `Auth.get_auth_transport_param` puts `key` in the connect
parameters (BASIC), and the renewal that follows the token error is the single request
the mock sees.

**Tests affected:** all three assert `len(token_requests) == 1`, carry a
`# UTS SPEC ERROR:` comment at the site, and pass. The assertion the specification is
really making — that the token was renewed — is preserved.

**Status:** fault in the specification; raise upstream.

### RTN14b's renewal-failure setup never establishes the connection

**Spec point:** RTN14b (`token-renewal-fails-1`).

**What the spec says:** `onConnectionAttempt: (conn) => conn.send_to_client(
ProtocolMessage(action: ERROR, …))`, with no `conn.respond_with_success()` first.

**Why it is wrong:** `helpers/mock_websocket.md` has a connection attempt produce a
`MockConnection` only once it is answered, so a message sent from an unanswered attempt
can reach nobody. Every other test in the same file establishes the connection first.

**Tests affected:** `test_rtn14b_token_renewal_fails` answers the attempt before the
ERROR (`respond_with_error`, which does both) and passes.

**Status:** fixture fault in the specification; raise upstream.

### RTN14e invents a five-second default connectionStateTtl

**Spec point:** RTN14e (`disconnected-to-suspended-0`).

**What the spec says:** `DEFAULT_CONNECTION_STATE_TTL = 5000  # 5 seconds`, described as
"In real implementation, this comes from server in CONNECTED message. For this test,
we'll use a short default value", and then advances `DEFAULT_CONNECTION_STATE_TTL + 100`.

**Why it is wrong:** the connection state TTL is a `connectionDetails` value, or the
library default (`features.md` TO3, two minutes). The test never connects, so nothing
supplies 5000, and no client option in any SDK sets it. The setup is a value the test
wishes for rather than one it can produce.

**Tests affected:** `test_rtn14e_disconnected_to_suspended` advances past the SDK's own
default TTL, which is `Defaults.connection_state_ttl` = 120000, and passes. Because the
clock is notional this costs nothing in wall time.

**Status:** fixture fault in the specification; raise upstream. It is separate from the
real deviation recorded below, where the server *does* send a TTL and ably-python
ignores it.

## Failing Tests

### A DISCONNECTED carrying a 5xx error with no fallback hosts stalls the connection — 1 gated test

**Spec point:** RTN15h3 (`non-token-error-resume-0`).

**What the spec says:** a DISCONNECTED message whose error is not a token error must
trigger an immediate reconnect with a resume attempt. The specification's own fixture
uses `code: 80003, statusCode: 503`.

**What the SDK does:** nothing at all. The connection stays CONNECTED, no further
connection attempt is made, and no state change is emitted — even though the server has
closed the transport. The client is left believing it is connected to a socket that no
longer exists.

**Root cause:** `ConnectionManager.on_disconnected`
(`ably/realtime/connectionmanager.py:437-450`) routes any `500 <= status_code <= 504` to
RTN17f1's fallback-host path, and when `self.__fallback_hosts` is empty it logs
`"No fallback host to try for disconnected protocol message"` and falls out of the
`if`/`elif` chain without calling `notify_state`. There is no path back to DISCONNECTED.
Any client configured with no fallback hosts — a custom endpoint, a local cluster, or
the empty list these unit tests use — is stranded by a DISCONNECTED whose status code is
a 5xx.

**Tests affected:** `test_rtn15h3_non_token_error_resume`, gated with `@deviation`,
keeping the specification's assertions (CONNECTING, then CONNECTED with the same
connection id, two attempts, `resume=key-1` on the second). Enabled, it fails with
`AssertionError: Timed out waiting for connection state connecting; it was connected`.

**Status:** open bug.

### Reconnection attempts stop resuming once the connection is SUSPENDED — 1 gated test

**Spec point:** RTN14h (`resume-after-ttl-0`), which replaced RTN15g in specification
6.1.0.

**What the spec says:** reconnection attempts in the SUSPENDED state must continue to
attempt to resume, regardless of how long the client has been disconnected. Every
attempt carries the original `connectionKey` in a `resume` query parameter; the server,
not the client, decides whether continuity survives.

**What the SDK does:** every reconnection attempt carries `resume=key-1` right up to the
moment the connection is suspended, and none afterwards. Measured over 72 attempts in
150 seconds of notional time: 60 with `resume`, 12 without — the 12 being every attempt
made after the suspend timer fired.

**Root cause:** `ConnectionManager.enact_state_change`
(`ably/realtime/connectionmanager.py:170-178`) clears `__connection_details`,
`connection_id`, `__connection_key` and `msg_serial` on entry to SUSPENDED, citing
RTN16d; `__get_transport_params` adds `resume` only `if self.connection_details`. RTN16d
is about *recovery keys* being invalidated, not about suppressing resume, and RTN14h now
says the opposite for the suspended case.

**Tests affected:** `test_rtn14h_resume_after_ttl`, gated with `@deviation`, keeping the
specification's assertion that every reconnection attempt carries `resume=key-1`.
Enabled, it fails with `KeyError: 'resume'`.

**Status:** open bug.

### RTB1 backoff and jitter are not implemented at all — 4 gated tests

**Spec point:** RTB1, RTB1a, RTB1b.

**What the spec says:** the retry delay for a DISCONNECTED connection is
`disconnectedRetryTimeout × backoff × jitter`, and for a SUSPENDED channel
`channelRetryTimeout × backoff × jitter`, where the backoff coefficient for the nth
retry is `min((n + 2) / 3, 2)` and the jitter coefficient is uniform on [0.8, 1.0]. The
delay is reported to the application as `ConnectionStateChange.retryIn` /
`ChannelStateChange.retryIn`.

**What the SDK does:** every retry waits exactly the configured timeout. There is no
backoff coefficient, no jitter, and no `retryIn`:

- `ConnectionManager.start_retry_timer` (`connectionmanager.py:753`) schedules
  `self.options.disconnected_retry_timeout` (or `suspended_retry_timeout`) unchanged.
- `RealtimeChannel.__start_retry_timer` (`channel.py:866-871`) schedules
  `self.ably.options.channel_retry_timeout` unchanged.
- `ConnectionStateChange` (`ably/types/connectionstate.py`) and `ChannelStateChange`
  (`ably/types/channelstate.py`) carry `previous`, `current`, `event`/`resumed` and
  `reason`. Neither has `retryIn`.
- Grepping `ably/` for `jitter`, `backoff`, `retry_in` or `retryIn` returns nothing.

**Tests affected:** all four, gated with `@deviation`. Because `retryIn` does not exist,
each delay is measured instead as the notional time between the state change that
schedules a retry and the state change the retry produces, read from the `FakeClock`:
the retry runs on the timer seam and a timer's callback runs with the clock reading
exactly its due time, so the measurement is exact. Enabled, they fail with:

| Test | Failure |
|---|---|
| `test_rtb1a_backoff_coefficient_sequence` | `assert (1.3333333333333333 * 0.8) <= 1.0` — the second retry's coefficient is 1, not 4/3 |
| `test_rtb1b_jitter_coefficient_range` | `assert 0.5 >= 0.8` — the delay is the flat timeout, so the implied jitter is degenerate |
| `test_rtb1_disconnected_retry_delay` | `assert 2000.0 >= ((2000 * (4.0 / 3.0)) * 0.8)` |
| `test_rtb1_suspended_channel_retry_delay` | `assert 3000.0 >= ((3000 * (4.0 / 3.0)) * 0.8)` |

Two further adaptations were needed to reach the observable at all, and are recorded
under Adapted Tests: the specification's 1000 jitter samples become 40, and the channel
test reaches SUSPENDED through a server-initiated DETACHED rather than a channel ERROR.

**Status:** open bug — an unimplemented feature rather than a wrong one.

## Adapted Tests

### A refused connection and a connect timeout reach no failure path — 1 adapted test, 6 more shaped by it

**Spec point:** RTN14d (`retry-recoverable-failure-0`) most directly; the same defect
shapes RTN14e, RTN14f, RTN14h and both connection tests in `backoff_jitter_test.md`.

**What the spec says:** `conn.respond_with_refused()` is a recoverable connection
failure. RTN14d expects DISCONNECTED "after first failure", then a retry after
`disconnectedRetryTimeout`. RTN14 expects the failure to be attributable, and RTN17d/e
expect a failed host to send the client to its fallbacks.

**What the SDK does — measured, with `fallback_hosts=[]` and
`realtime_request_timeout=1000`:**

| injected | state at settle | state change | reason |
|---|---|---|---|
| `ConnectionRefusedError` (`respond_with_refused`) | still CONNECTING | at t=1000 | 50003 / 504 |
| `asyncio.TimeoutError` (`respond_with_timeout`) | still CONNECTING | at t=1000 | 50003 / 504 |
| `socket.gaierror` (`respond_with_dns_error`) | already DISCONNECTED | at t=0 | 40000 / 400, naming the cause |

A refused connection and a connect timeout are therefore indistinguishable from each
other *and* from a server that accepts the socket and says nothing: all three surface as
the transition timer expiring with "Connection cancelled due to request timeout".

**Root cause:** `WebSocketTransport.ws_connect`
(`ably/transport/websockettransport.py:117`) catches only
`(WebSocketException, socket.gaierror)`:

```python
except (WebSocketException, socket.gaierror) as e:
    exception = AblyException(f'Error opening websocket connection: {e}', 400, 40000)
    self._emit('failed', exception)
```

`ConnectionRefusedError` is an `OSError`, not a `WebSocketException`, and
`asyncio.TimeoutError` is neither, so neither reaches `_emit('failed')`. The future
`ConnectionManager.try_host` awaits is completed only by the `connected` or `failed`
events, so it never completes; the `except` clause in `connect_base` that would enter
`connect_with_fallback_hosts` is never reached, and the attempt is ended only by the
transition timer started in `start_connect`. The coordinating session measured the
consequence with the default fallback hosts in place: **one connection attempt and no
fallback host tried** for refused and for timeout, against six attempts (primary plus
all five fallbacks) for a DNS error. So RTN17d's fallback behaviour is unreachable for
the two commonest transport failures.

**Tests affected:**

- `test_rtn14d_retry_recoverable_failure` — **adapted, passing.** It asserts that the
  refusal moves nothing (`state == CONNECTING` after settling), that DISCONNECTED
  arrives only when the transition timer expires, and that the reason is the timer's
  50003 rather than the refusal's. It fails if the defect is fixed, which is the point.
- `test_rtn14e_disconnected_to_suspended`, `test_rtn14f_suspended_retries_indefinitely`,
  `test_rtn14h_resume_after_ttl`, `test_rtb1_disconnected_retry_delay`,
  `test_rtb1a_backoff_coefficient_sequence`, `test_rtb1b_jitter_coefficient_range` —
  each passes a short `realtime_request_timeout` so the retry cycle turns at all, since
  otherwise every refused attempt would sit out the full ten-second default.

**Status:** open bug. Widening the `except` to `(WebSocketException, OSError,
asyncio.TimeoutError)` — or, better, emitting `failed` from a `finally`-style guard so
no exception type can leave the future hanging — would fix all of it. Not fixed here:
the finding is the output.

### A token error with no means to renew reports the renewal failure, not the server's error

**Spec point:** RTN15h1 (`token-error-no-renew-0`).

**What the spec says:** after a DISCONNECTED carrying `40142 / 401` that cannot be
renewed, the connection is FAILED and `errorReason.code == 40142`,
`errorReason.statusCode == 401`.

**What the SDK does:** the connection is FAILED, as required, but `error_reason` is the
error from the attempted renewal: `40171 / 403`, "Need a new token but auth_options does
not include a way to request one".

**Root cause:** `ConnectionManager.on_token_error` records the server's error as
`__error_reason`, then calls `Auth._ensure_valid_auth_credentials(force=True)`, which
raises `AblyAuthException(…, 403, 40171)` because a client given a bare `token` has no
way to obtain another. `on_error_from_authorize` then calls
`notify_state(FAILED, that exception)`, and `enact_state_change` overwrites
`__error_reason` with it.

**Note on the specification:** `connection_open_failures_test.md`'s own RSA4a test
asserts exactly `40171` for the same situation reached through an ERROR rather than a
DISCONNECTED, and cites RSA4a2 for it. The two UTS specifications disagree with each
other about which error a non-renewable token error should surface; ably-python matches
the RSA4a one. `test_rsa4a_token_error_no_renewal` passes unmodified.

**Tests affected:** `test_rtn15h1_token_error_no_renew` asserts `40171 / 403` with the
specification's expectation in a comment above. It fails if the SDK changes which error
it keeps.

**Status:** arguably correct as it stands; the specifications should be reconciled
first.

### The server's connectionStateTtl is parsed and never used

**Spec point:** RTN14e, RTN14f, RTN14h (and RTN21 generally).

**What the spec says:** the `connectionStateTtl` in a CONNECTED message's
`connectionDetails` governs how long the client may stay DISCONNECTED before it is
SUSPENDED. RTN14h's fixture sets 5000 for exactly that reason.

**What the SDK does:** `ConnectionDetails.from_dict` parses `connectionStateTtl`
(`ably/types/connectiondetails.py:19`) and nothing ever reads it.
`ConnectionManager.start_suspend_timer` (`connectionmanager.py:745`) uses
`Defaults.connection_state_ttl` — 120000 — directly, and no client option overrides it.
A server that shortens or lengthens the TTL is ignored.

**Tests affected:** `test_rtn14h_resume_after_ttl` sends the specification's
`connectionStateTtl: 5000` and then advances 150000ms of notional time rather than the
specification's 37500ms, because suspension arrives on the default instead.
`test_rtn14e_disconnected_to_suspended` and `test_rtn14f_suspended_retries_indefinitely`
advance to the same default. All three say so in a comment. The cost is notional only —
the three tests take 0.06s, 0.09s and 0.08s.

**Status:** open bug. It is recorded centrally as well (`deviations.md`, RTN21); the
entry here records how it shaped these three fixtures.

### A channel ERROR fails the channel instead of prompting a re-attach

**Spec point:** RTL13b, reached through RTB1 (`suspended-channel-retry-delay-1`).

**What the spec says:** RTB1's channel test sends `ERROR` on an attached channel to
provoke the re-attach whose repeated failure suspends the channel, citing RTL13b.

**What the SDK does:** `RealtimeChannel._on_message` (`ably/realtime/channel.py:775`)
takes `ProtocolMessageAction.ERROR` on a channel straight to
`_notify_state(ChannelState.FAILED, reason=error)`. No re-attach is attempted, the
channel never reaches SUSPENDED, and no retry timer is ever started — so the
specification's route to the observable is closed.

**Tests affected:** `test_rtb1_suspended_channel_retry_delay` provokes the re-attach
with a server-initiated DETACHED (RTL13a) instead, which ably-python does answer with
`_request_state(ATTACHING)`. From there the specification's scenario runs as written:
each re-attach is refused with DETACHED, the channel is suspended, and the retry delay
is measured. A comment at the site records the substitution.

**Status:** open bug, but it belongs to the channel specifications rather than to this
batch; recorded here because it changed this test's fixture. `channel_error.md` in
another batch should own it.

### RTB1b's sample count

**Spec point:** RTB1b (`jitter-coefficient-range-0`).

**What the spec says:** sample the jitter generator 1000 times and check the range, the
mean and the spread.

**What the test does:** ably-python has no jitter generator to sample, so each sample
costs a whole reconnection cycle, and the series has to finish before the 120000ms
suspend timer moves the retries onto `suspended_retry_timeout`. 40 samples are taken.
That is still four orders of magnitude outside the mean's tolerance for a uniform
distribution (the standard error of the mean is 0.009 against a ±0.05 allowance), so the
test separates a uniform generator from a degenerate one just as firmly. The reduction
is noted in a comment.

**Status:** an adaptation to the measurement, not a difference in behaviour.

### `Connection.id` and `Connection.key` are not part of the public API

**Spec point:** RTN8, RTN9, read incidentally by nine tests across this batch.

**What the spec says:** `client.connection.id` and `client.connection.key`.

**What the SDK does:** the connection id lives on
`client.connection.connection_manager.connection_id` and the key on
`client.connection.connection_details.connection_key`.

**Tests affected:** every test that reads either; each carries a comment at the first
site. This is recorded centrally (`deviations.md`, and `connection_id_key_test.py` owns
the spec points); it is noted here only so the reading is not mistaken for a
translation liberty.

**Status:** recorded elsewhere; no action from this batch.

## Mock Infrastructure Limitations

### RTN20 has no network connectivity listener to mock — 4 tests

**Spec point:** RTN20, RTN20a, RTN20b, RTN20c.

**What the spec says:** RTN20 applies "when the client library can subscribe to OS
events for network/internet connectivity changes". `network_change_test.md` requires an
injectable `MockNetworkListener` with `simulate_network_lost()` and
`simulate_network_available()`, installed "via the same mechanism the SDK uses to
receive real network events".

**What the SDK does:** nothing — there is no network connectivity abstraction anywhere
in `ably/`, no OS-event subscription, and no seam through which a mock could be
installed. `ConnectionManager.check_connection` is a one-shot HTTP probe used on the
fallback-host path, not an event source.

**Why it is not an SDK deviation:** RTN20 is conditional on the platform, and
`network_change_test.md`'s own platform table lists Python under "Not typically
available — RTN20 may not apply", adding that "SDKs that do not implement network
monitoring should skip these tests entirely".

**Tests affected:** all four are skipped stubs carrying their Test IDs, so the
specification's coverage is still accounted for if ably-python ever gains the
abstraction.

**Status:** not applicable to this SDK as it stands.
