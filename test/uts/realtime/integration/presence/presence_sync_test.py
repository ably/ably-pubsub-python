"""Derived from uts/realtime/integration/presence/presence_sync.md in ably/specification.

Spec points: RTP2, RTP11a

Client B attaches to a channel where client A is already present, so its members arrive
through the server-initiated SYNC rather than through live PRESENCE messages.
`presence.get()` waits for the SYNC to complete (RTP11a), which is why neither test polls:
a member delivered by SYNC is in the map by the time `get()` answers, and a `get()` that
answered early would show an empty set rather than a late one.

The specification is json only — it has no `## Protocol Variants` section — so these two
take the JSON default `sandbox_realtime_client` applies rather than the
`use_binary_protocol` fixture.

`enter_client` on a connection authenticated by key alone is refused 40012, a root cause
recorded in [deviations.md](../../../deviations.md), so the client entering members on
behalf of others is built with `client_id='*'`.
"""

from ably.realtime.connection import ConnectionState
from ably.types.presence import PresenceAction
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client
from test.uts.helpers.sandbox import random_id

# The specification's `member_count` for the multiple-member case.
MEMBER_COUNT = 10


# UTS: realtime/integration/RTP2/sync-delivers-members-0
async def test_rtp2_sync_delivers_members(realtime_sandbox):
    api_key = realtime_sandbox.key_str
    channel_name = 'presence-sync-' + random_id()

    client_a = sandbox_realtime_client(api_key, client_id='sync-member-a', auto_connect=False)
    client_b = sandbox_realtime_client(api_key, auto_connect=False)

    client_a.connect()
    await await_connection_state(client_a, ConnectionState.CONNECTED, timeout=10)

    channel_a = client_a.channels.get(channel_name)
    await channel_a.attach()
    await channel_a.presence.enter(data='sync-data')

    # Client A is already present by the time client B connects.
    client_b.connect()
    await await_connection_state(client_b, ConnectionState.CONNECTED, timeout=10)

    channel_b = client_b.channels.get(channel_name)
    await channel_b.attach()

    members = await channel_b.presence.get()

    assert len(members) == 1
    assert members[0].client_id == 'sync-member-a'
    assert members[0].data == 'sync-data'
    assert members[0].action == PresenceAction.PRESENT


# UTS: realtime/integration/RTP2/sync-multiple-members-1
async def test_rtp2_sync_multiple_members(realtime_sandbox):
    api_key = realtime_sandbox.key_str
    channel_name = 'presence-sync-multi-' + random_id()

    client_a = sandbox_realtime_client(api_key, auto_connect=False, client_id='*')
    client_b = sandbox_realtime_client(api_key, auto_connect=False)

    client_a.connect()
    await await_connection_state(client_a, ConnectionState.CONNECTED, timeout=10)

    channel_a = client_a.channels.get(channel_name)
    await channel_a.attach()

    for i in range(MEMBER_COUNT):
        await channel_a.presence.enter_client(f'sync-user-{i}', data=f'data-{i}')

    client_b.connect()
    await await_connection_state(client_b, ConnectionState.CONNECTED, timeout=10)

    channel_b = client_b.channels.get(channel_name)
    await channel_b.attach()

    members = await channel_b.presence.get()

    assert len(members) == MEMBER_COUNT

    members_by_client_id = {member.client_id: member for member in members}
    for i in range(MEMBER_COUNT):
        member = members_by_client_id.get(f'sync-user-{i}')
        assert member is not None
        assert member.data == f'data-{i}'
