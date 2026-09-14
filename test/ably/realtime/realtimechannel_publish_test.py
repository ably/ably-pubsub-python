import asyncio

import pytest

from ably.pubsub.realtime.channel import ChannelState
from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.transport.websockettransport import ProtocolMessageAction
from ably.pubsub.types.channeloptions import ChannelOptions
from ably.pubsub.types.message import Message
from ably.pubsub.util.crypto import CipherParams
from ably.pubsub.util.exceptions import AblyException, IncompatibleClientIdException
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase, WaitableEvent, assert_waiter


@pytest.mark.parametrize("transport", ["json", "msgpack"], ids=["JSON", "MsgPack"])
class TestRealtimeChannelPublish(BaseAsyncTestCase):
    """Tests for RTN7 spec - Message acknowledgment"""

    @pytest.fixture(autouse=True)
    async def setup(self, transport):
        self.test_vars = await TestApp.get_test_vars()
        self.use_binary_protocol = True if transport == 'msgpack' else False

    # RTN7a - Basic ACK/NACK functionality
    async def test_publish_returns_ack_on_success(self):
        """RTN7a: Verify that publish awaits ACK from server"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_ack_channel')
        await channel.attach()

        # Publish should complete successfully when ACK is received
        await channel.publish('test_event', 'test_data')

        await ably.close()

    async def test_publish_raises_on_nack(self):
        """RTN7a: Verify that publish raises exception when NACK is received"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_nack_channel')
        await channel.attach()

        connection_manager = ably.connection.connection_manager

        # Intercept transport send to simulate NACK
        original_send = connection_manager.transport.send

        async def send_and_nack(message):
            await original_send(message)
            # Simulate NACK from server
            if message.get('action') == ProtocolMessageAction.MESSAGE:
                msg_serial = message.get('msgSerial', 0)
                nack_message = {
                    'action': ProtocolMessageAction.NACK,
                    'msgSerial': msg_serial,
                    'count': 1,
                    'error': {
                        'message': 'Test NACK error',
                        'statusCode': 400,
                        'code': 40000
                    }
                }
                await connection_manager.transport.on_protocol_message(nack_message)

        connection_manager.transport.send = send_and_nack

        # Publish should raise exception when NACK is received
        with pytest.raises(AblyException) as exc_info:
            await channel.publish('test_event', 'test_data')

        assert 'Test NACK error' in str(exc_info.value)
        assert exc_info.value.code == 40000

        await ably.close()

    # RTN7b - msgSerial incrementing
    async def test_msgserial_increments_sequentially(self):
        """RTN7b: Verify that msgSerial increments for each message"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_msgserial_channel')
        await channel.attach()

        connection_manager = ably.connection.connection_manager
        sent_serials = []

        # Intercept messages to capture msgSerial values
        original_send = connection_manager.transport.send

        async def capture_serial(message):
            if message.get('action') == ProtocolMessageAction.MESSAGE:
                sent_serials.append(message.get('msgSerial'))
            await original_send(message)

        connection_manager.transport.send = capture_serial

        # Publish multiple messages
        await channel.publish('event1', 'data1')
        await channel.publish('event2', 'data2')
        await channel.publish('event3', 'data3')

        # Verify msgSerial increments: 0, 1, 2
        assert sent_serials == [0, 1, 2], f"Expected [0, 1, 2], got {sent_serials}"

        await ably.close()

    # RTN7e - Fail pending messages on SUSPENDED, CLOSED, FAILED
    async def test_pending_messages_fail_on_suspended(self):
        """RTN7e: Verify pending messages fail when connection enters SUSPENDED state"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_suspended_channel')
        await channel.attach()

        connection_manager = ably.connection.connection_manager

        # Block ACKs to keep message pending
        original_send = connection_manager.transport.send
        blocked_messages = []

        async def block_acks(message):
            if message.get('action') == ProtocolMessageAction.MESSAGE:
                blocked_messages.append(message)
                # Don't actually send - keep it pending
                return
            await original_send(message)

        connection_manager.transport.send = block_acks

        # Start publish but don't await (it will hang waiting for ACK)
        publish_task = asyncio.create_task(channel.publish('test_event', 'test_data'))

        # Wait for message to be pending
        async def check_pending():
            return connection_manager.pending_message_queue.count() > 0
        await assert_waiter(check_pending, timeout=2)

        # Force connection to SUSPENDED state
        connection_manager.notify_state(
            ConnectionState.SUSPENDED,
            AblyException('Test suspension', 400, 80002)
        )

        # The publish should now complete with an exception
        with pytest.raises(AblyException) as exc_info:
            await publish_task

        assert 'Test suspension' in str(exc_info.value) or exc_info.value.code == 80002

        await ably.close()

    async def test_pending_messages_fail_on_failed(self):
        """RTN7e: Verify pending messages fail when connection enters FAILED state"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_failed_channel')
        await channel.attach()

        connection_manager = ably.connection.connection_manager

        # Block ACKs
        original_send = connection_manager.transport.send

        async def block_acks(message):
            if message.get('action') == ProtocolMessageAction.MESSAGE:
                return  # Don't send
            await original_send(message)

        connection_manager.transport.send = block_acks

        # Start publish
        publish_task = asyncio.create_task(channel.publish('test_event', 'test_data'))

        # Wait for message to be pending
        async def check_pending():
            return connection_manager.pending_message_queue.count() > 0
        await assert_waiter(check_pending, timeout=2)

        # Force FAILED state
        connection_manager.notify_state(
            ConnectionState.FAILED,
            AblyException('Test failure', 80000, 500)
        )

        # Should raise exception
        with pytest.raises(AblyException):
            await publish_task

        await ably.close()

    # RTN7d - Fail on DISCONNECTED when queueMessages=false
    async def test_fail_on_disconnected_when_queue_messages_false(self):
        """RTN7d: Verify pending messages fail on DISCONNECTED if queueMessages is false"""
        # Create client with queueMessages=False
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol, queue_messages=False)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_disconnected_channel')
        await channel.attach()

        connection_manager = ably.connection.connection_manager

        # Block ACKs
        original_send = connection_manager.transport.send

        async def block_acks(message):
            if message.get('action') == ProtocolMessageAction.MESSAGE:
                return
            await original_send(message)

        connection_manager.transport.send = block_acks

        # Start publish
        publish_task = asyncio.create_task(channel.publish('test_event', 'test_data'))

        # Wait for message to be pending
        async def check_pending():
            return connection_manager.pending_message_queue.count() > 0
        await assert_waiter(check_pending, timeout=2)

        # Force DISCONNECTED state
        connection_manager.notify_state(
            ConnectionState.DISCONNECTED,
            AblyException('Test disconnect', 400, 80003)
        )

        # Should raise exception because queueMessages is false
        with pytest.raises(AblyException):
            await publish_task

        await ably.close()

    async def test_queue_on_disconnected_when_queue_messages_true(self):
        """RTN7d: Verify messages are queued (not failed) on DISCONNECTED when queueMessages is true"""
        # Create client with queueMessages=True (default)
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol, queue_messages=True)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_queue_channel')
        await channel.attach()

        connection_manager = ably.connection.connection_manager

        # Block ACKs
        original_send = connection_manager.transport.send

        async def block_acks(message):
            if message.get('action') == ProtocolMessageAction.MESSAGE:
                return
            await original_send(message)

        connection_manager.transport.send = block_acks

        # Start publish (will be pending)
        publish_task = asyncio.create_task(channel.publish('test_event', 'test_data'))

        # Wait for message to be pending
        async def check_pending():
            return connection_manager.pending_message_queue.count() > 0
        await assert_waiter(check_pending, timeout=2)

        # Force DISCONNECTED state
        connection_manager.notify_state(ConnectionState.DISCONNECTED, None)

        # Give time for state transition
        async def check_disconnected():
            return connection_manager.state != ConnectionState.CONNECTED
        await assert_waiter(check_disconnected, timeout=2)

        # Task should still be pending (not failed) because queueMessages=True
        assert not publish_task.done(), "Publish should still be pending when queueMessages=True"

        # Message should still be in pending queue OR moved to queued_messages
        assert connection_manager.pending_message_queue.count() + len(connection_manager.queued_messages) > 0

        # Now restore connection would normally complete the publish
        # For this test, we'll just cancel it
        publish_task.cancel()

        await ably.close()

    async def test_publish_fails_on_initialized_when_queue_messages_false(self):
        """RTN7d: Verify publish fails immediately when connection is CONNECTING and queueMessages=false"""
        # Create client with queueMessages=False
        ably = await TestApp.get_ably_realtime(
            use_binary_protocol=self.use_binary_protocol,
            queue_messages=False,
            auto_connect=False
        )

        channel = ably.channels.get('test_initialized_channel')

        # Try to publish while in the INITIALIZED state with queueMessages=false
        with pytest.raises(AblyException) as exc_info:
            await channel.publish('test_event', 'test_data')

        # Verify it failed with appropriate error
        assert exc_info.value.code == 90000
        assert exc_info.value.status_code == 400

        await ably.close()

    # RTN19a2 - Reset msgSerial on new connectionId
    async def test_msgserial_resets_on_new_connection_id(self):
        """RTN19a2: Verify msgSerial resets to 0 when connectionId changes"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_reset_serial_channel')
        await channel.attach()

        connection_manager = ably.connection.connection_manager

        # Publish a message to increment msgSerial
        await channel.publish('event1', 'data1')

        # msgSerial should now be 1
        assert connection_manager.msg_serial == 1, f"Expected msgSerial=1, got {connection_manager.msg_serial}"

        # Simulate new connection with different connectionId
        new_connection_id = 'new_connection_id_12345'

        # Simulate server sending CONNECTED with new connectionId
        from ably.pubsub.types.connectiondetails import ConnectionDetails
        new_connection_details = ConnectionDetails(
            connection_state_ttl=120000,
            max_idle_interval=15000,
            connection_key='new_key',
            client_id=None
        )

        connection_manager.on_connected(new_connection_details, new_connection_id)

        # msgSerial should be reset to 0
        assert connection_manager.msg_serial == 0, (
            f"Expected msgSerial=0 after new connection, got {connection_manager.msg_serial}"
        )

        await ably.close()

    async def test_msgserial_not_reset_on_same_connection_id(self):
        """RTN19a2: Verify msgSerial is NOT reset when connectionId stays the same"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_same_connection_channel')
        await channel.attach()

        connection_manager = ably.connection.connection_manager

        # Publish messages to increment msgSerial
        await channel.publish('event1', 'data1')
        await channel.publish('event2', 'data2')

        # msgSerial should be 2
        assert connection_manager.msg_serial == 2

        # Simulate reconnection with SAME connectionId (transport change, not new connection)
        same_connection_id = connection_manager.connection_id

        from ably.pubsub.types.connectiondetails import ConnectionDetails
        connection_details = ConnectionDetails(
            connection_state_ttl=120000,
            max_idle_interval=15000,
            connection_key='different_key',  # Key can change
            client_id=None
        )

        connection_manager.on_connected(connection_details, same_connection_id)

        # msgSerial should NOT be reset (stays at 2)
        assert connection_manager.msg_serial == 2, (
            f"Expected msgSerial=2 (unchanged), got {connection_manager.msg_serial}"
        )

        await ably.close()

    # Test that multiple messages get correct msgSerial values
    async def test_multiple_messages_concurrent(self):
        """RTN7b: Test that multiple concurrent publishes get sequential msgSerials"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_concurrent_channel')
        await channel.attach()

        # Publish multiple messages concurrently
        tasks = [
            channel.publish('event', f'data{i}')
            for i in range(5)
        ]

        # All should complete successfully
        await asyncio.gather(*tasks)

        # msgSerial should have incremented to 5
        assert ably.connection.connection_manager.msg_serial == 5

        await ably.close()

    # RTN19a - Resend messages awaiting ACK on reconnect
    async def test_pending_messages_resent_on_reconnect(self):
        """RTN19a: Verify messages awaiting ACK are resent when transport reconnects"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_resend_channel')
        await channel.attach()

        connection_manager = ably.connection.connection_manager

        # Block ACKs from being processed
        original_on_ack = connection_manager.on_ack
        connection_manager.on_ack = lambda *args: None

        # Publish a message
        publish_future = asyncio.create_task(connection_manager.send_protocol_message({
            "action": ProtocolMessageAction.MESSAGE,
            "channel": channel.name,
            "messages": [{"name": "test", "data": "data"}]
        }))

        # Wait for message to be pending
        async def check_pending():
            return connection_manager.pending_message_queue.count() == 1
        await assert_waiter(check_pending, timeout=2)

        # Verify msgSerial was assigned
        pending_msg = list(connection_manager.pending_message_queue.messages)[0]
        assert pending_msg.message.get('msgSerial') == 0

        # Simulate requeueing (what happens on disconnect)
        connection_manager.requeue_pending_messages()

        # Pending queue should now be empty (messages moved to queued_messages)
        assert connection_manager.pending_message_queue.count() == 0
        assert len(connection_manager.queued_messages) == 1

        # Verify the PendingMessage object is in the queue (preserves Future)
        queued_msg = connection_manager.queued_messages.pop()
        assert queued_msg.message.get('msgSerial') == 0, "msgSerial should be preserved"

        # Add back to pending queue to simulate resend
        connection_manager.pending_message_queue.push(queued_msg)

        # Restore on_ack and simulate ACK from server
        connection_manager.on_ack = original_on_ack
        connection_manager.on_ack(0, 1, None)

        # Future should be resolved
        result = await asyncio.wait_for(publish_future, timeout=1)
        assert result is not None, "Publish should have succeeded"

        await ably.close()

    async def test_msgserial_preserved_on_resume(self):
        """RTN19a2: Verify msgSerial counter is preserved when resuming (same connectionId)"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_preserve_serial_channel')
        await channel.attach()

        connection_manager = ably.connection.connection_manager
        original_connection_id = connection_manager.connection_id

        # Block ACKs to keep messages pending
        original_on_ack = connection_manager.on_ack
        connection_manager.on_ack = lambda *args: None

        # Publish a message (msgSerial will be 0)
        asyncio.create_task(connection_manager.send_protocol_message({
            "action": ProtocolMessageAction.MESSAGE,
            "channel": channel.name,
            "messages": [{"name": "test1", "data": "data1"}]
        }))

        # Wait for message to be pending
        async def check_pending():
            return connection_manager.pending_message_queue.count() == 1
        await assert_waiter(check_pending, timeout=2)

        # msgSerial counter should be at 1 now
        assert connection_manager.msg_serial == 1

        # Simulate resume with SAME connectionId
        from ably.pubsub.types.connectiondetails import ConnectionDetails
        connection_details = ConnectionDetails(
            connection_state_ttl=120000,
            max_idle_interval=15000,
            connection_key='same_key',
            client_id=None
        )
        connection_manager.on_connected(connection_details, original_connection_id)

        # msgSerial counter should STILL be 1 (preserved on resume)
        assert connection_manager.msg_serial == 1, (
            f"Expected msgSerial=1 preserved, got {connection_manager.msg_serial}"
        )

        # Restore on_ack and clean up
        connection_manager.on_ack = original_on_ack
        connection_manager.pending_message_queue.complete_all_messages(AblyException("cleanup", 0, 0))

        await ably.close()

    async def test_msgserial_reset_on_failed_resume(self):
        """RTN19a2: Verify msgSerial counter is reset when resume fails (new connectionId)"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_reset_serial_resume_channel')
        await channel.attach()

        connection_manager = ably.connection.connection_manager

        # Block ACKs to keep messages pending
        original_on_ack = connection_manager.on_ack
        connection_manager.on_ack = lambda *args: None

        # Publish a message (msgSerial will be 0)
        asyncio.create_task(connection_manager.send_protocol_message({
            "action": ProtocolMessageAction.MESSAGE,
            "channel": channel.name,
            "messages": [{"name": "test1", "data": "data1"}]
        }))

        # Wait for message to be pending
        async def check_pending():
            return connection_manager.pending_message_queue.count() == 1
        await assert_waiter(check_pending, timeout=2)

        # msgSerial counter should be at 1 now
        assert connection_manager.msg_serial == 1

        # Simulate NEW connection (different connectionId = failed resume)
        from ably.pubsub.types.connectiondetails import ConnectionDetails
        new_connection_details = ConnectionDetails(
            connection_state_ttl=120000,
            max_idle_interval=15000,
            connection_key='new_key',
            client_id=None
        )
        new_connection_id = 'new_connection_id_67890'
        connection_manager.on_connected(new_connection_details, new_connection_id)

        # msgSerial counter should be reset to 0 (new connection)
        assert connection_manager.msg_serial == 0, (
            f"Expected msgSerial reset to 0, got {connection_manager.msg_serial}"
        )

        # Restore on_ack and clean up
        connection_manager.on_ack = original_on_ack
        connection_manager.pending_message_queue.complete_all_messages(AblyException("cleanup", 0, 0))

        await ably.close()

    # Test ACK with count > 1
    async def test_ack_with_multiple_count(self):
        """RTN7a/RTN7b: Test that ACK with count > 1 completes multiple messages"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_multi_ack_channel')
        await channel.attach()

        connection_manager = ably.connection.connection_manager

        # Intercept transport to delay ACKs
        original_send = connection_manager.transport.send
        pending_messages = []

        async def delay_ack(message):
            if message.get('action') == ProtocolMessageAction.MESSAGE:
                pending_messages.append(message)
                # Don't send yet
                return
            await original_send(message)

        connection_manager.transport.send = delay_ack

        # Start 3 publishes
        task1 = asyncio.create_task(channel.publish('event1', 'data1'))
        task2 = asyncio.create_task(channel.publish('event2', 'data2'))
        task3 = asyncio.create_task(channel.publish('event3', 'data3'))

        # Wait for message to be pending
        async def check_pending():
            return connection_manager.pending_message_queue.count() == 3
        await assert_waiter(check_pending, timeout=2)

        # Send ACK for all 3 messages at once (count=3)
        ack_message = {
            'action': ProtocolMessageAction.ACK,
            'msgSerial': 0,  # First message serial
            'count': 3  # Acknowledging 3 messages
        }
        await connection_manager.transport.on_protocol_message(ack_message)

        # All tasks should now complete
        await task1
        await task2
        await task3

        await ably.close()

    async def test_queued_messages_sent_before_channel_reattach(self):
        """RTL3d + RTL6c2: Verify queued messages are sent immediately on reconnection,
        without waiting for channel reattachment to complete"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol, queue_messages=True)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_rtl3d_rtl6c2_channel')
        await channel.attach()

        # Verify channel is ATTACHED
        assert channel.state == ChannelState.ATTACHED

        connection_manager = ably.connection.connection_manager

        # Track channel reattachment
        channel_attaching_seen = False

        def track_attaching(state_change):
            nonlocal channel_attaching_seen
            if state_change.current == ChannelState.ATTACHING:
                channel_attaching_seen = True

        channel.on('attaching', track_attaching)

        # Force an invalid resume to ensure a new connection
        # (like test_attached_channel_reattaches_on_invalid_resume)
        assert connection_manager.connection_details
        connection_manager.connection_details.connection_key = 'ably-python-fake-key'

        # Queue a message before disconnecting (to ensure it gets queued)
        # Block message sending first
        original_send = connection_manager.transport.send

        async def block_messages(message):
            if message.get('action') == ProtocolMessageAction.MESSAGE:
                # Don't send MESSAGE, just queue it
                return
            await original_send(message)

        connection_manager.transport.send = block_messages

        # Publish a message (will be blocked and moved to pending)
        publish_task = asyncio.create_task(channel.publish('test_event', 'test_data'))

        # Wait for message to be pending
        async def check_pending():
            return connection_manager.pending_message_queue.count() > 0
        await assert_waiter(check_pending, timeout=2)

        # Now disconnect to move pending messages to queued
        assert connection_manager.transport
        await connection_manager.transport.dispose()
        connection_manager.notify_state(ConnectionState.DISCONNECTED, retry_immediately=False)

        # Give time for state transition and message requeueing
        async def check_requeue_happened():
            return len(connection_manager.queued_messages) > 0
        await assert_waiter(check_requeue_happened, timeout=2)

        # Verify message was moved to queued_messages
        queued_count_before = len(connection_manager.queued_messages)
        assert queued_count_before > 0, "Message should be queued after DISCONNECTED"
        assert not publish_task.done(), "Publish task should still be pending"

        # Reconnect (will fail resume due to fake key, creating new connection)
        ably.connect()

        # Wait for CONNECTED state (RTL3d + RTL6c2 happens here)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=10)

        # Give time for send_queued_messages() and channel reattachment to process
        async def check_sent_queued_messages():
            return len(connection_manager.queued_messages) == 0
        await assert_waiter(check_sent_queued_messages, timeout=2)

        # Verify queued messages were sent (RTL6c2)
        queued_count_after = len(connection_manager.queued_messages)
        assert queued_count_after < queued_count_before, \
            "Queued messages should be sent immediately when entering CONNECTED (RTL6c2)"

        # Verify channel transitioned to ATTACHING (RTL3d)
        assert channel_attaching_seen, "Channel should have transitioned to ATTACHING (RTL3d)"

        # Wait for channel to reach ATTACHED state
        if channel.state != ChannelState.ATTACHED:
            await asyncio.wait_for(channel.once_async(ChannelState.ATTACHED), timeout=5)

        # Verify publish completes successfully
        await asyncio.wait_for(publish_task, timeout=5)

        await ably.close()

    # RSL1i - Message size limit tests
    async def test_publish_message_exceeding_size_limit(self):
        """RSL1i: Verify that publishing a message exceeding the size limit raises an exception"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_size_limit_channel')
        await channel.attach()

        # Create a message that exceeds the default 65536 byte limit
        # 70KB of data should definitely exceed the limit
        large_data = 'x' * (70 * 1024)

        # Attempt to publish should raise AblyException with code 40009
        with pytest.raises(AblyException) as exc_info:
            await channel.publish('test_event', large_data)

        assert exc_info.value.code == 40009
        assert 'Maximum size of messages' in str(exc_info.value)

        await ably.close()

    async def test_publish_message_within_size_limit(self):
        """RSL1i: Verify that publishing a message within the size limit succeeds"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_size_ok_channel')
        await channel.attach()

        # Create a message that is well within the 65536 byte limit
        # 10KB of data should be safe
        medium_data = 'x' * (10 * 1024)

        # Publish should complete successfully
        await channel.publish('test_event', medium_data)

        await ably.close()

    # RTL6g - Client ID validation tests
    async def test_publish_with_matching_client_id(self):
        """RTL6g2: Verify that publishing with explicit matching clientId succeeds"""
        ably = await TestApp.get_ably_realtime(
            use_binary_protocol=self.use_binary_protocol, client_id='test_client_123'
        )
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_client_id_channel')
        await channel.attach()

        # Create message with matching clientId
        message = Message(name='test_event', data='test_data', client_id='test_client_123')

        # Publish should succeed with matching clientId
        await channel.publish(message)

        await ably.close()

    async def test_publish_with_null_client_id_when_identified(self):
        """RTL6g1: Verify that publishing with null clientId gets populated by server when client is identified"""
        ably = await TestApp.get_ably_realtime(
            use_binary_protocol=self.use_binary_protocol, client_id='test_client_456'
        )
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_null_client_id_channel')
        await channel.attach()

        # Publish without explicit clientId (will be populated by server)
        await channel.publish('test_event', 'test_data')

        await ably.close()

    async def test_publish_with_mismatched_client_id_fails(self):
        """RTL6g3: Verify that publishing with mismatched clientId is rejected"""
        ably = await TestApp.get_ably_realtime(
            use_binary_protocol=self.use_binary_protocol, client_id='test_client_789'
        )
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_mismatch_client_id_channel')
        await channel.attach()

        # Create message with different clientId
        message = Message(name='test_event', data='test_data', client_id='different_client')

        # Publish should raise IncompatibleClientIdException
        with pytest.raises(IncompatibleClientIdException) as exc_info:
            await channel.publish(message)

        assert exc_info.value.code == 40012
        assert 'incompatible' in str(exc_info.value).lower()

        await ably.close()

    async def test_publish_with_wildcard_client_id_fails(self):
        """RTL6g3: Verify that publishing with wildcard clientId is rejected"""
        ably = await TestApp.get_ably_realtime(
            use_binary_protocol=self.use_binary_protocol, client_id='test_client_wildcard'
        )
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_wildcard_client_id_channel')
        await channel.attach()

        # Create message with wildcard clientId
        message = Message(name='test_event', data='test_data', client_id='*')

        # Publish should raise IncompatibleClientIdException
        with pytest.raises(IncompatibleClientIdException) as exc_info:
            await channel.publish(message)

        assert exc_info.value.code == 40012
        assert 'wildcard' in str(exc_info.value).lower()

        await ably.close()

    # RTL6i - Data type variation tests
    async def test_publish_with_string_data(self):
        """RTL6i: Verify that publishing with string data succeeds"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_string_data_channel')
        await channel.attach()

        # Publish message with string data
        await channel.publish('test_event', 'simple string data')

        await ably.close()

    async def test_publish_with_json_object_data(self):
        """RTL6i: Verify that publishing with JSON object data succeeds"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_json_object_channel')
        await channel.attach()

        # Publish message with JSON object data
        json_data = {
            'key1': 'value1',
            'key2': 42,
            'key3': True,
            'nested': {'inner': 'data'}
        }
        await channel.publish('test_event', json_data)

        await ably.close()

    async def test_publish_with_json_array_data(self):
        """RTL6i: Verify that publishing with JSON array data succeeds"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_json_array_channel')
        await channel.attach()

        # Publish message with JSON array data
        array_data = ['item1', 'item2', 42, True, {'nested': 'object'}]
        await channel.publish('test_event', array_data)

        await ably.close()

    async def test_publish_with_null_data(self):
        """RTL6i3: Verify that publishing with null data succeeds"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_null_data_channel')
        await channel.attach()

        # Publish message with null data (RTL6i3: null data is permitted)
        await channel.publish('test_event', None)

        await ably.close()

    async def test_publish_with_null_name(self):
        """RTL6i3: Verify that publishing with null name succeeds"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_null_name_channel')
        await channel.attach()

        # Publish message with null name (RTL6i3: null name is permitted)
        await channel.publish(None, 'test data')

        await ably.close()

    async def test_publish_message_array(self):
        """RTL6i2: Verify that publishing an array of messages succeeds"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_message_array_channel')
        await channel.attach()

        # Publish array of messages (RTL6i2)
        messages = [
            Message(name='event1', data='data1'),
            Message(name='event2', data='data2'),
            Message(name='event3', data={'key': 'value'}),
        ]
        await channel.publish(messages)

        await ably.close()

    # RTL6c4 - Channel state validation tests
    async def test_publish_fails_on_suspended_channel(self):
        """RTL6c4: Verify that publishing on a SUSPENDED channel fails"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_suspended_channel')
        await channel.attach()

        # Force channel to SUSPENDED state
        channel._notify_state(ChannelState.SUSPENDED)

        # Verify channel is SUSPENDED
        assert channel.state == ChannelState.SUSPENDED

        # Attempt to publish should raise AblyException with code 90001
        with pytest.raises(AblyException) as exc_info:
            await channel.publish('test_event', 'test_data')

        assert exc_info.value.code == 90001
        assert 'suspended' in str(exc_info.value).lower()

        await ably.close()

    async def test_publish_fails_on_failed_channel(self):
        """RTL6c4: Verify that publishing on a FAILED channel fails"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get('test_failed_channel')
        await channel.attach()

        # Force channel to FAILED state
        channel._notify_state(ChannelState.FAILED)

        # Verify channel is FAILED
        assert channel.state == ChannelState.FAILED

        # Attempt to publish should raise AblyException with code 90001
        with pytest.raises(AblyException) as exc_info:
            await channel.publish('test_event', 'test_data')

        assert exc_info.value.code == 90001
        assert 'failed' in str(exc_info.value).lower()

        await ably.close()

    # RSL1k - Idempotent publishing test
    async def test_idempotent_realtime_publishing(self):
        """RSL1k2, RSL1k5: Verify that messages with explicit IDs can be published for idempotent behavior"""
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        channel = ably.channels.get(f'test_idempotent_channel_{self.use_binary_protocol}')
        await channel.attach()

        idempotent_id = 'test-msg-id-12345'
        different_id = 'test-msg-id-67890'

        data_received = []
        different_id_received = WaitableEvent()
        def on_message(message):
            try:
                data_received.append(message.data)

                if message.id == different_id:
                    different_id_received.finish()
            except Exception as e:
                different_id_received.finish()
                raise e

        await channel.subscribe(on_message)

        # RSL1k2: Publish messages with explicit IDs
        # Messages with explicit IDs should include those IDs in the published message
        message1 = Message(name='idempotent_event', data='first message', id=idempotent_id)

        # Publish should succeed with explicit ID
        await channel.publish(message1)

        # Publish another message with the same ID (RSL1k5: idempotent publishing)
        # With idempotent publishing enabled on the server, messages with the same ID
        # should be deduplicated. Here we verify that publishing with the same ID succeeds.
        message2 = Message(name='idempotent_event', data='second message', id=idempotent_id)
        await channel.publish(message2)

        # Publish a message with a different ID
        message3 = Message(name='unique_event', data='third message', id=different_id)
        await channel.publish(message3)

        await different_id_received.wait()

        assert len(data_received) == 2, "Only two messages should have been received"
        assert data_received[0] == 'first message'
        assert data_received[1] == 'third message'

        await ably.close()

    async def test_publish_with_encryption(self):
        """Verify that encrypted messages can be published and received correctly"""
        # Create connection with binary protocol enabled
        ably = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await asyncio.wait_for(ably.connection.once_async(ConnectionState.CONNECTED), timeout=5)

        # Get channel with encryption enabled
        cipher_params = CipherParams(secret_key=b'0123456789abcdef0123456789abcdef')
        channel_options = ChannelOptions(cipher=cipher_params)
        channel = ably.channels.get('encrypted_channel', channel_options)
        await channel.attach()

        received_data = None
        data_received = WaitableEvent()
        def on_message(message):
            nonlocal received_data
            try:
                received_data = message.data
                data_received.finish()
            except Exception as e:
                data_received.finish()
                raise e

        await channel.subscribe(on_message)

        await channel.publish('encrypted_event', 'sensitive data')

        await data_received.wait()

        assert received_data == 'sensitive data'

        await ably.close()
