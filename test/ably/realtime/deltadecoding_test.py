"""
Unit tests for delta (vcdiff) message decoding.

A protocol message can carry several messages, each one a delta from the message before it, so the
decoding context is chained per message and a batch that fails part way through leaves it untouched.
"""

import base64

import pytest

from ably import AblyRealtime
from ably.types.channelstate import ChannelState
from ably.types.message import Message
from ably.types.mixins import DecodingContext
from ably.types.options import VCDiffDecoder
from ably.util.exceptions import AblyException
from test.ably.utils import BaseAsyncTestCase


class AppendingDecoder(VCDiffDecoder):
    """A decoder whose output depends on the base, so a wrong base is visible in the result"""

    def __init__(self):
        self.number_of_calls = 0

    def decode(self, delta: bytes, base: bytes) -> bytes:
        self.number_of_calls += 1
        return base + delta


class FailingDecoder(VCDiffDecoder):

    def decode(self, delta: bytes, base: bytes) -> bytes:
        raise Exception("Failed to decode delta.")


def full_message(id, data):
    return {'id': id, 'name': id, 'data': data, 'encoding': 'utf-8'}


def delta_message(id, delta, from_id):
    """A message carrying `delta` as a vcdiff delta from the message `from_id`"""
    return {
        'id': id,
        'name': id,
        'data': base64.b64encode(delta.encode()).decode(),
        'encoding': 'utf-8/vcdiff/base64',
        'extras': {'delta': {'format': 'vcdiff', 'from': from_id}},
    }


class TestDeltaBatchDecoding(BaseAsyncTestCase):
    """Message.from_encoded_array over a protocol message's messages"""

    def test_batch_of_chained_deltas_decodes(self):
        decoder = AppendingDecoder()
        context = DecodingContext(vcdiff_decoder=decoder)

        messages = Message.from_encoded_array([
            full_message('m:0', 'a'),
            delta_message('m:1', 'b', from_id='m:0'),
            delta_message('m:2', 'c', from_id='m:1'),
        ], context=context)

        assert [message.data for message in messages] == ['a', 'ab', 'abc']
        assert decoder.number_of_calls == 2
        assert context.last_message_id == 'm:2'

    def test_delta_chains_from_the_previous_batch(self):
        context = DecodingContext(vcdiff_decoder=AppendingDecoder())

        Message.from_encoded_array([full_message('m:0', 'a')], context=context)
        messages = Message.from_encoded_array([delta_message('m:1', 'b', from_id='m:0')],
                                              context=context)

        assert [message.data for message in messages] == ['ab']

    def test_delta_from_an_unknown_message_is_rejected(self):
        context = DecodingContext(vcdiff_decoder=AppendingDecoder())
        Message.from_encoded_array([full_message('m:0', 'a')], context=context)

        with pytest.raises(AblyException) as excinfo:
            Message.from_encoded_array([delta_message('m:9', 'b', from_id='m:8')], context=context)

        assert excinfo.value.code == 40018

    def test_a_batch_that_fails_leaves_the_context_unchanged(self):
        # RTL18: the batch is discarded and replayed by the server from the last channel serial,
        # so the base payload has to still be the one the replayed batch decodes against
        context = DecodingContext(vcdiff_decoder=AppendingDecoder())
        Message.from_encoded_array([full_message('m:0', 'a')], context=context)
        base_payload, last_message_id = context.base_payload, context.last_message_id

        with pytest.raises(AblyException):
            Message.from_encoded_array([
                delta_message('m:1', 'b', from_id='m:0'),
                delta_message('m:2', 'c', from_id='out-of-order'),
            ], context=context)

        assert context.base_payload == base_payload
        assert context.last_message_id == last_message_id

    def test_a_batch_whose_decoder_fails_leaves_the_context_unchanged(self):
        context = DecodingContext(vcdiff_decoder=FailingDecoder())
        Message.from_encoded_array([full_message('m:0', 'a')], context=context)
        base_payload, last_message_id = context.base_payload, context.last_message_id

        with pytest.raises(AblyException) as excinfo:
            Message.from_encoded_array([delta_message('m:1', 'b', from_id='m:0')], context=context)

        assert excinfo.value.code == 40018
        assert context.base_payload == base_payload
        assert context.last_message_id == last_message_id

    def test_messages_decode_without_a_decoding_context(self):
        # the REST paths (history, for one) decode without a context
        messages = Message.from_encoded_array([full_message('m:0', 'a')])

        assert [message.data for message in messages] == ['a']

    def test_a_delta_without_a_decoding_context_reports_the_missing_decoder(self):
        # and not a failure to look up the previous message id in a context that isn't there
        with pytest.raises(AblyException) as excinfo:
            Message.from_encoded_array([delta_message('m:1', 'b', from_id='m:0')])

        assert excinfo.value.code == 40019


class TestChannelDeltaBatch(BaseAsyncTestCase):
    """RealtimeChannel handling of a protocol message carrying several deltas"""

    def setup_channel(self, decoder):
        ably = AblyRealtime(key='not_a.real:key', auto_connect=False, vcdiff_decoder=decoder)
        channel = ably.channels.get('delta')
        received = []
        # subscribe() would also wait for the channel to attach, which this client cannot do
        channel._RealtimeChannel__message_emitter.on(lambda message: received.append(message))
        return ably, channel, received

    async def test_every_message_of_a_delta_batch_is_emitted(self):
        ably, channel, received = self.setup_channel(AppendingDecoder())

        channel._on_message({
            'action': 15,
            'channel': 'delta',
            'channelSerial': 'serial-1',
            'messages': [
                full_message('m:0', 'a'),
                delta_message('m:1', 'b', from_id='m:0'),
                delta_message('m:2', 'c', from_id='m:1'),
            ],
        })

        assert [message.data for message in received] == ['a', 'ab', 'abc']
        assert channel._RealtimeChannel__channel_serial == 'serial-1'
        await ably.close()

    async def test_a_batch_that_fails_to_decode_starts_recovery(self):
        ably, channel, received = self.setup_channel(FailingDecoder())
        channel._on_message({
            'action': 15, 'channel': 'delta', 'channelSerial': 'serial-1',
            'messages': [full_message('m:0', 'a')],
        })

        channel._on_message({
            'action': 15,
            'channel': 'delta',
            'channelSerial': 'serial-2',
            'messages': [delta_message('m:1', 'b', from_id='m:0')],
        })

        # RTL18b/RTL18c: the batch is dropped and the channel reattaches from the serial of the
        # last batch it decoded
        assert [message.data for message in received] == ['a']
        assert channel._RealtimeChannel__channel_serial == 'serial-1'
        assert channel.state == ChannelState.ATTACHING
        assert channel.error_reason.code == 40018
        await ably.close()
