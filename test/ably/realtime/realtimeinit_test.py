import asyncio

import pytest

from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.server import Auth
from ably.pubsub.util.exceptions import AblyAuthException
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase


class TestRealtimeInit(BaseAsyncTestCase):
    @pytest.fixture(autouse=True)
    async def setup(self):
        self.test_vars = await TestApp.get_test_vars()
        self.valid_key_format = "api:key"

    async def test_init_with_valid_key(self):
        ably = await TestApp.get_ably_realtime(key=self.test_vars["keys"][0]["key_str"], auto_connect=False)
        assert Auth.Method.BASIC == ably.auth.auth_mechanism, "Unexpected Auth method mismatch"
        assert ably.auth.auth_options.key_name == self.test_vars["keys"][0]['key_name']
        assert ably.auth.auth_options.key_secret == self.test_vars["keys"][0]['key_secret']

    async def test_init_with_incorrect_key(self):
        with pytest.raises(AblyAuthException):
            await TestApp.get_ably_realtime(key="some invalid key", auto_connect=False)

    async def test_init_with_valid_key_format(self):
        key = self.valid_key_format.split(":")
        ably = await TestApp.get_ably_realtime(key=self.valid_key_format, auto_connect=False)
        assert Auth.Method.BASIC == ably.auth.auth_mechanism, "Unexpected Auth method mismatch"
        assert ably.auth.auth_options.key_name == key[0]
        assert ably.auth.auth_options.key_secret == key[1]

    async def test_init_without_autoconnect(self):
        ably = await TestApp.get_ably_realtime(auto_connect=False)
        assert ably.connection.state == ConnectionState.INITIALIZED
        ably.connect()
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        assert ably.connection.state == ConnectionState.CONNECTED
        await ably.close()
        assert ably.connection.state == ConnectionState.CLOSED
