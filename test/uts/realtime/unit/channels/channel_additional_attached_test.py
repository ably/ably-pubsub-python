"""Derived from uts/realtime/unit/channels/channel_additional_attached.md in ably/specification.

Spec points: RTL12
"""

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelstate import ChannelState
from ably.types.flags import Flag
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import settle
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')


def attach_responder(mock_ws, channel_name):
    """Answers every ATTACH for `channel_name` with a bare ATTACHED."""

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client({'action': ProtocolMessageAction.ATTACHED, 'channel': channel_name})

    return on_message_from_client


# UTS: realtime/unit/RTL12/update-emits-with-error-0
async def test_rtl12_update_emits_with_error():
    channel_name = 'test-RTL12-update'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = attach_responder(mock_ws, channel_name)
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await channel.attach()

    update_events = []

    def record(change):
        update_events.append(change)

    channel.on('update', record)

    mock_ws.send_to_client({
        'action': ProtocolMessageAction.ATTACHED,
        'channel': channel_name,
        'error': {'code': 50000, 'statusCode': 500, 'message': 'generic serverside failure'},
    })
    await settle()

    assert channel.state == ChannelState.ATTACHED
    assert len(update_events) == 1
    # The specification asserts `event == ChannelEvent.update`; ably-python has
    # no ChannelStateChange.event, the event being the key the listener is
    # registered against
    assert update_events[0].current == ChannelState.ATTACHED
    assert update_events[0].previous == ChannelState.ATTACHED
    assert update_events[0].resumed is False
    assert update_events[0].reason.code == 50000


# UTS: realtime/unit/RTL12/resumed-no-update-1
async def test_rtl12_resumed_no_update():
    channel_name = 'test-RTL12-no-update'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = attach_responder(mock_ws, channel_name)
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await channel.attach()

    update_events = []

    def record(change):
        update_events.append(change)

    channel.on('update', record)

    mock_ws.send_to_client({
        'action': ProtocolMessageAction.ATTACHED,
        'channel': channel_name,
        'flags': Flag.RESUMED,
    })
    await settle()

    assert channel.state == ChannelState.ATTACHED
    assert update_events == []


# UTS: realtime/unit/RTL12/no-error-null-reason-2
async def test_rtl12_no_error_null_reason():
    channel_name = 'test-RTL12-no-error'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = attach_responder(mock_ws, channel_name)
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await channel.attach()

    update_events = []

    def record(change):
        update_events.append(change)

    channel.on('update', record)

    mock_ws.send_to_client({'action': ProtocolMessageAction.ATTACHED, 'channel': channel_name})
    await settle()

    assert channel.state == ChannelState.ATTACHED
    assert len(update_events) == 1
    assert update_events[0].resumed is False
    assert update_events[0].reason is None
