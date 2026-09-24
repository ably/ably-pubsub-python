"""Derived from uts/realtime/unit/channels/channel_error.md in ably/specification.

Spec points: RTL14
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
from test.uts.helpers.mock_websocket import (
    CONNECTED_MESSAGE_NO_IDLE,
    MockWebSocket,
    attached_message,
    connected_message,
    server_detached_message,
)

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')

# How long an operation which the specification expects to settle is given
# before a test calls it hung
OPERATION_TIMEOUT = 1.0


def channel_error_message(channel, code, message, status_code):
    """An ERROR protocol message scoped to `channel`.

    A channel attribute is what distinguishes this from the connection-level
    ERROR of RTN15i; `ERROR_MESSAGE` in the helpers builds the latter.
    """
    return {
        'action': int(ProtocolMessageAction.ERROR),
        'channel': channel,
        'error': {'code': code, 'statusCode': status_code, 'message': message},
    }


def attach_echo(mock_ws, recorder=None):
    """A handler which confirms every ATTACH with an ATTACHED for the same channel."""
    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            if recorder is not None:
                recorder.append(msg)
            mock_ws.send_to_client(attached_message(msg.get('channel')))
    return on_message_from_client


async def connected_client(mock_ws, **kwargs):
    """A client connected through `mock_ws`."""
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


# UTS: realtime/unit/RTL14/attached-to-failed-0
async def test_rtl14_attached_to_failed():
    channel_name = 'test-RTL14-attached'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = attach_echo(mock_ws)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    channel_state_changes = []

    def record(change):
        channel_state_changes.append(change)

    channel.on(record)

    mock_ws.send_to_client(channel_error_message(channel_name, 40160, 'Not permitted', 401))
    await await_channel_state(channel, ChannelState.FAILED, OPERATION_TIMEOUT)

    assert channel.state == ChannelState.FAILED

    assert channel.error_reason is not None
    assert channel.error_reason.code == 40160
    assert channel.error_reason.status_code == 401
    assert 'Not permitted' in channel.error_reason.message

    assert len(channel_state_changes) == 1
    assert channel_state_changes[0].current == ChannelState.FAILED
    assert channel_state_changes[0].previous == ChannelState.ATTACHED
    assert channel_state_changes[0].reason is not None
    assert channel_state_changes[0].reason.code == 40160

    # A channel-scoped ERROR is dispatched to the channel and leaves the
    # connection alone
    assert client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/unit/RTL14/attaching-to-failed-1
async def test_rtl14_attaching_to_failed():
    channel_name = 'test-RTL14-attaching'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(
                channel_error_message(msg.get('channel'), 40160, 'Not permitted', 401))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    with pytest.raises(AblyException) as error:
        await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert channel.state == ChannelState.FAILED

    assert channel.error_reason is not None
    assert channel.error_reason.code == 40160

    assert error.value.code == 40160

    assert client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/unit/RTL14/pending-detach-error-2
async def test_rtl14_pending_detach_error():
    channel_name = 'test-RTL14-detaching'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        action = msg.get('action')
        if action == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(msg.get('channel')))
        elif action == ProtocolMessageAction.DETACH:
            mock_ws.send_to_client(
                channel_error_message(msg.get('channel'), 90198, 'Detach failed', 500))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    with pytest.raises(AblyException) as error:
        await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)

    assert channel.state == ChannelState.FAILED

    assert channel.error_reason is not None
    assert channel.error_reason.code == 90198

    assert error.value.code == 90198

    assert client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/unit/RTL14/other-channels-unaffected-3
async def test_rtl14_other_channels_unaffected():
    channel_name_a = 'test-RTL14-a'
    channel_name_b = 'test-RTL14-b'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = attach_echo(mock_ws)
    client = await connected_client(mock_ws)
    channel_a = client.channels.get(channel_name_a)
    channel_b = client.channels.get(channel_name_b)

    await asyncio.wait_for(channel_a.attach(), OPERATION_TIMEOUT)
    await asyncio.wait_for(channel_b.attach(), OPERATION_TIMEOUT)
    assert channel_a.state == ChannelState.ATTACHED
    assert channel_b.state == ChannelState.ATTACHED

    mock_ws.send_to_client(channel_error_message(channel_name_a, 40160, 'Not permitted', 401))
    await await_channel_state(channel_a, ChannelState.FAILED, OPERATION_TIMEOUT)

    assert channel_a.state == ChannelState.FAILED
    assert channel_a.error_reason is not None

    assert channel_b.state == ChannelState.ATTACHED
    assert channel_b.error_reason is None

    assert client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/unit/RTL14/cancels-pending-timers-4
async def test_rtl14_cancels_pending_timers():
    channel_name = 'test-RTL14-timers'
    attach_messages = []
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
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

    # A server-initiated DETACHED re-attaches the channel (RTL13a); the second
    # ATTACH goes unanswered, so the attach times out into SUSPENDED
    mock_ws.send_to_client(server_detached_message(channel_name, 90198, 'Detach', 500))
    await poll_until(lambda: len(attach_messages) == 2, OPERATION_TIMEOUT, 'a re-attach')

    await clock.advance(150)
    await await_channel_state(channel, ChannelState.SUSPENDED, OPERATION_TIMEOUT)

    # The channel retry timer is now pending; the ERROR arrives before it fires
    mock_ws.send_to_client(channel_error_message(channel_name, 40160, 'Not permitted', 401))
    await await_channel_state(channel, ChannelState.FAILED, OPERATION_TIMEOUT)

    attach_count_after_error = len(attach_messages)

    await clock.advance(500)
    await settle()

    assert channel.state == ChannelState.FAILED
    assert len(attach_messages) == attach_count_after_error
