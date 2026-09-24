"""Derived from uts/realtime/unit/channels/channel_attributes.md in ably/specification.

Spec points: RTL4c, RTL23, RTL24
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
    realtime_client,
)
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import (
    CONNECTED_MESSAGE,
    MockWebSocket,
    attached_message,
    server_detached_message,
)

# How long an operation which the specification expects to settle is given
# before a test calls it hung
OPERATION_TIMEOUT = 1.0


def channel_error_message(channel, code, message, status_code):
    """An ERROR message scoped to a channel, which RTN15i routes to that channel."""
    return {
        'action': int(ProtocolMessageAction.ERROR),
        'channel': channel,
        'error': {'code': code, 'statusCode': status_code, 'message': message},
    }


async def connected_client(mock_ws, **kwargs):
    """A client connected through `mock_ws`, which the channel tests open with."""
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


# UTS: realtime/unit/RTL23/name-attribute-0
async def test_rtl23_name_attribute():
    client = realtime_client()

    channel = client.channels.get('my-channel')
    assert channel.name == 'my-channel'

    # Also works with special characters
    channel2 = client.channels.get('namespace:channel-name')
    assert channel2.name == 'namespace:channel-name'


# UTS: realtime/unit/RTL24/error-reason-channel-error-0
async def test_rtl24_error_reason_channel_error():
    channel_name = 'test-RTL24-error'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name, flags=0))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert channel.error_reason is None

    mock_ws.send_to_client(
        channel_error_message(channel_name, 90001, 'Channel error occurred', 500))

    await await_channel_state(channel, ChannelState.FAILED, OPERATION_TIMEOUT)

    assert channel.error_reason is not None
    assert channel.error_reason.code == 90001
    assert channel.error_reason.status_code == 500
    assert channel.error_reason.message == 'Channel error occurred'


# UTS: realtime/unit/RTL24/error-reason-attach-failure-1
@deviation
async def test_rtl24_error_reason_attach_failure():
    # DEVIATION: an attach rejected with a DETACHED carrying an error leaves `error_reason`
    # unset. `_on_message` (`ably/realtime/channel.py:735`) answers a DETACHED received while
    # ATTACHING with `_notify_state(ChannelState.SUSPENDED)` and no reason, discarding the
    # error. `attach()` then reaches `raise state_change.reason` (`:150`) with `reason` None,
    # which raises `TypeError: exceptions must derive from BaseException` rather than the
    # AblyException RTL24 describes.
    channel_name = 'test-RTL24-attach-fail'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(
                server_detached_message(channel_name, 40160, 'Permission denied', status_code=401))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    with pytest.raises(AblyException):
        await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert channel.error_reason is not None
    assert channel.error_reason.code == 40160
    assert channel.error_reason.status_code == 401


# UTS: realtime/unit/RTL4c/error-cleared-on-attach-0
@deviation
async def test_rtl4c_error_cleared_on_attach():
    # DEVIATION: as above, the error on the DETACHED which rejects the first attach is
    # discarded, so `error_reason` is never set and the attach raises TypeError rather than
    # an AblyException. The clearing half of RTL4c is covered by
    # `test_rtl4c_error_cleared_preserved_detach`, which sets the error with an ERROR message.
    channel_name = 'test-RTL24-clear-attach'
    attach_count = 0

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        nonlocal attach_count
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_count += 1
            if attach_count == 1:
                mock_ws.send_to_client(
                    server_detached_message(channel_name, 50000, 'Temporary error', status_code=500))
            else:
                mock_ws.send_to_client(attached_message(channel_name, flags=0))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    with pytest.raises(AblyException):
        await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.error_reason is not None
    assert channel.error_reason.code == 50000

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert channel.state == ChannelState.ATTACHED
    assert channel.error_reason is None


# UTS: realtime/unit/RTL4c/error-cleared-preserved-detach-1
async def test_rtl4c_error_cleared_preserved_detach():
    channel_name = 'test-RTL24-clear-detach'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name, flags=0))
        elif msg.get('action') == ProtocolMessageAction.DETACH:
            mock_ws.send_to_client({
                'action': int(ProtocolMessageAction.DETACHED), 'channel': channel_name})

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    mock_ws.send_to_client(channel_error_message(channel_name, 90002, 'Channel error', 500))

    await await_channel_state(channel, ChannelState.FAILED, OPERATION_TIMEOUT)

    assert channel.error_reason is not None
    assert channel.error_reason.code == 90002

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.error_reason is None

    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)

    assert channel.state == ChannelState.DETACHED
    assert channel.error_reason is None
