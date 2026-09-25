"""Derived from uts/realtime/integration/proxy/connection_open_failures.md in ably/specification.

Spec points: RTN14a, RTN14b, RTN14c, RTN14d, RTN14g

The five faults here are the ones a connection can meet before it is ever open: a
fatal ERROR in place of CONNECTED, a token error in place of CONNECTED, a refused
WebSocket, and a CONNECTED that never arrives. Each is injected by a `uts-proxy`
rule carrying `times: 1`, so the attempt that follows the fault reaches the sandbox
unaltered and the test can tell a client that gave up from one that retried.

`test/uts/realtime/unit/connection/connection_open_failures_test.py` covers the same
five spec points against `MockWebSocket`, and is the place where the state machine
itself is pinned — it drives the transition and retry timers through a `FakeClock`,
answers the connection attempt synthetically, and so can assert on timings that real
network traffic would make flaky. What these tests add is the transport underneath:
the SDK opens a real WebSocket, the frames it reads are the sandbox's own with one
substituted, and the retry it makes is a second connection the proxy's event log
records. A fault the unit tier can only describe — a refused TCP connection, a token
renewed against the real `/keys/…/requestToken` — is here exercised end to end.

`endpoint='localhost'` names both hosts and disables the fallbacks (REC2c2), so every
attempt arrives at the one session port and appears in the one event log. A realtime
connection carries its credentials in the WebSocket's query string rather than in an
Authorization header, so `key=` works over the session's plain `ws://` where a REST
client's basic auth would be refused; RTN14b is the exception and authenticates with a
callback, because renewing a token is what it is about.
"""

from ably import AblyRest
from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import contains_in_order
from test.uts.helpers.sandbox import SANDBOX_ENDPOINT

# The specification's `AWAIT_STATE ... WITH timeout`, in seconds: 15 for a
# connection that is meant to fail, 30 for one that has to fail and then succeed.
FAILURE_TIMEOUT = 15
RECOVERY_TIMEOUT = 30

# The specification's `realtimeRequestTimeout: 3000` and
# `disconnectedRetryTimeout: 2000`. Both are milliseconds in ably-python too.
REALTIME_REQUEST_TIMEOUT_MS = 3000
DISCONNECTED_RETRY_TIMEOUT_MS = 2000


def connection_id(client):
    """The specification's `client.connection.id`.

    `Connection` exposes no `id`; the connection manager holds it, and clears it
    on the terminal states. See the house ruling on missing accessors in
    `test/uts/deviations.md`.
    """
    return client.connection.connection_manager.connection_id


def connection_key(client):
    """The specification's `client.connection.key`.

    `Connection` exposes no `key` either. It arrives in `connectionDetails`, and
    the whole `ConnectionDetails` is `None` until a CONNECTED has been received.
    """
    details = client.connection.connection_details
    return details.connection_key if details is not None else None


def record_states(client):
    """The specification's `state_changes`, filled from `client.connection.on(...)`.

    Registered before `connect()` in every test here, since the first transition a
    specification names is the CONNECTING that `connect()` itself causes.
    """
    states = []

    def on_change(change):
        states.append(change.current)

    client.connection.on(on_change)
    return states


def ws_connects(log):
    """The `ws_connect` events the proxy recorded, in the order it accepted them.

    One per attempt the client made, each carrying the `queryParams` the SDK put
    in the WebSocket URL.
    """
    return [event for event in log if event['type'] == 'ws_connect']


def token_auth_callback(api_key):
    """The specification's `request_token_from_sandbox(api_key, params)`.

    The client under test points at the proxy, where a rule is waiting for the
    first CONNECTED. A token requested through that client would go out over the
    session's plain HTTP, where basic auth is refused (RSC18), and would add
    traffic to the log beside the connections the test counts. So the callback
    builds a Rest client of its own aimed straight at the sandbox and closes it
    again; the token arrives over a connection the proxy never sees.
    """
    async def auth_callback(params):
        inner_rest = AblyRest(key=api_key, endpoint=SANDBOX_ENDPOINT)
        try:
            return await inner_rest.auth.request_token()
        finally:
            await inner_rest.close()

    return auth_callback


# UTS: realtime/proxy/RTN14a/fatal-connect-error-0
async def test_rtn14a_fatal_connect_error(realtime_sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'ws_frame_to_client', 'action': 'CONNECTED'},
        'action': {
            'type': 'replace',
            'message': {
                'action': 9,
                'error': {'code': 40005, 'statusCode': 400, 'message': 'Invalid key'},
            },
        },
        'times': 1,
        'comment': 'RTN14a: Replace CONNECTED with fatal ERROR',
    }])

    client = sandbox_realtime_client(
        key=realtime_sandbox.key_str,
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
        auto_connect=False,
    )
    state_changes = record_states(client)

    client.connect()

    await await_connection_state(client, ConnectionState.FAILED, timeout=FAILURE_TIMEOUT)

    # Connection transitioned to FAILED
    assert client.connection.state == ConnectionState.FAILED

    # Error reason is set from the injected ERROR message
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 40005
    assert client.connection.error_reason.status_code == 400

    # State sequence includes CONNECTING -> FAILED
    assert contains_in_order(state_changes, [ConnectionState.CONNECTING, ConnectionState.FAILED])

    # Connection ID/key not set (never received real CONNECTED)
    assert connection_id(client) is None
    assert connection_key(client) is None


# UTS: realtime/proxy/RTN14b/token-error-renew-reconnect-0
@deviation
async def test_rtn14b_token_error_renew_reconnect(realtime_sandbox, proxy_session):
    auth_callback_calls = []
    request_token = token_auth_callback(realtime_sandbox.key_str)

    async def auth_callback(params):
        auth_callback_calls.append(params)
        return await request_token(params)

    session = await proxy_session(rules=[{
        'match': {'type': 'ws_frame_to_client', 'action': 'CONNECTED'},
        'action': {
            'type': 'replace',
            'message': {
                'action': 9,
                'error': {'code': 40142, 'statusCode': 401, 'message': 'Token expired'},
            },
        },
        'times': 1,
        'comment': 'RTN14b: Token error on first connect, renewal should succeed',
    }])

    client = sandbox_realtime_client(
        auth_callback=auth_callback,
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
        auto_connect=False,
    )
    state_changes = record_states(client)

    client.connect()

    await await_connection_state(client, ConnectionState.CONNECTED, timeout=RECOVERY_TIMEOUT)

    # Successfully connected after token renewal
    assert client.connection.state == ConnectionState.CONNECTED

    # Connection properties are set (from the real CONNECTED on second attempt)
    assert connection_id(client) is not None
    assert connection_key(client) is not None

    # authCallback was called at least twice (initial token + renewal)
    assert len(auth_callback_calls) >= 2

    # State sequence shows the SDK went through CONNECTING, then back to CONNECTING after
    # the error, and finally reached CONNECTED
    assert contains_in_order(state_changes, [ConnectionState.CONNECTING, ConnectionState.CONNECTED])

    # Proxy event log shows two WebSocket connections
    log = await session.get_log()
    assert len(ws_connects(log)) >= 2

    # No residual error reason on successful connection
    assert client.connection.error_reason is None


# UTS: realtime/proxy/RTN14d/retry-after-refused-0
async def test_rtn14d_retry_after_refused(realtime_sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'ws_connect', 'count': 1},
        'action': {'type': 'refuse_connection'},
        'times': 1,
        'comment': 'RTN14d: Refuse first WebSocket connection',
    }])

    client = sandbox_realtime_client(
        key=realtime_sandbox.key_str,
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
        auto_connect=False,
        disconnected_retry_timeout=DISCONNECTED_RETRY_TIMEOUT_MS,
    )
    state_changes = record_states(client)

    client.connect()

    await await_connection_state(client, ConnectionState.CONNECTED, timeout=RECOVERY_TIMEOUT)

    # Successfully connected after retry
    assert client.connection.state == ConnectionState.CONNECTED

    # Connection properties are set
    assert connection_id(client) is not None
    assert connection_key(client) is not None

    # State sequence shows CONNECTING -> DISCONNECTED -> CONNECTING -> CONNECTED
    assert contains_in_order(state_changes, [
        ConnectionState.CONNECTING,
        ConnectionState.DISCONNECTED,
        ConnectionState.CONNECTING,
        ConnectionState.CONNECTED,
    ])

    # Proxy event log shows two WebSocket connection attempts
    log = await session.get_log()
    assert len(ws_connects(log)) >= 2


# UTS: realtime/proxy/RTN14g/server-error-causes-failed-0
async def test_rtn14g_server_error_causes_failed(realtime_sandbox, proxy_session):
    session = await proxy_session(rules=[{
        'match': {'type': 'ws_frame_to_client', 'action': 'CONNECTED'},
        'action': {
            'type': 'replace',
            'message': {
                'action': 9,
                'error': {'code': 50000, 'statusCode': 500, 'message': 'Internal server error'},
            },
        },
        'times': 1,
        'comment': 'RTN14g: Connection-level ERROR (server error) during open',
    }])

    client = sandbox_realtime_client(
        key=realtime_sandbox.key_str,
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
        auto_connect=False,
    )
    state_changes = record_states(client)

    client.connect()

    await await_connection_state(client, ConnectionState.FAILED, timeout=FAILURE_TIMEOUT)

    # Connection transitioned to FAILED
    assert client.connection.state == ConnectionState.FAILED

    # Error reason is set from the injected ERROR message
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 50000
    assert client.connection.error_reason.status_code == 500
    assert client.connection.error_reason.message == 'Internal server error'

    # State sequence includes CONNECTING -> FAILED
    assert contains_in_order(state_changes, [ConnectionState.CONNECTING, ConnectionState.FAILED])

    # Connection ID/key not set
    assert connection_id(client) is None
    assert connection_key(client) is None


# UTS: realtime/proxy/RTN14c/connection-timeout-0
async def test_rtn14c_connection_timeout(realtime_sandbox, proxy_session):
    # No `times`, so every CONNECTED is suppressed: the WebSocket opens and the
    # sandbox answers, but nothing the SDK would read as an open connection
    # reaches it, and only its own timeout can end the attempt.
    session = await proxy_session(rules=[{
        'match': {'type': 'ws_frame_to_client', 'action': 'CONNECTED'},
        'action': {'type': 'suppress'},
        'comment': 'RTN14c: Suppress CONNECTED to force timeout',
    }])

    client = sandbox_realtime_client(
        key=realtime_sandbox.key_str,
        endpoint='localhost',
        port=session.proxy_port,
        tls=False,
        use_binary_protocol=False,
        auto_connect=False,
        realtime_request_timeout=REALTIME_REQUEST_TIMEOUT_MS,
    )
    state_changes = record_states(client)

    client.connect()

    await await_connection_state(client, ConnectionState.DISCONNECTED, timeout=FAILURE_TIMEOUT)

    # Connection timed out and transitioned to DISCONNECTED
    assert client.connection.state == ConnectionState.DISCONNECTED

    # Error reason indicates timeout
    assert client.connection.error_reason is not None
    assert ('timeout' in client.connection.error_reason.message
            or client.connection.error_reason.code in (50003, 80003))

    # State sequence includes CONNECTING -> DISCONNECTED
    assert contains_in_order(state_changes, [ConnectionState.CONNECTING, ConnectionState.DISCONNECTED])

    # Connection ID/key not set (CONNECTED was never received)
    assert connection_id(client) is None
    assert connection_key(client) is None
