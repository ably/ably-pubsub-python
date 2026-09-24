"""Derived from uts/realtime/unit/presence/realtime_presence_channel_state.md in ably/specification.

Spec points: RTL9, RTL9a, RTL11, RTL11a, RTP1, RTP5, RTP5a, RTP5b, RTP5f, RTP13

`syncComplete` is `presence.sync_complete`, and `get(waitForSync: false)` is
`presence.get(False)`.

A channel reaches SUSPENDED from a SUSPENDED connection, not from a DISCONNECTED one
(RTL3c), so the two tests whose premise is a SUSPENDED channel drop the transport, leave
the reconnection attempt unanswered and run a `FakeClock` past the connection state TTL.

PRESENCE is an `ack_required` action, so a presence operation is only resolved once the
server answers it; every handler here which captures a PRESENCE also acknowledges it,
except in RTL11a, where the specification holds the ACK back on purpose.
"""

import asyncio
import uuid

import pytest

from ably.realtime.connection import ConnectionState
from ably.realtime.presence import RealtimePresence
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelstate import ChannelState
from ably.types.flags import Flag
from ably.types.presence import PresenceAction
from ably.util.exceptions import AblyException
from test.uts.helpers.client import (
    await_channel_state,
    connected_client,
    poll_until,
    realtime_client,
)
from test.uts.helpers.clock import FakeClock, advance_to_connection_state, settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import (
    CONNECTED_MESSAGE_NO_IDLE,
    MockWebSocket,
    attached_message,
    channel_error_message,
    connected_message,
    detached_message,
)

CONNECTED_MESSAGE = connected_message('conn-1', connectionKey='connection-key')

# How long an operation which the specification expects to settle is given
# before a test calls it hung
OPERATION_TIMEOUT = 2.0


def random_id():
    return uuid.uuid4().hex[:8]


def present_member(client_id, connection_id, id, **fields):
    return {
        'action': PresenceAction.PRESENT,
        'clientId': client_id,
        'connectionId': connection_id,
        'id': id,
        'timestamp': 100,
        **fields,
    }


def sync_message(channel_name, channel_serial, presence):
    return {
        'action': int(ProtocolMessageAction.SYNC),
        'channel': channel_name,
        'channelSerial': channel_serial,
        'presence': presence,
    }


def presence_actions(protocol_message):
    """The wire actions of the presence messages one PRESENCE protocol message carries."""
    return [item.get('action') for item in protocol_message.get('presence', [])]


# UTS: realtime/unit/RTP1/has-presence-triggers-sync-0
async def test_rtp1_has_presence_triggers_sync():
    channel_name = f'test-RTP1-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name, flags=int(Flag.HAS_PRESENCE)))
            mock_ws.send_to_client(sync_message(channel_name, 'seq1:', [
                present_member('alice', 'c1', 'c1:0:0'),
            ]))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    members = await asyncio.wait_for(channel.presence.get(), OPERATION_TIMEOUT)

    assert len(members) == 1
    assert members[0].client_id == 'alice'
    assert channel.presence.sync_complete is True


# UTS: realtime/unit/RTP1/no-has-presence-empty-1
async def test_rtp1_no_has_presence_empty():
    channel_name = f'test-RTP1-empty-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    members = await asyncio.wait_for(channel.presence.get(), OPERATION_TIMEOUT)

    assert len(members) == 0
    # An ATTACHED without HAS_PRESENCE puts the map in sync at once
    assert channel.presence.sync_complete is True


# UTS: realtime/unit/RTP1/no-has-presence-clears-existing-2
async def test_rtp1_no_has_presence_clears_existing():
    channel_name = f'test-RTP19a-{random_id()}'
    connections = []
    attach_messages = []

    def on_connection_attempt(conn):
        connections.append(conn)
        conn.respond_with_success(connected_message(f'conn-{len(connections)}'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            if len(connections) == 1:
                mock_ws.send_to_client(
                    attached_message(channel_name, flags=int(Flag.HAS_PRESENCE)))
                mock_ws.send_to_client(sync_message(channel_name, 'seq1:', [
                    present_member('alice', 'c1', 'c1:0:0'),
                    present_member('bob', 'c2', 'c2:0:0'),
                ]))
            else:
                mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws, disconnected_retry_timeout=100)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    members = await asyncio.wait_for(channel.presence.get(), OPERATION_TIMEOUT)
    assert len(members) == 2

    leave_events = []

    def on_leave(message):
        leave_events.append(message)

    await channel.presence.subscribe('leave', on_leave)

    mock_ws.simulate_disconnect()

    # The channel holds ATTACHED across the drop, so the second ATTACH is what
    # marks the re-attach having happened
    await poll_until(lambda: len(attach_messages) == 2, OPERATION_TIMEOUT, 'a second ATTACH')
    await settle()

    members_after = await asyncio.wait_for(channel.presence.get(), OPERATION_TIMEOUT)

    assert len(members_after) == 0

    assert len(leave_events) == 2
    assert any(event.client_id == 'alice' for event in leave_events)
    assert any(event.client_id == 'bob' for event in leave_events)

    # RTP19a: a synthesized LEAVE carries no id
    assert all(event.id is None for event in leave_events)


# UTS: realtime/unit/RTP5a/detached-clears-presence-maps-0
async def test_rtp5a_detached_clears_presence_maps():
    channel_name = f'test-RTP5a-detached-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name, flags=int(Flag.HAS_PRESENCE)))
            mock_ws.send_to_client(sync_message(channel_name, 'seq1:', [
                present_member('alice', 'c1', 'c1:0:0'),
            ]))
        elif msg['action'] == ProtocolMessageAction.DETACH:
            mock_ws.send_to_client(detached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    members = await asyncio.wait_for(channel.presence.get(), OPERATION_TIMEOUT)
    assert len(members) == 1

    leave_events = []

    def on_leave(message):
        leave_events.append(message)

    await channel.presence.subscribe('leave', on_leave)

    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.DETACHED
    await settle()

    # RTP5a: clearing the maps on DETACHED emits nothing
    assert len(leave_events) == 0

    # The specification reads the cleared map back with `get(waitForSync: false)`,
    # which RTP11b has implicitly re-attach a DETACHED channel; the maps
    # themselves are what RTP5a is about
    assert len(channel.presence.members.values()) == 0
    assert len(channel.presence._my_members.values()) == 0


# UTS: realtime/unit/RTP5a/failed-clears-presence-maps-1
async def test_rtp5a_failed_clears_presence_maps():
    channel_name = f'test-RTP5a-failed-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name, flags=int(Flag.HAS_PRESENCE)))
            mock_ws.send_to_client(sync_message(channel_name, 'seq1:', [
                present_member('alice', 'c1', 'c1:0:0'),
            ]))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    members = await asyncio.wait_for(channel.presence.get(), OPERATION_TIMEOUT)
    assert len(members) == 1

    leave_events = []

    def on_leave(message):
        leave_events.append(message)

    await channel.presence.subscribe('leave', on_leave)

    mock_ws.send_to_client(channel_error_message(channel_name, 90001, 'Channel failed'))

    await await_channel_state(channel, ChannelState.FAILED, OPERATION_TIMEOUT)
    await settle()

    # RTP5a: clearing the maps on FAILED emits nothing
    assert len(leave_events) == 0
    assert len(channel.presence.members.values()) == 0


# UTS: realtime/unit/RTP5b/attached-sends-queued-presence-0
async def test_rtp5b_attached_sends_queued_presence():
    channel_name = f'test-RTP5b-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.PRESENCE:
            captured_presence.append(msg)
            mock_ws.send_to_client(
                {'action': int(ProtocolMessageAction.ACK), 'msgSerial': msg['msgSerial'], 'count': 1})

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    # The ATTACH is left unanswered, holding the channel in ATTACHING
    attach_future = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    enter_future = asyncio.ensure_future(channel.presence.enter(data='queued'))
    await settle()

    assert len(captured_presence) == 0

    mock_ws.send_to_client(attached_message(channel_name))

    await asyncio.wait_for(enter_future, OPERATION_TIMEOUT)
    await asyncio.wait_for(attach_future, OPERATION_TIMEOUT)

    assert len(captured_presence) == 1
    assert presence_actions(captured_presence[0]) == [int(PresenceAction.ENTER)]
    assert captured_presence[0]['presence'][0]['data'] == 'queued'


# UTS: realtime/unit/RTP5f/suspended-maintains-presence-map-0
async def test_rtp5f_suspended_maintains_presence_map():
    channel_name = f'test-RTP5f-{random_id()}'
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name, flags=int(Flag.HAS_PRESENCE)))
            mock_ws.send_to_client(sync_message(channel_name, 'seq1:', [
                present_member('alice', 'c1', 'c1:0:0'),
                present_member('bob', 'c2', 'c2:0:0'),
            ]))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(
        mock_ws, clock=clock, realtime_request_timeout=300000,
        disconnected_retry_timeout=1000, suspended_retry_timeout=600000)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    members = await asyncio.wait_for(channel.presence.get(), OPERATION_TIMEOUT)
    assert len(members) == 2

    # The channel follows the connection to SUSPENDED, so every reconnection
    # attempt is left unanswered and the clock runs past the connection state TTL
    mock_ws.on_connection_attempt = lambda conn: None
    mock_ws.simulate_disconnect()
    await settle()

    await advance_to_connection_state(client, clock, ConnectionState.SUSPENDED, step=5000)
    await await_channel_state(channel, ChannelState.SUSPENDED, OPERATION_TIMEOUT)

    members_during_suspended = await asyncio.wait_for(
        channel.presence.get(False), OPERATION_TIMEOUT)

    assert len(members_during_suspended) == 2


# UTS: realtime/unit/RTP13/sync-complete-attribute-0
async def test_rtp13_sync_complete_attribute():
    channel_name = f'test-RTP13-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name, flags=int(Flag.HAS_PRESENCE)))
            # A non-empty cursor leaves the sync running
            mock_ws.send_to_client(sync_message(channel_name, 'seq1:cursor1', [
                present_member('alice', 'c1', 'c1:0:0'),
            ]))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    await poll_until(
        lambda: len(channel.presence.members.values()) == 1,
        OPERATION_TIMEOUT,
        'the first sync message to land',
    )

    assert channel.presence.sync_complete is False

    mock_ws.send_to_client(sync_message(channel_name, 'seq1:', [
        present_member('bob', 'c2', 'c2:0:0'),
    ]))
    await poll_until(
        lambda: channel.presence.sync_complete, OPERATION_TIMEOUT, 'the sync to complete')

    assert channel.presence.sync_complete is True


# UTS: realtime/unit/RTL9/presence-attribute-0
async def test_rtl9_presence_attribute():
    channel_name = f'test-RTL9a-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
        on_message_from_client=lambda msg: None,
    )
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    presence = channel.presence

    assert presence is not None
    assert isinstance(presence, RealtimePresence)

    # RTL9a: the same object every time it is read
    assert channel.presence is channel.presence
    assert client.channels.get(channel_name).presence is presence


# UTS: realtime/unit/RTL11/queued-presence-fail-detached-0
@deviation
async def test_rtl11_queued_presence_fail_detached():
    channel_name = f'test-RTL11-detached-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.DETACH:
            mock_ws.send_to_client(detached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.PRESENCE:
            captured_presence.append(msg)

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.DETACHED

    with pytest.raises(AblyException) as raised:
        await asyncio.wait_for(
            channel.presence.enter(data='queued-enter'), OPERATION_TIMEOUT)

    assert len(captured_presence) == 0
    assert raised.value.code is not None


# UTS: realtime/unit/RTL11/queued-presence-fail-suspended-1
async def test_rtl11_queued_presence_fail_suspended():
    channel_name = f'test-RTL11-suspended-{random_id()}'
    captured_presence = []
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.PRESENCE:
            captured_presence.append(msg)

    mock_ws.on_message_from_client = on_message_from_client
    # The channel's RTL4f attach timeout and the connection's transition timeout
    # are the same option, so it is set beyond the connection state TTL: the
    # channel is to follow the connection to SUSPENDED rather than time its own
    # attach out first
    client = await connected_client(
        mock_ws, clock=clock, client_id='my-client', realtime_request_timeout=300000,
        disconnected_retry_timeout=1000, suspended_retry_timeout=600000)
    channel = client.channels.get(channel_name)

    # The ATTACH is left unanswered, holding the channel in ATTACHING
    attach_future = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    enter_future = asyncio.ensure_future(channel.presence.enter(data='queued-enter'))
    update_future = asyncio.ensure_future(channel.presence.update(data='queued-update'))
    await settle()

    assert len(captured_presence) == 0

    mock_ws.on_connection_attempt = lambda conn: None
    mock_ws.simulate_disconnect()
    await settle()

    await advance_to_connection_state(client, clock, ConnectionState.SUSPENDED, step=5000)
    await await_channel_state(channel, ChannelState.SUSPENDED, OPERATION_TIMEOUT)

    assert len(captured_presence) == 0

    with pytest.raises(AblyException):
        await asyncio.wait_for(enter_future, OPERATION_TIMEOUT)

    with pytest.raises(AblyException):
        await asyncio.wait_for(update_future, OPERATION_TIMEOUT)

    attach_future.cancel()


# UTS: realtime/unit/RTL11/queued-presence-fail-failed-2
async def test_rtl11_queued_presence_fail_failed():
    channel_name = f'test-RTL11-failed-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.PRESENCE:
            captured_presence.append(msg)

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    # The ATTACH is left unanswered, holding the channel in ATTACHING
    attach_future = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    enter_future = asyncio.ensure_future(channel.presence.enter(data='queued-enter'))
    await settle()

    assert len(captured_presence) == 0

    mock_ws.send_to_client(channel_error_message(channel_name, 90001, 'Channel failed'))
    await await_channel_state(channel, ChannelState.FAILED, OPERATION_TIMEOUT)

    assert len(captured_presence) == 0

    with pytest.raises(AblyException):
        await asyncio.wait_for(enter_future, OPERATION_TIMEOUT)

    attach_future.cancel()


# UTS: realtime/unit/RTL11a/ack-nack-unaffected-by-state-0
async def test_rtl11a_ack_nack_unaffected_by_state():
    channel_name = f'test-RTL11a-{random_id()}'
    captured_presence = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.DETACH:
            mock_ws.send_to_client(detached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.PRESENCE:
            # The ACK is withheld until after the channel has detached
            captured_presence.append(msg)

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws, client_id='my-client')
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    enter_future = asyncio.ensure_future(channel.presence.enter(data='awaiting-ack'))
    await poll_until(lambda: captured_presence, OPERATION_TIMEOUT, 'the PRESENCE to be sent')

    assert len(captured_presence) == 1

    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.DETACHED

    mock_ws.send_to_client({
        'action': int(ProtocolMessageAction.ACK),
        'msgSerial': captured_presence[0]['msgSerial'],
        'count': 1,
    })

    assert await asyncio.wait_for(enter_future, OPERATION_TIMEOUT) is None
