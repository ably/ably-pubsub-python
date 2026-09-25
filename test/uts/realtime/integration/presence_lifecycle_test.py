"""Derived from uts/realtime/integration/presence_lifecycle.md in ably/specification.

Spec points: RTP4, RTP6, RTP8, RTP9, RTP10, RTP11a

Two connections against the sandbox: client A drives the presence set, client B watches
it. Everything client B asserts is read back from the server, so each phase waits for the
event to arrive before it calls `presence.get()`.

`RealtimePresence.subscribe()` is a coroutine, because it carries out the RTP6d implicit
attach, and a presence action is named by its lowercase wire name — `'enter'`,
`'present'`, `'update'`, `'leave'` — which is what `set_presence` emits.

Two adaptations, both of them root causes already recorded in
[deviations.md](../../deviations.md):

- Subscribing to several actions at once (RTP6b) raises `TypeError: unhashable type:
  'list'`, because the list reaches pyee as a dict key. The one listener is registered
  once per action instead, which is what the array form means.
- `enter_client` on a connection authenticated by key alone is refused 40012, so the
  client entering members on behalf of others is built with `client_id='*'`.
"""

import asyncio

from ably.realtime.connection import ConnectionState
from ably.types.presence import PresenceAction
from test.uts.helpers.client import (
    await_connection_state,
    sandbox_realtime_client,
    wall_clock_poll_until,
)
from test.uts.helpers.sandbox import random_id

# The specification's `member_count`. It notes that RTP4 says 250 and that 50 validates
# the same behaviour without the runtime.
MEMBER_COUNT = 50

# What the specification gives the bulk enter to be observed, against the 10 seconds it
# gives a single transition.
BULK_TIMEOUT = 15.0


# UTS: realtime/integration/RTP4/bulk-enter-observed-0
async def test_rtp4_bulk_enter_observed(realtime_sandbox, use_binary_protocol):
    api_key = realtime_sandbox.key_str
    channel_name = 'presence-bulk-' + random_id()

    client_a = sandbox_realtime_client(
        api_key, use_binary_protocol=use_binary_protocol, client_id='*')
    client_b = sandbox_realtime_client(api_key, use_binary_protocol=use_binary_protocol)

    client_a.connect()
    await await_connection_state(client_a, ConnectionState.CONNECTED, timeout=10)
    client_b.connect()
    await await_connection_state(client_b, ConnectionState.CONNECTED, timeout=10)

    channel_a = client_a.channels.get(channel_name)
    channel_b = client_b.channels.get(channel_name)
    await channel_b.attach()

    # Subscribe on client B before client A enters. Members are counted by clientId from
    # both ENTER and PRESENT events: if client B's connection drops mid-test, members it
    # missed arrive via the presence re-sync as PRESENT events rather than ENTER, and an
    # ENTER-only count would undercount forever.
    entered_client_ids = set()

    def on_member(event):
        entered_client_ids.add(event.client_id)

    await channel_b.presence.subscribe('enter', on_member)
    await channel_b.presence.subscribe('present', on_member)

    await channel_a.attach()

    await asyncio.gather(*[
        channel_a.presence.enter_client(f'user-{i}', data=f'data-{i}')
        for i in range(MEMBER_COUNT)
    ])

    await wall_clock_poll_until(
        lambda: len(entered_client_ids) >= MEMBER_COUNT,
        timeout=BULK_TIMEOUT,
        interval=0.2,
        description='client B to observe every member entering')

    members = await channel_b.presence.get()

    assert len(entered_client_ids) == MEMBER_COUNT

    assert len(members) == MEMBER_COUNT

    members_by_client_id = {member.client_id: member for member in members}
    for i in range(MEMBER_COUNT):
        member = members_by_client_id.get(f'user-{i}')
        assert member is not None
        assert member.data == f'data-{i}'


# UTS: realtime/integration/RTP8/enter-update-leave-lifecycle-0
async def test_rtp8_enter_update_leave_lifecycle(realtime_sandbox, use_binary_protocol):
    api_key = realtime_sandbox.key_str
    channel_name = 'presence-lifecycle-' + random_id()

    client_a = sandbox_realtime_client(
        api_key, use_binary_protocol=use_binary_protocol, client_id='lifecycle-client')
    client_b = sandbox_realtime_client(api_key, use_binary_protocol=use_binary_protocol)

    client_a.connect()
    await await_connection_state(client_a, ConnectionState.CONNECTED, timeout=10)
    client_b.connect()
    await await_connection_state(client_b, ConnectionState.CONNECTED, timeout=10)

    channel_a = client_a.channels.get(channel_name)
    channel_b = client_b.channels.get(channel_name)
    await channel_b.attach()

    all_events = []
    await channel_b.presence.subscribe(lambda event: all_events.append(event))

    await channel_a.attach()

    # --- Phase 1: Enter ---
    await channel_a.presence.enter(data='hello')

    await wall_clock_poll_until(
        lambda: len(all_events) >= 1, interval=0.2, description='the ENTER event on client B')

    members_after_enter = await channel_b.presence.get()
    assert len(members_after_enter) == 1
    assert members_after_enter[0].client_id == 'lifecycle-client'
    assert members_after_enter[0].data == 'hello'

    # --- Phase 2: Update ---
    await channel_a.presence.update(data='world')

    await wall_clock_poll_until(
        lambda: len(all_events) >= 2, interval=0.2, description='the UPDATE event on client B')

    members_after_update = await channel_b.presence.get()
    assert len(members_after_update) == 1
    assert members_after_update[0].data == 'world'

    # --- Phase 3: Leave ---
    await channel_a.presence.leave(data='goodbye')

    await wall_clock_poll_until(
        lambda: len(all_events) >= 3, interval=0.2, description='the LEAVE event on client B')

    members_after_leave = await channel_b.presence.get()
    assert len(members_after_leave) == 0

    assert len(all_events) >= 3

    enter_event = all_events[0]
    assert enter_event.action == PresenceAction.ENTER
    assert enter_event.client_id == 'lifecycle-client'
    assert enter_event.data == 'hello'

    update_event = all_events[1]
    assert update_event.action == PresenceAction.UPDATE
    assert update_event.client_id == 'lifecycle-client'
    assert update_event.data == 'world'

    leave_event = all_events[2]
    assert leave_event.action == PresenceAction.LEAVE
    assert leave_event.client_id == 'lifecycle-client'
    assert leave_event.data == 'goodbye'
