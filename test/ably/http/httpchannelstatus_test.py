import logging

import pytest

from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, VaryByProtocolTestsMetaclass

log = logging.getLogger(__name__)


class TestHttpChannelStatus(BaseAsyncTestCase, metaclass=VaryByProtocolTestsMetaclass):

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.ably = await TestApp.get_ably_rest()
        yield
        await self.ably.close()

    def per_protocol_setup(self, use_binary_protocol):
        self.ably.options.use_binary_protocol = use_binary_protocol
        self.use_binary_protocol = use_binary_protocol

    async def test_channel_status(self):
        channel_name = self.get_channel_name('test_channel_status')
        channel = self.ably.channels[channel_name]

        channel_status = await channel.status()

        assert channel_status is not None, "Expected non-None channel_status"
        assert channel_name == channel_status.channel_id, "Expected channel name to match"
        assert channel_status.status.is_active is True, "Expected is_active to be True"
        assert isinstance(channel_status.status.occupancy.metrics.publishers, int) and\
            channel_status.status.occupancy.metrics.publishers >= 0,\
            "Expected publishers to be a non-negative int"
        assert isinstance(channel_status.status.occupancy.metrics.connections, int) and\
            channel_status.status.occupancy.metrics.connections >= 0,\
            "Expected connections to be a non-negative int"
        assert isinstance(channel_status.status.occupancy.metrics.subscribers, int) and\
            channel_status.status.occupancy.metrics.subscribers >= 0,\
            "Expected subscribers to be a non-negative int"
        assert isinstance(channel_status.status.occupancy.metrics.presence_members, int) and\
            channel_status.status.occupancy.metrics.presence_members >= 0,\
            "Expected presence_members to be a non-negative int"
        assert isinstance(channel_status.status.occupancy.metrics.presence_connections, int) and\
            channel_status.status.occupancy.metrics.presence_connections >= 0,\
            "Expected presence_connections to be a non-negative int"
        assert isinstance(channel_status.status.occupancy.metrics.presence_subscribers, int) and\
            channel_status.status.occupancy.metrics.presence_subscribers >= 0,\
            "Expected presence_subscribers to be a non-negative int"
