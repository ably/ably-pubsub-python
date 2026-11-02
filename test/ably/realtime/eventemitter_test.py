import asyncio

import pytest

from ably.pubsub.realtime.connection import ConnectionState
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase


class TestEventEmitter(BaseAsyncTestCase):
    @pytest.fixture(autouse=True)
    async def setup(self):
        self.test_vars = await TestApp.get_test_vars()

    async def test_event_listener_error(self):
        realtime = await TestApp.get_ably_realtime()
        call_count = 0

        def listener(_):
            nonlocal call_count
            call_count += 1
            raise Exception()

        # If a listener throws an exception it should not propagate (#RTE6)
        listener.side_effect = Exception()
        realtime.connection.on(ConnectionState.CONNECTED, listener)

        realtime.connect()
        await realtime.connection.once_async(ConnectionState.CONNECTED)

        assert call_count == 1
        await realtime.close()

    async def test_event_emitter_off(self):
        realtime = await TestApp.get_ably_realtime()
        call_count = 0

        def listener(_):
            nonlocal call_count
            call_count += 1

        realtime.connection.on(ConnectionState.CONNECTED, listener)
        realtime.connection.off(ConnectionState.CONNECTED, listener)

        await realtime.connection.once_async(ConnectionState.CONNECTED)

        assert call_count == 0
        await asyncio.sleep(0)
        assert call_count == 0
        await realtime.close()
