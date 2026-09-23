"""Derived from uts/realtime/unit/auth/connection_auth_test.md in ably/specification.

Spec points: RTN2e, RTN27b, RSA4, RSA4c, RSA4c1, RSA4c2, RSA4c3, RSA4d, RSA8d, RSA12a
"""

import time

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.tokendetails import TokenDetails
from ably.util.exceptions import AblyException
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

AUTH_MESSAGE = {'action': int(ProtocolMessageAction.AUTH)}

# A retry far enough out that a DISCONNECTED connection does not reconnect
# behind the assertions.
NO_RECONNECT = 60000


def now():
    return int(time.time() * 1000)


def connect_successfully(connection_id='connection-id', connection_key='connection-key'):
    """A handler that completes the attempt and sends CONNECTED behind it."""
    message = connected_message(connection_id, connectionKey=connection_key)

    def on_connection_attempt(conn):
        conn.respond_with_success(message)

    return on_connection_attempt


async def poll_until(condition, timeout=5.0, description='condition'):
    """Waits for `condition` to hold, yielding to the event loop between checks.

    This is the specifications' `AWAIT UNTIL`. The auth paths chain tasks
    several levels deep, so a single yield is not enough to see the result of
    one; the deadline is a safety net, not a delay.
    """
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f'Timed out waiting for {description}')
        await settle(passes=5)


# UTS: realtime/unit/RTN2e/token-before-websocket-0
async def test_rtn2e_token_before_websocket():
    callback_invoked = False
    callback_invoked_time = None
    connection_attempt_time = None
    captured_ws_url = None

    async def auth_callback(params):
        nonlocal callback_invoked, callback_invoked_time
        callback_invoked = True
        callback_invoked_time = time.monotonic()
        return TokenDetails(token='callback-provided-token', expires=now() + 3600000)

    def on_connection_attempt(conn):
        nonlocal connection_attempt_time, captured_ws_url
        connection_attempt_time = time.monotonic()
        captured_ws_url = conn.url
        conn.respond_with_success(connected_message('connection-id', connectionKey='connection-key'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, auth_callback=auth_callback)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert callback_invoked is True
    assert callback_invoked_time < connection_attempt_time
    assert captured_ws_url.query_params['accessToken'] == 'callback-provided-token'
    assert captured_ws_url.query_params.get('key') is None
    assert client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/unit/RTN2e/callback-error-prevents-connect-1
async def test_rtn2e_callback_error_prevents_connect():
    connection_attempted = False

    async def auth_callback(params):
        raise Exception('Auth callback failed')

    def on_connection_attempt(conn):
        nonlocal connection_attempted
        connection_attempted = True
        conn.respond_with_success(connected_message('connection-id', connectionKey='connection-key'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, auth_callback=auth_callback, disconnected_retry_timeout=NO_RECONNECT)

    client.connect()
    await await_connection_state(client, ConnectionState.DISCONNECTED)

    assert connection_attempted is False
    assert client.connection.error_reason is not None
    assert (client.connection.error_reason.status_code == 401
            or client.connection.error_reason.code == 40170)


# UTS: realtime/unit/RTN2e/callback-params-include-clientid-2
@deviation
async def test_rtn2e_callback_params_include_clientid():
    received_params = None

    async def auth_callback(params):
        nonlocal received_params
        received_params = params
        return TokenDetails(token='token-for-client', expires=now() + 3600000, client_id='my-client-id')

    mock_ws = MockWebSocket(on_connection_attempt=connect_successfully())
    client = realtime_client(mock_ws, auth_callback=auth_callback, client_id='my-client-id')

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert received_params is not None
    # `TokenParams` is a plain dict here, and ably-python spells its members
    # snake_case throughout, so `client_id` is the idiomatic rendering of the
    # specification's `clientId`. The deviation is that the member is absent:
    # `Auth.__init__` leaves `client_id` unset on a realtime client, so
    # `_ensure_valid_auth_credentials` never puts it in the token params.
    assert received_params['client_id'] == 'my-client-id'


# UTS: realtime/unit/RTN2e/reuse-valid-token-3
async def test_rtn2e_reuse_valid_token():
    callback_count = 0

    async def auth_callback(params):
        nonlocal callback_count
        callback_count += 1
        return TokenDetails(token='reusable-token', expires=now() + 3600000)

    mock_ws = MockWebSocket(on_connection_attempt=connect_successfully())
    client = realtime_client(mock_ws, auth_callback=auth_callback)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await client.close()
    assert client.connection.state == ConnectionState.CLOSED

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert callback_count == 1


# UTS: realtime/unit/RSA4c2/callback-error-causes-disconnected-0
async def test_rsa4c2_callback_error_causes_disconnected():
    auth_callback_count = 0

    async def auth_callback(params):
        nonlocal auth_callback_count
        auth_callback_count += 1
        if auth_callback_count == 1:
            raise AblyException('Auth server unavailable', 500, 50000)
        return TokenDetails(token=f'valid-token-{auth_callback_count}', expires=now() + 3600000)

    mock_ws = MockWebSocket(on_connection_attempt=connect_successfully())
    client = realtime_client(mock_ws, auth_callback=auth_callback, disconnected_retry_timeout=NO_RECONNECT)

    client.connect()
    await await_connection_state(client, ConnectionState.DISCONNECTED)

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 80019
    assert client.connection.error_reason.status_code == 401
    # RSA4c1 requires `cause` to carry the underlying 50000 error.
    # `ConnectionManager.on_error_from_authorize` builds the 80019 without one,
    # so the callback's own error is only in the log.
    assert client.connection.error_reason.cause is None


# UTS: realtime/unit/RSA4c3/callback-error-stays-connected-0
@deviation
async def test_rsa4c3_callback_error_stays_connected():
    auth_callback_count = 0

    async def auth_callback(params):
        nonlocal auth_callback_count
        auth_callback_count += 1
        if auth_callback_count == 1:
            return TokenDetails(token='initial-token', expires=now() + 3600000)
        raise AblyException('Auth server unavailable', 500, 50000)

    mock_ws = MockWebSocket(on_connection_attempt=connect_successfully())
    client = realtime_client(mock_ws, auth_callback=auth_callback)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    state_changes = []
    client.connection.on(lambda change: state_changes.append(change))

    mock_ws.send_to_client(AUTH_MESSAGE)

    await poll_until(lambda: client.connection.error_reason is not None,
                     description='errorReason to be set')

    assert client.connection.state == ConnectionState.CONNECTED

    non_connected_changes = [c for c in state_changes if c.current != ConnectionState.CONNECTED]
    assert non_connected_changes == []

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 80019
    assert client.connection.error_reason.status_code == 401
    assert client.connection.error_reason.cause is not None
    assert client.connection.error_reason.cause.code == 50000


# UTS: realtime/unit/RSA4d/callback-403-causes-failed-0
@deviation
async def test_rsa4d_callback_403_causes_failed():
    async def auth_callback(params):
        raise AblyException('Account disabled', 403, 40300)

    mock_ws = MockWebSocket(on_connection_attempt=connect_successfully())
    client = realtime_client(mock_ws, auth_callback=auth_callback, disconnected_retry_timeout=NO_RECONNECT)

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED)

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 80019
    assert client.connection.error_reason.status_code == 403
    assert client.connection.error_reason.cause is not None
    assert client.connection.error_reason.cause.code == 40300


# UTS: realtime/unit/RSA4d/callback-403-reauth-causes-failed-1
@deviation
async def test_rsa4d_callback_403_reauth_causes_failed():
    auth_callback_count = 0

    async def auth_callback(params):
        nonlocal auth_callback_count
        auth_callback_count += 1
        if auth_callback_count == 1:
            return TokenDetails(token='initial-token', expires=now() + 3600000)
        raise AblyException('Account suspended', 403, 40300)

    mock_ws = MockWebSocket(on_connection_attempt=connect_successfully())
    client = realtime_client(mock_ws, auth_callback=auth_callback, disconnected_retry_timeout=NO_RECONNECT)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    mock_ws.send_to_client(AUTH_MESSAGE)

    await await_connection_state(client, ConnectionState.FAILED)

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 80019
    assert client.connection.error_reason.status_code == 403
    assert client.connection.error_reason.cause is not None
    assert client.connection.error_reason.cause.code == 40300
