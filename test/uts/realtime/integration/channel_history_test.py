"""Derived from uts/realtime/integration/channel_history_test.md in ably/specification.

Spec points: RTL10d

The specification carries a `## Protocol Variants` section, so the test runs once per
protocol and passes `use_binary_protocol` to both clients.

Its setup leaves `autoConnect` at the library default and calls `connect()` anyway, which
is what is derived here: the client is already CONNECTING by the time `connect()` is
called and the call is a no-op.

`RealtimeChannel` inherits `history()` from the REST `Channel`, so the read goes over
HTTP rather than the connection. A message does not reach history the instant its publish
is acknowledged, so the fetch is a `wall_clock_poll_until` answering `None` until the
page holds all three — a `PaginatedResult` is truthy whether or not it holds anything,
so returning the page directly would be satisfied by the first empty one.

`RealtimeChannel.publish()` takes its arguments positionally; the keyword form the
specification writes raises `ValueError`.
"""

from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client, wall_clock_poll_until
from test.uts.helpers.sandbox import random_id


# UTS: realtime/integration/RTL10d/history-cross-client-0
async def test_rtl10d_history_cross_client(realtime_sandbox, use_binary_protocol):
    channel_name = 'history-RTL10d-' + random_id()

    publisher = sandbox_realtime_client(
        realtime_sandbox.key_str, use_binary_protocol=use_binary_protocol)
    subscriber = sandbox_realtime_client(
        realtime_sandbox.key_str, use_binary_protocol=use_binary_protocol)

    publisher.connect()
    subscriber.connect()

    await await_connection_state(publisher, ConnectionState.CONNECTED, timeout=10)
    await await_connection_state(subscriber, ConnectionState.CONNECTED, timeout=10)

    pub_channel = publisher.channels.get(channel_name)
    sub_channel = subscriber.channels.get(channel_name)

    await pub_channel.attach()
    await sub_channel.attach()

    await pub_channel.publish('event1', 'data1')
    await pub_channel.publish('event2', 'data2')
    await pub_channel.publish('event3', 'data3')

    async def all_three_messages():
        page = await sub_channel.history()
        return page if len(page.items) == 3 else None

    history = await wall_clock_poll_until(
        all_three_messages, description='all three messages to reach history')

    assert len(history.items) == 3

    # The default order is backwards: newest first.
    assert history.items[0].name == 'event3'
    assert history.items[0].data == 'data3'

    assert history.items[1].name == 'event2'
    assert history.items[1].data == 'data2'

    assert history.items[2].name == 'event1'
    assert history.items[2].data == 'data1'
