"""Derived from uts/realtime/integration/channels/channel_publish_test.md in ably/specification.

Spec points: RTL6, RTL6f, RSL4, RSL6, RSL6a2

The specification carries a `## Protocol Variants` section, so every test here runs once
per protocol and passes `use_binary_protocol` to both clients it builds.

`RealtimeChannel.publish()` takes its arguments positionally; the keyword form the
specification writes, which `RestChannel.publish()` does accept, raises `ValueError`.

A binary payload arrives as a `bytearray` rather than `bytes` under either protocol, so
the type assertion reads both. `bytearray` compares equal to the `bytes` that was
published, so the equality the specification asks for is unaffected.

`Connection#id` is not a public member of ably-python's `Connection`; `connection_id`
below reads the same value off the connection manager, per the house ruling on missing
accessors in [deviations.md](../../../deviations.md).

The specification's `AWAIT_STATE` for CONNECTED is given ten seconds here. `await_connection_state`
defaults to five, which is the budget a mock-backed test needs; a real connect to the sandbox
opens a websocket over the network, and ten is the figure the sibling `channel_history_test.md`
spells out for the same wait.
"""

from ably.realtime.connection import ConnectionState
from ably.types.message import Message
from test.uts.helpers.client import await_connection_state, sandbox_realtime_client, wall_clock_poll_until
from test.uts.helpers.sandbox import random_id


def connection_id(client):
    """The specification's `client.connection.id`."""
    return client.connection.connection_manager.connection_id


async def connected_pair(key, use_binary_protocol):
    """The publisher and subscriber every test here opens with, both CONNECTED."""
    publisher = sandbox_realtime_client(
        key, auto_connect=False, use_binary_protocol=use_binary_protocol)
    subscriber = sandbox_realtime_client(
        key, auto_connect=False, use_binary_protocol=use_binary_protocol)
    publisher.connect()
    subscriber.connect()
    await await_connection_state(publisher, ConnectionState.CONNECTED, timeout=10)
    await await_connection_state(subscriber, ConnectionState.CONNECTED, timeout=10)
    return publisher, subscriber


# UTS: realtime/integration/RTL6/string-data-roundtrip-0
async def test_rtl6_string_data_roundtrip(realtime_sandbox, use_binary_protocol):
    publisher, subscriber = await connected_pair(realtime_sandbox.key_str, use_binary_protocol)

    channel_name = 'publish-string-' + random_id()
    pub_channel = publisher.channels.get(channel_name)
    sub_channel = subscriber.channels.get(channel_name)

    received = []

    def on_message(message):
        received.append(message)

    await sub_channel.subscribe(on_message)
    await pub_channel.attach()

    await pub_channel.publish('string-event', 'hello world')

    await wall_clock_poll_until(
        lambda: len(received) >= 1, description='the published string to be delivered')

    assert len(received) == 1
    assert received[0].name == 'string-event'
    assert received[0].data == 'hello world'
    assert isinstance(received[0].data, str)


# UTS: realtime/integration/RTL6/json-data-roundtrip-1
async def test_rtl6_json_data_roundtrip(realtime_sandbox, use_binary_protocol):
    publisher, subscriber = await connected_pair(realtime_sandbox.key_str, use_binary_protocol)

    channel_name = 'publish-json-' + random_id()
    pub_channel = publisher.channels.get(channel_name)
    sub_channel = subscriber.channels.get(channel_name)

    json_data = {'key': 'value', 'nested': {'count': 42}, 'list': [1, 2, 3]}

    received = []

    def on_message(message):
        received.append(message)

    await sub_channel.subscribe(on_message)
    await pub_channel.attach()

    await pub_channel.publish('json-event', json_data)

    await wall_clock_poll_until(
        lambda: len(received) >= 1, description='the published object to be delivered')

    assert len(received) == 1
    assert received[0].name == 'json-event'
    assert received[0].data['key'] == 'value'
    assert received[0].data['nested']['count'] == 42
    assert received[0].data['list'] == [1, 2, 3]


# UTS: realtime/integration/RTL6/binary-data-roundtrip-2
async def test_rtl6_binary_data_roundtrip(realtime_sandbox, use_binary_protocol):
    publisher, subscriber = await connected_pair(realtime_sandbox.key_str, use_binary_protocol)

    channel_name = 'publish-binary-' + random_id()
    pub_channel = publisher.channels.get(channel_name)
    sub_channel = subscriber.channels.get(channel_name)

    binary_data = bytes([0, 1, 2, 255, 128, 64])

    received = []

    def on_message(message):
        received.append(message)

    await sub_channel.subscribe(on_message)
    await pub_channel.attach()

    await pub_channel.publish('binary-event', binary_data)

    await wall_clock_poll_until(
        lambda: len(received) >= 1, description='the published bytes to be delivered')

    assert len(received) == 1
    assert received[0].name == 'binary-event'
    assert isinstance(received[0].data, (bytes, bytearray))
    assert received[0].data == binary_data


# UTS: realtime/integration/RTL6f/connectionid-matches-publisher-0
async def test_rtl6f_connectionid_matches_publisher(realtime_sandbox, use_binary_protocol):
    publisher, subscriber = await connected_pair(realtime_sandbox.key_str, use_binary_protocol)

    channel_name = 'publish-connid-' + random_id()
    pub_channel = publisher.channels.get(channel_name)
    sub_channel = subscriber.channels.get(channel_name)

    publisher_connection_id = connection_id(publisher)

    received = []

    def on_message(message):
        received.append(message)

    await sub_channel.subscribe(on_message)
    await pub_channel.attach()

    await pub_channel.publish('connid-test', 'data')

    await wall_clock_poll_until(
        lambda: len(received) >= 1, description='the published message to be delivered')

    assert received[0].connection_id == publisher_connection_id
    assert received[0].connection_id != connection_id(subscriber)


# UTS: realtime/integration/RSL6a2/message-extras-roundtrip-0
async def test_rsl6a2_message_extras_roundtrip(realtime_sandbox, use_binary_protocol):
    publisher, subscriber = await connected_pair(realtime_sandbox.key_str, use_binary_protocol)

    # The `pushenabled:` namespace is what lets a message carry push extras.
    channel_name = 'pushenabled:publish-extras-' + random_id()
    pub_channel = publisher.channels.get(channel_name)
    sub_channel = subscriber.channels.get(channel_name)

    extras = {'push': {'notification': {'title': 'Testing'}}}

    received = []

    def on_message(message):
        received.append(message)

    await sub_channel.subscribe(on_message)
    await pub_channel.attach()

    await pub_channel.publish(Message(name='extras-test', data='payload', extras=extras))

    await wall_clock_poll_until(
        lambda: len(received) >= 1, description='the message carrying extras to be delivered')

    assert received[0].extras is not None
    assert received[0].extras['push']['notification']['title'] == 'Testing'
