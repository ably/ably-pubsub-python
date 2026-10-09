"""Derived from uts/realtime/unit/channels/channels_collection.md in ably/specification.

Spec points: RTS1, RTS2, RTS3a, RTS4c, RTS4d, RTS4e

The specification's `channels.exists(name)` and `channels.names` are spelled
`name in channels` and iteration over the collection in ably-python, and
`channels.release(name)` is synchronous. Reading an attribute the collection
does not define creates a channel of that name (`Channels.__getattr__` in
`ably/rest/channel.py`), so these tests never name one that is not there.
"""

import asyncio

import pytest

from ably.pubsub.realtime.channel import Channels as RealtimeChannels
from ably.pubsub.realtime.channel import RealtimeChannel
from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.transport.websockettransport import ProtocolMessageAction
from ably.pubsub.types.channelstate import ChannelState
from ably.pubsub.util.exceptions import AblyException
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.mock_websocket import (
    CONNECTED_MESSAGE,
    MockWebSocket,
    attached_message,
    detached_message,
)

# How long an operation which the specification expects to settle is given
# before a test calls it hung
OPERATION_TIMEOUT = 1.0


# UTS: realtime/unit/RTS1/channels-collection-accessible-0
async def test_rts1_channels_collection_accessible():
    client = realtime_client()

    channels = client.channels

    assert isinstance(channels, RealtimeChannels)
    assert channels is not None


# UTS: realtime/unit/RTS2/channel-exists-check-0
async def test_rts2_channel_exists_check():
    channel_name = 'test-RTS2'
    other_channel_name = 'test-RTS2-other'
    client = realtime_client()

    # `exists(name)` in the specification; `Channels.__contains__` here
    exists_before = channel_name in client.channels

    client.channels.get(channel_name)

    exists_after = channel_name in client.channels
    exists_other = other_channel_name in client.channels

    assert exists_before is False
    assert exists_after is True
    assert exists_other is False


# UTS: realtime/unit/RTS2/iterate-channels-1
async def test_rts2_iterate_channels():
    channel_name_a = 'test-RTS2-a'
    channel_name_b = 'test-RTS2-b'
    channel_name_c = 'test-RTS2-c'
    client = realtime_client()

    client.channels.get(channel_name_a)
    client.channels.get(channel_name_b)
    client.channels.get(channel_name_c)

    # The specification's `channels.names`; iterating the collection yields the
    # channels themselves, each of which carries its name
    names = [channel.name for channel in client.channels]

    assert channel_name_a in names
    assert channel_name_b in names
    assert channel_name_c in names
    assert len(names) == 3


# UTS: realtime/unit/RTS3a/get-creates-new-channel-0
async def test_rts3a_get_creates_new_channel():
    channel_name = 'test-RTS3a'
    client = realtime_client()

    channel = client.channels.get(channel_name)

    assert isinstance(channel, RealtimeChannel)
    assert channel.name == channel_name
    assert (channel_name in client.channels) is True


# UTS: realtime/unit/RTS3a/get-returns-existing-channel-1
async def test_rts3a_get_returns_existing_channel():
    channel_name = 'test-RTS3a-existing'
    client = realtime_client()

    channel1 = client.channels.get(channel_name)
    channel2 = client.channels.get(channel_name)

    assert channel1 is channel2
    assert channel1.name == channel_name
    assert channel2.name == channel_name


# UTS: realtime/unit/RTS3a/subscript-operator-channel-2
async def test_rts3a_subscript_operator_channel():
    channel_name = 'test-RTS3a-subscript'
    client = realtime_client()

    channel1 = client.channels[channel_name]
    channel2 = client.channels.get(channel_name)
    channel3 = client.channels[channel_name]

    assert channel1 is channel2
    assert channel2 is channel3
    assert channel1.name == channel_name


# UTS: realtime/unit/RTS4c/release-nonexistent-noop-0
async def test_rts4c_release_nonexistent_noop():
    channel_name = 'test-RTS4c-nonexistent'
    client = realtime_client()

    client.channels.release(channel_name)

    assert (channel_name in client.channels) is False


# UTS: realtime/unit/RTS4d/release-removes-channel-0
async def test_rts4d_release_removes_channel():
    channel_name = 'test-RTS4d'
    client = realtime_client()

    channel = client.channels.get(channel_name)
    assert channel.state == ChannelState.INITIALIZED
    assert (channel_name in client.channels) is True

    client.channels.release(channel_name)

    assert (channel_name in client.channels) is False


async def connected_client(answer_detach):
    """A connected client whose mock answers each ATTACH, and each DETACH if `answer_detach`.

    Returns the client and the list of messages it sends.
    """
    messages_from_client = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        messages_from_client.append(msg)
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(msg['channel']))
        elif msg.get('action') == ProtocolMessageAction.DETACH and answer_detach:
            mock_ws.send_to_client(detached_message(msg['channel']))

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(mock_ws)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client, messages_from_client


# UTS: realtime/unit/RTS4d/release-after-detach-1
async def test_rts4d_release_after_detach():
    channel_name = 'test-RTS4d-detached'
    client, _ = await connected_client(answer_detach=True)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.DETACHED

    client.channels.release(channel_name)

    assert (channel_name in client.channels) is False


# UTS: realtime/unit/RTS4e/release-attached-fails-0
async def test_rts4e_release_attached_fails():
    channel_name = 'test-RTS4e-attached'
    client, messages_from_client = await connected_client(answer_detach=False)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    with pytest.raises(AblyException) as exc_info:
        client.channels.release(channel_name)

    assert exc_info.value.code == 90011
    assert exc_info.value.status_code == 400
    assert channel.state == ChannelState.ATTACHED
    assert (channel_name in client.channels) is True
    assert client.channels.get(channel_name) is channel
    detach_messages = [m for m in messages_from_client if m.get('action') == ProtocolMessageAction.DETACH]
    assert len(detach_messages) == 0


# UTS: realtime/unit/RTS3a/get-after-release-new-3
async def test_rts3a_get_after_release_new():
    channel_name = 'test-RTS3a-release'
    client = realtime_client()

    channel1 = client.channels.get(channel_name)

    client.channels.release(channel_name)

    channel2 = client.channels.get(channel_name)

    assert channel1 is not channel2
    assert channel2.name == channel_name
    assert (channel_name in client.channels) is True
