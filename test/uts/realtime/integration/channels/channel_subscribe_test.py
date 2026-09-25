"""Derived from uts/realtime/integration/channels/channel_subscribe_test.md in ably/specification.

Spec points: RTL7, RTL7a, RTL7b, RTL7d

There is no `## Protocol Variants` section, so these run against JSON only and take no
`use_binary_protocol`.

`RealtimeChannel.subscribe()` is a coroutine that attaches the channel (RTL7c) and
returns nothing, so every registration here is awaited, including the second one in
RTL7b which the specification writes without `AWAIT`. Each listener is its own `def`:
`EventEmitter` keys its wrapper registry on the listener object alone, so registering
one function against two events would overwrite the first registration.

`RealtimeChannel.publish()` takes its arguments positionally; the keyword form the
specification writes raises `ValueError`.

The specification's `AWAIT_STATE` for CONNECTED is given ten seconds here. `await_connection_state`
defaults to five, which is the budget a mock-backed test needs; a real connect to the sandbox
opens a websocket over the network, and ten is the figure the sibling `channel_history_test.md`
spells out for the same wait.
"""

from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client, wall_clock_poll_until
from test.uts.helpers.sandbox import random_id


async def connected_pair(key, **kwargs):
    """Two realtime clients built as the specification's setup builds them, both CONNECTED.

    `kwargs` reaches each client, which is how RTL7 gives its two their client ids. Both
    clients otherwise take the same options, so a single mapping serves.
    """
    first = sandbox_realtime_client(key, auto_connect=False, **kwargs)
    second = sandbox_realtime_client(key, auto_connect=False, **kwargs)
    first.connect()
    second.connect()
    await await_connection_state(first, ConnectionState.CONNECTED, timeout=10)
    await await_connection_state(second, ConnectionState.CONNECTED, timeout=10)
    return first, second


# UTS: realtime/integration/RTL7a/subscribe-all-messages-0
async def test_rtl7a_subscribe_all_messages(realtime_sandbox):
    publisher, subscriber = await connected_pair(realtime_sandbox.key_str)

    channel_name = 'subscribe-all-' + random_id()
    pub_channel = publisher.channels.get(channel_name)
    sub_channel = subscriber.channels.get(channel_name)

    received = []

    def on_message(message):
        received.append(message)

    await sub_channel.subscribe(on_message)
    await pub_channel.attach()

    await pub_channel.publish('event-a', 'data-a')
    await pub_channel.publish('event-b', 'data-b')
    await pub_channel.publish('event-c', 'data-c')

    await wall_clock_poll_until(
        lambda: len(received) >= 3, description='all three messages to be delivered')

    assert len(received) == 3

    names = [message.name for message in received]
    assert 'event-a' in names
    assert 'event-b' in names
    assert 'event-c' in names


# UTS: realtime/integration/RTL7b/subscribe-filtered-by-name-0
async def test_rtl7b_subscribe_filtered_by_name(realtime_sandbox):
    publisher, subscriber = await connected_pair(realtime_sandbox.key_str)

    channel_name = 'subscribe-filtered-' + random_id()
    pub_channel = publisher.channels.get(channel_name)
    sub_channel = subscriber.channels.get(channel_name)

    target_received = []
    all_received = []

    def on_target(message):
        target_received.append(message)

    def on_any(message):
        all_received.append(message)

    await sub_channel.subscribe('target', on_target)

    # Subscribing to every event as well gives the poll below something to wait on that
    # covers the messages the filtered subscription is meant to drop.
    await sub_channel.subscribe(on_any)

    await pub_channel.attach()

    await pub_channel.publish('other', 'ignored')
    await pub_channel.publish('target', 'wanted-1')
    await pub_channel.publish('other', 'ignored')
    await pub_channel.publish('target', 'wanted-2')

    await wall_clock_poll_until(
        lambda: len(all_received) >= 4, description='all four messages to be delivered')

    assert len(all_received) == 4

    assert len(target_received) == 2
    assert target_received[0].name == 'target'
    assert target_received[0].data == 'wanted-1'
    assert target_received[1].name == 'target'
    assert target_received[1].data == 'wanted-2'


# UTS: realtime/integration/RTL7/bidirectional-message-flow-0
async def test_rtl7_bidirectional_message_flow(realtime_sandbox):
    client_a = sandbox_realtime_client(
        realtime_sandbox.key_str, auto_connect=False, client_id='client-a')
    client_b = sandbox_realtime_client(
        realtime_sandbox.key_str, auto_connect=False, client_id='client-b')
    client_a.connect()
    client_b.connect()
    await await_connection_state(client_a, ConnectionState.CONNECTED, timeout=10)
    await await_connection_state(client_b, ConnectionState.CONNECTED, timeout=10)

    channel_name = 'subscribe-bidir-' + random_id()
    channel_a = client_a.channels.get(channel_name)
    channel_b = client_b.channels.get(channel_name)

    received_by_a = []
    received_by_b = []

    def on_message_for_a(message):
        received_by_a.append(message)

    def on_message_for_b(message):
        received_by_b.append(message)

    await channel_a.subscribe(on_message_for_a)
    await channel_b.subscribe(on_message_for_b)

    await channel_a.publish('from-a', 'hello from a')
    await channel_b.publish('from-b', 'hello from b')

    await wall_clock_poll_until(
        lambda: len(received_by_a) >= 2 and len(received_by_b) >= 2,
        description='both clients to receive both messages')

    # Each client receives both publishers' messages, its own echo included.
    a_names = [message.name for message in received_by_a]
    b_names = [message.name for message in received_by_b]

    assert 'from-a' in a_names
    assert 'from-b' in a_names
    assert 'from-a' in b_names
    assert 'from-b' in b_names
