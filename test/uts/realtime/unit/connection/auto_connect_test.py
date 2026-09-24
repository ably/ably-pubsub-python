"""Derived from uts/realtime/unit/connection/auto_connect_test.md in ably/specification.

Spec points: RTN3
"""

from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import settle
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')


# UTS: realtime/unit/RTN3/auto-connect-true-0
async def test_rtn3_auto_connect_true():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    # `auto_connect` is the option's own default, and this test is about the
    # default, so it is named rather than left to `realtime_client`
    client = realtime_client(mock_ws, auto_connect=True)

    await await_connection_state(client, ConnectionState.CONNECTED)

    assert client.connection.state == ConnectionState.CONNECTED
    # The specification asserts `client.connection.id`; ably-python exposes the
    # connection id on the connection manager instead
    assert client.connection.connection_manager.connection_id == 'connection-id'


# UTS: realtime/unit/RTN3/auto-connect-false-1
async def test_rtn3_auto_connect_false():
    connection_attempted = []

    def on_connection_attempt(conn):
        connection_attempted.append(conn)
        conn.respond_with_success(CONNECTED_MESSAGE)

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, auto_connect=False)

    await settle()

    assert connection_attempted == []
    assert client.connection.state == ConnectionState.INITIALIZED


# UTS: realtime/unit/RTN3/explicit-connect-after-false-2
async def test_rtn3_explicit_connect_after_false():
    connection_attempted = []

    def on_connection_attempt(conn):
        connection_attempted.append(conn)
        conn.respond_with_success(CONNECTED_MESSAGE)

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, auto_connect=False)

    assert client.connection.state == ConnectionState.INITIALIZED
    assert connection_attempted == []

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert len(connection_attempted) == 1
    assert client.connection.state == ConnectionState.CONNECTED
