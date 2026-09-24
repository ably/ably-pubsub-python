"""Derived from uts/realtime/unit/presence/realtime_presence_reentry.md in ably/specification.

Spec points: RTP17a, RTP17e, RTP17g, RTP17g1, RTP17i

The RTP17 internal presence map is filled from the server's echo of a presence message,
so each server here answers a PRESENCE with an ACK and then plays the member back on the
current connection, as the specification's setups do. PRESENCE is an `ack_required`
action, so the ACK is what resolves the client's `enter()`.

A reconnection is driven by dropping the transport: the connection retries at once, the
mock answers with a fresh connectionId, and the channels re-attach, which is what brings
about the re-entry under test.
"""

import asyncio
import uuid

from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelstate import ChannelState
from ably.types.flags import Flag
from ably.types.presence import PresenceAction
from test.uts.helpers.client import await_channel_state, connected_client, poll_until
from test.uts.helpers.clock import settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import MockWebSocket, attached_message, connected_message

# How long an operation which the specification expects to settle is given
# before a test calls it hung
OPERATION_TIMEOUT = 2.0


def random_id():
    return uuid.uuid4().hex[:8]


def ack_message(msg_serial):
    return {'action': int(ProtocolMessageAction.ACK), 'msgSerial': msg_serial, 'count': 1}


def nack_message(msg_serial, code, status_code, message):
    return {
        'action': int(ProtocolMessageAction.NACK),
        'msgSerial': msg_serial,
        'count': 1,
        'error': {'code': code, 'statusCode': status_code, 'message': message},
    }


def echo_of(msg, channel_name, connection_id, default_client_id):
    """The PRESENCE messages a server plays back for the client's own `msg`."""
    echoes = []
    for index, item in enumerate(msg.get('presence', [])):
        echoes.append({
            'action': int(ProtocolMessageAction.PRESENCE),
            'channel': channel_name,
            'connectionId': connection_id,
            'presence': [{
                'action': item.get('action'),
                'clientId': item.get('clientId') or default_client_id,
                'connectionId': connection_id,
                'id': f'{connection_id}:{msg["msgSerial"]}:{index}',
                'timestamp': 1000 + index,
                'data': item.get('data'),
            }],
        })
    return echoes


def counting_connections(mock_ws):
    """Answers each attempt with a CONNECTED carrying a fresh connectionId.

    Returns the list the attempts are counted in, so a handler can tell which
    connection it is answering on.
    """
    connections = []

    def on_connection_attempt(conn):
        connections.append(conn)
        conn.respond_with_success(connected_message(f'conn-{len(connections)}'))

    mock_ws.on_connection_attempt = on_connection_attempt
    return connections


def echoing_server(mock_ws, channel_name, connections, captured_presence,
                   default_client_id='my-client', attached_flags=0):
    """Attaches the channel and echoes back every presence message the client sends."""
    def on_message_from_client(msg):
        connection_id = f'conn-{len(connections)}'
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name, flags=attached_flags))
        elif msg['action'] == ProtocolMessageAction.PRESENCE:
            captured_presence.append(msg)
            mock_ws.send_to_client(ack_message(msg['msgSerial']))
            for echo in echo_of(msg, channel_name, connection_id, default_client_id):
                mock_ws.send_to_client(echo)

    mock_ws.on_message_from_client = on_message_from_client


async def member_present(channel, client_id):
    """Waits for the server's echo of `client_id` to reach the presence map."""
    await poll_until(
        lambda: any(m.client_id == client_id for m in channel.presence.members.values()),
        OPERATION_TIMEOUT,
        f'the presence echo for {client_id}',
    )


def presence_items(captured_presence):
    items = []
    for msg in captured_presence:
        items.extend(msg.get('presence', []))
    return items


# UTS: realtime/unit/RTP17i/auto-reentry-on-attached-0
async def test_rtp17i_auto_reentry_on_attached():
    channel_name = f'test-RTP17i-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket()
    connections = counting_connections(mock_ws)
    echoing_server(mock_ws, channel_name, connections, captured_presence)

    client = await connected_client(
        mock_ws, client_id='my-client', disconnected_retry_timeout=100)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    await asyncio.wait_for(channel.presence.enter(data='hello'), OPERATION_TIMEOUT)
    await member_present(channel, 'my-client')

    assert len(captured_presence) == 1

    captured_presence.clear()

    mock_ws.simulate_disconnect()
    await poll_until(
        lambda: len(connections) == 2, OPERATION_TIMEOUT, 'the connection to be re-established')
    await await_channel_state(channel, ChannelState.ATTACHED, OPERATION_TIMEOUT)

    # RTP17i: the member is re-entered on the fresh ATTACHED
    await poll_until(
        lambda: captured_presence, OPERATION_TIMEOUT, 'the re-entry to be published')

    assert len(captured_presence) >= 1

    reenter = next(
        (m for m in captured_presence
         if m['presence'][0]['action'] == int(PresenceAction.ENTER)), None)
    assert reenter is not None


# UTS: realtime/unit/RTP17g/reentry-publishes-enter-with-data-0
async def test_rtp17g_reentry_publishes_enter_with_data():
    channel_name = f'test-RTP17g-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket()
    connections = counting_connections(mock_ws)
    echoing_server(mock_ws, channel_name, connections, captured_presence)

    # RTP15f has a client with a concrete clientId refused `enterClient` for any
    # other one, so the client entering alice and bob on their behalf holds the
    # wildcard clientId the specification's own note allows for
    client = await connected_client(mock_ws, client_id='*', disconnected_retry_timeout=100)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    await asyncio.wait_for(
        channel.presence.enter_client('alice', data='alice-data'), OPERATION_TIMEOUT)
    await asyncio.wait_for(
        channel.presence.enter_client('bob', data='bob-data'), OPERATION_TIMEOUT)
    await member_present(channel, 'alice')
    await member_present(channel, 'bob')

    assert len(captured_presence) == 2

    captured_presence.clear()

    mock_ws.simulate_disconnect()
    await poll_until(
        lambda: len(connections) == 2, OPERATION_TIMEOUT, 'the connection to be re-established')
    await await_channel_state(channel, ChannelState.ATTACHED, OPERATION_TIMEOUT)

    await poll_until(
        lambda: len(presence_items(captured_presence)) >= 2,
        OPERATION_TIMEOUT,
        'both members to be re-entered',
    )

    items = presence_items(captured_presence)
    assert len(items) >= 2

    alice_reentry = next((p for p in items if p.get('clientId') == 'alice'), None)
    bob_reentry = next((p for p in items if p.get('clientId') == 'bob'), None)

    assert alice_reentry is not None
    assert alice_reentry['action'] == int(PresenceAction.ENTER)
    assert alice_reentry['data'] == 'alice-data'

    assert bob_reentry is not None
    assert bob_reentry['action'] == int(PresenceAction.ENTER)
    assert bob_reentry['data'] == 'bob-data'


# UTS: realtime/unit/RTP17g1/reentry-omits-id-new-connid-0
async def test_rtp17g1_reentry_omits_id_new_connid():
    channel_name = f'test-RTP17g1-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket()
    connections = counting_connections(mock_ws)
    echoing_server(mock_ws, channel_name, connections, captured_presence)

    client = await connected_client(
        mock_ws, client_id='my-client', disconnected_retry_timeout=100)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    await asyncio.wait_for(channel.presence.enter(data='hello'), OPERATION_TIMEOUT)
    await member_present(channel, 'my-client')

    assert len(connections) == 1

    captured_presence.clear()

    mock_ws.simulate_disconnect()
    await poll_until(
        lambda: len(connections) == 2, OPERATION_TIMEOUT, 'the connection to be re-established')
    await await_channel_state(channel, ChannelState.ATTACHED, OPERATION_TIMEOUT)

    assert len(connections) == 2

    await poll_until(
        lambda: captured_presence, OPERATION_TIMEOUT, 'the re-entry to be published')

    reentry_presence = captured_presence[0]['presence'][0]

    assert reentry_presence['action'] == int(PresenceAction.ENTER)
    # RTP17g1: the stored id belongs to the old connection, so it is left off
    assert 'id' not in reentry_presence
    assert reentry_presence['data'] == 'hello'


# UTS: realtime/unit/RTP17i/no-reentry-with-resumed-flag-1
async def test_rtp17i_no_reentry_with_resumed_flag():
    channel_name = f'test-RTP17i-resumed-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket()
    connections = counting_connections(mock_ws)
    echoing_server(mock_ws, channel_name, connections, captured_presence)

    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    await asyncio.wait_for(channel.presence.enter(data='hello'), OPERATION_TIMEOUT)
    await member_present(channel, 'my-client')

    captured_presence.clear()

    mock_ws.send_to_client(attached_message(channel_name, flags=int(Flag.RESUMED)))
    await settle()

    # RTP17i: an ATTACHED with RESUMED on an attached channel leaves the server's
    # copy of the presence state in place, so nothing is re-entered
    assert len(captured_presence) == 0


# UTS: realtime/unit/RTP17e/failed-reentry-emits-update-error-0
@deviation
async def test_rtp17e_failed_reentry_emits_update_error():
    channel_name = f'test-RTP17e-{random_id()}'

    mock_ws = MockWebSocket()
    connections = counting_connections(mock_ws)

    def on_message_from_client(msg):
        connection_id = f'conn-{len(connections)}'
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.PRESENCE:
            if len(connections) == 1:
                mock_ws.send_to_client(ack_message(msg['msgSerial']))
                for echo in echo_of(msg, channel_name, connection_id, 'my-client'):
                    mock_ws.send_to_client(echo)
            else:
                mock_ws.send_to_client(
                    nack_message(msg['msgSerial'], 40160, 401, 'Presence denied'))

    mock_ws.on_message_from_client = on_message_from_client

    client = await connected_client(
        mock_ws, client_id='my-client', disconnected_retry_timeout=100)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    await asyncio.wait_for(channel.presence.enter(data='hello'), OPERATION_TIMEOUT)
    await member_present(channel, 'my-client')

    channel_events = []

    def on_update(change):
        if change.reason is not None:
            channel_events.append(change)

    channel.on('update', on_update)

    mock_ws.simulate_disconnect()
    await poll_until(
        lambda: len(connections) == 2, OPERATION_TIMEOUT, 'the connection to be re-established')
    await await_channel_state(channel, ChannelState.ATTACHED, OPERATION_TIMEOUT)

    await poll_until(
        lambda: channel_events, OPERATION_TIMEOUT, 'the re-entry failure to be reported')

    assert len(channel_events) >= 1

    update_event = channel_events[0]
    assert update_event.resumed is True
    assert update_event.reason is not None
    assert update_event.reason.code == 91004
    assert 'my-client' in update_event.reason.message
    assert update_event.reason.cause is not None
    assert update_event.reason.cause.code == 40160


# UTS: realtime/unit/RTP17a/server-publishes-without-subscribe-0
async def test_rtp17a_server_publishes_without_subscribe():
    channel_name = f'test-RTP17a-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(connected_message('conn-1')),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            # A channel carrying the presence capability but not subscribe
            mock_ws.send_to_client(attached_message(channel_name, flags=int(Flag.PRESENCE)))
        elif msg['action'] == ProtocolMessageAction.PRESENCE:
            captured_presence.append(msg)
            mock_ws.send_to_client(ack_message(msg['msgSerial']))
            mock_ws.send_to_client({
                'action': int(ProtocolMessageAction.PRESENCE),
                'channel': channel_name,
                'presence': [{
                    'action': int(PresenceAction.ENTER),
                    'clientId': 'my-client',
                    'connectionId': 'conn-1',
                    'id': 'conn-1:0:0',
                    'timestamp': 1000,
                }],
            })

    mock_ws.on_message_from_client = on_message_from_client

    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    await asyncio.wait_for(channel.presence.enter(), OPERATION_TIMEOUT)
    await member_present(channel, 'my-client')

    members = await asyncio.wait_for(channel.presence.get(False), OPERATION_TIMEOUT)

    assert len(members) == 1
    assert members[0].client_id == 'my-client'
