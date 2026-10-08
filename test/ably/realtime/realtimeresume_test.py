import asyncio

import pytest

from ably.pubsub.realtime.channel import ChannelState
from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.transport.websockettransport import ProtocolMessageAction
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, random_string


async def send_and_await(rest_channel, realtime_channel):
    event = random_string(5)
    message = random_string(5)
    future = asyncio.Future()

    def on_message(_):
        future.set_result(None)

    await realtime_channel.subscribe(event, on_message)
    await rest_channel.publish(event, message)

    await future


class TestRealtimeResume(BaseAsyncTestCase):
    @pytest.fixture(autouse=True)
    async def setup(self):
        self.test_vars = await TestApp.get_test_vars()
        self.valid_key_format = "api:key"

    # RTN15c6 - valid resume response
    async def test_connection_resume(self):
        ably = await TestApp.get_ably_realtime()

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        prev_connection_id = ably.connection.connection_manager.connection_id
        connection_key = ably.connection.connection_details.connection_key
        await ably.connection.connection_manager.transport.dispose()
        ably.connection.connection_manager.notify_state(ConnectionState.DISCONNECTED)

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        new_connection_id = ably.connection.connection_manager.connection_id
        assert ably.connection.connection_manager.transport.params["resume"] == connection_key
        assert prev_connection_id == new_connection_id

        await ably.close()

    # RTN15c4 - fatal resume error
    async def test_fatal_resume_error(self):
        ably = await TestApp.get_ably_realtime()

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        ably.auth.auth_options.key_name = "wrong-key"
        await ably.connection.connection_manager.transport.dispose()
        ably.connection.connection_manager.notify_state(ConnectionState.DISCONNECTED)

        state_change = await ably.connection.once_async(ConnectionState.FAILED)
        assert state_change.reason.code == 40101
        assert state_change.reason.status_code == 401
        await ably.close()

    # RTN15c7 - invalid resume response
    async def test_invalid_resume_response(self):
        ably = await TestApp.get_ably_realtime()

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        assert ably.connection.connection_manager.connection_details
        ably.connection.connection_manager.connection_details.connection_key = 'ably-python-fake-key'

        assert ably.connection.connection_manager.transport
        await ably.connection.connection_manager.transport.dispose()
        ably.connection.connection_manager.notify_state(ConnectionState.DISCONNECTED)

        state_change = await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        assert state_change.reason.code == 80018
        assert state_change.reason.status_code == 400
        assert ably.connection.error_reason == state_change.reason

        await ably.close()

    async def test_attached_channel_reattaches_on_invalid_resume(self):
        ably = await TestApp.get_ably_realtime()

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get(random_string(5))

        await channel.attach()

        assert ably.connection.connection_manager.connection_details
        ably.connection.connection_manager.connection_details.connection_key = 'ably-python-fake-key'

        assert ably.connection.connection_manager.transport
        await ably.connection.connection_manager.transport.dispose()
        ably.connection.connection_manager.notify_state(ConnectionState.DISCONNECTED)

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        assert channel.state == ChannelState.ATTACHING

        await channel.once_async(ChannelState.ATTACHED)

        await ably.close()

    async def test_suspended_channel_reattaches_on_invalid_resume(self):
        ably = await TestApp.get_ably_realtime()

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get(random_string(5))
        channel.state = ChannelState.SUSPENDED

        assert ably.connection.connection_manager.connection_details
        ably.connection.connection_manager.connection_details.connection_key = 'ably-python-fake-key'

        assert ably.connection.connection_manager.transport
        await ably.connection.connection_manager.transport.dispose()
        ably.connection.connection_manager.notify_state(ConnectionState.DISCONNECTED)

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        assert channel.state == ChannelState.ATTACHING

        await channel.once_async(ChannelState.ATTACHED)

        await ably.close()

    async def test_resume_receives_channel_messages_while_disconnected(self):
        realtime = await TestApp.get_ably_realtime()
        rest = await TestApp.get_ably_rest()

        channel_name = random_string(5)

        realtime_channel = realtime.channels.get(channel_name)
        rest_channel = rest.channels.get(channel_name)

        await realtime.connection.once_async(ConnectionState.CONNECTED)

        asyncio.create_task(realtime_channel.attach())
        state_change = await realtime_channel.once_async(ChannelState.ATTACHED)
        assert state_change.resumed is False

        await send_and_await(rest_channel, realtime_channel)

        assert realtime.connection.connection_manager.transport
        await realtime.connection.connection_manager.transport.dispose()
        realtime.connection.connection_manager.notify_state(ConnectionState.DISCONNECTED, retry_immediately=False)

        event_name = random_string(5)
        message = random_string(5)
        await rest_channel.publish(event_name, message)

        future = asyncio.Future()

        def on_message(message):
            future.set_result(message)

        await realtime_channel.subscribe(event_name, on_message)

        realtime.connect()
        await realtime.connection.once_async(ConnectionState.CONNECTED)

        state_change = await realtime_channel.once_async(ChannelState.ATTACHED)

        assert state_change.resumed is True

        received_message = await future

        assert received_message.data == message

        await realtime.close()
        await rest.close()

    async def test_resume_update_channel_attached(self):
        realtime = await TestApp.get_ably_realtime()

        name = random_string(5)
        channel = realtime.channels.get(name)
        await channel.attach()
        error_code = 123
        error_status_code = 456
        error_message = "some error"
        message = {
            "action": ProtocolMessageAction.ATTACHED,
            "channel": name,
            "error": {
                "code": error_code,
                "statusCode": error_status_code,
                "message": error_message
            }
        }
        future = asyncio.Future()

        def on_update(state_change):
            future.set_result(state_change)

        channel.once("update", on_update)
        await realtime.connection.connection_manager.transport.on_protocol_message(message)

        state_change = await future
        assert state_change.reason.code == error_code
        assert state_change.reason.status_code == error_status_code
        assert state_change.reason.message == error_message
        await realtime.close()
