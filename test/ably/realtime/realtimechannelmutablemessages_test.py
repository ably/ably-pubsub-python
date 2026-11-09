import logging
from typing import List

import pytest

from ably.pubsub.server import AblyException, CipherParams, MessageAction
from ably.pubsub.types.message import Message
from ably.pubsub.types.operations import MessageOperation
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, WaitableEvent, assert_waiter

log = logging.getLogger(__name__)


@pytest.mark.parametrize("transport", ["json", "msgpack"], ids=["JSON", "MsgPack"])
class TestRealtimeChannelMutableMessages(BaseAsyncTestCase):

    @pytest.fixture(autouse=True)
    async def setup(self, transport):
        self.test_vars = await TestApp.get_test_vars()
        self.ably = await TestApp.get_ably_realtime(
            use_binary_protocol=True if transport == 'msgpack' else False,
        )

    async def test_update_message_success(self):
        """Test successfully updating a message"""
        channel = self.ably.channels[self.get_channel_name('mutable:update_test')]

        # First publish a message
        result = await channel.publish('test-event', 'original data')
        assert result.serials is not None
        assert len(result.serials) > 0
        serial = result.serials[0]

        # Create message with serial for update
        message = Message(
            data='updated data',
            serial=serial,
        )

        # Update the message
        update_result = await channel.update_message(message)
        assert update_result is not None
        updated_message = await self.wait_until_message_with_action_appears(
            channel, serial, MessageAction.MESSAGE_UPDATE
        )
        assert updated_message.data == 'updated data'
        assert updated_message.version.serial == update_result.version_serial
        assert updated_message.serial == serial

    async def test_update_message_without_serial_fails(self):
        """Test that updating without a serial raises an exception"""
        channel = self.ably.channels[self.get_channel_name('mutable:update_test_no_serial')]

        message = Message(name='test-event', data='data')

        with pytest.raises(AblyException) as exc_info:
            await channel.update_message(message)

        assert exc_info.value.status_code == 400
        assert 'serial is required' in str(exc_info.value).lower()

    async def test_delete_message_success(self):
        """Test successfully deleting a message"""
        channel = self.ably.channels[self.get_channel_name('mutable:delete_test')]

        # First publish a message
        result = await channel.publish('test-event', 'data to delete')
        assert result.serials is not None
        assert len(result.serials) > 0
        serial = result.serials[0]

        # Create message with serial for deletion
        message = Message(serial=serial)

        operation = MessageOperation(
            description='Inappropriate content',
            metadata={'reason': 'moderation'}
        )

        # Delete the message
        delete_result = await channel.delete_message(message, operation)
        assert delete_result is not None

        # Verify the deletion propagated
        deleted_message = await self.wait_until_message_with_action_appears(
            channel, serial, MessageAction.MESSAGE_DELETE
        )
        assert deleted_message.action == MessageAction.MESSAGE_DELETE
        assert deleted_message.version.serial == delete_result.version_serial
        assert deleted_message.version.description == 'Inappropriate content'
        assert deleted_message.version.metadata == {'reason': 'moderation'}
        assert deleted_message.serial == serial

    async def test_delete_message_without_serial_fails(self):
        """Test that deleting without a serial raises an exception"""
        channel = self.ably.channels[self.get_channel_name('mutable:delete_test_no_serial')]

        message = Message(name='test-event', data='data')

        with pytest.raises(AblyException) as exc_info:
            await channel.delete_message(message)

        assert exc_info.value.status_code == 400
        assert 'serial is required' in str(exc_info.value).lower()

    async def test_append_message_success(self):
        """Test successfully appending to a message"""
        channel = self.ably.channels[self.get_channel_name('mutable:append_test')]

        # First publish a message
        result = await channel.publish('test-event', 'original content')
        assert result.serials is not None
        assert len(result.serials) > 0
        serial = result.serials[0]

        # Create message with serial and data to append
        message = Message(
            data=' appended content',
            serial=serial
        )

        operation = MessageOperation(
            description='Added more info',
            metadata={'type': 'amendment'}
        )

        # Append to the message
        append_result = await channel.append_message(message, operation)
        assert append_result is not None

        # Verify the append propagated - action will be MESSAGE_UPDATE, data should be concatenated
        appended_message = await self.wait_until_message_with_action_appears(
            channel, serial, MessageAction.MESSAGE_UPDATE
        )
        assert appended_message.data == 'original content appended content'
        assert appended_message.version.serial == append_result.version_serial
        assert appended_message.version.description == 'Added more info'
        assert appended_message.version.metadata == {'type': 'amendment'}
        assert appended_message.serial == serial

    async def test_append_message_without_serial_fails(self):
        """Test that appending without a serial raises an exception"""
        channel = self.ably.channels[self.get_channel_name('mutable:append_test_no_serial')]

        message = Message(name='test-event', data='data to append')

        with pytest.raises(AblyException) as exc_info:
            await channel.append_message(message)

        assert exc_info.value.status_code == 400
        assert 'serial is required' in str(exc_info.value).lower()

    async def test_update_message_with_encryption(self):
        """Test updating an encrypted message"""
        # Create channel with encryption
        channel_name = self.get_channel_name('mutable:update_encrypted')
        cipher_params = CipherParams(secret_key='keyfordecrypt_16', algorithm='aes')
        channel = self.ably.channels.get(channel_name, cipher=cipher_params)

        # Publish encrypted message
        result = await channel.publish('encrypted-event', 'secret data')
        assert result.serials is not None
        assert len(result.serials) > 0

        # Update the encrypted message
        message = Message(
            name='encrypted-event',
            data='updated secret data',
            serial=result.serials[0]
        )

        operation = MessageOperation(description='Updated encrypted message')
        update_result = await channel.update_message(message, operation)
        assert update_result is not None

    async def test_publish_returns_serials(self):
        """Test that publish returns PublishResult with serials"""
        channel = self.ably.channels[self.get_channel_name('mutable:publish_serials')]

        # Publish multiple messages
        messages = [
            Message('event1', 'data1'),
            Message('event2', 'data2'),
            Message('event3', 'data3')
        ]

        result = await channel.publish(messages)
        assert result is not None
        assert hasattr(result, 'serials')
        assert len(result.serials) == 3

    async def test_complete_workflow_publish_update_delete(self):
        """Test complete workflow: publish, update, delete"""
        channel = self.ably.channels[self.get_channel_name('mutable:complete_workflow')]

        # 1. Publish a message
        result = await channel.publish('workflow_event', 'Initial data')
        assert result.serials is not None
        assert len(result.serials) > 0
        serial = result.serials[0]

        # 2. Update the message
        update_message = Message(
            name='workflow_event_updated',
            data='Updated data',
            serial=serial
        )
        update_operation = MessageOperation(description='Updated message')
        update_result = await channel.update_message(update_message, update_operation)
        assert update_result is not None

        # 3. Delete the message
        delete_message = Message(serial=serial, data='Deleted')
        delete_operation = MessageOperation(description='Deleted message')
        delete_result = await channel.delete_message(delete_message, delete_operation)
        assert delete_result is not None

        versions = await self.wait_until_get_all_message_version(channel, serial, 3)

        assert versions[0].version.serial == serial
        assert versions[1].version.serial == update_result.version_serial
        assert versions[2].version.serial == delete_result.version_serial

    async def test_append_message_with_string_data(self):
        """Test appending string data to a message"""
        channel = self.ably.channels[self.get_channel_name('mutable:append_string')]

        # Publish initial message
        result = await channel.publish('append_event', 'Initial data')
        assert len(result.serials) > 0
        serial = result.serials[0]

        messages_received = []
        append_received = WaitableEvent()

        def on_message(message):
            messages_received.append(message)
            if len(messages_received) == 2:
                append_received.finish()

        await channel.subscribe(on_message)

        # Append data
        append_message = Message(
            data=' appended data',
            serial=serial
        )
        append_operation = MessageOperation(description='Appended to message')
        append_result = await channel.append_message(append_message, append_operation)
        assert append_result is not None

        # Verify the append
        appended_message = await self.wait_until_message_with_action_appears(
            channel, serial, MessageAction.MESSAGE_UPDATE
        )

        second_append_result = await channel.append_message(append_message, append_operation)

        await append_received.wait()

        assert messages_received[0].data == 'Initial data appended data'
        assert messages_received[0].action == MessageAction.MESSAGE_UPDATE
        assert appended_message.data == 'Initial data appended data'
        assert appended_message.version.serial == append_result.version_serial
        assert appended_message.version.description == 'Appended to message'
        assert appended_message.serial == serial

        assert messages_received[1].data == ' appended data'
        assert messages_received[1].action == MessageAction.MESSAGE_APPEND
        assert messages_received[1].version.serial == second_append_result.version_serial

    # RTL32b, TM2i
    async def test_update_message_preserves_extras(self):
        """Test that extras are preserved when updating a message"""
        channel = self.ably.channels[self.get_channel_name('mutable:update_extras')]

        # Publish a message
        result = await channel.publish('test-event', 'original data')
        assert len(result.serials) > 0
        serial = result.serials[0]

        messages_received = []
        update_received = WaitableEvent()

        def on_message(message):
            if message.action == MessageAction.MESSAGE_UPDATE:
                messages_received.append(message)
                update_received.finish()

        await channel.subscribe(on_message)

        # Update with extras
        message = Message(
            data='updated data',
            serial=serial,
            extras={'headers': {'status': 'complete'}},
        )

        update_result = await channel.update_message(message)
        assert update_result is not None

        await update_received.wait()

        assert len(messages_received) > 0
        received = messages_received[0]
        assert received.extras is not None
        assert received.extras['headers']['status'] == 'complete'

    async def wait_until_message_with_action_appears(self, channel, serial, action):
        message: Message | None = None
        async def check_message_action():
            nonlocal message
            try:
                message = await channel.get_message(serial)
                return message.action == action
            except Exception:
                return False

        await assert_waiter(check_message_action)

        return message

    async def wait_until_get_all_message_version(self, channel, serial, count):
        versions: List[Message] = []
        async def check_message_versions():
            nonlocal versions
            versions = (await channel.get_message_versions(serial)).items
            return len(versions) >= count

        await assert_waiter(check_message_versions)

        return versions
