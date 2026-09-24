"""Derived from uts/realtime/unit/connection/error_reason_test.md in ably/specification.

Spec points: RTN25
"""

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')


def error_message(code, status_code, message):
    return {
        'action': int(ProtocolMessageAction.ERROR),
        'error': {'code': code, 'statusCode': status_code, 'message': message},
    }


def send_error_and_close(error):
    def on_connection_attempt(conn):
        conn.respond_with_success()
        conn.send_to_client_and_close(error)

    return on_connection_attempt


# UTS: realtime/unit/RTN25/error-reason-on-failed-0
async def test_rtn25_error_reason_on_failed():
    mock_ws = MockWebSocket(
        on_connection_attempt=send_error_and_close(error_message(40005, 400, 'Invalid API key')),
    )
    client = realtime_client(mock_ws, key='invalid.key:secret')

    assert client.connection.error_reason is None

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED)

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 40005
    assert client.connection.error_reason.status_code == 400
    assert client.connection.error_reason.message == 'Invalid API key'


# UTS: realtime/unit/RTN25/error-reason-disconnected-1
async def test_rtn25_error_reason_disconnected():
    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: conn.respond_with_refused())
    # A refused connect reaches DISCONNECTED when the connecting transition
    # timer expires, so a short request timeout keeps that wait small
    client = realtime_client(mock_ws, realtime_request_timeout=300)

    client.connect()
    await await_connection_state(client, ConnectionState.DISCONNECTED)

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.message is not None


# UTS: realtime/unit/RTN25/error-reason-suspended-2
async def test_rtn25_error_reason_suspended():
    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: conn.respond_with_refused())
    clock = FakeClock()
    client = realtime_client(mock_ws, clock=clock, disconnected_retry_timeout=500)

    client.connect()
    await settle()

    # UTS SPEC ERROR: the specification advances past a 5000 ms
    # connectionStateTtl. The interval the library suspends on is
    # `Defaults.connection_state_ttl`, 120000 ms, which is also the default
    # `features.md` gives for the attribute; 5000 ms would never suspend.
    await clock.advance(120100)

    assert client.connection.state == ConnectionState.SUSPENDED
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.message is not None


# UTS: realtime/unit/RTN25/error-reason-token-error-3
async def test_rtn25_error_reason_token_error():
    mock_ws = MockWebSocket(
        on_connection_attempt=send_error_and_close(error_message(40142, 401, 'Token expired')),
    )
    client = realtime_client(mock_ws, token='expired_token')

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED)

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 40171


# UTS: realtime/unit/RTN25/error-reason-cleared-on-connect-4
async def test_rtn25_error_reason_cleared_on_connect():
    attempts = []

    def on_connection_attempt(conn):
        attempts.append(conn)
        if len(attempts) == 1:
            conn.respond_with_refused()
        else:
            conn.respond_with_success(CONNECTED_MESSAGE)

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    clock = FakeClock()
    client = realtime_client(
        mock_ws, clock=clock, disconnected_retry_timeout=100, realtime_request_timeout=300)

    client.connect()
    await settle()
    await clock.advance(300)

    assert client.connection.state == ConnectionState.DISCONNECTED
    failure_error = client.connection.error_reason
    assert failure_error is not None

    await clock.advance(150)
    await await_connection_state(client, ConnectionState.CONNECTED)

    # The specification asserts errorReason is null once connected while
    # allowing an implementation to keep the last error instead. ably-python
    # keeps it: `Connection` only ever replaces `error_reason` with a non-null
    # reason, and clears it in `connect()`, which a retry does not go through.
    assert client.connection.error_reason is failure_error


# UTS: realtime/unit/RTN25/error-reason-protocol-error-5
async def test_rtn25_error_reason_protocol_error():
    mock_ws = MockWebSocket(
        on_connection_attempt=send_error_and_close(
            error_message(50000, 500, 'Internal server error')),
    )
    client = realtime_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED)

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 50000
    assert client.connection.error_reason.status_code == 500
    assert client.connection.error_reason.message == 'Internal server error'


# UTS: realtime/unit/RTN25/error-reason-in-state-change-6
async def test_rtn25_error_reason_in_state_change():
    mock_ws = MockWebSocket(
        on_connection_attempt=send_error_and_close(
            error_message(40003, 400, 'Access token invalid')),
    )
    client = realtime_client(mock_ws)

    state_changes = []

    # `EventEmitter.on` tests its listener with `inspect.isfunction`, so a
    # bound built-in such as `list.append` is rejected
    def on_failed(change):
        state_changes.append(change)

    client.connection.on(ConnectionState.FAILED, on_failed)

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED)
    await settle()

    assert len(state_changes) == 1

    change = state_changes[0]

    assert change.reason is not None
    assert change.reason.code == 40003
    assert change.reason.status_code == 400
    assert change.reason.message == 'Access token invalid'

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == change.reason.code
    assert client.connection.error_reason.message == change.reason.message
