import asyncio

import pytest

from ably.pubsub.realtime.channel import ChannelState, RealtimeChannel
from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.transport.websockettransport import ProtocolMessageAction
from ably.pubsub.types.channeloptions import ChannelOptions
from ably.pubsub.types.message import Message
from ably.pubsub.util.exceptions import AblyException
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, random_string


class TestRealtimeChannel(BaseAsyncTestCase):
    @pytest.fixture(autouse=True)
    async def setup(self):
        self.test_vars = await TestApp.get_test_vars()
        self.valid_key_format = "api:key"

    async def test_channels_get(self):
        ably = await TestApp.get_ably_realtime()
        channel = ably.channels.get('my_channel')
        assert channel == ably.channels.get('my_channel')
        assert isinstance(channel, RealtimeChannel)
        await ably.close()

    async def test_channels_release(self):
        ably = await TestApp.get_ably_realtime()
        ably.channels.get('my_channel')
        ably.channels.release('my_channel')

        for _ in ably.channels:
            raise AssertionError("Expected no channels to exist")

        await ably.close()

    async def test_channel_attach(self):
        ably = await TestApp.get_ably_realtime()
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        channel = ably.channels.get('my_channel')
        assert channel.state == ChannelState.INITIALIZED
        await channel.attach()
        assert channel.state == ChannelState.ATTACHED
        await ably.close()

    async def test_channel_detach(self):
        ably = await TestApp.get_ably_realtime()
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        channel = ably.channels.get('my_channel')
        await channel.attach()
        await channel.detach()
        assert channel.state == ChannelState.DETACHED
        await ably.close()

    # RTL7b
    async def test_subscribe(self):
        ably = await TestApp.get_ably_realtime()

        first_message_future = asyncio.Future()
        second_message_future = asyncio.Future()

        def listener(message):
            if not first_message_future.done():
                first_message_future.set_result(message)
            else:
                second_message_future.set_result(message)

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        channel = ably.channels.get('my_channel')
        await channel.attach()
        await channel.subscribe('event', listener)

        # publish a message using rest client
        await channel.publish('event', 'data')
        message = await first_message_future

        assert isinstance(message, Message)
        assert message.name == 'event'
        assert message.data == 'data'

        # test that the listener is called again for further publishes
        await channel.publish('event', 'data')
        await second_message_future

        await ably.close()

    # TM2a, TM2c, TM2f
    async def test_check_inner_fields_updated(self):
        ably = await TestApp.get_ably_realtime()

        message_future = asyncio.Future()

        def listener(msg: Message):
            if not message_future.done():
                message_future.set_result(msg)

        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        channel = ably.channels.get('my_channel')
        await channel.attach()
        await channel.subscribe('event', listener)

        # publish a message using rest client
        await channel.publish('event', 'data')
        message = await message_future

        assert isinstance(message, Message)
        assert message.name == 'event'
        assert message.data == 'data'
        assert message.id is not None
        assert message.timestamp is not None

        await ably.close()

    async def test_subscribe_coroutine(self):
        ably = await TestApp.get_ably_realtime()
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        channel = ably.channels.get('my_channel')
        await channel.attach()

        message_future = asyncio.Future()

        # AsyncMock doesn't work in python 3.7 so use an actual coroutine
        async def listener(msg):
            message_future.set_result(msg)

        await channel.subscribe('event', listener)

        # publish a message using rest client
        rest = await TestApp.get_ably_rest()
        rest_channel = rest.channels.get('my_channel')
        await rest_channel.publish('event', 'data')

        message = await message_future
        assert isinstance(message, Message)
        assert message.name == 'event'
        assert message.data == 'data'

        await ably.close()
        await rest.close()

    # RTL7a
    async def test_subscribe_all_events(self):
        ably = await TestApp.get_ably_realtime()
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        channel = ably.channels.get('my_channel')
        await channel.attach()

        message_future = asyncio.Future()

        def listener(msg):
            message_future.set_result(msg)

        await channel.subscribe(listener)

        # publish a message using rest client
        rest = await TestApp.get_ably_rest()
        rest_channel = rest.channels.get('my_channel')
        await rest_channel.publish('event', 'data')
        message = await message_future

        assert isinstance(message, Message)
        assert message.name == 'event'
        assert message.data == 'data'

        await ably.close()
        await rest.close()

    # RTL7c
    async def test_subscribe_auto_attach(self):
        ably = await TestApp.get_ably_realtime()
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        channel = ably.channels.get('my_channel')
        assert channel.state == ChannelState.INITIALIZED

        def listener(_):
            pass

        await channel.subscribe('event', listener)

        assert channel.state == ChannelState.ATTACHED

        await ably.close()

    # RTL8b
    async def test_unsubscribe(self):
        ably = await TestApp.get_ably_realtime()
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        channel = ably.channels.get('my_channel')
        await channel.attach()

        message_future = asyncio.Future()
        call_count = 0

        def listener(msg):
            nonlocal call_count
            call_count += 1
            message_future.set_result(msg)

        await channel.subscribe('event', listener)

        # publish a message using rest client
        rest = await TestApp.get_ably_rest()
        rest_channel = rest.channels.get('my_channel')
        await rest_channel.publish('event', 'data')
        await message_future
        assert call_count == 1

        # unsubscribe the listener from the channel
        channel.unsubscribe('event', listener)

        # test that the listener is not called again for further publishes
        await rest_channel.publish('event', 'data')
        await asyncio.sleep(1)
        assert call_count == 1

        await ably.close()
        await rest.close()

    # RTL8c
    async def test_unsubscribe_all(self):
        ably = await TestApp.get_ably_realtime()
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        channel = ably.channels.get('my_channel')
        await channel.attach()

        message_future = asyncio.Future()
        call_count = 0

        def listener(msg):
            nonlocal call_count
            call_count += 1
            message_future.set_result(msg)

        await channel.subscribe('event', listener)

        # publish a message using rest client
        rest = await TestApp.get_ably_rest()
        rest_channel = rest.channels.get('my_channel')
        await rest_channel.publish('event', 'data')
        await message_future
        assert call_count == 1

        # unsubscribe all listeners from the channel
        channel.unsubscribe()

        # test that the listener is not called again for further publishes
        await rest_channel.publish('event', 'data')
        await asyncio.sleep(1)
        assert call_count == 1

        await ably.close()
        await rest.close()

    async def test_realtime_request_timeout_attach(self):
        ably = await TestApp.get_ably_realtime(realtime_request_timeout=2000)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        original_send_protocol_message = ably.connection.connection_manager.send_protocol_message

        async def new_send_protocol_message(msg):
            if msg.get('action') == ProtocolMessageAction.ATTACH:
                return
            await original_send_protocol_message(msg)
        ably.connection.connection_manager.send_protocol_message = new_send_protocol_message

        channel = ably.channels.get('channel_name')
        with pytest.raises(AblyException) as exception:
            await channel.attach()
        assert exception.value.code == 90007
        assert exception.value.status_code == 408
        await ably.close()

    async def test_realtime_request_timeout_detach(self):
        ably = await TestApp.get_ably_realtime(realtime_request_timeout=2000)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        original_send_protocol_message = ably.connection.connection_manager.send_protocol_message

        async def new_send_protocol_message(msg):
            if msg.get('action') == ProtocolMessageAction.DETACH:
                return
            await original_send_protocol_message(msg)
        ably.connection.connection_manager.send_protocol_message = new_send_protocol_message

        channel = ably.channels.get('channel_name')
        await channel.attach()
        with pytest.raises(AblyException) as exception:
            await channel.detach()
        assert exception.value.code == 90007
        assert exception.value.status_code == 408
        await ably.close()

    async def test_channel_detached_once_connection_closed(self):
        ably = await TestApp.get_ably_realtime(realtime_request_timeout=2000)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        channel = ably.channels.get(random_string(5))
        await channel.attach()

        await ably.close()
        assert channel.state == ChannelState.DETACHED

    async def test_channel_failed_once_connection_failed(self):
        ably = await TestApp.get_ably_realtime(realtime_request_timeout=2000)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        channel = ably.channels.get(random_string(5))
        await channel.attach()

        ably.connection.connection_manager.notify_state(ConnectionState.SUSPENDED)
        assert channel.state == ChannelState.SUSPENDED

        await ably.close()

    async def test_channel_suspended_once_connection_suspended(self):
        ably = await TestApp.get_ably_realtime(realtime_request_timeout=2000)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)
        channel = ably.channels.get(random_string(5))
        await channel.attach()

        ably.connection.connection_manager.notify_state(ConnectionState.FAILED)
        assert channel.state == ChannelState.FAILED

        await ably.close()

    async def test_attach_while_connecting(self):
        ably = await TestApp.get_ably_realtime()
        channel = ably.channels.get(random_string(5))
        await channel.attach()
        assert channel.state == ChannelState.ATTACHED
        await ably.close()

    # RTL13a
    async def test_channel_attach_retry_immediately_on_unexpected_detached(self):
        ably = await TestApp.get_ably_realtime(channel_retry_timeout=500)
        channel_name = random_string(5)
        channel = ably.channels.get(channel_name)
        await channel.attach()

        # Simulate an unexpected DETACHED message from ably
        message = {
            "action": ProtocolMessageAction.DETACHED,
            "channel": channel_name,
        }
        assert ably.connection.connection_manager.transport
        await ably.connection.connection_manager.transport.on_protocol_message(message)

        # The channel should retry attachment immediately
        assert channel.state == ChannelState.ATTACHING

        # Make sure the channel sucessfully re-attaches
        await channel.once_async(ChannelState.ATTACHED)

        await ably.close()

    # RTL13b
    async def test_channel_attach_retry_after_unsuccessful_attach(self):
        ably = await TestApp.get_ably_realtime(channel_retry_timeout=500, realtime_request_timeout=1000)
        channel_name = random_string(5)
        channel = ably.channels.get(channel_name)
        call_count = 0

        original_send_protocol_message = ably.connection.connection_manager.send_protocol_message

        # Discard the first ATTACHED message recieved
        async def new_send_protocol_message(msg):
            nonlocal call_count
            if call_count == 0 and msg.get('action') == ProtocolMessageAction.ATTACH:
                call_count += 1
                return
            await original_send_protocol_message(msg)
        ably.connection.connection_manager.send_protocol_message = new_send_protocol_message

        with pytest.raises(AblyException):
            await channel.attach()

        # The channel should become SUSPENDED but will still retry again after channel_retry_timeout
        assert channel.state == ChannelState.SUSPENDED

        # Make sure the channel sucessfully re-attaches
        await channel.once_async(ChannelState.ATTACHED)

        await ably.close()

    async def test_channel_initialized_on_connection_from_terminal_state(self):
        ably = await TestApp.get_ably_realtime()
        channel_name = random_string(5)
        channel = ably.channels.get(channel_name)
        await channel.attach()
        await ably.close()
        ably.connect()
        assert channel.state == ChannelState.INITIALIZED
        await ably.close()

    async def test_channel_error(self):
        ably = await TestApp.get_ably_realtime()
        channel_name = random_string(5)
        channel = ably.channels.get(channel_name)
        await channel.attach()
        code = 12345
        status_code = 123

        msg = {
            "action": ProtocolMessageAction.ERROR,
            "channel": channel_name,
            "error": {
                "message": "test error",
                "code": code,
                "statusCode": status_code,
            },
        }

        assert ably.connection.connection_manager.transport
        await ably.connection.connection_manager.transport.on_protocol_message(msg)

        assert channel.state == ChannelState.FAILED
        assert channel.error_reason
        assert channel.error_reason.code == code
        assert channel.error_reason.status_code == status_code

        await ably.close()

    async def test_channel_error_cleared_upon_attach(self):
        ably = await TestApp.get_ably_realtime()
        channel_name = random_string(5)
        channel = ably.channels.get(channel_name)
        await channel.attach()
        code = 12345
        status_code = 123

        msg = {
            "action": ProtocolMessageAction.ERROR,
            "channel": channel_name,
            "error": {
                "message": "test error",
                "code": code,
                "statusCode": status_code,
            },
        }

        assert ably.connection.connection_manager.transport
        await ably.connection.connection_manager.transport.on_protocol_message(msg)

        assert channel.error_reason is not None
        await channel.attach()
        assert channel.error_reason is None

        await ably.close()

    async def test_channel_error_cleared_upon_connect_from_terminal_state(self):
        ably = await TestApp.get_ably_realtime()
        channel_name = random_string(5)
        channel = ably.channels.get(channel_name)
        await channel.attach()
        code = 12345
        status_code = 123

        msg = {
            "action": ProtocolMessageAction.ERROR,
            "channel": channel_name,
            "error": {
                "message": "test error",
                "code": code,
                "statusCode": status_code,
            },
        }

        assert ably.connection.connection_manager.transport
        await ably.connection.connection_manager.transport.on_protocol_message(msg)

        await ably.close()

        assert channel.error_reason is not None
        ably.connect()
        assert channel.error_reason is None

        await ably.close()

    async def test_channel_params_received_by_relatime(self):
        ably = await TestApp.get_ably_realtime()
        channel_name = random_string(5)
        channel = ably.channels.get(channel_name, ChannelOptions(params={
            "rewind": "1"
        }))
        await channel.attach()
        assert channel.params["rewind"] == "1"

        await ably.close()

    async def test_channel_params_unknown_params_skipped_by_relatime(self):
        ably = await TestApp.get_ably_realtime()
        channel_name = random_string(5)
        channel = ably.channels.get(channel_name, ChannelOptions(params={
            "rewind": "1",
            "foo": "bar"
        }))
        await channel.attach()
        assert channel.params["rewind"] == "1"
        assert channel.params.get("foo") is None

        await ably.close()

    async def test_channel_params_as_dict(self):
        ably = await TestApp.get_ably_realtime()
        channel_name = random_string(5)
        channel = ably.channels.get(channel_name, ChannelOptions(params={"delta": "vcdiff"}))
        await channel.attach()
        assert channel.params["delta"] == "vcdiff"

        await ably.close()

    async def test_channel_get_channel_with_same_params(self):
        ably = await TestApp.get_ably_realtime()
        channel_name = random_string(5)
        channel = ably.channels.get(channel_name, ChannelOptions(params={"rewind": "1"}))
        await channel.attach()
        same_channel = ably.channels.get(channel_name, ChannelOptions(params={"rewind": "1"}))
        assert channel == same_channel

        await ably.close()

    async def test_channel_get_channel_with_different_params(self):
        ably = await TestApp.get_ably_realtime()
        channel_name = random_string(5)
        channel = ably.channels.get(channel_name, ChannelOptions(params={"rewind": "1"}))
        await channel.attach()

        with pytest.raises(AblyException) as exception:
            ably.channels.get(channel_name, ChannelOptions(params={"delta": "vcdiff"}))

        assert exception.value.code == 40000
        assert exception.value.status_code == 400

        assert channel.params == {"rewind": "1"}

        await ably.close()
