"""Derived from uts/realtime/unit/connection/connection_id_key_test.md in ably/specification.

Spec points: RTN8, RTN8a, RTN8b, RTN8d, RTN9, RTN9a, RTN9b, RTN9d
"""

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

FATAL_ERROR_MESSAGE = {
    'action': int(ProtocolMessageAction.ERROR),
    'error': {'code': 80000, 'statusCode': 400, 'message': 'Fatal error'},
}


def connection_id(client):
    """The specifications' `connection.id`.

    ably-python has no `Connection#id`; the value the CONNECTED message carries
    is held on the connection manager. See
    [deviations.md](../../../deviations.md).
    """
    return client.connection.connection_manager.connection_id


def connection_key(client):
    """The specifications' `connection.key`.

    ably-python has no `Connection#key`; the value is reached through the
    connection details, which are themselves cleared whenever the key would be.
    See [deviations.md](../../../deviations.md).
    """
    details = client.connection.connection_details
    return details.connection_key if details is not None else None


def respond_with(connection_id, connection_key):
    def on_connection_attempt(conn):
        conn.respond_with_success(connected_message(connection_id, connectionKey=connection_key))

    return on_connection_attempt


def respond_with_numbered(attempts):
    """Hands each successive attempt its own connection id and key."""

    def on_connection_attempt(conn):
        attempts.append(conn)
        index = len(attempts)
        conn.respond_with_success(
            connected_message(f'conn-id-{index}', connectionKey=f'conn-key-{index}'))

    return on_connection_attempt


# UTS: realtime/unit/RTN8a/id-unset-until-connected-0
async def test_rtn8a_id_unset_until_connected():
    mock_ws = MockWebSocket(on_connection_attempt=respond_with('unique-conn-id-1', 'conn-key-1'))
    client = realtime_client(mock_ws)

    assert connection_id(client) is None

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert connection_id(client) == 'unique-conn-id-1'


# UTS: realtime/unit/RTN9a/key-unset-until-connected-0
async def test_rtn9a_key_unset_until_connected():
    mock_ws = MockWebSocket(on_connection_attempt=respond_with('unique-conn-id-1', 'conn-key-1'))
    client = realtime_client(mock_ws)

    assert connection_key(client) is None

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert connection_key(client) == 'conn-key-1'


# UTS: realtime/unit/RTN8b/id-unique-per-connection-0
async def test_rtn8b_id_unique_per_connection():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=respond_with_numbered(attempts))
    client1 = realtime_client(mock_ws)
    client2 = realtime_client(mock_ws)

    client1.connect()
    await await_connection_state(client1, ConnectionState.CONNECTED)

    client2.connect()
    await await_connection_state(client2, ConnectionState.CONNECTED)

    assert connection_id(client1) != connection_id(client2)
    assert connection_id(client1) == 'conn-id-1'
    assert connection_id(client2) == 'conn-id-2'


# UTS: realtime/unit/RTN9b/key-unique-per-connection-0
async def test_rtn9b_key_unique_per_connection():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=respond_with_numbered(attempts))
    client1 = realtime_client(mock_ws)
    client2 = realtime_client(mock_ws)

    client1.connect()
    await await_connection_state(client1, ConnectionState.CONNECTED)

    client2.connect()
    await await_connection_state(client2, ConnectionState.CONNECTED)

    assert connection_key(client1) != connection_key(client2)
    assert connection_key(client1) == 'conn-key-1'
    assert connection_key(client2) == 'conn-key-2'


# UTS: realtime/unit/RTN8d/id-null-after-closed-0
async def test_rtn8d_id_null_after_closed():
    mock_ws = MockWebSocket(on_connection_attempt=respond_with('conn-id-1', 'conn-key-1'))
    client = realtime_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert connection_id(client) == 'conn-id-1'

    await client.close()
    await await_connection_state(client, ConnectionState.CLOSED)

    assert connection_id(client) is None


# UTS: realtime/unit/RTN9d/key-null-after-closed-0
async def test_rtn9d_key_null_after_closed():
    mock_ws = MockWebSocket(on_connection_attempt=respond_with('conn-id-1', 'conn-key-1'))
    client = realtime_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert connection_key(client) == 'conn-key-1'

    await client.close()
    await await_connection_state(client, ConnectionState.CLOSED)

    assert connection_key(client) is None


# UTS: realtime/unit/RTN8d/id-key-null-after-failed-1
async def test_rtn8d_id_key_null_after_failed():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_error(FATAL_ERROR_MESSAGE),
    )
    client = realtime_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED)

    assert connection_id(client) is None
    assert connection_key(client) is None


# UTS: realtime/unit/RTN8d/id-key-retained-in-suspended-2
@deviation
async def test_rtn8d_id_key_retained_in_suspended():
    attempts = []

    def on_connection_attempt(conn):
        attempts.append(conn)
        if len(attempts) == 1:
            conn.respond_with_success(connected_message('conn-id-1', connectionKey='conn-key-1'))
        else:
            conn.respond_with_refused()

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    clock = FakeClock()
    client = realtime_client(
        mock_ws, clock=clock, disconnected_retry_timeout=1000, suspended_retry_timeout=100)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert connection_id(client) == 'conn-id-1'
    assert connection_key(client) == 'conn-key-1'

    # The retry that follows SUSPENDED leaves that state again within the
    # window being advanced, so the id and key are read as the connection
    # enters SUSPENDED rather than once the window has run out
    at_suspended = {}

    def on_suspended(change):
        at_suspended['id'] = connection_id(client)
        at_suspended['key'] = connection_key(client)

    client.connection.once(ConnectionState.SUSPENDED, on_suspended)

    mock_ws.simulate_disconnect()
    await settle()
    await clock.advance(121000)

    assert at_suspended, 'the connection never reached SUSPENDED'
    assert at_suspended['id'] == 'conn-id-1'
    assert at_suspended['key'] == 'conn-key-1'
