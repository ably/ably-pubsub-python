"""Derived from uts/realtime/unit/presence/realtime_presence_enter.md in ably/specification.

Spec points: RTP4, RTP8, RTP8a, RTP8c, RTP8d, RTP8e, RTP8g, RTP8h, RTP8j, RTP9, RTP9a,
RTP9d, RTP10, RTP10a, RTP10c, RTP14, RTP14a, RTP15, RTP15a, RTP15c, RTP15e, RTP15f,
RTP16, RTP16a, RTP16b, RTP16c

A PRESENCE ProtocolMessage is `ack_required` (`ably/realtime/connectionmanager.py:38-42`)
exactly as a MESSAGE is, so `presence.enter()` and its siblings resolve only once the
server answers. Every specification here records the PRESENCE without answering it; an
ACK is added so that the awaited call returns, as `channel_publish_test.py` does for
publishes.

The specifications reach for a wildcard `clientId` wherever one connection acts on behalf
of several. `ClientOptions` accepts `'*'` here, so the tests use it as written.
"""

import asyncio
import uuid

import pytest

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelstate import ChannelState
from ably.types.flags import Flag
from ably.types.presence import PresenceAction
from ably.util.exceptions import AblyException
from test.uts.helpers.client import (
    await_channel_state,
    await_connection_state,
    poll_until,
    realtime_client,
)
from test.uts.helpers.clock import settle
from test.uts.helpers.mock_websocket import MockWebSocket, attached_message, connected_message

CONNECTED_MESSAGE = connected_message('conn-1', connectionKey='connection-key')

# How long an operation which the specification expects to settle is given
# before a test calls it hung
OPERATION_TIMEOUT = 2.0


def random_id():
    return uuid.uuid4().hex[:8]


def ack_message(protocol_message):
    """An ACK for one PRESENCE ProtocolMessage."""
    return {
        'action': int(ProtocolMessageAction.ACK),
        'msgSerial': protocol_message['msgSerial'],
        'count': 1,
    }


def nack_message(protocol_message, code, status_code, message):
    return {
        'action': int(ProtocolMessageAction.NACK),
        'msgSerial': protocol_message['msgSerial'],
        'count': 1,
        'error': {'code': code, 'statusCode': status_code, 'message': message},
    }


def presence_server(mock_ws, channel_name, captured=None, ack=True, attach_flags=0):
    """The handler most of these specifications set on the mock.

    An ATTACH is answered with ATTACHED, and each PRESENCE is recorded in
    `captured` and acknowledged.
    """
    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            if attach_flags:
                mock_ws.send_to_client(attached_message(channel_name, flags=attach_flags))
            else:
                mock_ws.send_to_client(attached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.PRESENCE:
            if captured is not None:
                captured.append(msg)
            if ack:
                mock_ws.send_to_client(ack_message(msg))

    mock_ws.on_message_from_client = on_message_from_client
    return mock_ws


async def connected_client(mock_ws, **kwargs):
    """A client connected through `mock_ws`, which the presence tests open with."""
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


# UTS: realtime/unit/RTP8a/enter-sends-presence-enter-0
async def test_rtp8a_enter_sends_presence_enter():
    channel_name = f'test-RTP8a-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    presence_server(mock_ws, channel_name, captured_presence)
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    await channel.attach()
    await channel.presence.enter()

    assert len(captured_presence) == 1
    assert captured_presence[0]['action'] == ProtocolMessageAction.PRESENCE
    assert captured_presence[0]['channel'] == channel_name
    assert len(captured_presence[0]['presence']) == 1
    assert captured_presence[0]['presence'][0]['action'] == PresenceAction.ENTER

    # RTP8c asks for the clientId to be left out of the PresenceMessage, the
    # connection's own being implied. This SDK resolves the connection's clientId
    # and sends it; see deviations.md.
    assert captured_presence[0]['presence'][0]['clientId'] == 'my-client'


# UTS: realtime/unit/RTP8e/enter-with-data-0
async def test_rtp8e_enter_with_data():
    channel_name = f'test-RTP8e-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    presence_server(mock_ws, channel_name, captured_presence)
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    await channel.attach()
    await channel.presence.enter('hello world')

    assert len(captured_presence) == 1
    assert captured_presence[0]['presence'][0]['action'] == PresenceAction.ENTER
    assert captured_presence[0]['presence'][0]['data'] == 'hello world'


# UTS: realtime/unit/RTP8d/enter-implicitly-attaches-0
async def test_rtp8d_enter_implicitly_attaches():
    channel_name = f'test-RTP8d-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    presence_server(mock_ws, channel_name)
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    assert channel.state == ChannelState.INITIALIZED

    await channel.presence.enter()

    assert channel.state == ChannelState.ATTACHED


# UTS: realtime/unit/RTP8g/enter-detached-failed-errors-0
async def test_rtp8g_enter_detached_failed_errors():
    channel_name = f'test-RTP8g-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client({
                'action': int(ProtocolMessageAction.ERROR),
                'channel': channel_name,
                'error': {'code': 90001, 'statusCode': 400, 'message': 'Channel failed'},
            })

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    with pytest.raises(AblyException):
        await channel.attach()
    assert channel.state == ChannelState.FAILED

    with pytest.raises(AblyException) as error:
        await channel.presence.enter()

    assert error.value is not None


# UTS: realtime/unit/RTP8j/enter-null-clientid-errors-0
async def test_rtp8j_enter_null_clientid_errors():
    channel_name = f'test-RTP8j-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    presence_server(mock_ws, channel_name)
    # No clientId — anonymous client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    with pytest.raises(AblyException) as error:
        await channel.presence.enter()

    assert error.value is not None
    assert error.value.code == 40012


# UTS: realtime/unit/RTP8j/enter-wildcard-clientid-errors-1
async def test_rtp8j_enter_wildcard_clientid_errors():
    channel_name = f'test-RTP8j-wild-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    presence_server(mock_ws, channel_name)
    client = await connected_client(mock_ws, client_id='*')
    channel = client.channels.get(channel_name)

    await channel.attach()

    with pytest.raises(AblyException) as error:
        await channel.presence.enter()

    assert error.value is not None
    assert error.value.code == 40012


# UTS: realtime/unit/RTP8h/nack-presence-permission-denied-0
async def test_rtp8h_nack_presence_permission_denied():
    channel_name = f'test-RTP8h-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.PRESENCE:
            mock_ws.send_to_client(
                nack_message(msg, 40160, 401, 'Presence permission denied'))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    await channel.attach()

    with pytest.raises(AblyException) as error:
        await channel.presence.enter()

    assert error.value is not None
    assert error.value.code == 40160


# UTS: realtime/unit/RTP9a/update-sends-presence-update-0
async def test_rtp9a_update_sends_presence_update():
    channel_name = f'test-RTP9a-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    presence_server(mock_ws, channel_name, captured_presence)
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    await channel.attach()
    await channel.presence.update('new-status')

    assert len(captured_presence) == 1
    assert captured_presence[0]['presence'][0]['action'] == PresenceAction.UPDATE
    assert captured_presence[0]['presence'][0]['data'] == 'new-status'

    # RTP9d asks for the clientId to be left out; this SDK sends the connection's
    # own clientId. See deviations.md.
    assert captured_presence[0]['presence'][0]['clientId'] == 'my-client'


# UTS: realtime/unit/RTP10a/leave-sends-presence-leave-0
async def test_rtp10a_leave_sends_presence_leave():
    channel_name = f'test-RTP10a-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    presence_server(mock_ws, channel_name, captured_presence)
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    await channel.attach()
    await channel.presence.leave()

    assert len(captured_presence) == 1
    assert captured_presence[0]['presence'][0]['action'] == PresenceAction.LEAVE

    # RTP10c asks for the clientId to be left out; this SDK sends the connection's
    # own clientId. See deviations.md.
    assert captured_presence[0]['presence'][0]['clientId'] == 'my-client'


# UTS: realtime/unit/RTP10a/leave-with-data-1
async def test_rtp10a_leave_with_data():
    channel_name = f'test-RTP10a-data-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    presence_server(mock_ws, channel_name, captured_presence)
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    await channel.attach()
    await channel.presence.leave('goodbye')

    assert captured_presence[0]['presence'][0]['action'] == PresenceAction.LEAVE
    assert captured_presence[0]['presence'][0]['data'] == 'goodbye'


# UTS: realtime/unit/RTP14a/enterclient-on-behalf-0
async def test_rtp14a_enterclient_on_behalf():
    channel_name = f'test-RTP14a-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    presence_server(mock_ws, channel_name, captured_presence)
    client = await connected_client(mock_ws, client_id='*')
    channel = client.channels.get(channel_name)

    await channel.attach()

    await channel.presence.enter_client('user-alice', 'alice-data')
    await channel.presence.enter_client('user-bob', 'bob-data')

    assert len(captured_presence) == 2

    assert captured_presence[0]['presence'][0]['action'] == PresenceAction.ENTER
    assert captured_presence[0]['presence'][0]['clientId'] == 'user-alice'
    assert captured_presence[0]['presence'][0]['data'] == 'alice-data'

    assert captured_presence[1]['presence'][0]['action'] == PresenceAction.ENTER
    assert captured_presence[1]['presence'][0]['clientId'] == 'user-bob'
    assert captured_presence[1]['presence'][0]['data'] == 'bob-data'


# UTS: realtime/unit/RTP15a/updateclient-leaveclient-0
async def test_rtp15a_updateclient_leaveclient():
    channel_name = f'test-RTP15a-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    presence_server(mock_ws, channel_name, captured_presence)
    client = await connected_client(mock_ws, client_id='*')
    channel = client.channels.get(channel_name)

    await channel.attach()

    await channel.presence.enter_client('user-1', 'entered')
    await channel.presence.update_client('user-1', 'updated')
    await channel.presence.leave_client('user-1', 'leaving')

    assert len(captured_presence) == 3

    assert captured_presence[0]['presence'][0]['action'] == PresenceAction.ENTER
    assert captured_presence[0]['presence'][0]['clientId'] == 'user-1'
    assert captured_presence[0]['presence'][0]['data'] == 'entered'

    assert captured_presence[1]['presence'][0]['action'] == PresenceAction.UPDATE
    assert captured_presence[1]['presence'][0]['clientId'] == 'user-1'
    assert captured_presence[1]['presence'][0]['data'] == 'updated'

    assert captured_presence[2]['presence'][0]['action'] == PresenceAction.LEAVE
    assert captured_presence[2]['presence'][0]['clientId'] == 'user-1'
    assert captured_presence[2]['presence'][0]['data'] == 'leaving'


# UTS: realtime/unit/RTP15e/enterclient-implicitly-attaches-0
async def test_rtp15e_enterclient_implicitly_attaches():
    channel_name = f'test-RTP15e-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    presence_server(mock_ws, channel_name)
    client = await connected_client(mock_ws, client_id='*')
    channel = client.channels.get(channel_name)

    assert channel.state == ChannelState.INITIALIZED

    await channel.presence.enter_client('user-1')

    assert channel.state == ChannelState.ATTACHED


# UTS: realtime/unit/RTP15f/enterclient-mismatched-clientid-0
async def test_rtp15f_enterclient_mismatched_clientid():
    channel_name = f'test-RTP15f-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    presence_server(mock_ws, channel_name)
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    await channel.attach()

    with pytest.raises(AblyException) as error:
        await channel.presence.enter_client('other-client')

    assert error.value is not None
    assert error.value.code == 40012
    assert client.connection.state == ConnectionState.CONNECTED
    assert channel.state == ChannelState.ATTACHED


# UTS: realtime/unit/RTP16a/presence-sent-when-attached-0
async def test_rtp16a_presence_sent_when_attached():
    channel_name = f'test-RTP16a-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    presence_server(mock_ws, channel_name, captured_presence)
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    await channel.attach()
    await channel.presence.enter()

    assert len(captured_presence) == 1


# UTS: realtime/unit/RTP16b/presence-queued-when-attaching-0
async def test_rtp16b_presence_queued_when_attaching():
    channel_name = f'test-RTP16b-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    # The ATTACHED is withheld so that the channel stays ATTACHING
    presence_server(mock_ws, channel_name, captured_presence)

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.PRESENCE:
            captured_presence.append(msg)
            mock_ws.send_to_client(ack_message(msg))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    attaching = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    entering = asyncio.ensure_future(channel.presence.enter())
    await settle()

    assert len(captured_presence) == 0

    mock_ws.send_to_client(attached_message(channel_name))

    await asyncio.wait_for(entering, OPERATION_TIMEOUT)
    await asyncio.wait_for(attaching, OPERATION_TIMEOUT)

    assert len(captured_presence) == 1
    assert captured_presence[0]['presence'][0]['action'] == PresenceAction.ENTER


# UTS: realtime/unit/RTP16c/presence-errors-other-states-0
async def test_rtp16c_presence_errors_other_states():
    channel_name = f'test-RTP16c-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client({
                'action': int(ProtocolMessageAction.DETACHED),
                'channel': channel_name,
                'error': {'code': 90001, 'statusCode': 400, 'message': 'Detached'},
            })

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    # A DETACHED received while ATTACHING moves the channel to SUSPENDED rather than
    # the DETACHED the specification expects, with no reason attached, so `attach()`
    # raises `None`. Both are recorded against the channel specifications; see
    # test/uts/deviations.md.
    with pytest.raises(TypeError):
        await channel.attach()
    assert channel.state == ChannelState.SUSPENDED

    with pytest.raises(AblyException) as error:
        await channel.presence.enter()

    assert error.value is not None


# UTS: realtime/unit/RTP15c/enterclient-no-side-effects-0
async def test_rtp15c_enterclient_no_side_effects():
    channel_name = f'test-RTP15c-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    presence_server(mock_ws, channel_name, captured_presence)
    client = await connected_client(mock_ws, client_id='*')
    channel = client.channels.get(channel_name)

    await channel.attach()

    # A wildcard client cannot enter on its own behalf here (RTP8j), so the
    # specification's normal enter is made for a named client of its own
    await channel.presence.enter_client('main-client', 'main-client')
    await channel.presence.enter_client('other-user', 'other-data')
    await channel.presence.leave_client('other-user')

    assert len(captured_presence) == 3

    assert captured_presence[0]['presence'][0]['action'] == PresenceAction.ENTER
    assert captured_presence[0]['presence'][0]['data'] == 'main-client'
    assert captured_presence[0]['presence'][0]['clientId'] == 'main-client'

    assert captured_presence[1]['presence'][0]['action'] == PresenceAction.ENTER
    assert captured_presence[1]['presence'][0]['clientId'] == 'other-user'

    assert captured_presence[2]['presence'][0]['action'] == PresenceAction.LEAVE
    assert captured_presence[2]['presence'][0]['clientId'] == 'other-user'


# UTS: realtime/unit/RTP4/bulk-enterclient-same-connection-0
async def test_rtp4_bulk_enterclient_same_connection():
    channel_name = f'test-RTP4-same-{random_id()}'
    member_count = 50
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name, flags=int(Flag.HAS_PRESENCE)))
        elif msg['action'] == ProtocolMessageAction.PRESENCE:
            captured_presence.append(msg)
            mock_ws.send_to_client(ack_message(msg))
            # The server echoes each ENTER back as a presence event
            for index, entry in enumerate(msg['presence']):
                mock_ws.send_to_client({
                    'action': int(ProtocolMessageAction.PRESENCE),
                    'channel': channel_name,
                    'presence': [{
                        'action': PresenceAction.ENTER,
                        'clientId': entry['clientId'],
                        'connectionId': 'conn-1',
                        'id': f"conn-1:{msg['msgSerial']}:{index}",
                        'timestamp': 100,
                        'data': entry.get('data'),
                    }],
                })

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws, client_id='*')
    channel = client.channels.get(channel_name)

    await channel.attach()

    received_enters = []

    def on_enter(message):
        received_enters.append(message)

    await channel.presence.subscribe('enter', on_enter)

    for i in range(member_count):
        await channel.presence.enter_client(f'user-{i}', f'data-{i}')

    await poll_until(
        lambda: len(received_enters) == member_count,
        description=f'{member_count} enter events')

    mock_ws.send_to_client({
        'action': int(ProtocolMessageAction.SYNC),
        'channel': channel_name,
        'channelSerial': 'seq1:',
        'presence': [{
            'action': PresenceAction.PRESENT,
            'clientId': f'user-{i}',
            'connectionId': 'conn-1',
            'id': f'conn-1:{i}:0',
            'timestamp': 100,
            'data': f'data-{i}',
        } for i in range(member_count)],
    })

    members = await channel.presence.get()

    assert len(captured_presence) == member_count
    assert len(received_enters) == member_count
    assert len(members) == member_count

    by_client_id = {member.client_id: member for member in members}
    for i in range(member_count):
        member = by_client_id.get(f'user-{i}')
        assert member is not None
        assert member.data == f'data-{i}'


# UTS: realtime/unit/RTP4/bulk-enterclient-diff-connections-1
async def test_rtp4_bulk_enterclient_diff_connections():
    channel_name = f'test-RTP4-diff-{random_id()}'
    member_count = 50
    captured_presence_a = []

    mock_ws_a = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(connected_message('conn-A')),
    )
    presence_server(
        mock_ws_a, channel_name, captured_presence_a, attach_flags=int(Flag.HAS_PRESENCE))

    mock_ws_b = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(connected_message('conn-B')),
    )
    presence_server(mock_ws_b, channel_name, attach_flags=int(Flag.HAS_PRESENCE))

    client_a = await connected_client(mock_ws_a, client_id='*')
    client_b = await connected_client(mock_ws_b)
    channel_a = client_a.channels.get(channel_name)
    channel_b = client_b.channels.get(channel_name)

    await channel_a.attach()
    await channel_b.attach()

    received_enters_b = []

    def on_enter(message):
        received_enters_b.append(message)

    await channel_b.presence.subscribe('enter', on_enter)

    for i in range(member_count):
        await channel_a.presence.enter_client(f'user-{i}', f'data-{i}')

    for i in range(member_count):
        mock_ws_b.send_to_client({
            'action': int(ProtocolMessageAction.PRESENCE),
            'channel': channel_name,
            'presence': [{
                'action': PresenceAction.ENTER,
                'clientId': f'user-{i}',
                'connectionId': 'conn-A',
                'id': f'conn-A:{i}:0',
                'timestamp': 100,
                'data': f'data-{i}',
            }],
        })

    await poll_until(
        lambda: len(received_enters_b) == member_count,
        description=f'{member_count} enter events on the observing client')

    mock_ws_b.send_to_client({
        'action': int(ProtocolMessageAction.SYNC),
        'channel': channel_name,
        'channelSerial': 'seq1:',
        'presence': [{
            'action': PresenceAction.PRESENT,
            'clientId': f'user-{i}',
            'connectionId': 'conn-A',
            'id': f'conn-A:{i}:0',
            'timestamp': 100,
            'data': f'data-{i}',
        } for i in range(member_count)],
    })

    members = await channel_b.presence.get()

    assert len(captured_presence_a) == member_count
    assert len(received_enters_b) == member_count
    assert len(members) == member_count

    by_client_id = {member.client_id: member for member in members}
    for i in range(member_count):
        member = by_client_id.get(f'user-{i}')
        assert member is not None
        assert member.data == f'data-{i}'
        assert member.connection_id == 'conn-A'
