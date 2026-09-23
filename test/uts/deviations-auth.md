# Deviations — realtime unit auth

Covers the four specifications derived into `test/uts/realtime/unit/auth/`:
`realtime_authorize.md`, `auth_callback_errors_test.md`, `connection_auth_test.md`
and `token_expiry_non_renewable_test.md` — 29 tests, 20 passing, 8 gated behind
`RUN_DEVIATIONS`, 1 unimplementable.

Every gated test has been confirmed to fail when enabled:

```
RUN_DEVIATIONS=1 uv run --frozen --extra crypto --extra dev pytest test/uts/realtime/unit/auth/
```

Headings are fixed and appear even when they hold nothing.

## UTS Spec Errors

### RSA4c3 — two specifications assert opposite things about `errorReason`

`connection_auth_test.md` (`RSA4c3/callback-error-stays-connected-0`) asserts that an
authCallback failure during an RTN22 reauth leaves `connection.errorReason` set to an
80019 whose `cause` is the callback's error. `auth_callback_errors_test.md`
(`RSA4c3/callback-error-connected-stays-0`) asserts the opposite in its own words —
"errorReason is NOT set … the auth failure is silently swallowed" — citing
[specification#466](https://github.com/ably/specification/issues/466).

`features.md` as it stands backs the first: RSA4c1 still says an ErrorInfo with code
80019 "should be emitted with the state change if there is one (per RSA4c2/3) **and set
as the connection errorReason**". So the two UTS specs cannot both be derived, and one
of them has to change when #466 lands.

- Test impact: derived from both, as written. `test_rsa4c3_callback_error_stays_connected`
  is gated as a Failing Test below, because the current `features.md` makes it the
  spec-correct reading and ably-python does not satisfy it.
  `test_rsa4c3_callback_error_connected_stays` passes, because ably-python happens to
  behave the way #466 proposes.
- Neither fails fast: the contradiction is between two UTS specs and an unlanded
  features change, not an assertion `features.md` flatly refutes, so both readings are
  still derivable.
- Status: for the specification. Whichever way #466 is resolved, one of the two tests
  has to be regenerated from the corrected spec.

### RTC8a1 — a note that calls an assertion implementation-dependent, then asserts it

`RTC8a1/successful-reauth-update-event-0` carries the note "Whether `connection.id` is
updated from the reauth CONNECTED message is implementation-dependent. Some SDKs only
set `connection.id` during initial transport activation", and then asserts
`client.connection.id == "connection-id-2"` unconditionally. An SDK the note excuses
fails the test. Either the note or the assertion should go.

- Test impact: none. ably-python does update the connection id on a reauth CONNECTED,
  so `test_rtc8a1_successful_reauth_update_event` passes, reading the id from the
  connection manager (see the Adapted note on RTN3 below).
- Status: for the specification.

### `auth_callback_errors_test.md` files a REST test under `realtime/unit`

`RSA4e/rest-callback-error-40170-0` drives a REST client and a mocked HTTP client, but
takes the Test ID `realtime/unit/RSA4e/rest-callback-error-40170-0` and lives in a
realtime spec. Same class of fault as the existing `fallback.md` entry (REC3a/REC3b/REC3
drive a Realtime client from `rest/unit`).

- Test impact: none. Derived as written into
  `test/uts/realtime/unit/auth/auth_callback_errors_test.py`, where its Test ID puts it,
  and it passes.
- Status: for the specification.

### RSA4c2 is duplicated across two specs

`connection_auth_test.md`'s `RSA4c2/callback-error-causes-disconnected-0` and
`auth_callback_errors_test.md`'s `RSA4c2/callback-error-connecting-disconnected-1` are
the same test with the same setup; the second adds assertions on the state-change event.
`auth_callback_errors_test.md`'s own closing note acknowledges the overlap. Both are
derived, since each has its own Test ID.

## Failing Tests

The specification's assertion is preserved and gated behind `@deviation`. Removing the
mark is the only change needed once the SDK behaviour lands.

### An authCallback error is always rewritten as 401/40170, so RSA4d is unreachable — 4 tests

`ably/rest/auth.py:182-187` wraps **every** exception an authCallback raises as
`AblyException("auth_callback raised an exception", 401, 40170, cause=e)`, discarding the
original `statusCode`. `ConnectionManager.on_error_from_authorize`
(`connectionmanager.py:479-491`) then branches on `exception.status_code == 403` to reach
FAILED, and that branch can never be taken for an authCallback: the status is always 401,
so a 403 goes to the `__fail_state` (DISCONNECTED) with an 80019/401 instead.

RSA4d requires FAILED with 80019/**403** and `cause` set to the 403, both during the
connect sequence and during an RTN22 reauth (RSA4d1).

| Test | Observed with `RUN_DEVIATIONS=1` |
|---|---|
| `connection_auth_test.py::test_rsa4d_callback_403_causes_failed` | `Timed out waiting for connection state failed; it was disconnected` |
| `connection_auth_test.py::test_rsa4d_callback_403_reauth_causes_failed` | `Timed out waiting for connection state failed; it was connected` |
| `auth_callback_errors_test.py::test_rsa4d_callback_403_connecting_failed` | `Timed out waiting for connection state failed; it was disconnected` |
| `auth_callback_errors_test.py::test_rsa4d_callback_403_reauth_failed` | `Timed out waiting for connection state failed; it was connected` |

Status: open bug. The fix is to preserve the callback error's `statusCode` (or to let an
`AblyException` from the callback through unwrapped), which also restores the `cause`
chain recorded under Adapted Tests below.

### A failed RTN22 reauth leaves no trace on the connection — 1 test

`WebSocketTransport.on_protocol_message` (`websockettransport.py:170-175`) handles a
server AUTH by awaiting `auth.authorize()` inside a bare `except Exception` that only
logs. Nothing reaches `on_error_from_authorize`, so no 80019 is built and
`connection.errorReason` stays as it was.

- Spec: RSA4c1/RSA4c3 as `features.md` has them — the connection stays CONNECTED, and an
  80019/401 with the callback's error as `cause` is set as `errorReason`.
- Test: `connection_auth_test.py::test_rsa4c3_callback_error_stays_connected` —
  `AssertionError: Timed out waiting for errorReason to be set`.
- Status: open bug, but see the UTS Spec Error above: specification#466 would make
  ably-python's behaviour the correct one, in which case this entry closes as a spec
  change rather than a fix.

### TokenParams passed to an authCallback carry no clientId on a realtime client — 1 test

`Auth.__init__` (`ably/rest/auth.py:36-41`) sets `self.__client_id = None` when
`ably._is_realtime`, deferring the clientId to the CONNECTED `connectionDetails`.
`_ensure_valid_auth_credentials` only adds `token_params['client_id']` when
`self.client_id is not None`, so an authCallback on a realtime client is called with the
clientId missing entirely, even though `ClientOptions.clientId` was set.

- Spec: RSA12a/RTN2e — the library passes `TokenParams` including any configured
  `clientId`.
- Test: `connection_auth_test.py::test_rtn2e_callback_params_include_clientid` —
  `KeyError: 'client_id'`.
- The snake_case key itself is idiomatic translation, not the deviation; the deviation is
  the absent member. The REST client does pass it, so the SDK is inconsistent with itself.
- Status: open bug.

### RSA4f invalid-format validation is not implemented — 1 test

`Auth.request_token` matches `TokenDetails`, `dict`, `str` and `None` in turn and then
falls through to `token_path = f"/keys/{token_request.key_name}/requestToken"`. A value
of another type — the specification uses `12345` — raises
`AttributeError: 'int' object has no attribute 'key_name'`, which is not an
`AblyException`, so `try_host`'s `except AblyException` does not catch it and
`connect_base`'s `except Exception` notifies DISCONNECTED with the raw `AttributeError`
as the reason. `connection.errorReason` is then an `AttributeError` with no `code`.

- Spec: RSA4f/RSA4c2 — an object that is not a String, JsonObject, TokenRequest or
  TokenDetails is an invalid token format, giving DISCONNECTED with 80019/401.
- Test: `auth_callback_errors_test.py::test_rsa4f_callback_invalid_type_format` —
  `AttributeError: 'AttributeError' object has no attribute 'code'`.
- Status: open bug, two parts: no RSA4f type check, and a non-`AblyException` reaching
  `Connection#errorReason`.

### No 40171 log at instantiation with a non-renewable token — 1 test

`Auth.__init__` logs `"using token auth with supplied token only"` at debug level when a
client is built with a token and no key, authCallback or authUrl. RSA4a1 requires an
**info**-level message carrying error code 40171 and, per TI5, the help URL
`https://help.ably.io/error/40171`. Nothing in `ably/` mentions 40171 outside
`request_token`'s raise and `on_error_from_authorize`'s branch, and `grep -rn href ably/`
finds no help URLs anywhere.

- Test: `token_expiry_non_renewable_test.py::test_rsa4a1_non_renewable_token_logs_warning`
  — `assert False` on the "an info record mentions 40171" assertion.
- The specification collects the log through a `logHandler` client option, which
  ably-python does not have (already recorded in `deviations.md` under RSC2/RSC3/RSC4/
  TO3b/TO3c/TO3c2). The test uses pytest's `caplog` on the `ably` logger instead, which
  is idiomatic rendering, not a second deviation.
- Status: open bug. The RSA4a2 half of the same spec — a token error on a non-renewable
  token giving FAILED with 40171 and no retry — is implemented and both its tests pass.

## Adapted Tests

The test asserts what the SDK does, with the specification's expectation in a comment
above. These run, so they guard against regression.

### An 80019 from a failed auth carries no `cause` — 2 tests

`ConnectionManager.on_error_from_authorize` builds
`AblyException('Client configured authentication provider request failed', 401, 80019)`
with no `cause` argument, so the error the authCallback raised survives only in the log.
RSA4c1/RSA4c2 require `cause` to be set to the underlying error.

| Test | Asserts |
|---|---|
| `connection_auth_test.py::test_rsa4c2_callback_error_causes_disconnected` | DISCONNECTED, 80019/401, and `errorReason.cause is None` |
| `auth_callback_errors_test.py::test_rsa4c2_callback_error_connecting_disconnected` | the same, plus the state change carrying the 80019 |

Adapted rather than gated because the state, code and status are all correct and worth
guarding; only the `cause` link is missing. Same root cause as the RSA4d entry above —
`request_token`'s wrapper is what loses the original error's shape, and
`on_error_from_authorize` then drops what is left. Status: open bug.

### An authCallback that never returns is caught only by the connect timeout — 1 test

RSA4c treats an auth attempt that outruns `realtimeRequestTimeout` as an auth error,
giving DISCONNECTED with 80019/401. ably-python applies no timeout to the callback:
`await auth_callback(token_params)` is unbounded, and the CONNECTING transition timer
(`connectionmanager.py:699-724`) ends the attempt instead, with the generic
`AblyException("Connection cancelled due to request timeout", 504, 50003)` it raises for
any connect that does not complete in time.

- Test: `auth_callback_errors_test.py::test_rsa4c2_callback_timeout_connecting_disconnected`
  asserts DISCONNECTED with 50003/504, driven on a `FakeClock`.
- The resulting state is right and the error is stable and attributable, so an adapted
  assertion is worth more here than a skipped one. Status: open bug, cosmetic — the
  connection recovers either way, but the error does not say the auth provider is at
  fault.

### `connection.id` and `connection.key` are read elsewhere

`RTC8a1/successful-reauth-update-event-0` asserts `client.connection.id` and
`client.connection.key`. Same root cause as the existing `RTN3` entry in
`deviations.md` ("`connection.id` … Not exposed"); `test_rtc8a1_successful_reauth_update_event`
reads `client.connection.connection_manager.connection_id` and
`client.connection.connection_details.connection_key` and passes. No new entry.

## Mock Infrastructure Limitations

### A token over 128KiB cannot reach a connection attempt — 1 test

`RSA4f/callback-oversized-token-format-1` has the authCallback return a 131073-character
token. ably-python accepts it (there is no RSA4f size check) and puts it in the websocket
URL's `accessToken` parameter, which makes the URL longer than `httpx.URL` accepts:
`PendingConnection.__init__` (`test/uts/helpers/mock_websocket.py:233`) parses every
connection URL through `httpx.URL`, which raises `InvalidURL: URL too long` above 64 KiB.
The exception is raised inside `_MockConnect.__aenter__` before the attempt is recorded,
and `ws_connect` catches only `WebSocketException` and `socket.gaierror`, so the client
simply stays in CONNECTING and nothing about the SDK is observable.

- Test: `auth_callback_errors_test.py::test_rsa4f_callback_oversized_token_format`,
  a skipped stub with the derived body kept.
- The SDK deviation behind it is real — no 128KiB check on a token from an authCallback —
  but the mock cannot show it. Letting `RecordedUrl` fall back to a parsed-by-hand URL
  when `httpx.URL` refuses one would make this test derivable.
