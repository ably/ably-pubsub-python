from datetime import datetime, timedelta

import pytest
import respx

from ably.pubsub.http.paginatedresult import PaginatedResult
from ably.pubsub.types.presence import PresenceMessage
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, VaryByProtocolTestsMetaclass, dont_vary_protocol


class TestPresence(BaseAsyncTestCase, metaclass=VaryByProtocolTestsMetaclass):

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.test_vars = await TestApp.get_test_vars()
        self.ably = await TestApp.get_ably_rest()
        self.channel = self.ably.channels.get('persisted:presence_fixtures')
        self.ably.options.use_binary_protocol = True
        yield
        self.ably.channels.release('persisted:presence_fixtures')
        await self.ably.close()

    def per_protocol_setup(self, use_binary_protocol):
        self.ably.options.use_binary_protocol = use_binary_protocol

    async def test_channel_presence_get(self):
        presence_page = await self.channel.presence.get()
        assert isinstance(presence_page, PaginatedResult)
        assert len(presence_page.items) == 6
        member = presence_page.items[0]
        assert isinstance(member, PresenceMessage)
        assert member.action
        assert member.id
        assert member.client_id
        assert member.data
        assert member.connection_id
        assert member.timestamp

    async def test_channel_presence_history(self):
        presence_history = await self.channel.presence.history()
        assert isinstance(presence_history, PaginatedResult)
        assert len(presence_history.items) == 6
        member = presence_history.items[0]
        assert isinstance(member, PresenceMessage)
        assert member.action
        assert member.id
        assert member.client_id
        assert member.data
        assert member.connection_id
        assert member.timestamp
        assert member.encoding

    async def test_presence_get_encoded(self):
        presence_history = await self.channel.presence.history()
        assert presence_history.items[-1].data == "true"
        assert presence_history.items[-2].data == "24"
        assert presence_history.items[-3].data == "This is a string clientData payload"
        # this one doesn't have encoding field
        assert presence_history.items[-4].data == '{ "test": "This is a JSONObject clientData payload"}'
        assert presence_history.items[-5].data == {"example": {"json": "Object"}}

    async def test_timestamp_is_datetime(self):
        presence_page = await self.channel.presence.get()
        member = presence_page.items[0]
        assert isinstance(member.timestamp, datetime)

    async def test_presence_message_has_correct_member_key(self):
        presence_page = await self.channel.presence.get()
        member = presence_page.items[0]

        assert member.member_key == f"{member.connection_id}:{member.client_id}"

    def presence_mock_url(self):
        kwargs = {
            'scheme': 'https' if self.test_vars['tls'] else 'http',
            'host': self.test_vars['host']
        }
        port = self.test_vars['tls_port'] if self.test_vars.get('tls') else kwargs['port']
        if port == 80:
            kwargs['port_sufix'] = ''
        else:
            kwargs['port_sufix'] = ':' + str(port)
        url = '{scheme}://{host}{port_sufix}/channels/persisted%3Apresence_fixtures/presence'
        return url.format(**kwargs)

    def history_mock_url(self):
        kwargs = {
            'scheme': 'https' if self.test_vars['tls'] else 'http',
            'host': self.test_vars['host']
        }
        port = self.test_vars['tls_port'] if self.test_vars.get('tls') else kwargs['port']
        if port == 80:
            kwargs['port_sufix'] = ''
        else:
            kwargs['port_sufix'] = ':' + str(port)
        url = '{scheme}://{host}{port_sufix}/channels/persisted%3Apresence_fixtures/presence/history'
        return url.format(**kwargs)

    @dont_vary_protocol
    @respx.mock
    async def test_get_presence_default_limit(self):
        url = self.presence_mock_url()
        self.respx_add_empty_msg_pack(url)
        await self.channel.presence.get()
        assert 'limit' not in respx.calls[0].request.url.params.keys()

    @dont_vary_protocol
    @respx.mock
    async def test_get_presence_with_limit(self):
        url = self.presence_mock_url()
        self.respx_add_empty_msg_pack(url)
        await self.channel.presence.get(300)
        assert '300' == respx.calls[0].request.url.params.get('limit')

    @dont_vary_protocol
    @respx.mock
    async def test_get_presence_max_limit_is_1000(self):
        url = self.presence_mock_url()
        self.respx_add_empty_msg_pack(url)
        with pytest.raises(ValueError):
            await self.channel.presence.get(5000)

    @dont_vary_protocol
    @respx.mock
    async def test_history_default_limit(self):
        url = self.history_mock_url()
        self.respx_add_empty_msg_pack(url)
        await self.channel.presence.history()
        assert 'limit' not in respx.calls[0].request.url.params.keys()

    @dont_vary_protocol
    @respx.mock
    async def test_history_with_limit(self):
        url = self.history_mock_url()
        self.respx_add_empty_msg_pack(url)
        await self.channel.presence.history(300)
        assert '300' == respx.calls[0].request.url.params.get('limit')

    @dont_vary_protocol
    @respx.mock
    async def test_history_with_direction(self):
        url = self.history_mock_url()
        self.respx_add_empty_msg_pack(url)
        await self.channel.presence.history(direction='backwards')
        assert 'backwards' == respx.calls[0].request.url.params.get('direction')

    @dont_vary_protocol
    @respx.mock
    async def test_history_max_limit_is_1000(self):
        url = self.history_mock_url()
        self.respx_add_empty_msg_pack(url)
        with pytest.raises(ValueError):
            await self.channel.presence.history(5000)

    @dont_vary_protocol
    @respx.mock
    async def test_with_milisecond_start_end(self):
        url = self.history_mock_url()
        self.respx_add_empty_msg_pack(url)
        await self.channel.presence.history(start=100000, end=100001)
        assert '100000' == respx.calls[0].request.url.params.get('start')
        assert '100001' == respx.calls[0].request.url.params.get('end')

    @dont_vary_protocol
    @respx.mock
    async def test_with_timedate_startend(self):
        url = self.history_mock_url()
        start = datetime(2015, 8, 15, 17, 11, 44, 706539)
        start_ms = 1439658704706
        end = start + timedelta(hours=1)
        end_ms = start_ms + (1000 * 60 * 60)
        self.respx_add_empty_msg_pack(url)
        await self.channel.presence.history(start=start, end=end)
        assert str(start_ms) in respx.calls[0].request.url.params.get('start')
        assert str(end_ms) in respx.calls[0].request.url.params.get('end')

    @dont_vary_protocol
    @respx.mock
    async def test_with_start_gt_end(self):
        url = self.history_mock_url()
        end = datetime(2015, 8, 15, 17, 11, 44, 706539)
        start = end + timedelta(hours=1)
        self.respx_add_empty_msg_pack(url)
        with pytest.raises(ValueError, match="'end' parameter has to be greater than or equal to 'start'"):
            await self.channel.presence.history(start=start, end=end)


class TestPresenceCrypt(BaseAsyncTestCase, metaclass=VaryByProtocolTestsMetaclass):

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.ably = await TestApp.get_ably_rest()
        key = b'0123456789abcdef'
        self.channel = self.ably.channels.get('persisted:presence_fixtures', cipher={'key': key})
        yield
        self.ably.channels.release('persisted:presence_fixtures')
        await self.ably.close()

    def per_protocol_setup(self, use_binary_protocol):
        self.ably.options.use_binary_protocol = use_binary_protocol

    async def test_presence_history_encrypted(self):
        presence_history = await self.channel.presence.history()
        assert presence_history.items[0].data == {'foo': 'bar'}

    async def test_presence_get_encrypted(self):
        messages = await self.channel.presence.get()
        messages = (msg for msg in messages.items if msg.client_id == 'client_encoded')
        message = next(messages)

        assert message.data == {'foo': 'bar'}
