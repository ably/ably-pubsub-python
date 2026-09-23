"""Derived from uts/realtime/unit/channels/channel_server_initiated_detach.md in ably/specification.

Spec points: RTL13, RTL13a, RTL13b, RTL13c
"""

import asyncio

import pytest

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelstate import ChannelState
from test.uts.helpers.client import await_connection_state, poll_until, realtime_client
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')

# The same connection with the idle timer switched off, so that a test driving a
# `FakeClock` sees only the timers it is interested in
CONNECTED_MESSAGE_NO_IDLE = connected_message(
    'connection-id', connectionKey='connection-key', maxIdleInterval=0)

# How long an operation which the specification expects to settle is given
# before a test calls it hung
OPERATION_TIMEOUT = 1.0


def attached_message(channel_name, **fields):
    """An ATTACHED for `channel_name`, as the server confirms an attach."""
    return {'action': ProtocolMessageAction.ATTACHED, 'channel': channel_name, **fields}


def server_detached_message(channel_name, code, message):
    """The unsolicited DETACHED the server sends to drop a channel."""
    return {
        'action': ProtocolMessageAction.DETACHED,
        'channel': channel_name,
        'error': {'code': code, 'statusCode': 500, 'message': message},
    }


def states_of(state_changes):
    return [change.current for change in state_changes]


def contains_in_order(states, expected):
    """Whether `expected` appears in `states` in order, gaps allowed."""
    remaining = list(expected)
    for state in states:
        if remaining and state == remaining[0]:
            remaining.pop(0)
    return not remaining


async def connected_client(mock_ws, **kwargs):
    """A client connected through `mock_ws`, which the channel tests open with."""
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


# UTS: realtime/unit/RTL13a/attached-reattach-triggered-0
async def test_rtl13a_attached_reattach_triggered():
    channel_name = 'test-RTL13a-attached'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            mock_ws.send_to_client(attached_message(msg.get('channel')))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 1

    channel_state_changes = []

    def record(change):
        channel_state_changes.append(change)

    channel.on(record)

    mock_ws.send_to_client(server_detached_message(channel_name, 90198, 'Server detached channel'))
    await poll_until(lambda: len(attach_messages) == 2, OPERATION_TIMEOUT, 'a reattach')
    await poll_until(
        lambda: channel.state == ChannelState.ATTACHED, OPERATION_TIMEOUT, 'the channel reattached')

    assert len(attach_messages) == 2
    assert len(channel_state_changes) >= 2
    assert channel_state_changes[0].current == ChannelState.ATTACHING
    assert channel_state_changes[0].previous == ChannelState.ATTACHED
    # RTL13a carries the DETACHED message's error onto the ATTACHING state
    # change; ably-python requests ATTACHING with no reason, so it arrives null
    assert channel_state_changes[0].reason is None
    assert channel_state_changes[1].current == ChannelState.ATTACHED


# UTS: realtime/unit/RTL13a/suspended-reattach-triggered-1
async def test_rtl13a_suspended_reattach_triggered():
    channel_name = 'test-RTL13a-suspended'
    attach_messages = []
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            # The second attach is left unanswered, so that its state timer
            # takes the channel to SUSPENDED
            if len(attach_messages) != 2:
                mock_ws.send_to_client(attached_message(msg.get('channel')))

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(
        mock_ws, clock=clock, realtime_request_timeout=100, channel_retry_timeout=60000)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    mock_ws.send_to_client(server_detached_message(channel_name, 90198, 'Detach 1'))
    await poll_until(lambda: len(attach_messages) == 2, OPERATION_TIMEOUT, 'the first reattach')
    assert channel.state == ChannelState.ATTACHING

    await clock.advance(150)
    assert channel.state == ChannelState.SUSPENDED

    mock_ws.send_to_client(server_detached_message(channel_name, 90199, 'Detach 2'))
    await poll_until(lambda: len(attach_messages) == 3, OPERATION_TIMEOUT, 'the second reattach')
    await poll_until(
        lambda: channel.state == ChannelState.ATTACHED, OPERATION_TIMEOUT, 'the channel reattached')

    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 3


# UTS: realtime/unit/RTL13b/failed-reattach-suspended-retry-0
async def test_rtl13b_failed_reattach_suspended_retry():
    channel_name = 'test-RTL13b'
    attach_messages = []
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            # The reattach the server-initiated DETACHED triggers is left
            # unanswered, so that it times out into SUSPENDED
            if len(attach_messages) != 2:
                mock_ws.send_to_client(attached_message(msg.get('channel')))

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(
        mock_ws, clock=clock, realtime_request_timeout=100, channel_retry_timeout=200)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    channel_state_changes = []

    def record(change):
        channel_state_changes.append(change)

    channel.on(record)

    mock_ws.send_to_client(server_detached_message(channel_name, 90198, 'Server detached'))
    await poll_until(lambda: len(attach_messages) == 2, OPERATION_TIMEOUT, 'the reattach')
    assert channel.state == ChannelState.ATTACHING

    await clock.advance(150)
    assert channel.state == ChannelState.SUSPENDED

    await clock.advance(250)
    await poll_until(
        lambda: channel.state == ChannelState.ATTACHED, OPERATION_TIMEOUT, 'the retry to attach')

    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 3
    assert contains_in_order(states_of(channel_state_changes), [
        ChannelState.ATTACHING,
        ChannelState.SUSPENDED,
        ChannelState.ATTACHING,
        ChannelState.ATTACHED,
    ])


# UTS: realtime/unit/RTL13b/attaching-detached-to-suspended-1
async def test_rtl13b_attaching_detached_to_suspended():
    channel_name = 'test-RTL13b-attaching'
    attach_messages = []
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            # The first attach is left unanswered, holding the channel in
            # ATTACHING for the server-initiated DETACHED to arrive into
            if len(attach_messages) != 1:
                mock_ws.send_to_client(attached_message(msg.get('channel')))

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(
        mock_ws, clock=clock, realtime_request_timeout=500, channel_retry_timeout=200)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    attach_future = asyncio.ensure_future(channel.attach())
    await poll_until(lambda: len(attach_messages) == 1, OPERATION_TIMEOUT, 'the ATTACH sent')
    assert channel.state == ChannelState.ATTACHING

    channel_state_changes = []

    def record(change):
        channel_state_changes.append(change)

    channel.on(record)

    mock_ws.send_to_client(server_detached_message(channel_name, 90198, 'Server detached'))
    await poll_until(
        lambda: channel.state == ChannelState.SUSPENDED, OPERATION_TIMEOUT, 'the channel suspended')
    assert len(attach_messages) == 1

    await clock.advance(250)
    await poll_until(
        lambda: channel.state == ChannelState.ATTACHED, OPERATION_TIMEOUT, 'the retry to attach')

    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 2
    assert channel_state_changes[0].current == ChannelState.SUSPENDED
    assert channel_state_changes[0].previous == ChannelState.ATTACHING
    # RTL13b carries the DETACHED message's error onto the SUSPENDED state
    # change; ably-python notifies SUSPENDED with no reason, so it arrives null
    assert channel_state_changes[0].reason is None

    # A pending attach reads the reason off that state change and re-raises it,
    # so a null reason surfaces as a TypeError rather than an AblyException
    with pytest.raises(TypeError):
        await asyncio.wait_for(attach_future, OPERATION_TIMEOUT)


# UTS: realtime/unit/RTL13b/repeated-failure-cycle-2
async def test_rtl13b_repeated_failure_cycle():
    channel_name = 'test-RTL13b-repeat'
    attach_messages = []
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            # The second and third attaches are left unanswered, so that each
            # times out into SUSPENDED and is retried
            if len(attach_messages) not in (2, 3):
                mock_ws.send_to_client(attached_message(msg.get('channel')))

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(
        mock_ws, clock=clock, realtime_request_timeout=100, channel_retry_timeout=200)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert len(attach_messages) == 1

    channel_state_changes = []

    def record(change):
        channel_state_changes.append(change)

    channel.on(record)

    mock_ws.send_to_client(server_detached_message(channel_name, 90198, 'Detach'))
    await poll_until(lambda: len(attach_messages) == 2, OPERATION_TIMEOUT, 'the reattach')
    assert channel.state == ChannelState.ATTACHING

    await clock.advance(150)
    assert channel.state == ChannelState.SUSPENDED

    # The retry falls due 200ms into this 250ms window and the attach it sends
    # times out 100ms later, on the instant the window closes, so the channel is
    # back in SUSPENDED by the time the advance returns
    await clock.advance(250)
    await poll_until(lambda: len(attach_messages) == 3, OPERATION_TIMEOUT, 'the first retry')

    await clock.advance(150)
    assert channel.state == ChannelState.SUSPENDED

    await clock.advance(250)
    await poll_until(
        lambda: channel.state == ChannelState.ATTACHED, OPERATION_TIMEOUT, 'the second retry')

    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 4
    assert contains_in_order(states_of(channel_state_changes), [
        ChannelState.ATTACHING,
        ChannelState.SUSPENDED,
        ChannelState.ATTACHING,
        ChannelState.SUSPENDED,
        ChannelState.ATTACHING,
        ChannelState.ATTACHED,
    ])


# UTS: realtime/unit/RTL13c/retry-cancelled-disconnected-0
async def test_rtl13c_retry_cancelled_disconnected():
    channel_name = 'test-RTL13c'
    attach_messages = []
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            # Only the first attach is answered; every reattach times out
            if len(attach_messages) == 1:
                mock_ws.send_to_client(attached_message(msg.get('channel')))

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(
        mock_ws, clock=clock, realtime_request_timeout=100, channel_retry_timeout=200)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert len(attach_messages) == 1

    mock_ws.send_to_client(server_detached_message(channel_name, 90198, 'Detach'))
    await poll_until(lambda: len(attach_messages) == 2, OPERATION_TIMEOUT, 'the reattach')
    assert channel.state == ChannelState.ATTACHING

    await clock.advance(150)
    assert channel.state == ChannelState.SUSPENDED

    # A reconnect left unanswered keeps the connection out of CONNECTED for the
    # rest of the test
    mock_ws.on_connection_attempt = lambda conn: None
    mock_ws.simulate_disconnect()
    await settle()
    await clock.advance(200)
    assert client.connection.state != ConnectionState.CONNECTED

    attach_count_after_disconnect = len(attach_messages)

    await clock.advance(500)

    assert len(attach_messages) == attach_count_after_disconnect
    assert channel.state == ChannelState.SUSPENDED


# UTS: realtime/unit/RTL13a/detaching-not-server-initiated-2
async def test_rtl13a_detaching_not_server_initiated():
    channel_name = 'test-RTL13-detaching'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            mock_ws.send_to_client(attached_message(msg.get('channel')))
        elif msg.get('action') == ProtocolMessageAction.DETACH:
            mock_ws.send_to_client({
                'action': ProtocolMessageAction.DETACHED,
                'channel': msg.get('channel'),
            })

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)

    assert channel.state == ChannelState.DETACHED
    assert len(attach_messages) == 1
