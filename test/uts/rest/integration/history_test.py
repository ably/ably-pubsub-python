"""Derived from uts/rest/integration/history.md in ably/specification.

Spec points: RSL2a, RSL2b1, RSL2b2, RSL2b3
"""

import asyncio

from test.uts.helpers.client import sandbox_rest_client, wall_clock_poll_until
from test.uts.helpers.sandbox import random_id


def history_page_of(channel, count):
    """A poll condition answering with the history page once it holds `count` messages.

    A `PaginatedResult` is truthy whether or not it holds anything, so answering with the
    page straight from `history()` would be satisfied by the first empty one. History is
    not immediately consistent after a publish, and the first page usually is empty.
    """
    async def condition():
        result = await channel.history()
        return result if len(result.items) == count else None

    return condition


# UTS: rest/integration/RSL2a/history-returns-messages-0
async def test_rsl2a_history_returns_messages(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)
    channel_name = 'history-test-RSL2a-' + random_id()
    channel = client.channels.get(channel_name)

    await channel.publish(name='event1', data='data1')
    await channel.publish(name='event2', data='data2')
    await channel.publish(name='event3', data={'key': 'value'})

    history = await wall_clock_poll_until(
        history_page_of(channel, 3), description='three messages to reach history')

    assert len(history.items) == 3

    # Default order is backwards (newest first)
    assert history.items[0].name == 'event3'
    assert history.items[0].data == {'key': 'value'}

    assert history.items[1].name == 'event2'
    assert history.items[1].data == 'data2'

    assert history.items[2].name == 'event1'
    assert history.items[2].data == 'data1'

    assert all(message.timestamp is not None for message in history.items)


# UTS: rest/integration/RSL2b1/history-direction-forwards-0
async def test_rsl2b1_history_direction_forwards(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)
    channel_name = 'history-direction-' + random_id()
    channel = client.channels.get(channel_name)

    # Publish messages - ordering is determined by server timestamp
    await channel.publish(name='first', data='1')
    await channel.publish(name='second', data='2')
    await channel.publish(name='third', data='3')

    await wall_clock_poll_until(
        history_page_of(channel, 3), description='three messages to reach history')

    # history() is history(direction=None, limit=None, start=None, end=None), so every
    # argument goes by keyword.
    history = await channel.history(direction='forwards')

    assert len(history.items) == 3
    assert history.items[0].name == 'first'
    assert history.items[1].name == 'second'
    assert history.items[2].name == 'third'


# UTS: rest/integration/RSL2b2/history-limit-parameter-0
async def test_rsl2b2_history_limit_parameter(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)
    channel_name = 'history-limit-' + random_id()
    channel = client.channels.get(channel_name)

    for i in range(1, 11):
        await channel.publish(name=f'event-{i}', data=str(i))

    await wall_clock_poll_until(
        history_page_of(channel, 10), description='ten messages to reach history')

    history = await channel.history(limit=5)

    assert len(history.items) == 5

    # Should get the 5 most recent (backwards direction by default)
    assert history.items[0].name == 'event-10'
    assert history.items[4].name == 'event-6'


# UTS: rest/integration/RSL2b3/history-time-range-0
async def test_rsl2b3_history_time_range(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)
    channel_name = 'history-timerange-' + random_id()
    channel = client.channels.get(channel_name)

    await channel.publish(name='early1', data='e1')
    await channel.publish(name='early2', data='e2')

    # Small delay to help ensure server assigns distinct timestamps between batches
    await asyncio.sleep(0.002)

    await channel.publish(name='late1', data='l1')
    await channel.publish(name='late2', data='l2')

    async def four_messages():
        result = await channel.history()
        return result.items if len(result.items) == 4 else None

    all_messages = await wall_clock_poll_until(
        four_messages, description='four messages to reach history')

    # Use server-assigned timestamps to define the time boundary. Client-side now() must
    # not be used here - client and server clocks may differ, and publishes may complete
    # within the same client-clock millisecond. Message.timestamp is milliseconds since
    # the epoch as a plain int, which is the form history's start and end take.
    early_timestamps = [m.timestamp for m in all_messages if m.name.startswith('early')]
    late_timestamps = [m.timestamp for m in all_messages if m.name.startswith('late')]

    max_early_ts = max(early_timestamps)
    min_late_ts = min(late_timestamps)
    time_boundary = (max_early_ts + min_late_ts) // 2

    early_history = await channel.history(
        start=max_early_ts - 1000,
        end=time_boundary,
    )

    late_history = await channel.history(
        start=time_boundary + 1,
        end=min_late_ts + 1000,
    )

    assert len(early_history.items) >= 1
    assert len(late_history.items) >= 1

    assert any(message.name.startswith('early') for message in early_history.items)
    assert any(message.name.startswith('late') for message in late_history.items)

    # UTS SPEC ERROR: the four assertions above hold whether or not `start` and `end` are
    # honoured. A server or client that dropped them entirely would answer both queries
    # with all four messages, which is non-empty and does contain an "early" and a "late"
    # name, so the test passes. What discriminates is that each window excludes the other
    # batch, asserted below. The premise the specification's 2ms wait exists to establish
    # is asserted first: with the two batches in the same millisecond the boundary
    # arithmetic has no side to put them on, and the test should say so rather than fail
    # on an exclusion that cannot hold.
    assert min_late_ts > max_early_ts
    assert not any(message.name.startswith('late') for message in early_history.items)
    assert not any(message.name.startswith('early') for message in late_history.items)


# UTS: rest/integration/RSL2/history-empty-channel-0
async def test_rsl2_history_empty_channel(sandbox, use_binary_protocol):
    client = sandbox_rest_client(sandbox.key_str, use_binary_protocol=use_binary_protocol)
    # Use a fresh channel with no messages
    channel_name = 'history-empty-' + random_id()
    channel = client.channels.get(channel_name)

    history = await channel.history()

    assert isinstance(history.items, list)
    assert len(history.items) == 0
    # has_next and is_last are methods here, not properties.
    assert history.has_next() is False
    assert history.is_last() is True
