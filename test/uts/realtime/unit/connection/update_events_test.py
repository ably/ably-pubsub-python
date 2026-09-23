"""Derived from uts/realtime/unit/connection/update_events_test.md in ably/specification.

Spec points: RTN24
"""

from ably.realtime.connection import ConnectionState
from ably.types.connectionstate import ConnectionEvent
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

# Every connection state, for the specification's "subscribe to everything and
# count what arrives"
CONNECTION_STATES = (
    ConnectionState.INITIALIZED,
    ConnectionState.CONNECTING,
    ConnectionState.CONNECTED,
    ConnectionState.DISCONNECTED,
    ConnectionState.SUSPENDED,
    ConnectionState.CLOSING,
    ConnectionState.CLOSED,
    ConnectionState.FAILED,
)


def connection_id(client):
    """The specifications' `connection.id`; ably-python keeps it on the
    connection manager. See [deviations.md](../../../deviations.md)."""
    return client.connection.connection_manager.connection_id


def connection_key(client):
    """The specifications' `connection.key`; ably-python reaches it through the
    connection details. See [deviations.md](../../../deviations.md)."""
    details = client.connection.connection_details
    return details.connection_key if details is not None else None


def respond_with(message):
    def on_connection_attempt(conn):
        conn.respond_with_success(message)

    return on_connection_attempt


# UTS: realtime/unit/RTN24/connected-emits-update-0
async def test_rtn24_connected_emits_update():
    first = connected_message(
        'connection-id-1', connectionKey='connection-key-1', clientId='client-123')
    mock_ws = MockWebSocket(on_connection_attempt=respond_with(first))
    client = realtime_client(mock_ws)

    connected_events = []
    update_events = []

    def on_connected(change):
        connected_events.append(change)

    def on_update(change):
        update_events.append(change)

    client.connection.on(ConnectionState.CONNECTED, on_connected)
    client.connection.on(ConnectionEvent.UPDATE, on_update)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await settle()

    assert len(connected_events) == 1
    assert len(update_events) == 0

    # connectionId is a top-level ProtocolMessage field rather than part of
    # connectionDetails, so it does not change for an in-progress connection
    mock_ws.send_to_client(connected_message(
        'connection-id-1', connectionKey='connection-key-1', clientId='client-123',
        maxIdleInterval=20000))
    await settle()

    assert client.connection.state == ConnectionState.CONNECTED
    assert len(connected_events) == 1
    assert len(update_events) == 1

    update_change = update_events[0]

    assert update_change.previous == ConnectionState.CONNECTED
    assert update_change.current == ConnectionState.CONNECTED
    assert update_change.reason is None

    assert connection_id(client) == 'connection-id-1'
    assert connection_key(client) == 'connection-key-1'


# UTS: realtime/unit/RTN24/update-event-with-error-1
@deviation
async def test_rtn24_update_event_with_error():
    first = connected_message('connection-id-1', connectionKey='connection-key-1')
    mock_ws = MockWebSocket(on_connection_attempt=respond_with(first))
    client = realtime_client(mock_ws)

    update_events = []

    def on_update(change):
        update_events.append(change)

    client.connection.on(ConnectionEvent.UPDATE, on_update)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await settle()

    renewed = connected_message('connection-id-1', connectionKey='connection-key-1')
    renewed['error'] = {
        'code': 40142, 'statusCode': 401, 'message': 'Token expired; renewed automatically'}
    mock_ws.send_to_client(renewed)
    await settle()

    assert len(update_events) == 1

    update_change = update_events[0]

    assert update_change.previous == ConnectionState.CONNECTED
    assert update_change.current == ConnectionState.CONNECTED
    assert update_change.reason is not None
    assert update_change.reason.code == 40142
    assert update_change.reason.status_code == 401
    assert 'Token expired' in update_change.reason.message


# UTS: realtime/unit/RTN24/connection-details-override-2
async def test_rtn24_connection_details_override():
    first = connected_message(
        'connection-id-1', connectionKey='connection-key-1', maxIdleInterval=10000,
        connectionStateTtl=60000, maxMessageSize=16384, serverId='server-1',
        clientId='client-original')
    mock_ws = MockWebSocket(on_connection_attempt=respond_with(first))
    client = realtime_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await settle()

    assert connection_id(client) == 'connection-id-1'
    assert connection_key(client) == 'connection-key-1'

    # UTS SPEC ERROR: the specification's second message also changes clientId,
    # which no CONNECTED for an in-progress connection does, and which RSA15
    # makes immutable once configured. The clientId is held at the value the
    # first message established so that the override the test is about — the
    # operational parameters — is what it exercises.
    mock_ws.send_to_client(connected_message(
        'connection-id-1', connectionKey='connection-key-1', maxIdleInterval=20000,
        connectionStateTtl=120000, maxMessageSize=32768, serverId='server-2',
        clientId='client-original'))
    await settle()

    assert connection_id(client) == 'connection-id-1'
    assert connection_key(client) == 'connection-key-1'

    # The specification leaves the accessors for the overridden details open.
    # ably-python keeps them on `Connection#connection_details`, which parses
    # connectionStateTtl, maxIdleInterval, connectionKey and clientId only.
    details = client.connection.connection_details

    assert details.max_idle_interval == 20000
    assert details.connection_state_ttl == 120000

    assert client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/unit/RTN24/no-duplicate-connected-event-3
async def test_rtn24_no_duplicate_connected_event():
    first = connected_message('connection-id-1', connectionKey='connection-key-1')
    mock_ws = MockWebSocket(on_connection_attempt=respond_with(first))
    client = realtime_client(mock_ws)

    all_events = []

    def record_state(state):
        def on_state(change):
            all_events.append({'type': 'state', 'state': state, 'change': change})

        return on_state

    for state in CONNECTION_STATES:
        client.connection.on(state, record_state(state))

    def on_update(change):
        all_events.append({'type': 'update', 'change': change})

    client.connection.on(ConnectionEvent.UPDATE, on_update)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await settle()

    initial_event_count = len(all_events)

    for _ in range(3):
        mock_ws.send_to_client(
            connected_message('connection-id-1', connectionKey='connection-key-1'))
        await settle()

    new_events = all_events[initial_event_count:]

    assert len(new_events) == 3

    for event in new_events:
        assert event['type'] == 'update'
        assert event['change'].previous == ConnectionState.CONNECTED
        assert event['change'].current == ConnectionState.CONNECTED

    connected_state_events = [
        event for event in all_events
        if event['type'] == 'state' and event['state'] == ConnectionState.CONNECTED
    ]

    assert len(connected_state_events) == 1
