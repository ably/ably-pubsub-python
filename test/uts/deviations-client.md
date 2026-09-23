# Deviations — realtime unit client specs

Covers the tests derived from `uts/realtime/unit/client/realtime_client.md`,
`realtime_timeouts.md`, `realtime_time.md`, `realtime_request.md` and
`realtime_stats.md`. The four headings are fixed and appear even when they hold
nothing. [deviations.md](deviations.md) holds the same record for the rest of the
suite.

Run the gated tests with:

```
RUN_DEVIATIONS=1 uv run --frozen --extra crypto --extra dev pytest test/uts/realtime/unit/client
```

## UTS Spec Errors

### `realtime_client.md` RTC12 points at a specification file that does not exist

- **Spec point**: RTC12, test `realtime/unit/RTC12/constructor-string-detection-0`.
- **What the spec says**: "**See:** `uts/test/realtime/unit/client/client_options.md` -
  RSC1, RSC1a, RSC1c", and "The same test cases apply".
- **What is actually there**: no such path exists in the specification repository
  (`uts/test/...` is not a directory at all), and no RSC1, RSC1a or RSC1c test is
  declared anywhere under `uts/rest/unit`. The referenced cases cannot be reused
  because they were never written.
- **Root cause**: a dangling cross-reference. `realtime_client.md` also points
  `RTC12/invalid-arguments-error-1` at `uts/rest/unit/auth/auth_scheme.md` RSC1b,
  which does exist, so only the first reference is broken.
- **Tests affected**: `test_rtc12_constructor_string_detection`. The test is derived
  from the three cases the spec lists in its own body (API key string, token string,
  empty string) rather than from the missing file, so it is a running test rather
  than a fail-fast placeholder; a `# NOTE:` at the site records the broken reference.
- **Status**: open against the specification. Either write the RSC1/RSC1a/RSC1c tests
  and fix the path, or drop the reference and keep the inline cases as the definition.

## Failing Tests

### The `echo_messages` client option does not exist and no `echo` parameter is sent

- **Spec point**: RTC1a (TO3h), test `realtime/unit/RTC1a/echo-messages-option-0`.
- **What the spec says**: `echoMessages` defaults to true and is carried on the
  websocket URL as `echo=true`, or `echo=false` when the option is set to false.
- **What the SDK does**: `Options.__init__` has no `echo_messages` parameter, and
  neither it nor any spelling of it reaches `AuthOptions`, so passing one raises
  `TypeError: __init__() got an unexpected keyword argument 'echo_messages'`. The
  connection URL carries no `echo` parameter under any configuration: the only query
  parameters built are the auth parameter, `v`, `format`, `resume` and whatever
  `transport_params` adds.
- **Root cause**: `ably/types/options.py` (option absent) and
  `ConnectionManager.__get_transport_params` (`ably/realtime/connectionmanager.py:204`).
- **Tests affected**: `test_rtc1a_echo_messages_option`, gated with `@deviation`.
  Confirmed to fail when enabled: `KeyError: 'echo'`.
- **Status**: open bug. The option is missing outright rather than spelled
  differently, so messages published by a client are always echoed back to it.

### The `recover` option is stored but never used

- **Spec point**: RTC1c (TO3i, RTN16), test `realtime/unit/RTC1c/recover-option-0`.
- **What the spec says**: the `recover` option takes a recovery key, and the
  connection key it carries is sent as the `recover` query parameter on the first
  connection attempt only (RTN16k).
- **What the SDK does**: `recover` is accepted by `Options.__init__` and exposed as a
  property, and nothing else in the library reads it. No `recover` parameter is ever
  sent, and no recovery key is ever decoded, so connection state recovery is absent.
- **Root cause**: `ably/types/options.py:111` is the only assignment; there is no
  read anywhere under `ably/`.
- **Tests affected**: `test_rtc1c_recover_option`, gated with `@deviation`. Confirmed
  to fail when enabled:
  `AssertionError: assert 'recover' in {'format': 'msgpack', 'key': ..., 'v': '5'}`.
  Its second and third cases (the parameter being dropped on a reconnect, and an
  unparseable recovery key being tolerated) would pass on their own, since the
  parameter is never present; they are kept so that the test becomes meaningful once
  recovery lands.
- **Status**: open bug.

## Adapted Tests

### A string constructor argument is only ever read as an API key

- **Spec point**: RTC12 / RSC1, RSC1a, RSC1c, test
  `realtime/unit/RTC12/constructor-string-detection-0`.
- **What the spec says**: a string argument is an API key when it contains `:` and a
  token when it does not; an empty string is an error.
- **What the SDK does**: `AblyRest.__init__` treats its first positional argument as
  a key unconditionally and hands it to `AuthOptions.set_key`, which requires exactly
  two colon-separated parts. A token string raises `AblyAuthException` 40101/401,
  "key of not len 2 parameters". A token is supplied through the separate `token` or
  `token_details` arguments instead. The empty-string case is compliant — it raises.
- **Root cause**: `ably/rest/rest.py:52-66` and `ably/types/authoptions.py:28`.
- **Tests affected**: `test_rtc12_constructor_string_detection` asserts basic auth for
  the key string and the 40101 for the token string, with the spec's expectation in a
  comment.
- **Status**: intentional / SDK-wide. ably-python's constructor takes credentials as
  distinct named arguments and has no string-sniffing path to restore.

### No credentials raises a bare `ValueError` in the constructor

- **Spec point**: RTC12 / RSC1b, test `realtime/unit/RTC12/invalid-arguments-error-1`.
- **What the spec says**: error code 40106 is raised when no valid credentials are
  provided.
- **What the SDK does**: `AblyRest.__init__` raises
  `ValueError("key is missing. Either an API key, token, or token auth method must be
  provided")`, which carries no Ably error code, and does so at construction rather
  than at the first request.
- **Root cause**: `ably/rest/rest.py:63-67`.
- **Tests affected**: `test_rtc12_invalid_arguments_error`. This is the realtime
  counterpart of the REST suite's `test_rsc1b_no_auth_method_error`, which records the
  same behaviour.
- **Status**: open bug, shared with the REST client.

### `Auth.client_id` is held at None on a realtime client until CONNECTED

- **Spec point**: RTC17 (RSA7b1), test `realtime/unit/RTC17/client-id-attribute-0`.
- **What the spec says**: `client.clientId` returns the clientId from the auth object,
  and asserts `client.clientId == client.auth.clientId`.
- **What the SDK does**: `AblyRealtime.client_id` reads `options.client_id` and
  returns the configured value, while `Auth.__init__` sets `self.__client_id = None`
  whenever `ably._is_realtime`, deferring it to whatever a CONNECTED message confirms.
  The two therefore disagree on a client that has not connected, even when the clientId
  was given explicitly in the options.
- **Root cause**: `ably/rest/auth.py:34-41`.
- **Tests affected**: `test_rtc17_client_id_attribute` asserts
  `client.client_id == 'explicit-client-id'` and `client.auth.client_id is None`, with
  the spec's equality in a comment.
- **Status**: open bug. RSA12b only allows the realtime clientId to be unknown while
  it has not been configured; an explicit `client_id` should be visible on `auth`
  immediately.

### `transportParams` booleans are stringified with Python's capitalisation

- **Spec point**: RTC1f, test `realtime/unit/RTC1f/transport-params-option-0`, case
  RTC1f_2.
- **What the spec says**: a `transportParams` value of `true` appears in the query
  string as `"true"` and `false` as `"false"`.
- **What the SDK does**: `WebSocketTransport.connect` builds the query string with
  `urllib.parse.urlencode`, which renders each value through `str()`, so a Python bool
  becomes `True` or `False`. Integers are unaffected: `42` becomes `"42"` as required.
- **Root cause**: `ably/transport/websockettransport.py:89`.
- **Tests affected**: `test_rtc1f_transport_params_option` asserts `'True'` and
  `'False'` with the spec's expectation in a comment. Its other two cases (string
  params, and overriding `v` and `heartbeats`) are asserted exactly as the spec writes
  them and pass.
- **Status**: open bug. A caller can work around it by passing the strings directly,
  but a bool is what the spec's Stringifiable type admits.

### The HTTP timeout defaults live on the HTTP layer, in seconds

- **Spec point**: RTC7 (TO3l3, TO3l4), test
  `realtime/unit/RTC7/default-timeouts-applied-3`.
- **What the spec says**: `client.options.httpOpenTimeout == 4000` and
  `client.options.httpRequestTimeout == 10000`.
- **What the SDK does**: `Options` stores both as `None` when they are not configured,
  and `Http.http_open_timeout` / `Http.http_request_timeout` fall back to
  `CONNECTION_RETRY_DEFAULTS`, which holds `4` and `10` — seconds, not milliseconds,
  because that is what `httpx` takes. The three realtime timeouts the same test checks
  (`realtime_request_timeout` 10000, `disconnected_retry_timeout` 15000,
  `suspended_retry_timeout` 30000) are defaulted on `Options` and match the spec.
- **Root cause**: `ably/types/options.py:113-114` and `ably/http/http.py:119-120`,
  `306-315`.
- **Tests affected**: `test_rtc7_default_timeouts_applied` asserts both options are
  `None` and that the HTTP layer reports 4 and 10, with the spec's expectation in a
  comment.
- **Status**: open bug for the observable default being unreadable from `options`; the
  unit difference alone is internal.

### A refused connection is simulated as a DNS failure

- **Spec point**: RTC7, test `realtime/unit/RTC7/disconnected-retry-timeout-2`.
- **What the spec says**: the mock answers every attempt after the first with
  `conn.respond_with_refused()`.
- **What the SDK does**: `WebSocketTransport.ws_connect` catches only
  `(WebSocketException, socket.gaierror)`, so the `ConnectionRefusedError` a refused
  attempt raises never reaches `_emit('failed')`. The attempt instead hangs until the
  CONNECTING transition timer expires, which costs a further
  `realtime_request_timeout` of fake time and would mask the retry interval this test
  measures. `respond_with_dns_error()` is caught, fails fast, and drives exactly the
  same DISCONNECTED-and-retry path.
- **Root cause**: `ably/transport/websockettransport.py:121`.
- **Tests affected**: `test_rtc7_disconnected_retry_timeout` uses
  `respond_with_dns_error()` in place of `respond_with_refused()`, noted at the site.
  The assertion the spec makes — that no retry happens before the configured delay and
  one does after it — is unchanged, and was confirmed to fail
  (`assert 2 > 2`) when the option is raised to 5000 ms.
- **Status**: open bug in the SDK's exception handling; the test adapts around it.

## Mock Infrastructure Limitations

*(none)*
