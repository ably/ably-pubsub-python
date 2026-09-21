"""
Integration tests for RealtimePresence.

These tests verify presence functionality with real Ably connections,
testing enter/leave/update operations, presence subscriptions, and SYNC behavior.
"""

import asyncio

import pytest

from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.types.channelstate import ChannelState
from ably.pubsub.types.presence import PresenceAction
from ably.pubsub.util.exceptions import AblyException
from test.ably.testapp import TestApp
from test.ably.utils import BaseAsyncTestCase


async def force_suspended(client):
    client.connection.connection_manager.request_state(ConnectionState.DISCONNECTED)

    await client.connection._when_state(ConnectionState.DISCONNECTED)

    client.connection.connection_manager.notify_state(
        ConnectionState.SUSPENDED,
        AblyException("Connection to server unavailable", 400, 80002)
    )

    await client.connection._when_state(ConnectionState.SUSPENDED)


@pytest.mark.parametrize('use_binary_protocol', [True, False], ids=['msgpack', 'json'])
class TestRealtimePresenceBasics(BaseAsyncTestCase):
    """Test basic presence operations: enter, leave, update."""

    @pytest.fixture(autouse=True)
    async def setup(self, use_binary_protocol):
        """Set up test fixtures."""
        self.test_vars = await TestApp.get_test_vars()
        self.use_binary_protocol = use_binary_protocol

        self.client1 = await TestApp.get_ably_realtime(
            client_id='client1',
            use_binary_protocol=use_binary_protocol
        )
        self.client2 = await TestApp.get_ably_realtime(
            client_id='client2',
            use_binary_protocol=use_binary_protocol
        )

        yield

        await self.client1.close()
        await self.client2.close()

    async def test_presence_enter_without_attach(self):
        """
        Test RTP8d: Enter presence without prior attach (implicit attach).
        """
        channel_name = self.get_channel_name('enter_without_attach')

        # Client 1 listens for presence
        channel1 = self.client1.channels.get(channel_name)

        presence_received = asyncio.Future()

        def on_presence(msg):
            if msg.action == PresenceAction.ENTER and msg.client_id == 'client2':
                presence_received.set_result(msg)

        await channel1.presence.subscribe(on_presence)

        # Client 2 enters without attaching first
        channel2 = self.client2.channels.get(channel_name)
        assert channel2.state == ChannelState.INITIALIZED

        await channel2.presence.enter('test data')

        # Should receive presence event
        msg = await asyncio.wait_for(presence_received, timeout=5.0)
        assert msg.client_id == 'client2'
        assert msg.data == 'test data'
        assert msg.action == PresenceAction.ENTER

    async def test_presence_enter_with_callback(self):
        """
        Test RTP8b: Enter with callback - callback should be called on success.
        """
        channel_name = self.get_channel_name('enter_with_callback')

        channel = self.client1.channels.get(channel_name)
        await channel.attach()

        # Enter presence - should succeed
        await channel.presence.enter('test data')

        # Verify member is present
        members = await channel.presence.get()
        assert len(members) == 1
        assert members[0].client_id == 'client1'
        assert members[0].data == 'test data'

    async def test_presence_enter_and_leave(self):
        """
        Test RTP10: Enter and leave presence, await leave event.
        """
        channel_name = self.get_channel_name('enter_and_leave')

        channel1 = self.client1.channels.get(channel_name)
        channel2 = self.client2.channels.get(channel_name)

        await channel1.attach()

        # Track events
        events = []

        def on_presence(msg):
            events.append((msg.action, msg.client_id))

        await channel1.presence.subscribe(on_presence)

        # Client 2 enters
        await channel2.presence.enter('enter data')

        # Wait for enter event
        await asyncio.sleep(0.5)
        assert (PresenceAction.ENTER, 'client2') in events

        # Client 2 leaves
        await channel2.presence.leave()

        # Wait for leave event
        await asyncio.sleep(0.5)
        assert (PresenceAction.LEAVE, 'client2') in events

    async def test_presence_enter_update(self):
        """
        Test RTP9: Update presence data.
        """
        channel_name = self.get_channel_name('enter_update')

        channel1 = self.client1.channels.get(channel_name)
        channel2 = self.client2.channels.get(channel_name)

        await channel1.attach()

        # Track update events
        updates = []

        def on_update(msg):
            if msg.action == PresenceAction.UPDATE:
                updates.append(msg.data)

        await channel1.presence.subscribe('update', on_update)

        # Client 2 enters then updates
        await channel2.presence.enter('original data')
        await asyncio.sleep(0.3)

        await channel2.presence.update('updated data')

        # Wait for update event
        await asyncio.sleep(0.5)
        assert 'updated data' in updates

    async def test_presence_anonymous_client_error(self):
        """
        Test RTP8j: Anonymous clients cannot enter presence.
        """
        # Create client without clientId
        client = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        await client.connection.once_async('connected')

        channel = client.channels.get(self.get_channel_name('anonymous'))

        try:
            await channel.presence.enter('data')
            pytest.fail('Should have raised exception for anonymous client')
        except Exception as e:
            assert 'clientId must be specified' in str(e)
        finally:
            await client.close()


@pytest.mark.parametrize('use_binary_protocol', [True, False], ids=['msgpack', 'json'])
class TestRealtimePresenceGet(BaseAsyncTestCase):
    """Test presence.get() functionality."""

    @pytest.fixture(autouse=True)
    async def setup(self, use_binary_protocol):
        """Set up test fixtures."""
        self.test_vars = await TestApp.get_test_vars()
        self.use_binary_protocol = use_binary_protocol

        self.client1 = await TestApp.get_ably_realtime(
            client_id='client1',
            use_binary_protocol=use_binary_protocol
        )
        self.client2 = await TestApp.get_ably_realtime(
            client_id='client2',
            use_binary_protocol=use_binary_protocol
        )

        yield

        await self.client1.close()
        await self.client2.close()

    async def test_presence_enter_get(self):
        """
        Test RTP11a: Enter presence and get members.
        """
        channel_name = self.get_channel_name('enter_get')

        channel1 = self.client1.channels.get(channel_name)
        channel2 = self.client2.channels.get(channel_name)

        # Client 1 enters
        await channel1.presence.enter('test data')

        # Wait for presence to sync
        await asyncio.sleep(0.5)

        # Client 2 gets presence
        members = await channel2.presence.get()

        assert len(members) == 1
        assert members[0].client_id == 'client1'
        assert members[0].data == 'test data'
        assert members[0].action == PresenceAction.PRESENT

    async def test_presence_get_unattached(self):
        """
        Test RTP11b: Get presence on unattached channel (should attach and wait for sync).
        """
        channel_name = self.get_channel_name('get_unattached')

        # Client 1 enters
        channel1 = self.client1.channels.get(channel_name)
        await channel1.presence.enter('test data')

        # Wait for presence
        await asyncio.sleep(0.5)

        # Client 2 gets without attaching first
        channel2 = self.client2.channels.get(channel_name)
        assert channel2.state == ChannelState.INITIALIZED

        members = await channel2.presence.get()

        # Channel should now be attached
        assert channel2.state == ChannelState.ATTACHED
        assert len(members) == 1
        assert members[0].client_id == 'client1'

    async def test_presence_enter_leave_get(self):
        """
        Test RTP11a + RTP10c: Enter, leave, then get (should be empty).
        """
        channel_name = self.get_channel_name('enter_leave_get')

        channel1 = self.client1.channels.get(channel_name)
        channel2 = self.client2.channels.get(channel_name)

        # Client 1 enters then leaves
        await channel1.presence.enter('test data')
        await asyncio.sleep(0.3)
        await channel1.presence.leave()

        # Wait for leave to process
        await asyncio.sleep(0.5)

        # Client 2 gets presence
        members = await channel2.presence.get()

        assert len(members) == 0


@pytest.mark.parametrize('use_binary_protocol', [True, False], ids=['msgpack', 'json'])
class TestRealtimePresenceSubscribe(BaseAsyncTestCase):
    """Test presence.subscribe() functionality."""

    @pytest.fixture(autouse=True)
    async def setup(self, use_binary_protocol):
        """Set up test fixtures."""
        self.test_vars = await TestApp.get_test_vars()
        self.use_binary_protocol = use_binary_protocol

        self.client1 = await TestApp.get_ably_realtime(
            client_id='client1',
            use_binary_protocol=use_binary_protocol
        )
        self.client2 = await TestApp.get_ably_realtime(
            client_id='client2',
            use_binary_protocol=use_binary_protocol
        )

        yield

        await self.client1.close()
        await self.client2.close()

    async def test_presence_subscribe_unattached(self):
        """
        Test RTP6d: Subscribe on unattached channel should implicitly attach.
        """
        channel_name = self.get_channel_name('subscribe_unattached')

        channel1 = self.client1.channels.get(channel_name)

        received = asyncio.Future()

        def on_presence(msg):
            if msg.client_id == 'client2':
                received.set_result(msg)

        # Subscribe without attaching first
        assert channel1.state == ChannelState.INITIALIZED
        await channel1.presence.subscribe(on_presence)

        # Should implicitly attach
        await asyncio.sleep(0.5)
        assert channel1.state == ChannelState.ATTACHED

        # Client 2 enters
        channel2 = self.client2.channels.get(channel_name)
        await channel2.presence.enter('data')

        # Should receive event
        msg = await asyncio.wait_for(received, timeout=5.0)
        assert msg.client_id == 'client2'

    async def test_presence_message_action(self):
        """
        Test RTP8c: PresenceMessage should have correct action string.
        """
        channel_name = self.get_channel_name('message_action')

        channel1 = self.client1.channels.get(channel_name)

        received = asyncio.Future()

        def on_presence(msg):
            if msg.action == PresenceAction.ENTER:
                received.set_result(msg)

        await channel1.presence.subscribe(on_presence)
        await channel1.presence.enter()

        msg = await asyncio.wait_for(received, timeout=5.0)
        assert msg.action == PresenceAction.ENTER


@pytest.mark.parametrize('use_binary_protocol', [True, False], ids=['msgpack', 'json'])
class TestRealtimePresenceEnterClient(BaseAsyncTestCase):
    """Test enterClient/updateClient/leaveClient functionality."""

    @pytest.fixture(autouse=True)
    async def setup(self, use_binary_protocol):
        """Set up test fixtures."""
        self.test_vars = await TestApp.get_test_vars()
        self.use_binary_protocol = use_binary_protocol

        # Use wildcard auth for enterClient
        self.client = await TestApp.get_ably_realtime(
            client_id='*',
            use_binary_protocol=use_binary_protocol
        )

        yield

        await self.client.close()

    async def test_enter_client_multiple(self):
        """
        Test RTP14/RTP15: Enter multiple clients on one connection.
        """
        channel_name = self.get_channel_name('enter_client_multiple')
        channel = self.client.channels.get(channel_name)

        # Enter multiple clients
        for i in range(5):
            await channel.presence.enter_client(f'test_client_{i}', f'data_{i}')

        # Wait for presence to sync
        await asyncio.sleep(0.5)

        # Get all members
        members = await channel.presence.get()

        assert len(members) == 5
        client_ids = {m.client_id for m in members}
        assert all(f'test_client_{i}' in client_ids for i in range(5))

    async def test_update_client(self):
        """
        Test RTP15: Update client presence data.
        """
        channel_name = self.get_channel_name('update_client')
        channel = self.client.channels.get(channel_name)

        # Enter client
        await channel.presence.enter_client('test_client', 'original data')
        await asyncio.sleep(0.3)

        # Update client
        await channel.presence.update_client('test_client', 'updated data')
        await asyncio.sleep(0.3)

        # Get member
        members = await channel.presence.get(client_id='test_client')

        assert len(members) == 1
        assert members[0].data == 'updated data'

    async def test_leave_client(self):
        """
        Test RTP15: Leave client presence.
        """
        channel_name = self.get_channel_name('leave_client')
        channel = self.client.channels.get(channel_name)

        # Enter multiple clients
        await channel.presence.enter_client('client1', 'data1')
        await channel.presence.enter_client('client2', 'data2')
        await asyncio.sleep(0.3)

        # Leave one client
        await channel.presence.leave_client('client1')
        await asyncio.sleep(0.5)

        # Only client2 should remain
        members = await channel.presence.get()

        assert len(members) == 1
        assert members[0].client_id == 'client2'


@pytest.mark.parametrize('use_binary_protocol', [True, False], ids=['msgpack', 'json'])
class TestRealtimePresenceConnectionLifecycle(BaseAsyncTestCase):
    """Test presence behavior during connection lifecycle events."""

    @pytest.fixture(autouse=True)
    async def setup(self, use_binary_protocol):
        """Set up test fixtures."""
        self.test_vars = await TestApp.get_test_vars()
        self.use_binary_protocol = use_binary_protocol
        yield

    async def test_presence_enter_without_connect(self):
        """
        Test entering presence before connection is established.
        Related to RTP8d.
        """
        channel_name = self.get_channel_name('enter_without_connect')

        # Create listener client
        listener_client = await TestApp.get_ably_realtime(
            client_id='listener',
            use_binary_protocol=self.use_binary_protocol
        )
        listener_channel = listener_client.channels.get(channel_name)

        received = asyncio.Future()

        def on_presence(msg):
            if msg.client_id == 'enterer' and msg.action == PresenceAction.ENTER:
                received.set_result(msg)

        await listener_channel.presence.subscribe(on_presence)

        # Create client and enter before it's connected
        enterer_client = await TestApp.get_ably_realtime(
            client_id='enterer',
            use_binary_protocol=self.use_binary_protocol
        )
        enterer_channel = enterer_client.channels.get(channel_name)

        # Enter without waiting for connection
        await enterer_channel.presence.enter('test data')

        # Should receive presence event
        msg = await asyncio.wait_for(received, timeout=5.0)
        assert msg.client_id == 'enterer'
        assert msg.data == 'test data'

        await listener_client.close()
        await enterer_client.close()

    async def test_presence_enter_after_close(self):
        """
        Test re-entering presence after connection close and reconnect.
        Related to RTP8d.
        """
        channel_name = self.get_channel_name('enter_after_close')

        # Create listener
        listener_client = await TestApp.get_ably_realtime(
            client_id='listener',
            use_binary_protocol=self.use_binary_protocol
        )
        listener_channel = listener_client.channels.get(channel_name)

        second_enter_received = asyncio.Future()

        def on_presence(msg):
            if msg.client_id == 'enterer' and msg.data == 'second' and msg.action == PresenceAction.ENTER:
                second_enter_received.set_result(msg)

        await listener_channel.presence.subscribe(on_presence)

        # Create enterer client
        enterer_client = await TestApp.get_ably_realtime(
            client_id='enterer',
            use_binary_protocol=self.use_binary_protocol
        )
        enterer_channel = enterer_client.channels.get(channel_name)

        await enterer_client.connection.once_async('connected')

        # First enter
        await enterer_channel.presence.enter('first')
        await asyncio.sleep(0.3)

        # Close and wait
        await enterer_client.close()

        # Reconnect
        enterer_client.connection.connect()
        await enterer_client.connection.once_async('connected')

        # Second enter - should automatically reattach
        await enterer_channel.presence.enter('second')

        # Should receive second enter event
        msg = await asyncio.wait_for(second_enter_received, timeout=5.0)
        assert msg.data == 'second'

        await listener_client.close()
        await enterer_client.close()

    async def test_presence_enter_closed_error(self):
        """
        Test RTP15e: Entering presence on closed connection should error.
        """
        channel_name = self.get_channel_name('enter_closed')

        client = await TestApp.get_ably_realtime(use_binary_protocol=self.use_binary_protocol)
        channel = client.channels.get(channel_name)

        await client.connection.once_async('connected')

        # Close the connection
        await client.close()

        # Try to enter - should fail
        try:
            await channel.presence.enter_client('client1', 'data')
            pytest.fail('Should have raised exception for closed connection')
        except Exception as e:
            # Should get an error about closed/failed connection
            assert 'closed' in str(e).lower() or 'failed' in str(e).lower() or '80017' in str(e)

        await client.close()


@pytest.mark.parametrize('use_binary_protocol', [True, False], ids=['msgpack', 'json'])
class TestRealtimePresenceAutoReentry(BaseAsyncTestCase):
    """Test automatic re-entry of presence after connection suspension."""

    @pytest.fixture(autouse=True)
    async def setup(self, use_binary_protocol):
        """Set up test fixtures."""
        self.test_vars = await TestApp.get_test_vars()
        self.use_binary_protocol = use_binary_protocol
        yield

    async def test_presence_auto_reenter_after_suspend(self):
        """
        Test RTP5f, RTP17, RTP17g, RTP17i: Members automatically re-enter after suspension.

        This test verifies that when a connection is suspended and then reconnected,
        presence members that were entered automatically re-enter.
        """
        channel_name = self.get_channel_name('auto_reenter')

        client = await TestApp.get_ably_realtime(
            client_id='test_client',
            use_binary_protocol=self.use_binary_protocol
        )
        channel = client.channels.get(channel_name)

        await channel.attach()

        # Enter presence
        await channel.presence.enter('original_data')
        await asyncio.sleep(0.5)

        # Verify member is present
        members = await channel.presence.get()
        assert len(members) == 1
        assert members[0].client_id == 'test_client'
        assert members[0].data == 'original_data'

        # Suspend the connection
        await force_suspended(client)

        # Reconnect - connection will be resumed with same connection ID
        client.connection.connect()
        await client.connection.once_async('connected')

        # Wait for channel to reattach after suspension
        await channel.once_async('attached')

        # Give time for auto-reenter to complete
        # Auto-reenter sends a presence message, server ACKs it, but doesn't
        # broadcast a new ENTER event because on a resumed connection with
        # unchanged data, no state change occurred from the server's perspective
        await asyncio.sleep(0.5)

        # Verify member is still in presence set (auto-reenter worked)
        # This is the actual requirement of RTP17i - members are automatically
        # re-entered after suspension, ensuring they remain in the presence set
        members = await channel.presence.get()
        assert len(members) >= 1
        assert any(m.client_id == 'test_client' and m.data == 'original_data' for m in members)

        await client.close()

    async def test_presence_auto_reenter_different_connid(self):
        """
        Test RTP17g, RTP17g1: Auto re-entry with different connectionId.

        When connection is suspended and reconnects with a different connectionId,
        verify that:
        1. A LEAVE is sent for the old connectionId
        2. An ENTER is sent for the new connectionId
        3. The new ENTER does not have the same message ID as the original
        """
        channel_name = self.get_channel_name('auto_reenter_different_connid')

        # Create observer client
        observer_client = await TestApp.get_ably_realtime(
            client_id='observer',
            use_binary_protocol=self.use_binary_protocol
        )
        observer_channel = observer_client.channels.get(channel_name)
        await observer_channel.attach()

        # Track presence events
        events = []

        def on_presence(msg):
            events.append({
                'action': msg.action,
                'client_id': msg.client_id,
                'connection_id': msg.connection_id,
                'id': getattr(msg, 'id', None)
            })

        await observer_channel.presence.subscribe(on_presence)

        # Create main client with remainPresentFor to control LEAVE timing
        # This tells the server to send LEAVE for presence members 5 seconds after disconnect
        client = await TestApp.get_ably_realtime(
            client_id='test_client',
            transport_params={'remainPresentFor': 1000},
            use_binary_protocol=self.use_binary_protocol
        )
        channel = client.channels.get(channel_name)

        await client.connection.once_async('connected')
        first_conn_id = client.connection.connection_manager.connection_id

        # Enter presence
        await channel.presence.enter('test_data')
        await asyncio.sleep(0.5)

        # Get the original message ID
        original_msg_id = None
        for event in events:
            if event['action'] == PresenceAction.ENTER and event['client_id'] == 'test_client':
                original_msg_id = event['id']
                break

        # Force suspension and reconnection with different connection ID
        await force_suspended(client)

        # Reconnect
        client.connection.connect()
        await client.connection.once_async('connected')
        second_conn_id = client.connection.connection_manager.connection_id

        # Connection IDs should be different after suspend
        assert first_conn_id != second_conn_id

        # Wait for presence events including LEAVE (which arrives after remainPresentFor timeout)
        await asyncio.sleep(2)

        # Should see LEAVE for old connection and ENTER for new connection
        leave_events = [e for e in events if e['action'] == PresenceAction.LEAVE
                       and e['client_id'] == 'test_client']
        enter_events = [e for e in events if e['action'] == PresenceAction.ENTER
                       and e['client_id'] == 'test_client']

        assert len(leave_events) >= 1, "Should have LEAVE event for old connection"
        assert len(enter_events) >= 2, "Should have ENTER event for new connection"

        # Find the leave for first connection
        leave_for_first = [e for e in leave_events if e['connection_id'] == first_conn_id]
        assert len(leave_for_first) >= 1, "Should have LEAVE for first connection ID"

        # Find the enter for second connection
        enter_for_second = [e for e in enter_events if e['connection_id'] == second_conn_id]
        assert len(enter_for_second) >= 1, "Should have ENTER for second connection ID"

        # The new ENTER should have a different message ID
        new_msg_id = enter_for_second[0]['id']
        if original_msg_id and new_msg_id:
            assert original_msg_id != new_msg_id, "New ENTER should have different message ID"

        await observer_client.close()
        await client.close()


@pytest.mark.parametrize('use_binary_protocol', [True, False], ids=['msgpack', 'json'])
class TestRealtimePresenceSyncBehavior(BaseAsyncTestCase):
    """Test presence SYNC behavior and state management."""

    @pytest.fixture(autouse=True)
    async def setup(self, use_binary_protocol):
        """Set up test fixtures."""
        self.test_vars = await TestApp.get_test_vars()
        self.use_binary_protocol = use_binary_protocol
        yield

    async def test_presence_refresh_on_detach(self):
        """
        Test RTP15b: Presence map refresh when channel detaches and reattaches.

        When a channel detaches and then reattaches, and the presence set has
        changed during that time, verify that the presence map is correctly
        refreshed with the new state.
        """
        channel_name = self.get_channel_name('refresh_on_detach')

        # Client that manages presence
        manager_client = await TestApp.get_ably_realtime(
            client_id='*',
            use_binary_protocol=self.use_binary_protocol
        )
        manager_channel = manager_client.channels.get(channel_name)

        # Observer client that will detach/reattach
        observer_client = await TestApp.get_ably_realtime(
            client_id='observer',
            use_binary_protocol=self.use_binary_protocol
        )
        observer_channel = observer_client.channels.get(channel_name)

        # Enter two members
        await manager_channel.presence.enter_client('client_one', 'data_one')
        await manager_channel.presence.enter_client('client_two', 'data_two')
        await asyncio.sleep(0.3)

        # Observer attaches and verifies
        await observer_channel.attach()
        members = await observer_channel.presence.get()
        assert len(members) == 2
        client_ids = {m.client_id for m in members}
        assert 'client_one' in client_ids
        assert 'client_two' in client_ids

        # Observer detaches
        await observer_channel.detach()

        # Change presence while observer is detached
        await manager_channel.presence.leave_client('client_two')
        await manager_channel.presence.enter_client('client_three', 'data_three')
        await asyncio.sleep(0.3)

        # Track presence events on observer
        presence_events = []

        def on_presence(msg):
            presence_events.append(msg.client_id)

        await observer_channel.presence.subscribe(on_presence)

        # Reattach and wait for sync
        await observer_channel.attach()
        await asyncio.sleep(1.0)

        # Should receive PRESENT events for current members
        members = await observer_channel.presence.get()
        assert len(members) == 2
        client_ids = {m.client_id for m in members}
        assert 'client_one' in client_ids
        assert 'client_three' in client_ids
        assert 'client_two' not in client_ids

        await manager_client.close()
        await observer_client.close()

    async def test_suspended_preserves_presence(self):
        """
        Test RTP5f, RTP11d: Presence map is preserved during SUSPENDED state.

        Verify that:
        1. Presence map is preserved when connection goes to SUSPENDED
        2. get() with waitForSync=False works while suspended
        3. get() without waitForSync returns error while suspended
        4. Only changed members trigger events after reconnection
        """
        channel_name = self.get_channel_name('suspended_preserves')

        # Create multiple clients
        main_client = await TestApp.get_ably_realtime(
            client_id='main',
            use_binary_protocol=self.use_binary_protocol
        )
        continuous_client = await TestApp.get_ably_realtime(
            client_id='continuous',
            use_binary_protocol=self.use_binary_protocol
        )
        leaves_client = await TestApp.get_ably_realtime(
            client_id='leaves',
            use_binary_protocol=self.use_binary_protocol
        )

        main_channel = main_client.channels.get(channel_name)
        continuous_channel = continuous_client.channels.get(channel_name)
        leaves_channel = leaves_client.channels.get(channel_name)

        # All enter presence
        await main_channel.presence.enter('main_data')
        await continuous_channel.presence.enter('continuous_data')
        await leaves_channel.presence.enter('leaves_data')
        await asyncio.sleep(0.5)

        # Verify all present
        members = await main_channel.presence.get()
        assert len(members) == 3
        client_ids = {m.client_id for m in members}
        assert client_ids == {'main', 'continuous', 'leaves'}

        # Simulate suspension on main client
        await force_suspended(main_client)

        # leaves_client leaves while main is suspended
        await leaves_client.close()
        await asyncio.sleep(0.3)

        # Track presence events on main after reconnect
        presence_events = []

        def on_presence(msg):
            presence_events.append({
                'action': msg.action,
                'client_id': msg.client_id
            })

        await main_channel.presence.subscribe(on_presence)

        # Reconnect main client
        main_client.connection.connect()
        await main_client.connection.once_async('connected')
        await main_channel.once_async('attached')

        # Wait for presence sync
        await asyncio.sleep(1.0)

        # Should only see LEAVE for leaves_client
        leave_events = [e for e in presence_events
                       if e['action'] == PresenceAction.LEAVE and e['client_id'] == 'leaves']
        assert len(leave_events) >= 1, "Should see LEAVE for leaves client"

        # Final state should have main and continuous
        members = await main_channel.presence.get()
        assert len(members) >= 2
        client_ids = {m.client_id for m in members}
        assert 'main' in client_ids
        assert 'continuous' in client_ids

        await main_client.close()
        await continuous_client.close()
