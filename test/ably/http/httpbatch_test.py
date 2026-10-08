import logging

import pytest

from ably.pubsub.server import AblyException
from ably.pubsub.types.batch import (
    BatchPresenceSuccessResult,
    BatchPublishFailureResult,
    BatchPublishSpec,
    BatchPublishSuccessResult,
    BatchResult,
)
from ably.pubsub.types.message import Message
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, VaryByProtocolTestsMetaclass

log = logging.getLogger(__name__)


class TestHttpBatch(BaseAsyncTestCase, metaclass=VaryByProtocolTestsMetaclass):

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.test_vars = await TestApp.get_test_vars()
        self.ably = await TestApp.get_ably_rest()
        # keys[2] may publish to `canpublish:*` and to nothing else
        self.ably_restricted = await TestApp.get_ably_rest(key=self.test_vars['keys'][2]['key_str'])
        yield
        await self.ably.close()
        await self.ably_restricted.close()

    def per_protocol_setup(self, use_binary_protocol):
        self.ably.options.use_binary_protocol = use_binary_protocol
        self.ably_restricted.options.use_binary_protocol = use_binary_protocol
        self.use_binary_protocol = use_binary_protocol

    async def test_batch_publish_single_spec(self):
        channel_names = [self.get_channel_name('persisted:batch_publish_a'),
                         self.get_channel_name('persisted:batch_publish_b')]

        result = await self.ably.batch_publish(BatchPublishSpec(channels=channel_names, messages=[
            Message('string', 'This is a string message payload'),
            Message('binary', b'This is a byte[] message payload'),
            Message('json', {'test': 'This is a JSONObject message payload'}),
        ]))

        assert isinstance(result, BatchResult)
        assert result.success_count == 2
        assert result.failure_count == 0
        assert [entry.channel for entry in result.results] == channel_names
        for entry in result.results:
            assert isinstance(entry, BatchPublishSuccessResult)
            assert len(entry.serials) == 3

        for channel_name in channel_names:
            history = await self.ably.channels[channel_name].history(direction='forwards')
            messages = history.items
            assert [message.name for message in messages] == ['string', 'binary', 'json']
            assert messages[0].data == 'This is a string message payload'
            assert bytes(messages[1].data) == b'This is a byte[] message payload'
            assert messages[2].data == {'test': 'This is a JSONObject message payload'}
            # The library-generated ids share the prefix the result reports
            assert [message.id for message in messages] == [f'{result.results[0].message_id}:{serial}'
                                                            for serial in range(3)]

    async def test_batch_publish_array_of_specs(self):
        channel_a = self.get_channel_name('batch_publish_a')
        channel_b = self.get_channel_name('batch_publish_b')

        results = await self.ably.batch_publish([
            BatchPublishSpec(channels=[channel_a], messages=[Message('a', 'data-a')]),
            {'channels': [channel_a, channel_b], 'messages': [Message('b', 'data-b')]},
        ])

        assert isinstance(results, list)
        assert len(results) == 2
        assert [entry.channel for entry in results[0].results] == [channel_a]
        assert [entry.channel for entry in results[1].results] == [channel_a, channel_b]
        assert results[0].results[0].message_id != results[1].results[0].message_id

    async def test_batch_publish_partial_failure(self):
        allowed_channel = self.get_channel_name('canpublish:batch_publish')
        denied_channel = self.get_channel_name('batch_publish')

        result = await self.ably_restricted.batch_publish(BatchPublishSpec(
            channels=[allowed_channel, denied_channel],
            messages=[Message('event', 'data')],
        ))

        assert result.success_count == 1
        assert result.failure_count == 1

        success, failure = result.results
        assert isinstance(success, BatchPublishSuccessResult)
        assert success.channel == allowed_channel
        assert isinstance(failure, BatchPublishFailureResult)
        assert failure.channel == denied_channel
        assert isinstance(failure.error, AblyException)
        assert failure.error.code == 40160
        assert failure.error.status_code == 401

    async def test_batch_presence_empty_channels(self):
        channel_names = [self.get_channel_name('batch_presence_a'), self.get_channel_name('batch_presence_b')]

        result = await self.ably.batch_presence(channel_names)

        assert result.success_count == 2
        assert result.failure_count == 0
        assert [entry.channel for entry in result.results] == channel_names
        for entry in result.results:
            assert isinstance(entry, BatchPresenceSuccessResult)
            assert entry.presence == []
