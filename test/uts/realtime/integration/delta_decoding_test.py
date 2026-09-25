"""Derived from uts/realtime/integration/delta_decoding.md in ably/specification.

Spec points: PC3, PC3a, RTL18, RTL18b, RTL18c, RTL19b, RTL20

The full delta pipeline against the sandbox: a channel attached with
`params={'delta': 'vcdiff'}` has the server send every message after the first as a
vcdiff delta, and the SDK decodes it against the payload it stored for the previous one.

The specification's `plugins: { vcdiff: decoder }` is the `vcdiff_decoder` client option
here, and its `VCDiffDecoder` interface is `ably.types.options.VCDiffDecoder` —
`decode(delta, base) -> bytes`, the VD2a argument order. `AblyVCDiffDecoder` is the real
implementation, backed by the `vcdiff-decoder` library; `CountingDecoder` wraps it so a
test can assert how many deltas the server actually sent.

`clear_last_message_id` reaches into the channel's decoding context, which is what the
specification means by its implementation-specific `CLEAR channel._lastPayload.messageId`.
The stored id is the RTL20 base reference: clearing it makes the next delta fail its
check without any change to what the server sends.
"""

import os

from ably import AblyVCDiffDecoder
from ably.realtime.connection import ConnectionState
from ably.types.channeloptions import ChannelOptions
from ably.types.channelstate import ChannelState
from ably.types.options import VCDiffDecoder
from test.uts.helpers.client import (
    await_channel_state,
    await_connection_state,
    sandbox_realtime_client,
    wall_clock_poll_until,
)
from test.uts.helpers.deviations import deviation
from test.uts.helpers.sandbox import random_id

# The specification's `test_data`. The messages are deliberately similar, so that the
# server generates small vcdiff deltas rather than sending each one whole.
TEST_DATA = [
    {'foo': 'bar', 'count': 1, 'status': 'active'},
    {'foo': 'bar', 'count': 2, 'status': 'active'},
    {'foo': 'bar', 'count': 2, 'status': 'inactive'},
    {'foo': 'bar', 'count': 3, 'status': 'inactive'},
    {'foo': 'bar', 'count': 3, 'status': 'active'},
]

# The channel options that ask the server for deltas.
DELTA_PARAMS = ChannelOptions(params={'delta': 'vcdiff'})

# The specification's waits: 15 seconds for a straight delivery, 30 for one that has to
# go through the RTL18 recovery and a reattach first.
DELIVERY_TIMEOUT = 15.0
RECOVERY_TIMEOUT = 30.0


class CountingDecoder(VCDiffDecoder):
    """A real vcdiff decoder that records how many deltas it was given."""

    def __init__(self):
        self.decode_count = 0
        self.__decoder = AblyVCDiffDecoder()

    def decode(self, delta: bytes, base: bytes) -> bytes:
        self.decode_count += 1
        return self.__decoder.decode(delta, base)


class FailingDecoder(VCDiffDecoder):
    """A decoder that always fails, for the RTL18 decode-failure path."""

    def decode(self, delta: bytes, base: bytes) -> bytes:
        raise Exception('vcdiff decode failure')


def clear_last_message_id(channel):
    """Simulates a message gap by clearing the channel's stored last message id.

    The id lives on the channel's decoding context, which the channel builds in its
    constructor and holds privately. `DecodingContext.last_message_id` is the base
    reference RTL20 compares a delta's `extras.delta.from` against, so clearing it makes
    the next delta fail that check exactly as a dropped message would.
    """
    channel._RealtimeChannel__decoding_context.last_message_id = None


def record_attaching(channel):
    """Collects the state change behind every ATTACHING the channel enters from here.

    The specification watches this to see whether a decode failure sent the channel back
    round the RTL18 recovery: a test that expects no recovery asserts the list stayed
    empty, and one that expects recovery reads the error off the first entry.
    """
    changes = []
    channel.on(ChannelState.ATTACHING, lambda change: changes.append(change))
    return changes


async def delta_client(api_key, use_binary_protocol, decoder=None):
    """A CONNECTED client carrying the specification's vcdiff plugin."""
    client = sandbox_realtime_client(
        api_key, use_binary_protocol=use_binary_protocol, vcdiff_decoder=decoder)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=10)
    return client


async def publish_all(channel, payloads):
    """Publishes the dataset one message at a time, as the specification does."""
    for i, payload in enumerate(payloads):
        await channel.publish(str(i), payload)


# UTS: realtime/integration/PC3/delta-decode-end-to-end-0
async def test_pc3_delta_decode_end_to_end(realtime_sandbox, use_binary_protocol):
    channel_name = 'delta-PC3-' + random_id()
    counting_decoder = CountingDecoder()

    client = await delta_client(realtime_sandbox.key_str, use_binary_protocol, counting_decoder)

    channel = client.channels.get(channel_name, DELTA_PARAMS)
    await channel.attach()

    received_messages = []
    reattaches = record_attaching(channel)

    await channel.subscribe(lambda msg: received_messages.append(msg))

    await publish_all(channel, TEST_DATA)

    await wall_clock_poll_until(
        lambda: len(received_messages) == len(TEST_DATA) or reattaches,
        timeout=DELIVERY_TIMEOUT, interval=0.2, description='every message to be received')

    assert not reattaches, f'Channel reattaching due to decode failure: {reattaches[0].reason}'

    for i, payload in enumerate(TEST_DATA):
        assert received_messages[i].name == str(i)
        assert received_messages[i].data == payload

    # The first message is sent as a full payload, the rest as deltas.
    assert counting_decoder.decode_count == len(TEST_DATA) - 1


# UTS: realtime/integration/RTL19b/dissimilar-payloads-no-delta-0
async def test_rtl19b_dissimilar_payloads_no_delta(realtime_sandbox, use_binary_protocol):
    channel_name = 'delta-dissimilar-' + random_id()
    message_count = 5
    counting_decoder = CountingDecoder()

    client = await delta_client(realtime_sandbox.key_str, use_binary_protocol, counting_decoder)

    # Random binary payloads, 1KB each and completely dissimilar, so that a delta would
    # be no smaller than the message it encodes.
    payloads = [os.urandom(1024) for _ in range(message_count)]

    channel = client.channels.get(channel_name, DELTA_PARAMS)
    await channel.attach()

    received_messages = []
    reattaches = record_attaching(channel)

    await channel.subscribe(lambda msg: received_messages.append(msg))

    await publish_all(channel, payloads)

    await wall_clock_poll_until(
        lambda: len(received_messages) == message_count or reattaches,
        timeout=DELIVERY_TIMEOUT, interval=0.2, description='every message to be received')

    assert not reattaches, f'Channel reattaching due to decode failure: {reattaches[0].reason}'

    for i, payload in enumerate(payloads):
        assert received_messages[i].name == str(i)
        assert received_messages[i].data == payload

    # The server is expected to send full messages for dissimilar random binary payloads,
    # but it is free to generate deltas anyway, so the count is reported rather than
    # asserted. The assertions above hold either way: a delta that was sent was decoded
    # back to the payload that was published.
    print(f'Decoder was called {counting_decoder.decode_count} times '
          f'for {message_count} dissimilar messages')


# UTS: realtime/integration/PC3/no-deltas-without-param-1
async def test_pc3_no_deltas_without_param(realtime_sandbox, use_binary_protocol):
    channel_name = 'delta-no-param-' + random_id()
    counting_decoder = CountingDecoder()

    client = await delta_client(realtime_sandbox.key_str, use_binary_protocol, counting_decoder)

    # Attached without the delta param, so the server has not been asked for deltas.
    channel = client.channels.get(channel_name)
    await channel.attach()

    received_messages = []
    await channel.subscribe(lambda msg: received_messages.append(msg))

    await publish_all(channel, TEST_DATA)

    await wall_clock_poll_until(
        lambda: len(received_messages) == len(TEST_DATA),
        timeout=DELIVERY_TIMEOUT, interval=0.2, description='every message to be received')

    for i, payload in enumerate(TEST_DATA):
        assert received_messages[i].name == str(i)
        assert received_messages[i].data == payload

    assert counting_decoder.decode_count == 0


# UTS: realtime/integration/RTL18/recovery-message-id-mismatch-0
async def test_rtl18_recovery_message_id_mismatch(realtime_sandbox, use_binary_protocol):
    channel_name = 'delta-recovery-mismatch-' + random_id()
    counting_decoder = CountingDecoder()

    client = await delta_client(realtime_sandbox.key_str, use_binary_protocol, counting_decoder)

    channel = client.channels.get(channel_name, DELTA_PARAMS)
    await channel.attach()

    received_messages = []
    attaching_changes = record_attaching(channel)

    await channel.subscribe(lambda msg: received_messages.append(msg))

    # Publishing in two batches makes sure the server has sent and the client has
    # processed the first batch before the stored id is cleared. Published all at once
    # they could arrive in a single ProtocolMessage, decoded before the clear takes
    # effect.
    await publish_all(channel, TEST_DATA[:3])

    await wall_clock_poll_until(
        lambda: len(received_messages) >= 3,
        timeout=DELIVERY_TIMEOUT, interval=0.2, description='the first batch to be received')

    clear_last_message_id(channel)

    for i in range(3, len(TEST_DATA)):
        await channel.publish(str(i), TEST_DATA[i])

    # Recovery reattaches and the server resends from the channelSerial, so a message may
    # arrive twice; what is waited for is every name having arrived at least once.
    expected_names = {str(i) for i in range(len(TEST_DATA))}
    await wall_clock_poll_until(
        lambda: {msg.name for msg in received_messages} >= expected_names,
        timeout=RECOVERY_TIMEOUT, interval=0.2, description='every message to be received')

    for i, payload in enumerate(TEST_DATA):
        msg = next((m for m in received_messages if m.name == str(i)), None)
        assert msg is not None
        assert msg.data == payload

    # RTL18c: recovery was triggered, carrying the delta decode failure.
    assert len(attaching_changes) >= 1
    assert attaching_changes[0].reason.code == 40018


# UTS: realtime/integration/RTL18/recovery-decode-failure-1
async def test_rtl18_recovery_decode_failure(realtime_sandbox, use_binary_protocol):
    channel_name = 'delta-recovery-decode-' + random_id()

    client = await delta_client(
        realtime_sandbox.key_str, use_binary_protocol, FailingDecoder())

    channel = client.channels.get(channel_name, DELTA_PARAMS)
    await channel.attach()

    received_messages = []
    attaching_changes = record_attaching(channel)

    await channel.subscribe(lambda msg: received_messages.append(msg))

    await publish_all(channel, TEST_DATA)

    # The first message arrives as a non-delta, the second fails to decode and triggers
    # recovery, and the rest arrive after the reattach — as non-deltas, since the decode
    # context is gone.
    await wall_clock_poll_until(
        lambda: len(received_messages) >= len(TEST_DATA),
        timeout=RECOVERY_TIMEOUT, interval=0.2, description='every message to be received')

    for i, payload in enumerate(TEST_DATA):
        msg = next((m for m in received_messages if m.name == str(i)), None)
        assert msg is not None
        assert msg.data == payload

    # RTL18c: at least one recovery was triggered.
    assert len(attaching_changes) >= 1
    assert attaching_changes[0].reason.code == 40018


# UTS: realtime/integration/PC3/no-plugin-causes-failed-2
@deviation
async def test_pc3_no_plugin_causes_failed(realtime_sandbox, use_binary_protocol):
    channel_name = 'delta-no-plugin-' + random_id()

    # The subscriber asks for deltas with no decoder to apply them with. The publisher is
    # a separate connection so that the subscriber's channel going FAILED cannot fail the
    # publishes or their pending ACKs.
    subscriber = await delta_client(realtime_sandbox.key_str, use_binary_protocol)
    publisher = await delta_client(realtime_sandbox.key_str, use_binary_protocol)

    sub_channel = subscriber.channels.get(channel_name, DELTA_PARAMS)
    await sub_channel.attach()

    pub_channel = publisher.channels.get(channel_name)
    await pub_channel.attach()

    await publish_all(pub_channel, TEST_DATA)

    await await_channel_state(sub_channel, ChannelState.FAILED, timeout=DELIVERY_TIMEOUT)

    assert sub_channel.state == ChannelState.FAILED
    assert sub_channel.error_reason.code == 40019
