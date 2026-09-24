"""Derived from uts/realtime/unit/channels/message_field_population.md in ably/specification.

Spec points: TM2a, TM2c, TM2f
"""

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from test.uts.helpers.client import (
    await_connection_state,
    poll_until,
    realtime_client,
)
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import MockWebSocket, attached_message, connected_message

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')


def message_protocol_message(channel_name, messages, **fields):
    """A MESSAGE protocol message carrying `messages` on `channel_name`."""
    return {
        'action': int(ProtocolMessageAction.MESSAGE),
        'channel': channel_name,
        'messages': messages,
        **fields,
    }


def attaching_mock(channel_name):
    """A mock which connects and confirms an attach for `channel_name`."""
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    return mock_ws


async def subscribed_channel(mock_ws, channel_name, received):
    """A connected client whose `channel_name` is attached with `received` subscribed.

    The specification subscribes before connecting; `subscribe` here awaits the
    implicit attach, which needs a connection, so the client connects first.
    """
    client = realtime_client(mock_ws)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    channel = client.channels.get(channel_name)

    def record(message):
        received.append(message)

    await channel.subscribe(record)
    return client, channel


# UTS: realtime/unit/TM2a/id-from-protocol-message-0
async def test_tm2a_id_from_protocol_message():
    channel_name = 'test-TM2a-id'
    received = []

    mock_ws = attaching_mock(channel_name)
    await subscribed_channel(mock_ws, channel_name, received)

    mock_ws.send_to_client(message_protocol_message(
        channel_name,
        [
            {'name': 'first', 'data': 'a'},
            {'name': 'second', 'data': 'b'},
            {'name': 'third', 'data': 'c'},
        ],
        id='abc123:5',
        connectionId='abc123',
        timestamp=1700000000000,
    ))
    await poll_until(lambda: len(received) == 3, description='three messages are delivered')

    assert received[0].id == 'abc123:5:0'
    assert received[1].id == 'abc123:5:1'
    assert received[2].id == 'abc123:5:2'


# UTS: realtime/unit/TM2a/existing-id-not-overwritten-1
async def test_tm2a_existing_id_not_overwritten():
    channel_name = 'test-TM2a-existing'
    received = []

    mock_ws = attaching_mock(channel_name)
    await subscribed_channel(mock_ws, channel_name, received)

    mock_ws.send_to_client(message_protocol_message(
        channel_name,
        [{'id': 'my-custom-id', 'name': 'msg', 'data': 'hello'}],
        id='proto-id:0',
    ))
    await poll_until(lambda: len(received) == 1, description='the message is delivered')

    assert received[0].id == 'my-custom-id'


# UTS: realtime/unit/TM2a/no-id-without-protocol-id-2
@deviation
async def test_tm2a_no_id_without_protocol_id():
    channel_name = 'test-TM2a-no-proto-id'
    received = []

    mock_ws = attaching_mock(channel_name)
    await subscribed_channel(mock_ws, channel_name, received)

    mock_ws.send_to_client(message_protocol_message(
        channel_name,
        [{'name': 'msg', 'data': 'hello'}],
        connectionId='abc123',
    ))
    await poll_until(lambda: len(received) == 1, description='the message is delivered')

    assert received[0].id is None


# UTS: realtime/unit/TM2c/connectionid-from-protocol-0
async def test_tm2c_connectionid_from_protocol():
    channel_name = 'test-TM2c-connId'
    received = []

    mock_ws = attaching_mock(channel_name)
    await subscribed_channel(mock_ws, channel_name, received)

    mock_ws.send_to_client(message_protocol_message(
        channel_name,
        [{'name': 'msg', 'data': 'hello'}],
        id='msg:0',
        connectionId='server-conn-xyz',
    ))
    await poll_until(lambda: len(received) == 1, description='the message is delivered')

    assert received[0].connection_id == 'server-conn-xyz'


# UTS: realtime/unit/TM2c/existing-connectionid-kept-1
async def test_tm2c_existing_connectionid_kept():
    channel_name = 'test-TM2c-existing'
    received = []

    mock_ws = attaching_mock(channel_name)
    await subscribed_channel(mock_ws, channel_name, received)

    mock_ws.send_to_client(message_protocol_message(
        channel_name,
        [{'connectionId': 'msg-conn', 'name': 'msg', 'data': 'hello'}],
        id='msg:0',
        connectionId='proto-conn',
    ))
    await poll_until(lambda: len(received) == 1, description='the message is delivered')

    assert received[0].connection_id == 'msg-conn'


# UTS: realtime/unit/TM2f/timestamp-from-protocol-0
async def test_tm2f_timestamp_from_protocol():
    channel_name = 'test-TM2f-timestamp'
    received = []

    mock_ws = attaching_mock(channel_name)
    await subscribed_channel(mock_ws, channel_name, received)

    mock_ws.send_to_client(message_protocol_message(
        channel_name,
        [{'name': 'msg', 'data': 'hello'}],
        id='msg:0',
        timestamp=1700000000000,
    ))
    await poll_until(lambda: len(received) == 1, description='the message is delivered')

    assert received[0].timestamp == 1700000000000


# UTS: realtime/unit/TM2f/existing-timestamp-kept-1
async def test_tm2f_existing_timestamp_kept():
    channel_name = 'test-TM2f-existing'
    received = []

    mock_ws = attaching_mock(channel_name)
    await subscribed_channel(mock_ws, channel_name, received)

    mock_ws.send_to_client(message_protocol_message(
        channel_name,
        [{'timestamp': 1600000000000, 'name': 'msg', 'data': 'hello'}],
        id='msg:0',
        timestamp=1700000000000,
    ))
    await poll_until(lambda: len(received) == 1, description='the message is delivered')

    assert received[0].timestamp == 1600000000000


# UTS: realtime/unit/TM2a/all-fields-populated-together-3
async def test_tm2a_all_fields_populated_together():
    channel_name = 'test-TM2-all-fields'
    received = []

    mock_ws = attaching_mock(channel_name)
    await subscribed_channel(mock_ws, channel_name, received)

    mock_ws.send_to_client(message_protocol_message(
        channel_name,
        [
            {'name': 'first', 'data': 'a'},
            {'name': 'second', 'data': 'b'},
        ],
        id='connId:7',
        connectionId='connId',
        timestamp=1700000000000,
    ))
    await poll_until(lambda: len(received) == 2, description='two messages are delivered')

    assert received[0].id == 'connId:7:0'
    assert received[0].connection_id == 'connId'
    assert received[0].timestamp == 1700000000000
    assert received[0].name == 'first'
    assert received[0].data == 'a'

    assert received[1].id == 'connId:7:1'
    assert received[1].connection_id == 'connId'
    assert received[1].timestamp == 1700000000000
    assert received[1].name == 'second'
    assert received[1].data == 'b'
