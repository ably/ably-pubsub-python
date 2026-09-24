"""Derived from uts/realtime/unit/presence/realtime_presence_subscribe.md in ably/specification.

Spec points: RTP6, RTP6a, RTP6b, RTP6d, RTP6e, RTP7, RTP7a, RTP7b, RTP7c

`RealtimePresence.subscribe()` is a coroutine here, because it carries out the RTP6d
implicit attach, so the specifications' bare `channel.presence.subscribe(...)` is
awaited. A presence action is named by its lowercase wire name — `'enter'`, `'leave'`,
`'update'`, `'present'` — which is what `set_presence` emits.
"""

import uuid

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channeloptions import ChannelOptions
from ably.types.channelstate import ChannelState
from ably.types.flags import Flag
from ably.types.presence import PresenceAction
from test.uts.helpers.client import (
    await_channel_state,
    await_connection_state,
    poll_until,
    realtime_client,
)
from test.uts.helpers.clock import settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import MockWebSocket, attached_message, connected_message

CONNECTED_MESSAGE = connected_message('conn-1', connectionKey='connection-key')


def random_id():
    return uuid.uuid4().hex[:8]


def presence_message(action, client_id, connection_id, id, timestamp, **fields):
    return {
        'action': action,
        'clientId': client_id,
        'connectionId': connection_id,
        'id': id,
        'timestamp': timestamp,
        **fields,
    }


def presence_protocol_message(channel_name, presence):
    return {
        'action': int(ProtocolMessageAction.PRESENCE),
        'channel': channel_name,
        'presence': presence,
    }


def attaching_server(mock_ws, channel_name, attach_count=None, attach_flags=0, attached=True):
    """Answers each ATTACH with an ATTACHED, counting the attaches seen."""
    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            if attach_count is not None:
                attach_count.append(msg)
            if not attached:
                return
            if attach_flags:
                mock_ws.send_to_client(attached_message(channel_name, flags=attach_flags))
            else:
                mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    return mock_ws


async def connected_client(mock_ws, **kwargs):
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


# UTS: realtime/unit/RTP6a/subscribe-all-presence-events-0
async def test_rtp6a_subscribe_all_presence_events():
    channel_name = f'test-RTP6a-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name, attach_flags=int(Flag.HAS_PRESENCE))
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    received_events = []

    def on_event(message):
        received_events.append(message)

    await channel.presence.subscribe(on_event)
    await await_channel_state(channel, ChannelState.ATTACHED)

    mock_ws.send_to_client(presence_protocol_message(channel_name, [
        presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 1000),
    ]))
    mock_ws.send_to_client(presence_protocol_message(channel_name, [
        presence_message(PresenceAction.UPDATE, 'alice', 'c1', 'c1:1:0', 2000, data='updated'),
    ]))
    mock_ws.send_to_client(presence_protocol_message(channel_name, [
        presence_message(PresenceAction.LEAVE, 'alice', 'c1', 'c1:2:0', 3000),
    ]))

    await poll_until(lambda: len(received_events) == 3, description='three presence events')

    assert len(received_events) == 3
    assert received_events[0].action == PresenceAction.ENTER
    assert received_events[0].client_id == 'alice'
    assert received_events[1].action == PresenceAction.UPDATE
    assert received_events[1].data == 'updated'
    assert received_events[2].action == PresenceAction.LEAVE


# UTS: realtime/unit/RTP6b/subscribe-filtered-by-action-0
async def test_rtp6b_subscribe_filtered_by_action():
    channel_name = f'test-RTP6b-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    enter_events = []
    leave_events = []

    def on_enter(message):
        enter_events.append(message)

    def on_leave(message):
        leave_events.append(message)

    await channel.presence.subscribe('enter', on_enter)
    await channel.presence.subscribe('leave', on_leave)

    mock_ws.send_to_client(presence_protocol_message(channel_name, [
        presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 1000),
        presence_message(PresenceAction.UPDATE, 'alice', 'c1', 'c1:1:0', 2000),
        presence_message(PresenceAction.LEAVE, 'alice', 'c1', 'c1:2:0', 3000),
    ]))

    await poll_until(
        lambda: enter_events and leave_events, description='an enter and a leave event')

    assert len(enter_events) == 1
    assert enter_events[0].action == PresenceAction.ENTER

    assert len(leave_events) == 1
    assert leave_events[0].action == PresenceAction.LEAVE


# UTS: realtime/unit/RTP6b/subscribe-filtered-multiple-actions-1
@deviation
async def test_rtp6b_subscribe_filtered_multiple_actions():
    channel_name = f'test-RTP6b-multi-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    enter_leave_events = []

    def on_event(message):
        enter_leave_events.append(message)

    await channel.presence.subscribe(['enter', 'leave'], on_event)

    mock_ws.send_to_client(presence_protocol_message(channel_name, [
        presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 1000),
        presence_message(PresenceAction.UPDATE, 'alice', 'c1', 'c1:1:0', 2000),
        presence_message(PresenceAction.LEAVE, 'alice', 'c1', 'c1:2:0', 3000),
    ]))

    await poll_until(
        lambda: len(enter_leave_events) == 2, description='an enter and a leave event')

    assert len(enter_leave_events) == 2
    assert enter_leave_events[0].action == PresenceAction.ENTER
    assert enter_leave_events[1].action == PresenceAction.LEAVE


# UTS: realtime/unit/RTP6d/subscribe-implicitly-attaches-0
async def test_rtp6d_subscribe_implicitly_attaches():
    channel_name = f'test-RTP6d-{random_id()}'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name, attach_count=attach_messages)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    assert channel.state == ChannelState.INITIALIZED

    await channel.presence.subscribe(lambda message: None)
    await await_channel_state(channel, ChannelState.ATTACHED)

    assert len(attach_messages) == 1
    assert channel.state == ChannelState.ATTACHED


# UTS: realtime/unit/RTP6e/subscribe-no-attach-option-0
@deviation
async def test_rtp6e_subscribe_no_attach_option():
    channel_name = f'test-RTP6e-{random_id()}'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name, attach_count=attach_messages, attached=False)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name, ChannelOptions(attach_on_subscribe=False))

    assert channel.state == ChannelState.INITIALIZED

    await channel.presence.subscribe(lambda message: None)

    assert channel.state == ChannelState.INITIALIZED
    assert len(attach_messages) == 0


# UTS: realtime/unit/RTP7c/unsubscribe-all-listeners-0
async def test_rtp7c_unsubscribe_all_listeners():
    channel_name = f'test-RTP7c-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    events_a = []
    events_b = []

    def listener_a(message):
        events_a.append(message)

    def listener_b(message):
        events_b.append(message)

    await channel.presence.subscribe(listener_a)
    await channel.presence.subscribe(listener_b)

    mock_ws.send_to_client(presence_protocol_message(channel_name, [
        presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 1000),
    ]))

    await poll_until(lambda: events_a and events_b, description='both listeners called')
    assert len(events_a) == 1
    assert len(events_b) == 1

    channel.presence.unsubscribe()

    mock_ws.send_to_client(presence_protocol_message(channel_name, [
        presence_message(PresenceAction.ENTER, 'bob', 'c2', 'c2:0:0', 2000),
    ]))

    # The second event reaching the presence map is what marks it as delivered,
    # so that the listener counts below are read after it, not before
    await poll_until(
        lambda: len(channel.presence.members.values()) == 2,
        description='the second event applied to the presence map')
    await settle()

    assert len(events_a) == 1
    assert len(events_b) == 1


# UTS: realtime/unit/RTP7a/unsubscribe-specific-listener-0
async def test_rtp7a_unsubscribe_specific_listener():
    channel_name = f'test-RTP7a-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    events_a = []
    events_b = []

    def listener_a(message):
        events_a.append(message)

    def listener_b(message):
        events_b.append(message)

    await channel.presence.subscribe(listener_a)
    await channel.presence.subscribe(listener_b)

    channel.presence.unsubscribe(listener_a)

    mock_ws.send_to_client(presence_protocol_message(channel_name, [
        presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 1000),
    ]))

    await poll_until(lambda: events_b, description='the remaining listener called')

    assert len(events_a) == 0
    assert len(events_b) == 1


# UTS: realtime/unit/RTP7b/unsubscribe-for-specific-action-0
@deviation
async def test_rtp7b_unsubscribe_for_specific_action():
    channel_name = f'test-RTP7b-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    received = []

    def listener(message):
        received.append(message)

    await channel.presence.subscribe('enter', listener)
    await channel.presence.subscribe('leave', listener)

    channel.presence.unsubscribe('enter', listener)

    mock_ws.send_to_client(presence_protocol_message(channel_name, [
        presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 1000),
        presence_message(PresenceAction.LEAVE, 'alice', 'c1', 'c1:1:0', 2000),
    ]))

    await poll_until(lambda: received, description='the leave event')

    assert len(received) == 1
    assert received[0].action == PresenceAction.LEAVE


# UTS: realtime/unit/RTP6/presence-events-update-map-0
async def test_rtp6_presence_events_update_map():
    channel_name = f'test-RTP6-map-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    received = []

    def on_event(message):
        received.append(message)

    await channel.presence.subscribe(on_event)

    mock_ws.send_to_client(presence_protocol_message(channel_name, [
        presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 1000, data='hello'),
    ]))

    await poll_until(lambda: received, description='the enter event')

    members = await channel.presence.get(wait_for_sync=False)

    assert len(members) == 1
    assert members[0].client_id == 'alice'
    assert members[0].data == 'hello'
    # RTP2d2: stored as PRESENT whatever action delivered it
    assert members[0].action == PresenceAction.PRESENT


# UTS: realtime/unit/RTP6/multiple-presence-in-single-message-1
async def test_rtp6_multiple_presence_in_single_message():
    channel_name = f'test-RTP6-batch-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    received = []

    def on_event(message):
        received.append(message)

    await channel.presence.subscribe(on_event)

    mock_ws.send_to_client(presence_protocol_message(channel_name, [
        presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 1000),
        presence_message(PresenceAction.ENTER, 'bob', 'c2', 'c2:0:0', 1000),
        presence_message(PresenceAction.ENTER, 'carol', 'c3', 'c3:0:0', 1000),
    ]))

    await poll_until(lambda: len(received) == 3, description='three presence events')

    assert len(received) == 3
    assert received[0].client_id == 'alice'
    assert received[1].client_id == 'bob'
    assert received[2].client_id == 'carol'
