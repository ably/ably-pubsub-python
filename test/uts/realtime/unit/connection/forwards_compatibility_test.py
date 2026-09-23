"""Derived from uts/realtime/unit/connection/forwards_compatibility_test.md in ably/specification.

Spec points: RTF1, RSF1

The specification injects its raw frames with `send_to_client_raw`, to keep a
ProtocolMessage constructor from stripping the unknown fields. Here a message is a
plain dictionary all the way to the wire, so `send_to_client` carries the unknown
fields as written and no separate method is needed.
"""

from ably.realtime.channel import ChannelState
from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import settle
from test.uts.helpers.mock_websocket import HEARTBEAT_MESSAGE, MockWebSocket, connected_message

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')

MESSAGE_ACTION = int(ProtocolMessageAction.MESSAGE)


def attach_responder(mock_ws):
    """Answers every ATTACH the client sends with an ATTACHED for that channel."""
    def on_message_from_client(message):
        if message.get('action') == int(ProtocolMessageAction.ATTACH):
            mock_ws.send_to_client({
                'action': int(ProtocolMessageAction.ATTACHED),
                'channel': message.get('channel'),
                'flags': 0,
            })
    return on_message_from_client


# UTS: realtime/unit/RTF1/unrecognised-attributes-ignored-0
async def test_rtf1_unrecognised_attributes_ignored():
    channel_name = 'test-RTF1-extra-attrs'
    received_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = attach_responder(mock_ws)
    client = realtime_client(mock_ws, key='appId.keyId:keySecret', use_binary_protocol=False)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    channel = client.channels.get(channel_name)
    # ably-python's `subscribe` attaches and resolves once attached, so it stands in
    # for the specification's `subscribe` followed by `attach`
    await channel.subscribe(lambda message: received_messages.append(message))

    assert channel.state == ChannelState.ATTACHED

    mock_ws.send_to_client({
        'action': MESSAGE_ACTION,
        'channel': channel_name,
        'messages': [
            {
                'name': 'test-event',
                'data': 'hello',
                'serial': 'msg-serial-1',
            },
        ],
        'unknownField1': 'some-future-value',
        'unknownField2': 42,
        'unknownNestedObject': {'nestedKey': 'nestedValue'},
        'unknownArray': [1, 2, 3],
    })

    await settle()

    assert len(received_messages) == 1
    assert received_messages[0].name == 'test-event'
    assert received_messages[0].data == 'hello'

    assert client.connection.state == ConnectionState.CONNECTED
    assert channel.state == ChannelState.ATTACHED


# UTS: realtime/unit/RTF1/unknown-action-handled-1
async def test_rtf1_unknown_action_handled():
    channel_name = 'test-RTF1-unknown-action'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(message):
        # Echoing the ping's heartbeat is what shows the read loop still carrying
        # messages after the unknown action
        if message.get('action') == int(ProtocolMessageAction.HEARTBEAT):
            mock_ws.send_to_client({'action': int(ProtocolMessageAction.HEARTBEAT),
                                    'id': message.get('id')})

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(mock_ws, key='appId.keyId:keySecret', use_binary_protocol=False)

    state_changes = []
    client.connection.on(lambda change: state_changes.append(change.current))

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    # Action 254 is not defined in the current specification
    mock_ws.send_to_client({
        'action': 254,
        'channel': channel_name,
        'unknownPayload': 'future-feature-data',
    })

    mock_ws.send_to_client(HEARTBEAT_MESSAGE)

    await settle()
    await client.connection.ping()

    assert client.connection.state == ConnectionState.CONNECTED
    assert state_changes == [ConnectionState.CONNECTING, ConnectionState.CONNECTED]
    assert ConnectionState.DISCONNECTED not in state_changes
    assert ConnectionState.FAILED not in state_changes


# UTS: realtime/unit/RSF1/message-unrecognised-attrs-0
async def test_rsf1_message_unrecognised_attrs():
    channel_name = 'test-RSF1-extra-attrs'
    received_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = attach_responder(mock_ws)
    client = realtime_client(mock_ws, key='appId.keyId:keySecret', use_binary_protocol=False)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    channel = client.channels.get(channel_name)
    await channel.subscribe(lambda message: received_messages.append(message))

    assert channel.state == ChannelState.ATTACHED

    mock_ws.send_to_client({
        'action': MESSAGE_ACTION,
        'channel': channel_name,
        'messages': [
            {
                'name': 'event-1',
                'data': 'payload-1',
                'serial': 'serial-1',
                'futureField': 'future-value',
                'futureNumber': 99,
                'futureObject': {'nested': True},
            },
            {
                'name': 'event-2',
                'data': 'payload-2',
                'serial': 'serial-2',
                'anotherUnknownField': [1, 2, 3],
            },
        ],
    })

    await settle()

    assert len(received_messages) == 2
    assert received_messages[0].name == 'event-1'
    assert received_messages[0].data == 'payload-1'
    assert received_messages[1].name == 'event-2'
    assert received_messages[1].data == 'payload-2'

    assert client.connection.state == ConnectionState.CONNECTED
    assert channel.state == ChannelState.ATTACHED
