"""Derived from uts/realtime/unit/connection/connection_failures_test.md in ably/specification.

Spec points: RTN14h, RTN15, RTN15a, RTN15b, RTN15c, RTN15d, RTN15e, RTN15h, RTN15j
"""

import time

from ably.realtime.connection import ConnectionState
from ably.types.tokendetails import TokenDetails
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient
from test.uts.helpers.mock_websocket import ERROR_MESSAGE, MockWebSocket, connected_message

DISCONNECTED_ACTION = 6

TOKEN_ERROR = {
    'action': DISCONNECTED_ACTION,
    'error': {'code': 40142, 'statusCode': 401, 'message': 'Token expired'},
}


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


# UTS: realtime/unit/RTN15h1/token-error-no-renew-0
async def test_rtn15h1_token_error_no_renew():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected_message('connection-id', connectionKey='connection-key')),
    )
    client = realtime_client(mock_ws, token='some_token_string')

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    mock_ws.send_to_client_and_close(TOKEN_ERROR)

    await await_connection_state(client, ConnectionState.FAILED, timeout=2.0)

    assert client.connection.state == ConnectionState.FAILED
    assert client.connection.error_reason is not None
    # DEVIATION: see deviations.md. The specification asserts the
    # DISCONNECTED message's own 40142/401; ably-python reports the failed renewal
    # instead, which RSA4a2 gives as 40171
    assert client.connection.error_reason.code == 40171
    assert client.connection.error_reason.status_code == 403


# UTS: realtime/unit/RTN15h2/token-error-renew-success-0
async def test_rtn15h2_token_error_renew_success():
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
            conn.respond_with_success(connected_message('connection-1', connectionKey='key-1'))
        else:
            conn.respond_with_success(connected_message('connection-1', connectionKey='key-1-renewed'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, mock_http=mock_http, key='appId.keyId:keySecret')

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    first_connection_id = client.connection.connection_manager.connection_id
    first_connection_key = client.connection.connection_details.connection_key

    mock_ws.send_to_client_and_close(TOKEN_ERROR)

    await await_connection_state(client, ConnectionState.CONNECTING, timeout=2.0)
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert client.connection.state == ConnectionState.CONNECTED

    # UTS SPEC ERROR: the specification asserts two token requests, "initial + renewal",
    # having set the client up with a key. RSA4 has a key-authenticated realtime client
    # connect with basic auth, so the renewal is the only token request it makes
    assert len(token_requests) == 1

    # The specification reads `client.connection.id` and `client.connection.key`;
    # ably-python carries those on the connection manager and the connection details
    assert client.connection.connection_manager.connection_id == first_connection_id
    assert client.connection.connection_details.connection_key != first_connection_key
    assert client.connection.connection_details.connection_key == 'key-1-renewed'


# UTS: realtime/unit/RTN15h2/token-error-renew-fails-1
async def test_rtn15h2_token_error_renew_fails():
    calls = []

    async def auth_callback(token_params):
        calls.append(token_params)
        if len(calls) == 1:
            return TokenDetails(token='valid-token-1', expires=int(time.time() * 1000) + 3600000)
        raise Exception('Unable to renew token')

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected_message('connection-1', connectionKey='key-1')),
    )
    client = realtime_client(mock_ws, auth_callback=auth_callback)

    # RTN15h2i's DISCONNECTED is transient: RTN15a retries it immediately, and the
    # mock answers that retry with the cached token, so the state changes are
    # recorded and asserted on rather than waited for
    states = []
    client.connection.on(lambda change: states.append(change))

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    mock_ws.send_to_client_and_close(TOKEN_ERROR)

    await await_connection_state(client, ConnectionState.CONNECTING, timeout=5.0)

    disconnected = [change for change in states if change.current == ConnectionState.DISCONNECTED]
    assert len(disconnected) == 1
    assert len(calls) == 2
    assert disconnected[0].reason is not None
    assert client.connection.error_reason is not None


# UTS: realtime/unit/RTN15h3/non-token-error-resume-0
@deviation
async def test_rtn15h3_non_token_error_resume():
    connection_attempts = []

    def on_connection_attempt(conn):
        connection_attempts.append(conn)
        conn.respond_with_success(connected_message('connection-1', connectionKey='key-1'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, key='appId.keyId:keySecret')

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    original_connection_id = client.connection.connection_manager.connection_id

    mock_ws.send_to_client_and_close({
        'action': DISCONNECTED_ACTION,
        'error': {'code': 80003, 'statusCode': 503, 'message': 'Service unavailable'},
    })

    await await_connection_state(client, ConnectionState.CONNECTING, timeout=2.0)
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert client.connection.state == ConnectionState.CONNECTED
    assert client.connection.connection_manager.connection_id == original_connection_id
    assert len(connection_attempts) == 2
    assert connection_attempts[1].url.query_params['resume'] == 'key-1'


# UTS: realtime/unit/RTN15j/error-empty-channel-failed-0
async def test_rtn15j_error_empty_channel_failed():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected_message('connection-id', connectionKey='connection-key')),
    )
    client = realtime_client(mock_ws, key='appId.keyId:keySecret')

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    mock_ws.send_to_client_and_close(ERROR_MESSAGE(50000, 'Internal error'))

    await await_connection_state(client, ConnectionState.FAILED, timeout=2.0)

    assert client.connection.state == ConnectionState.FAILED
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 50000
    assert client.connection.error_reason.status_code == 500


# UTS: realtime/unit/RTN15a/unexpected-transport-disconnect-0
async def test_rtn15a_unexpected_transport_disconnect():
    connection_attempts = []

    def on_connection_attempt(conn):
        connection_attempts.append(conn)
        conn.respond_with_success(connected_message('connection-1', connectionKey='key-1'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, key='appId.keyId:keySecret')

    states = []
    client.connection.on(lambda change: states.append(change.current))

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    original_connection_id = client.connection.connection_manager.connection_id

    mock_ws.simulate_disconnect()

    # The specification awaits DISCONNECTED. RTN15a leaves it again through
    # `loop.call_soon`, so it is read from the recorded sequence
    await await_connection_state(client, ConnectionState.CONNECTING)
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert states == [
        ConnectionState.CONNECTING,
        ConnectionState.CONNECTED,
        ConnectionState.DISCONNECTED,
        ConnectionState.CONNECTING,
        ConnectionState.CONNECTED,
    ]
    assert client.connection.state == ConnectionState.CONNECTED
    assert client.connection.connection_manager.connection_id == original_connection_id
    assert len(connection_attempts) == 2


# UTS: realtime/unit/RTN15b/successful-resume-0
async def test_rtn15b_successful_resume():
    connection_attempts = []

    def on_connection_attempt(conn):
        connection_attempts.append(conn)
        if len(connection_attempts) == 1:
            conn.respond_with_success(connected_message('connection-1', connectionKey='key-1'))
        else:
            conn.respond_with_success(connected_message('connection-1', connectionKey='key-1-updated'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, key='appId.keyId:keySecret')

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert client.connection.connection_manager.connection_id == 'connection-1'

    mock_ws.simulate_disconnect()

    await await_connection_state(client, ConnectionState.CONNECTING)
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert client.connection.connection_manager.connection_id == 'connection-1'
    assert client.connection.connection_details.connection_key == 'key-1-updated'
    assert connection_attempts[1].url.query_params['resume'] == 'key-1'
    assert len(connection_attempts) == 2


# UTS: realtime/unit/RTN15c7/failed-resume-new-id-0
async def test_rtn15c7_failed_resume_new_id():
    connection_attempts = []

    def on_connection_attempt(conn):
        connection_attempts.append(conn)
        if len(connection_attempts) == 1:
            conn.respond_with_success(connected_message('connection-1', connectionKey='key-1'))
        else:
            message = connected_message('connection-2', connectionKey='key-2')
            message['error'] = {'code': 80008, 'statusCode': 400,
                                'message': 'Unable to recover connection'}
            conn.respond_with_success(message)

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, key='appId.keyId:keySecret')

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    original_connection_id = client.connection.connection_manager.connection_id

    mock_ws.simulate_disconnect()

    await await_connection_state(client, ConnectionState.CONNECTING)
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert client.connection.connection_manager.connection_id == 'connection-2'
    assert client.connection.connection_manager.connection_id != original_connection_id
    assert client.connection.connection_details.connection_key == 'key-2'
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 80008
    assert client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/unit/RTN15e/connection-key-updated-0
async def test_rtn15e_connection_key_updated():
    connection_attempts = []

    def on_connection_attempt(conn):
        connection_attempts.append(conn)
        if len(connection_attempts) == 1:
            conn.respond_with_success(connected_message('connection-1', connectionKey='key-1'))
        else:
            conn.respond_with_success(connected_message('connection-1', connectionKey='key-1-updated'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, key='appId.keyId:keySecret')

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    mock_ws.simulate_disconnect()

    await await_connection_state(client, ConnectionState.CONNECTING)
    await await_connection_state(client, ConnectionState.CONNECTED)

    # The specification reads `client.connection.key`; ably-python carries the
    # connection key on the connection details
    assert client.connection.connection_details.connection_key == 'key-1-updated'


# UTS: realtime/unit/RTN14h/resume-after-ttl-0
@deviation
async def test_rtn14h_resume_after_ttl():
    connection_attempts = []

    def on_connection_attempt(conn):
        connection_attempts.append(conn)
        if len(connection_attempts) == 1:
            conn.respond_with_success(
                connected_message('connection-1', connectionKey='key-1', connectionStateTtl=5000))
        else:
            conn.respond_with_refused()

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    clock = FakeClock()
    client = realtime_client(
        mock_ws, clock=clock, key='appId.keyId:keySecret',
        disconnected_retry_timeout=1000, suspended_retry_timeout=2000,
        # A refused connection reaches no failure path of its own, so each attempt
        # ends on the transition timer; a short one keeps the retry cycle turning
        realtime_request_timeout=1000,
    )

    states = []
    client.connection.on(lambda change: states.append(change.current))

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    mock_ws.simulate_disconnect()
    await settle()

    # The specification advances 15 times against a 5000ms connectionStateTtl.
    # ably-python suspends on the 120000ms default instead, so the window is
    # widened to reach the suspension the assertions are about
    for _ in range(60):
        await clock.advance(2500)

    assert ConnectionState.SUSPENDED in states

    reconnect_attempts = connection_attempts[1:]
    assert len(reconnect_attempts) > 0
    for attempt in reconnect_attempts:
        assert attempt.url.query_params['resume'] == 'key-1'


# UTS: realtime/unit/RTN15c5/token-error-during-resume-0
async def test_rtn15c5_token_error_during_resume():
    token_requests = []

    def on_request(request):
        if '/keys/' in request.path:
            token_requests.append(request)
            request.respond_with(200, token_response('renewed_token'))

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )

    connection_attempts = []

    def on_connection_attempt(conn):
        connection_attempts.append(conn)
        if len(connection_attempts) == 1:
            conn.respond_with_success(connected_message('connection-1', connectionKey='key-1'))
        elif len(connection_attempts) == 2:
            conn.respond_with_success()
            conn.send_to_client(ERROR_MESSAGE(40142, 'Token expired'))
        else:
            conn.respond_with_success(connected_message('connection-2', connectionKey='key-2'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    # A token error met while CONNECTING is retried on the retry timer rather than
    # immediately, so the retry interval is kept short
    client = realtime_client(mock_ws, mock_http=mock_http, key='appId.keyId:keySecret',
                             disconnected_retry_timeout=100)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    mock_ws.simulate_disconnect()

    await await_connection_state(client, ConnectionState.CONNECTING)
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=10.0)

    assert client.connection.state == ConnectionState.CONNECTED

    # UTS SPEC ERROR: as in RTN15h2's renewal test, the specification counts an
    # initial token request a key-authenticated client does not make
    assert len(token_requests) == 1

    assert len(connection_attempts) == 3


# UTS: realtime/unit/RTN15c4/fatal-error-during-resume-0
async def test_rtn15c4_fatal_error_during_resume():
    connection_attempts = []

    def on_connection_attempt(conn):
        connection_attempts.append(conn)
        if len(connection_attempts) == 1:
            conn.respond_with_success(connected_message('connection-1', connectionKey='key-1'))
        else:
            conn.respond_with_success()
            conn.send_to_client(ERROR_MESSAGE(50000, 'Internal server error'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, key='appId.keyId:keySecret')

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    mock_ws.simulate_disconnect()

    await await_connection_state(client, ConnectionState.FAILED)

    assert client.connection.state == ConnectionState.FAILED
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 50000
    assert len(connection_attempts) == 2
