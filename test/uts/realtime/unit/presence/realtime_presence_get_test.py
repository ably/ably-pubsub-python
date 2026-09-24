"""Derived from uts/realtime/unit/presence/realtime_presence_get.md in ably/specification.

Spec points: RTP11, RTP11a, RTP11b, RTP11c, RTP11c1, RTP11c2, RTP11c3, RTP11d

`presence.get()` takes `wait_for_sync` as its first argument, then `client_id` and
`connection_id`, which is the specifications' `waitForSync`, `clientId` and
`connectionId`.

The two RTP11d tests reach a SUSPENDED channel by driving the connection to SUSPENDED
with a `FakeClock`: a bare transport drop leaves the connection DISCONNECTED and the
channel ATTACHED, and only a SUSPENDED connection propagates SUSPENDED to its channels
(`ably/realtime/channel.py:1047`). The `connectionStateTtl` the specification puts in
the CONNECTED is parsed and then ignored, so the wait is the 120 s default; see
test/uts/deviations.md.
"""

import asyncio
import uuid

import pytest

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelstate import ChannelState
from ably.types.flags import Flag
from ably.util.exceptions import AblyException
from test.uts.helpers.client import (
    await_channel_state,
    await_connection_state,
    poll_until,
    realtime_client,
)
from test.uts.helpers.clock import FakeClock, advance_to_connection_state, settle
from test.uts.helpers.mock_websocket import MockWebSocket, attached_message, connected_message
from test.uts.helpers.presence import present_member, sync_message

CONNECTED_MESSAGE = connected_message('conn-1', connectionKey='connection-key')

# How long an operation which the specification expects to settle is given
# before a test calls it hung
OPERATION_TIMEOUT = 2.0


def random_id():
    return uuid.uuid4().hex[:8]


def attaching_server(mock_ws, channel_name, has_presence=True, then=None):
    """Answers each ATTACH with an ATTACHED, optionally followed by `then`."""
    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            if has_presence:
                mock_ws.send_to_client(
                    attached_message(channel_name, flags=int(Flag.HAS_PRESENCE)))
            else:
                mock_ws.send_to_client(attached_message(channel_name))
            if then is not None:
                mock_ws.send_to_client(then)

    mock_ws.on_message_from_client = on_message_from_client
    return mock_ws


async def connected_client(mock_ws, **kwargs):
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


async def suspended_channel(channel_name):
    """A channel which reached SUSPENDED, holding one member from a completed sync.

    Returns the channel. Getting there means turning the whole connection retry
    cycle: the transport drops, reconnection is refused, and the clock runs past
    the connection state TTL.
    """
    clock = FakeClock()
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected_message('conn-1', maxIdleInterval=0, connectionStateTtl=5000)),
    )
    attaching_server(mock_ws, channel_name, then=sync_message(channel_name, 'seq1:', [
        present_member('alice', 'c1', 'c1:0:0'),
    ]))
    client = await connected_client(
        mock_ws, clock=clock, realtime_request_timeout=300,
        disconnected_retry_timeout=1000, suspended_retry_timeout=600000)
    channel = client.channels.get(channel_name)

    await channel.attach()
    await poll_until(
        lambda: len(channel.presence.members.values()) == 1, description='the sync to land')

    # Every reconnection attempt is left unanswered, so the retry cycle runs out
    mock_ws.on_connection_attempt = lambda conn: None
    mock_ws.simulate_disconnect()
    await settle()

    await advance_to_connection_state(client, clock, ConnectionState.SUSPENDED, step=5000)
    await await_channel_state(channel, ChannelState.SUSPENDED, OPERATION_TIMEOUT)
    return channel


# UTS: realtime/unit/RTP11a/get-returns-members-single-sync-0
async def test_rtp11a_get_returns_members_single_sync():
    channel_name = f'test-RTP11a-single-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    getting = asyncio.ensure_future(channel.presence.get())
    await settle()

    assert not getting.done()

    mock_ws.send_to_client(sync_message(channel_name, 'seq1:', [
        present_member('alice', 'c1', 'c1:0:0', data='a'),
        present_member('bob', 'c2', 'c2:0:0', data='b'),
    ]))

    members = await asyncio.wait_for(getting, OPERATION_TIMEOUT)

    assert len(members) == 2
    assert sorted(member.client_id for member in members) == ['alice', 'bob']


# UTS: realtime/unit/RTP11a/get-waits-for-multi-sync-1
async def test_rtp11a_get_waits_for_multi_sync():
    channel_name = f'test-RTP11c1-multi-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    getting = asyncio.ensure_future(channel.presence.get())
    await settle()

    assert not getting.done()

    mock_ws.send_to_client(sync_message(channel_name, 'seq1:cursor1', [
        present_member('alice', 'c1', 'c1:0:0'),
    ]))
    await poll_until(
        lambda: len(channel.presence.members.values()) == 1,
        description='the first sync message to land')
    await settle()

    # A non-empty cursor leaves the sync incomplete
    assert not getting.done()

    mock_ws.send_to_client(sync_message(channel_name, 'seq1:', [
        present_member('bob', 'c2', 'c2:0:0'),
    ]))

    members = await asyncio.wait_for(getting, OPERATION_TIMEOUT)

    assert len(members) == 2
    assert sorted(member.client_id for member in members) == ['alice', 'bob']


# UTS: realtime/unit/RTP11c1/get-no-wait-returns-immediately-0
async def test_rtp11c1_get_no_wait_returns_immediately():
    channel_name = f'test-RTP11c1-nowait-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name, then=sync_message(channel_name, 'seq1:cursor1', [
        present_member('alice', 'c1', 'c1:0:0'),
    ]))
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()
    await poll_until(
        lambda: len(channel.presence.members.values()) == 1,
        description='the partial sync to land')

    # The sync is still running, so a waiting get would not return here
    assert channel.presence.members.sync_in_progress
    assert not channel.presence.sync_complete

    members = await channel.presence.get(wait_for_sync=False)

    assert len(members) == 1
    assert members[0].client_id == 'alice'


# UTS: realtime/unit/RTP11c2/get-filtered-by-clientid-0
async def test_rtp11c2_get_filtered_by_clientid():
    channel_name = f'test-RTP11c2-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name, then=sync_message(channel_name, 'seq1:', [
        present_member('alice', 'c1', 'c1:0:0'),
        present_member('bob', 'c2', 'c2:0:0'),
        present_member('alice', 'c3', 'c3:0:0'),
    ]))
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    members = await channel.presence.get(client_id='alice')

    assert len(members) == 2
    assert all(member.client_id == 'alice' for member in members)


# UTS: realtime/unit/RTP11c3/get-filtered-by-connectionid-0
async def test_rtp11c3_get_filtered_by_connectionid():
    channel_name = f'test-RTP11c3-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name, then=sync_message(channel_name, 'seq1:', [
        present_member('alice', 'c1', 'c1:0:0'),
        present_member('bob', 'c2', 'c2:0:0'),
        present_member('carol', 'c1', 'c1:0:1'),
    ]))
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    members = await channel.presence.get(connection_id='c1')

    assert len(members) == 2
    assert all(member.connection_id == 'c1' for member in members)


# UTS: realtime/unit/RTP11b/get-implicitly-attaches-0
async def test_rtp11b_get_implicitly_attaches():
    channel_name = f'test-RTP11b-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    attaching_server(mock_ws, channel_name, has_presence=False)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    assert channel.state == ChannelState.INITIALIZED

    members = await channel.presence.get(wait_for_sync=False)

    assert channel.state == ChannelState.ATTACHED
    assert members is not None


# UTS: realtime/unit/RTP11d/get-suspended-errors-default-0
async def test_rtp11d_get_suspended_errors_default():
    channel = await suspended_channel(f'test-RTP11d-{random_id()}')

    with pytest.raises(AblyException) as error:
        await channel.presence.get()

    assert error.value is not None
    assert error.value.code == 91005


# UTS: realtime/unit/RTP11d/get-suspended-no-wait-returns-1
async def test_rtp11d_get_suspended_no_wait_returns():
    channel = await suspended_channel(f'test-RTP11d-nowait-{random_id()}')

    members = await channel.presence.get(wait_for_sync=False)

    assert len(members) == 1
    assert members[0].client_id == 'alice'
