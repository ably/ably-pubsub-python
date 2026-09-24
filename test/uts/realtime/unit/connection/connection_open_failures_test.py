"""Derived from uts/realtime/unit/connection/connection_open_failures_test.md in ably/specification.

Spec points: RTN14, RTN14a, RTN14b, RTN14c, RTN14d, RTN14e, RTN14f, RTN14g
"""

import time

from ably.realtime.connection import ConnectionState
from ably.types.tokendetails import TokenDetails
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.mock_http import MockHttpClient
from test.uts.helpers.mock_websocket import ERROR_MESSAGE, MockWebSocket, connected_message

# The suspend timer runs on `Defaults.connection_state_ttl`, which no client option
# reaches, so the tests about suspension advance notional time to it
CONNECTION_STATE_TTL = 120000

TOKEN_ERROR = ERROR_MESSAGE(40142, 'Token expired')


def token_response(token):
    """The body an Ably token request returns."""
    issued = int(time.time() * 1000)
    return {
        'token': token,
        'keyName': 'appId.keyId',
        'issued': issued,
        'expires': issued + 3600000,
        'capability': '{"*":["*"]}',
    }


# UTS: realtime/unit/RTN14a/invalid-key-failed-0
async def test_rtn14a_invalid_key_failed():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_error(
            ERROR_MESSAGE(40005, 'Invalid key')),
    )
    client = realtime_client(mock_ws, key='invalid.key:secret')

    client.connect()

    await await_connection_state(client, ConnectionState.CONNECTING)
    await await_connection_state(client, ConnectionState.FAILED)

    assert client.connection.state == ConnectionState.FAILED
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 40005
    assert client.connection.error_reason.status_code == 400

    # The specification reads `client.connection.id` and `client.connection.key`;
    # ably-python carries those on the connection manager and the connection details
    assert client.connection.connection_manager.connection_id is None
    assert client.connection.connection_details is None


# UTS: realtime/unit/RTN14b/token-error-with-renewal-0
async def test_rtn14b_token_error_with_renewal():
    token_requests = []

    def on_request(request):
        if '/keys/' in request.path:
            token_requests.append(request)
            request.respond_with(200, token_response(f'renewed_token_{len(token_requests)}'))

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )

    connection_attempts = []

    def on_connection_attempt(conn):
        connection_attempts.append(conn)
        if len(connection_attempts) == 1:
            conn.respond_with_error(TOKEN_ERROR)
        else:
            conn.respond_with_success(
                connected_message('connection-id', connectionKey='connection-key'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    # A token error met while CONNECTING is retried on the retry timer rather than
    # immediately, so the retry interval is kept short
    client = realtime_client(mock_ws, mock_http=mock_http, key='appId.keyId:keySecret',
                             disconnected_retry_timeout=100)

    client.connect()

    await await_connection_state(client, ConnectionState.CONNECTED, timeout=10.0)

    assert client.connection.state == ConnectionState.CONNECTED

    # UTS SPEC ERROR: the specification asserts two token requests, "initial + renewal",
    # having set the client up with a key. RSA4 has a key-authenticated realtime client
    # connect with basic auth, so the renewal is the only token request it makes
    assert len(token_requests) == 1

    assert len(connection_attempts) == 2


# UTS: realtime/unit/RTN14b/token-renewal-fails-1
async def test_rtn14b_token_renewal_fails():
    calls = []

    async def auth_callback(token_params):
        calls.append(token_params)
        if len(calls) == 1:
            return TokenDetails(token='initial-token', expires=int(time.time() * 1000) + 3600000)
        raise Exception('Unable to renew token')

    def on_connection_attempt(conn):
        # The specification's setup sends the ERROR without establishing the
        # connection first; a message can only reach the client behind one
        conn.respond_with_error(TOKEN_ERROR)

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    # The retry that follows the failed renewal would ask the auth callback again,
    # so it is held off until the assertions have run
    client = realtime_client(mock_ws, auth_callback=auth_callback,
                             disconnected_retry_timeout=60000)

    states = []
    client.connection.on(lambda change: states.append(change.current))

    client.connect()
    await await_connection_state(client, ConnectionState.DISCONNECTED)

    assert client.connection.state == ConnectionState.DISCONNECTED
    assert len(calls) == 2
    assert client.connection.error_reason is not None
    assert states == [ConnectionState.CONNECTING, ConnectionState.DISCONNECTED]


# UTS: realtime/unit/RSA4a/token-error-no-renewal-0
async def test_rsa4a_token_error_no_renewal():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_error(TOKEN_ERROR),
    )
    client = realtime_client(mock_ws, token='expired_token_string')

    client.connect()

    await await_connection_state(client, ConnectionState.FAILED)

    assert client.connection.state == ConnectionState.FAILED
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 40171


# UTS: realtime/unit/RTN14c/connection-timeout-0
async def test_rtn14c_connection_timeout():
    # The attempt succeeds and the server sends nothing, so the connection is left
    # to the transition timer
    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: conn.respond_with_success())
    clock = FakeClock()
    client = realtime_client(mock_ws, clock=clock, key='appId.keyId:keySecret',
                             realtime_request_timeout=1000)

    client.connect()

    await await_connection_state(client, ConnectionState.CONNECTING)

    await clock.advance(1100)

    assert client.connection.state == ConnectionState.DISCONNECTED
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 50003


# UTS: realtime/unit/RTN14d/retry-recoverable-failure-0
async def test_rtn14d_retry_recoverable_failure():
    connection_attempts = []

    def on_connection_attempt(conn):
        connection_attempts.append(conn)
        if len(connection_attempts) == 1:
            conn.respond_with_refused()
        else:
            conn.respond_with_success(
                connected_message('connection-id', connectionKey='connection-key'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    clock = FakeClock()
    # DEVIATION: see deviations.md. A refused connection reaches
    # no failure path of its own, so the first attempt ends on the transition timer
    # rather than at once, and the test advances to it
    client = realtime_client(mock_ws, clock=clock, key='appId.keyId:keySecret',
                             disconnected_retry_timeout=1000, realtime_request_timeout=1000)

    client.connect()
    await settle()

    # The refusal itself moves nothing: the attempt is still outstanding
    assert client.connection.state == ConnectionState.CONNECTING

    await clock.advance(1100)

    assert client.connection.state == ConnectionState.DISCONNECTED
    # The reason is the transition timer's, not the refused connection's
    assert client.connection.error_reason.code == 50003

    await clock.advance(1100)

    assert client.connection.state == ConnectionState.CONNECTED
    assert len(connection_attempts) == 2


# UTS: realtime/unit/RTN14e/disconnected-to-suspended-0
async def test_rtn14e_disconnected_to_suspended():
    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: conn.respond_with_refused())
    clock = FakeClock()
    client = realtime_client(mock_ws, clock=clock, key='appId.keyId:keySecret',
                             disconnected_retry_timeout=1000, realtime_request_timeout=1000)

    states = []
    client.connection.on(lambda change: states.append(change.current))

    client.connect()

    await clock.advance(1100)

    assert client.connection.state == ConnectionState.DISCONNECTED

    # The specification advances past a 5000ms connectionStateTtl it sets for the
    # test. ably-python takes the TTL from its own defaults, so the advance is to that
    await clock.advance(CONNECTION_STATE_TTL + 100)

    assert client.connection.state == ConnectionState.SUSPENDED
    assert client.connection.error_reason is not None


# UTS: realtime/unit/RTN14f/suspended-retries-indefinitely-0
async def test_rtn14f_suspended_retries_indefinitely():
    states = []
    connection_attempts = []
    attempts_when_suspended = []

    def on_connection_attempt(conn):
        connection_attempts.append(conn)
        # The specification fails the first two attempts and succeeds on the third,
        # counting on suspension arriving after one. ably-python suspends on its own
        # 120000ms connectionStateTtl, so every attempt up to the first retry from
        # SUSPENDED fails instead
        if not attempts_when_suspended or len(connection_attempts) <= attempts_when_suspended[0] + 1:
            conn.respond_with_refused()
        else:
            conn.respond_with_success(
                connected_message('connection-id', connectionKey='connection-key'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    clock = FakeClock()
    client = realtime_client(mock_ws, clock=clock, key='appId.keyId:keySecret',
                             disconnected_retry_timeout=500, suspended_retry_timeout=1000,
                             realtime_request_timeout=1000)

    def on_state_change(change):
        states.append(change.current)
        if change.current == ConnectionState.SUSPENDED and not attempts_when_suspended:
            attempts_when_suspended.append(len(connection_attempts))

    client.connection.on(on_state_change)

    client.connect()

    for _ in range(60):
        await clock.advance(2500)
        if client.connection.state == ConnectionState.CONNECTED:
            break

    assert ConnectionState.SUSPENDED in states
    assert client.connection.state == ConnectionState.CONNECTED
    # Attempts were made from SUSPENDED: one that failed, and the one that connected
    assert len(connection_attempts) >= attempts_when_suspended[0] + 2
    assert len(connection_attempts) >= 3


# UTS: realtime/unit/RTN14g/error-empty-channel-failed-0
async def test_rtn14g_error_empty_channel_failed():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_error(
            ERROR_MESSAGE(50000, 'Internal server error')),
    )
    client = realtime_client(mock_ws, key='appId.keyId:keySecret')

    client.connect()

    await await_connection_state(client, ConnectionState.FAILED)
    await settle()

    assert client.connection.state == ConnectionState.FAILED
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 50000
    assert client.connection.error_reason.status_code == 500
    assert client.connection.error_reason.message == 'Internal server error'
