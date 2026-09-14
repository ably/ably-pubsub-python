from collections.abc import Iterable

import pytest

from ably.pubsub.rest.channel import Channel, Channels, Presence
from ably.pubsub.server import AblyException
from ably.pubsub.util.crypto import generate_random_key
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase


# makes no request, no need to use different protocols
class TestChannels(BaseAsyncTestCase):

    @pytest.fixture(autouse=True)
    async def setup(self):
        self.test_vars = await TestApp.get_test_vars()
        self.ably = await TestApp.get_ably_rest()
        yield
        await self.ably.close()

    def test_rest_channels_attr(self):
        assert hasattr(self.ably, 'channels')
        assert isinstance(self.ably.channels, Channels)

    def test_channels_get_returns_new_or_existing(self):
        channel = self.ably.channels.get('new_channel')
        assert isinstance(channel, Channel)
        channel_same = self.ably.channels.get('new_channel')
        assert channel is channel_same

    def test_channels_get_returns_new_with_options(self):
        key = generate_random_key()
        channel = self.ably.channels.get('new_channel', cipher={'key': key})
        assert isinstance(channel, Channel)
        assert channel.cipher.secret_key is key

    def test_channels_get_updates_existing_with_options(self):
        key = generate_random_key()
        channel = self.ably.channels.get('new_channel', cipher={'key': key})
        assert channel.cipher is not None

        channel_same = self.ably.channels.get('new_channel', cipher=None)
        assert channel is channel_same
        assert channel.cipher is None

    def test_channels_get_doesnt_updates_existing_with_none_options(self):
        key = generate_random_key()
        channel = self.ably.channels.get('new_channel', cipher={'key': key})
        assert channel.cipher is not None

        channel_same = self.ably.channels.get('new_channel')
        assert channel is channel_same
        assert channel.cipher is not None

    def test_channels_in(self):
        assert 'new_channel' not in self.ably.channels
        self.ably.channels.get('new_channel')
        new_channel_2 = self.ably.channels.get('new_channel_2')
        assert 'new_channel' in self.ably.channels
        assert new_channel_2 in self.ably.channels

    def test_channels_iteration(self):
        channel_names = [f'channel_{i}' for i in range(5)]
        [self.ably.channels.get(name) for name in channel_names]

        assert isinstance(self.ably.channels, Iterable)
        for name, channel in zip(channel_names, self.ably.channels):
            assert isinstance(channel, Channel)
            assert name == channel.name

    # RSN4a, RSN4b
    def test_channels_release(self):
        self.ably.channels.get('new_channel')
        self.ably.channels.release('new_channel')
        self.ably.channels.release('new_channel')

    def test_channel_has_presence(self):
        channel = self.ably.channels.get('new_channnel')
        assert channel.presence
        assert isinstance(channel.presence, Presence)

    async def test_without_permissions(self):
        key = self.test_vars["keys"][2]
        ably = await TestApp.get_ably_rest(key=key["key_str"])
        with pytest.raises(AblyException) as excinfo:
            await ably.channels['test_publish_without_permission'].publish('foo', 'woop')

        assert 40160 == excinfo.value.code
        await ably.close()
