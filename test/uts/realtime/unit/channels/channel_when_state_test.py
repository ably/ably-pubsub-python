"""Derived from uts/realtime/unit/channels/channel_when_state_test.md in ably/specification.

Spec points: RTL25, RTL25a, RTL25b
"""

import asyncio

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelstate import ChannelState
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import (
    MockWebSocket,
    attached_message,
    connected_message,
    detached_message,
)

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')

# How long an operation which the specification expects to settle is given
# before a test calls it hung
OPERATION_TIMEOUT = 1.0

# What the specification's WAIT(200) allows for a resolution that must not happen
NON_RESOLUTION_WINDOW = 0.2


def echo_attach_and_detach(mock_ws):
    """A handler confirming each ATTACH with an ATTACHED and each DETACH with a DETACHED."""
    def on_message_from_client(msg):
        action = msg.get('action')
        if action == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(msg.get('channel'), flags=0))
        elif action == ProtocolMessageAction.DETACH:
            mock_ws.send_to_client(detached_message(msg.get('channel')))
    return on_message_from_client


def when_state(channel, state):
    """The specification's `channel.whenState(state)`.

    RTL25 puts `whenState` on RealtimeChannel, mirroring `Connection#whenState`
    (RTN26). ably-python has `Connection._when_state` but nothing on
    RealtimeChannel, so this raises AttributeError. See
    deviations.md
    """
    return channel.when_state(state)


async def connected_client(mock_ws, **kwargs):
    """A client connected through `mock_ws`."""
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


# UTS: realtime/unit/RTL25a/resolves-immediately-current-0
@deviation
async def test_rtl25a_resolves_immediately_current():
    channel_name = 'test-RTL25a-immediate'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attach_and_detach(mock_ws)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    result = await asyncio.wait_for(when_state(channel, ChannelState.ATTACHED), OPERATION_TIMEOUT)

    assert result is None


# UTS: realtime/unit/RTL25b/waits-for-state-change-0
@deviation
async def test_rtl25b_waits_for_state_change():
    channel_name = 'test-RTL25b-deferred'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attach_and_detach(mock_ws)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    when_attached = asyncio.ensure_future(when_state(channel, ChannelState.ATTACHED))
    await settle()

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    result = await asyncio.wait_for(when_attached, OPERATION_TIMEOUT)

    assert result is not None
    assert result.current == ChannelState.ATTACHED
    assert result.previous in (ChannelState.INITIALIZED, ChannelState.ATTACHING)


# UTS: realtime/unit/RTL25b/fires-once-only-1
@deviation
async def test_rtl25b_fires_once_only():
    channel_name = 'test-RTL25b-once'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attach_and_detach(mock_ws)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    attach_count = []

    def count_attached(change):
        attach_count.append(change)

    channel.once(ChannelState.ATTACHED, count_attached)

    when_attached = asyncio.ensure_future(when_state(channel, ChannelState.ATTACHED))
    await settle()

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    result = await asyncio.wait_for(when_attached, OPERATION_TIMEOUT)
    assert result is not None
    assert len(attach_count) == 1

    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    await settle()

    assert len(attach_count) == 1


# UTS: realtime/unit/RTL25a/past-state-does-not-resolve-1
@deviation
async def test_rtl25a_past_state_does_not_resolve():
    channel_name = 'test-RTL25a-past'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attach_and_detach(mock_ws)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    # ATTACHING was passed through on the way here; whenState reads the current
    # state, not the states already visited
    when_attaching = asyncio.ensure_future(when_state(channel, ChannelState.ATTACHING))
    await asyncio.sleep(NON_RESOLUTION_WINDOW)

    assert not when_attaching.done()
    when_attaching.cancel()
