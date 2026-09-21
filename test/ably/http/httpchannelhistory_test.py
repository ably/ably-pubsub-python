import logging

import pytest
import respx

from ably.pubsub.request.paginatedresult import PaginatedResult
from ably.pubsub.server import AblyException
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, VaryByProtocolTestsMetaclass, dont_vary_protocol

log = logging.getLogger(__name__)


class TestHttpChannelHistory(BaseAsyncTestCase, metaclass=VaryByProtocolTestsMetaclass):

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.ably = await TestApp.get_ably_rest(fallback_hosts=[])
        self.test_vars = await TestApp.get_test_vars()
        yield
        await self.ably.close()

    def per_protocol_setup(self, use_binary_protocol):
        self.ably.options.use_binary_protocol = use_binary_protocol

    async def test_channel_history_types(self):
        history0 = self.get_channel('persisted:channelhistory_types')

        await history0.publish('history0', 'This is a string message payload')
        await history0.publish('history1', b'This is a byte[] message payload')
        await history0.publish('history2', {'test': 'This is a JSONObject message payload'})
        await history0.publish('history3', ['This is a JSONArray message payload'])

        history = await history0.history()
        assert isinstance(history, PaginatedResult)
        messages = history.items
        assert messages is not None, "Expected non-None messages"
        assert 4 == len(messages), "Expected 4 messages"

        message_contents = {m.name: m for m in messages}
        assert "This is a string message payload" == message_contents["history0"].data, \
               "Expect history0 to be expected String)"
        assert b"This is a byte[] message payload" == message_contents["history1"].data, \
               "Expect history1 to be expected byte[]"
        assert {"test": "This is a JSONObject message payload"} == message_contents["history2"].data, \
               "Expect history2 to be expected JSONObject"
        assert ["This is a JSONArray message payload"] == message_contents["history3"].data, \
               "Expect history3 to be expected JSONObject"

        expected_message_history = [
            message_contents['history3'],
            message_contents['history2'],
            message_contents['history1'],
            message_contents['history0'],
        ]
        assert expected_message_history == messages, "Expect messages in reverse order"

    async def test_channel_history_multi_50_forwards(self):
        history0 = self.get_channel('persisted:channelhistory_multi_50_f')

        for i in range(50):
            await history0.publish(f'history{i}', str(i))

        history = await history0.history(direction='forwards')
        assert history is not None
        messages = history.items
        assert len(messages) == 50, "Expected 50 messages"

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(50)]
        assert messages == expected_messages, 'Expect messages in forward order'

    async def test_channel_history_multi_50_backwards(self):
        history0 = self.get_channel('persisted:channelhistory_multi_50_b')

        for i in range(50):
            await history0.publish(f'history{i}', str(i))

        history = await history0.history(direction='backwards')
        assert history is not None
        messages = history.items
        assert 50 == len(messages), "Expected 50 messages"

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(49, -1, -1)]
        assert expected_messages == messages, 'Expect messages in reverse order'

    def history_mock_url(self, channel_name):
        kwargs = {
            'scheme': 'https' if self.test_vars['tls'] else 'http',
            'host': self.test_vars['host'],
            'channel_name': channel_name
        }
        port = self.test_vars['tls_port'] if self.test_vars.get('tls') else kwargs['port']
        if port == 80:
            kwargs['port_sufix'] = ''
        else:
            kwargs['port_sufix'] = ':' + str(port)
        url = '{scheme}://{host}{port_sufix}/channels/{channel_name}/messages'
        return url.format(**kwargs)

    @respx.mock
    @dont_vary_protocol
    async def test_channel_history_default_limit(self):
        self.per_protocol_setup(True)
        channel = self.ably.channels['persisted:channelhistory_limit']
        url = self.history_mock_url('persisted:channelhistory_limit')
        self.respx_add_empty_msg_pack(url)
        await channel.history()
        assert 'limit' not in respx.calls[0].request.url.params.keys()

    @respx.mock
    @dont_vary_protocol
    async def test_channel_history_with_limits(self):
        self.per_protocol_setup(True)
        channel = self.ably.channels['persisted:channelhistory_limit']
        url = self.history_mock_url('persisted:channelhistory_limit')
        self.respx_add_empty_msg_pack(url)

        await channel.history(limit=500)
        assert '500' in respx.calls[0].request.url.params.get('limit')

        await channel.history(limit=1000)
        assert '1000' in respx.calls[1].request.url.params.get('limit')

    @dont_vary_protocol
    async def test_channel_history_max_limit_is_1000(self):
        channel = self.ably.channels['persisted:channelhistory_limit']
        with pytest.raises(AblyException):
            await channel.history(limit=1001)

    async def test_channel_history_limit_forwards(self):
        history0 = self.get_channel('persisted:channelhistory_limit_f')

        for i in range(50):
            await history0.publish(f'history{i}', str(i))

        history = await history0.history(direction='forwards', limit=25)
        assert history is not None
        messages = history.items
        assert len(messages) == 25, "Expected 25 messages"

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(25)]
        assert messages == expected_messages, 'Expect messages in forward order'

    async def test_channel_history_limit_backwards(self):
        history0 = self.get_channel('persisted:channelhistory_limit_b')

        for i in range(50):
            await history0.publish(f'history{i}', str(i))

        history = await history0.history(direction='backwards', limit=25)
        assert history is not None
        messages = history.items
        assert len(messages) == 25, "Expected 25 messages"

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(49, 24, -1)]
        assert messages == expected_messages, 'Expect messages in forward order'

    async def test_channel_history_time_forwards(self):
        history0 = self.get_channel('persisted:channelhistory_time_f')

        for i in range(20):
            await history0.publish(f'history{i}', str(i))

        interval_start = await self.ably.time()

        for i in range(20, 40):
            await history0.publish(f'history{i}', str(i))

        interval_end = await self.ably.time()

        for i in range(40, 60):
            await history0.publish(f'history{i}', str(i))

        history = await history0.history(direction='forwards', start=interval_start,
                                         end=interval_end)

        messages = history.items
        assert 20 == len(messages)

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(20, 40)]
        assert expected_messages == messages, 'Expect messages in forward order'

    async def test_channel_history_time_backwards(self):
        history0 = self.get_channel('persisted:channelhistory_time_b')

        for i in range(20):
            await history0.publish(f'history{i}', str(i))

        interval_start = await self.ably.time()

        for i in range(20, 40):
            await history0.publish(f'history{i}', str(i))

        interval_end = await self.ably.time()

        for i in range(40, 60):
            await history0.publish(f'history{i}', str(i))

        history = await history0.history(direction='backwards', start=interval_start,
                                         end=interval_end)

        messages = history.items
        assert 20 == len(messages)

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(39, 19, -1)]
        assert expected_messages, messages == 'Expect messages in reverse order'

    async def test_channel_history_paginate_forwards(self):
        history0 = self.get_channel('persisted:channelhistory_paginate_f')

        for i in range(50):
            await history0.publish(f'history{i}', str(i))

        history = await history0.history(direction='forwards', limit=10)
        messages = history.items

        assert 10 == len(messages)

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(0, 10)]
        assert expected_messages == messages, 'Expected 10 messages'

        history = await history.next()
        messages = history.items
        assert 10 == len(messages)

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(10, 20)]
        assert expected_messages == messages, 'Expected 10 messages'

        history = await history.next()
        messages = history.items
        assert 10 == len(messages)

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(20, 30)]
        assert expected_messages == messages, 'Expected 10 messages'

    async def test_channel_history_paginate_backwards(self):
        history0 = self.get_channel('persisted:channelhistory_paginate_b')

        for i in range(50):
            await history0.publish(f'history{i}', str(i))

        history = await history0.history(direction='backwards', limit=10)
        messages = history.items
        assert 10 == len(messages)

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(49, 39, -1)]
        assert expected_messages == messages, 'Expected 10 messages'

        history = await history.next()
        messages = history.items
        assert 10 == len(messages)

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(39, 29, -1)]
        assert expected_messages == messages, 'Expected 10 messages'

        history = await history.next()
        messages = history.items
        assert 10 == len(messages)

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(29, 19, -1)]
        assert expected_messages == messages, 'Expected 10 messages'

    async def test_channel_history_paginate_forwards_first(self):
        history0 = self.get_channel('persisted:channelhistory_paginate_first_f')
        for i in range(50):
            await history0.publish(f'history{i}', str(i))

        history = await history0.history(direction='forwards', limit=10)
        messages = history.items
        assert 10 == len(messages)

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(0, 10)]
        assert expected_messages == messages, 'Expected 10 messages'

        history = await history.next()
        messages = history.items
        assert 10 == len(messages)

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(10, 20)]
        assert expected_messages == messages, 'Expected 10 messages'

        history = await history.first()
        messages = history.items
        assert 10 == len(messages)

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(0, 10)]
        assert expected_messages == messages, 'Expected 10 messages'

    async def test_channel_history_paginate_backwards_rel_first(self):
        history0 = self.get_channel('persisted:channelhistory_paginate_first_b')

        for i in range(50):
            await history0.publish(f'history{i}', str(i))

        history = await history0.history(direction='backwards', limit=10)
        messages = history.items
        assert 10 == len(messages)

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(49, 39, -1)]
        assert expected_messages == messages, 'Expected 10 messages'

        history = await history.next()
        messages = history.items
        assert 10 == len(messages)

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(39, 29, -1)]
        assert expected_messages == messages, 'Expected 10 messages'

        history = await history.first()
        messages = history.items
        assert 10 == len(messages)

        message_contents = {m.name: m for m in messages}
        expected_messages = [message_contents[f'history{i}'] for i in range(49, 39, -1)]
        assert expected_messages == messages, 'Expected 10 messages'
