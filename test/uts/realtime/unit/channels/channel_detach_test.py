"""Derived from uts/realtime/unit/channels/channel_detach.md in ably/specification.

Spec points: RTL5, RTL5a, RTL5b, RTL5d, RTL5e, RTL5f, RTL5i, RTL5j, RTL5k, RTL5l
"""

import asyncio

import pytest

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelstate import ChannelState
from ably.util.exceptions import AblyException
from test.uts.helpers.client import (
    await_channel_state,
    await_connection_state,
    poll_until,
    realtime_client,
)
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.deviations import deviation
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


def detached_message(channel_name, **fields):
    """A DETACHED for `channel_name`, as the server confirms a detach."""
    return {'action': ProtocolMessageAction.DETACHED, 'channel': channel_name, **fields}


async def connected_client(mock_ws, **kwargs):
    """A client connected through `mock_ws`, which the channel tests open with."""
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


# UTS: realtime/unit/RTL5a/detach-initialized-noop-0
async def test_rtl5a_detach_initialized_noop():
    channel_name = 'test-RTL5a'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    state_changes = []

    def record(change):
        state_changes.append(change)

    channel.on(record)

    assert channel.state == ChannelState.INITIALIZED

    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)

    assert channel.state == ChannelState.INITIALIZED
    assert state_changes == []


# UTS: realtime/unit/RTL5a/detach-already-detached-noop-1
async def test_rtl5a_detach_already_detached_noop():
    channel_name = 'test-RTL5a-detached'
    detach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg.get('action') == ProtocolMessageAction.DETACH:
            detach_messages.append(msg)
            mock_ws.send_to_client(detached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.DETACHED
    assert len(detach_messages) == 1

    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)

    assert channel.state == ChannelState.DETACHED
    assert len(detach_messages) == 1


# UTS: realtime/unit/RTL5i/detach-while-detaching-0
@deviation
async def test_rtl5i_detach_while_detaching():
    channel_name = 'test-RTL5i'
    detach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg.get('action') == ProtocolMessageAction.DETACH:
            detach_messages.append(msg)

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    first = asyncio.ensure_future(channel.detach())
    await await_channel_state(channel, ChannelState.DETACHING, OPERATION_TIMEOUT)

    second = asyncio.ensure_future(channel.detach())
    await settle()

    mock_ws.send_to_client(detached_message(channel_name))

    await asyncio.wait_for(first, OPERATION_TIMEOUT)
    await asyncio.wait_for(second, OPERATION_TIMEOUT)

    assert channel.state == ChannelState.DETACHED
    assert len(detach_messages) == 1


# UTS: realtime/unit/RTL5i/detach-while-attaching-1
async def test_rtl5i_detach_while_attaching():
    channel_name = 'test-RTL5i-attaching'
    messages_from_client = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        messages_from_client.append(msg)
        if msg.get('action') == ProtocolMessageAction.DETACH:
            mock_ws.send_to_client(detached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    attach_future = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    detach_future = asyncio.ensure_future(channel.detach())
    await settle()

    mock_ws.send_to_client(attached_message(channel_name))

    # The specification allows the superseded attach either to resolve or to be
    # rejected; ably-python resolves it on the DETACHING state change
    await asyncio.wait_for(attach_future, OPERATION_TIMEOUT)
    await asyncio.wait_for(detach_future, OPERATION_TIMEOUT)

    assert channel.state == ChannelState.DETACHED
    assert len(messages_from_client) == 2
    assert messages_from_client[0]['action'] == ProtocolMessageAction.ATTACH
    assert messages_from_client[1]['action'] == ProtocolMessageAction.DETACH


# UTS: realtime/unit/RTL5b/detach-failed-errors-0
async def test_rtl5b_detach_failed_errors():
    channel_name = 'test-RTL5b'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client({
                'action': ProtocolMessageAction.ERROR,
                'channel': channel_name,
                'error': {'code': 40160, 'statusCode': 401, 'message': 'Not permitted'},
            })

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    with pytest.raises(AblyException):
        await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.FAILED

    with pytest.raises(AblyException) as error:
        await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)

    # The 90001 the library passes lands in `status_code` and the 400 in `code`,
    # the two being the other way round in `AblyException(message, status_code, code)`
    assert error.value.status_code == 90001
    assert channel.state == ChannelState.FAILED


# UTS: realtime/unit/RTL5j/detach-suspended-to-detached-0
async def test_rtl5j_detach_suspended_to_detached():
    channel_name = 'test-RTL5j'
    detach_messages = []
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.DETACH:
            detach_messages.append(msg)

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(mock_ws, clock=clock, realtime_request_timeout=100)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    attach_future = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    await clock.advance(150)

    with pytest.raises(AblyException):
        await asyncio.wait_for(attach_future, OPERATION_TIMEOUT)
    assert channel.state == ChannelState.SUSPENDED

    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)

    assert channel.state == ChannelState.DETACHED
    assert detach_messages == []


# UTS: realtime/unit/RTL5l/detach-not-connected-immediate-0
@deviation
async def test_rtl5l_detach_not_connected_immediate():
    channel_name = 'test-RTL5l'
    detach_messages = []

    # A handler which does not answer the attempt holds the connection in
    # CONNECTING, which is the specification's "delay connection"
    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: None)

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.DETACH:
            detach_messages.append(msg)

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTING)

    attach_future = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)

    assert channel.state == ChannelState.DETACHED
    assert detach_messages == []
    attach_future.cancel()


# UTS: realtime/unit/RTL5l/detach-attached-when-disconnected-1
@deviation
async def test_rtl5l_detach_attached_when_disconnected():
    channel_name = 'test-channel'
    messages_sent = []
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )
    client = realtime_client(
        mock_ws, clock=clock, realtime_request_timeout=300, disconnected_retry_timeout=60000)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    def attach_responder(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(msg.get('channel')))

    mock_ws.on_message_from_client = attach_responder
    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    # The reconnect RTN15a starts straight after the drop is left unanswered, so
    # that its transition timer returns the connection to a settled DISCONNECTED
    mock_ws.on_connection_attempt = lambda conn: None
    mock_ws.simulate_disconnect()
    await settle()
    await clock.advance(500)
    assert client.connection.state == ConnectionState.DISCONNECTED

    def record(msg):
        messages_sent.append(msg)

    mock_ws.on_message_from_client = record

    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)

    assert channel.state == ChannelState.DETACHED
    detach_messages = [m for m in messages_sent if m.get('action') == ProtocolMessageAction.DETACH]
    assert detach_messages == []


# UTS: realtime/unit/RTL5d/normal-detach-flow-0
async def test_rtl5d_normal_detach_flow():
    channel_name = 'test-RTL5d'
    detach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg.get('action') == ProtocolMessageAction.DETACH:
            detach_messages.append(msg)
            mock_ws.send_to_client(detached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    states_during_detach = []

    def on_detaching(change):
        states_during_detach.append(channel.state)

    channel.on(ChannelState.DETACHING, on_detaching)

    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)

    assert states_during_detach == [ChannelState.DETACHING]
    assert channel.state == ChannelState.DETACHED
    assert len(detach_messages) == 1
    assert detach_messages[0]['action'] == ProtocolMessageAction.DETACH
    assert detach_messages[0]['channel'] == channel_name


# UTS: realtime/unit/RTL5f/timeout-returns-previous-state-0
async def test_rtl5f_timeout_returns_previous_state():
    channel_name = 'test-RTL5f'
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(mock_ws, clock=clock, realtime_request_timeout=100)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    detach_future = asyncio.ensure_future(channel.detach())
    await await_channel_state(channel, ChannelState.DETACHING, OPERATION_TIMEOUT)

    await clock.advance(150)

    with pytest.raises(AblyException) as error:
        await asyncio.wait_for(detach_future, OPERATION_TIMEOUT)

    assert channel.state == ChannelState.ATTACHED
    assert error.value is not None


# UTS: realtime/unit/RTL5k/attached-while-detaching-0
@deviation
async def test_rtl5k_attached_while_detaching():
    channel_name = 'test-RTL5k'
    detach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg.get('action') == ProtocolMessageAction.DETACH:
            detach_messages.append(msg)
            if len(detach_messages) == 1:
                mock_ws.send_to_client(attached_message(channel_name))
            else:
                mock_ws.send_to_client(detached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws, realtime_request_timeout=300)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)

    assert channel.state == ChannelState.DETACHED
    assert len(detach_messages) == 2


# UTS: realtime/unit/RTL5k/attached-while-detached-1
@deviation
async def test_rtl5k_attached_while_detached():
    channel_name = 'test-RTL5k-detached'
    detach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg.get('action') == ProtocolMessageAction.DETACH:
            detach_messages.append(msg)
            mock_ws.send_to_client(detached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.DETACHED
    assert len(detach_messages) == 1

    mock_ws.send_to_client(attached_message(channel_name))
    await poll_until(lambda: len(detach_messages) == 2, OPERATION_TIMEOUT, 'a second DETACH')

    assert len(detach_messages) == 2
    assert channel.state == ChannelState.DETACHED


# UTS: realtime/unit/RTL5/detach-state-change-events-0
async def test_rtl5_detach_state_change_events():
    channel_name = 'test-RTL5-events'
    state_changes = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg.get('action') == ProtocolMessageAction.DETACH:
            mock_ws.send_to_client(detached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    def record(change):
        state_changes.append(change)

    channel.on(record)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    state_changes.clear()

    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)

    assert len(state_changes) >= 2
    # The specification also asserts `event` on each change; ably-python has no
    # ChannelStateChange.event, the event being the key the listener is
    # registered against
    assert state_changes[0].current == ChannelState.DETACHING
    assert state_changes[0].previous == ChannelState.ATTACHED
    assert state_changes[1].current == ChannelState.DETACHED
    assert state_changes[1].previous == ChannelState.DETACHING
