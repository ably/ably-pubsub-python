"""
Unit tests for PresenceMap implementation.

Tests RTP2 specification requirements for presence map operations.
"""

from datetime import datetime

import pytest

from ably.pubsub.realtime.presencemap import PresenceMap, _is_newer
from ably.pubsub.types.presence import PresenceAction, PresenceMessage
from test.ably.utils import BaseAsyncTestCase


class TestPresenceMessageHelpers(BaseAsyncTestCase):
    """Test helper methods on PresenceMessage (RTP2b support)."""

    def test_is_synthesized_with_matching_connection_id(self):
        """Test that normal messages are not synthesized."""
        msg = PresenceMessage(
            id='connection123:0:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        assert not msg.is_synthesized()

    def test_is_synthesized_with_non_matching_connection_id(self):
        """Test that synthesized leave events are detected (RTP2b1)."""
        msg = PresenceMessage(
            id='different:0:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.LEAVE
        )
        assert msg.is_synthesized()

    def test_is_synthesized_without_id(self):
        """Test that messages without id are not considered synthesized."""
        msg = PresenceMessage(
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        assert not msg.is_synthesized()

    def test_parse_id_valid(self):
        """Test parsing valid presence message id (RTP2b2)."""
        msg = PresenceMessage(
            id='connection123:42:7',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        parsed = msg.parse_id()
        assert parsed['msgSerial'] == 42
        assert parsed['index'] == 7

    def test_parse_id_without_id(self):
        """Test parsing message without id raises ValueError."""
        msg = PresenceMessage(
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        with pytest.raises(ValueError) as context:
            msg.parse_id()
        assert "id is None or empty" in str(context.value)

    def test_parse_id_invalid_format(self):
        """Test parsing invalid id format raises ValueError."""
        msg = PresenceMessage(
            id='invalid',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        with pytest.raises(ValueError) as context:
            msg.parse_id()
        assert "invalid msgSerial or index" in str(context.value)

    def test_parse_id_non_numeric_parts(self):
        """Test parsing id with non-numeric msgSerial/index raises ValueError."""
        msg = PresenceMessage(
            id='connection123:abc:def',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        with pytest.raises(ValueError) as context:
            msg.parse_id()
        assert "invalid msgSerial or index" in str(context.value)

    def test_member_key_property(self):
        """Test member_key property (TP3h)."""
        msg = PresenceMessage(
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        assert msg.member_key == 'connection123:client1'

    def test_member_key_without_connection_id(self):
        """Test member_key when connection_id is missing."""
        msg = PresenceMessage(
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        assert msg.member_key is None

    def test_to_encoded(self):
        """Test converting message to wire format."""
        msg = PresenceMessage(
            id='connection123:0:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.ENTER,
            data='test data',
            timestamp=datetime(2024, 1, 1, 12, 0, 0)
        )
        encoded = msg.to_encoded()
        assert encoded['action'] == PresenceAction.ENTER
        assert encoded['id'] == 'connection123:0:0'
        assert encoded['connectionId'] == 'connection123'
        assert encoded['clientId'] == 'client1'
        assert encoded['data'] == 'test data'
        assert 'timestamp' in encoded

    def test_to_encoded_with_dict_data(self):
        """Test converting message with dict data (should be JSON serialized)."""
        msg = PresenceMessage(
            id='connection123:0:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.ENTER,
            data={'key': 'value', 'number': 42}
        )
        encoded = msg.to_encoded()
        assert encoded['data'] == '{"key": "value", "number": 42}'
        assert encoded['encoding'] == 'json'

    def test_to_encoded_with_list_data(self):
        """Test converting message with list data (should be JSON serialized)."""
        msg = PresenceMessage(
            id='connection123:0:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.ENTER,
            data=['item1', 'item2', 3]
        )
        encoded = msg.to_encoded()
        assert encoded['data'] == '["item1", "item2", 3]'
        assert encoded['encoding'] == 'json'

    def test_to_encoded_with_binary_data(self):
        """Test converting message with binary data (should be base64 encoded)."""
        import base64
        binary_data = b'binary data here'
        msg = PresenceMessage(
            id='connection123:0:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.ENTER,
            data=binary_data
        )
        encoded = msg.to_encoded()
        assert encoded['data'] == base64.b64encode(binary_data).decode('ascii')
        assert encoded['encoding'] == 'base64'

    def test_to_encoded_with_bytearray_data(self):
        """Test converting message with bytearray data (should be base64 encoded)."""
        import base64
        binary_data = bytearray(b'bytearray data')
        msg = PresenceMessage(
            id='connection123:0:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.ENTER,
            data=binary_data
        )
        encoded = msg.to_encoded()
        assert encoded['data'] == base64.b64encode(binary_data).decode('ascii')
        assert encoded['encoding'] == 'base64'

    def test_to_encoded_with_existing_encoding(self):
        """Test that existing encoding is preserved and appended to."""
        msg = PresenceMessage(
            id='connection123:0:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.ENTER,
            data=b'test',
            encoding='utf-8'
        )
        encoded = msg.to_encoded()
        assert 'utf-8' in encoded['encoding']
        assert 'base64' in encoded['encoding']
        assert encoded['encoding'] == 'utf-8/base64'

    def test_to_encoded_binary_mode(self):
        """Test converting message in binary mode (no base64 encoding)."""
        binary_data = b'binary data'
        msg = PresenceMessage(
            id='connection123:0:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.ENTER,
            data=binary_data
        )
        encoded = msg.to_encoded(binary=True)
        assert encoded['data'] == binary_data
        assert 'encoding' not in encoded  # No base64 added in binary mode

    def test_from_encoded_array(self):
        """Test decoding array of presence messages."""
        encoded_array = [
            {
                'id': 'conn1:0:0',
                'action': PresenceAction.ENTER,
                'clientId': 'client1',
                'connectionId': 'conn1',
                'data': 'data1'
            },
            {
                'id': 'conn2:0:0',
                'action': PresenceAction.PRESENT,
                'clientId': 'client2',
                'connectionId': 'conn2',
                'data': 'data2'
            }
        ]
        messages = PresenceMessage.from_encoded_array(encoded_array)
        assert len(messages) == 2
        assert messages[0].client_id == 'client1'
        assert messages[1].client_id == 'client2'


class TestNewnessComparison(BaseAsyncTestCase):
    """Test newness comparison logic (RTP2b)."""

    def test_synthesized_message_newer_by_timestamp(self):
        """Test RTP2b1: synthesized messages compared by timestamp."""
        older = PresenceMessage(
            id='different:0:0',  # Synthesized (doesn't match connection_id)
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.LEAVE,
            timestamp=datetime(2024, 1, 1, 12, 0, 0)
        )
        newer = PresenceMessage(
            id='connection123:5:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.PRESENT,
            timestamp=datetime(2024, 1, 1, 12, 0, 1)
        )
        assert _is_newer(newer, older)
        assert not _is_newer(older, newer)

    def test_synthesized_equal_timestamp_incoming_wins(self):
        """Test RTP2b1a: equal timestamps, incoming is newer."""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        existing = PresenceMessage(
            id='different:0:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.LEAVE,
            timestamp=timestamp
        )
        incoming = PresenceMessage(
            id='other:0:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.LEAVE,
            timestamp=timestamp
        )
        # Incoming should be considered newer (>=)
        assert _is_newer(incoming, existing)

    def test_normal_message_newer_by_msg_serial(self):
        """Test RTP2b2: normal messages compared by msgSerial."""
        older = PresenceMessage(
            id='connection123:5:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.PRESENT,
            timestamp=datetime(2024, 1, 1, 12, 0, 0)
        )
        newer = PresenceMessage(
            id='connection123:10:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.PRESENT,
            timestamp=datetime(2024, 1, 1, 11, 0, 0)  # Earlier timestamp doesn't matter
        )
        assert _is_newer(newer, older)
        assert not _is_newer(older, newer)

    def test_normal_message_newer_by_index(self):
        """Test RTP2b2: when msgSerial equal, compare by index."""
        older = PresenceMessage(
            id='connection123:5:2',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        newer = PresenceMessage(
            id='connection123:5:3',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        assert _is_newer(newer, older)
        assert not _is_newer(older, newer)

    def test_normal_message_same_serial_and_index(self):
        """Test equal msgSerial and index - incoming is not newer."""
        msg1 = PresenceMessage(
            id='connection123:5:3',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        msg2 = PresenceMessage(
            id='connection123:5:3',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        # Index not greater, so not newer
        assert not _is_newer(msg2, msg1)


class TestPresenceMapBasicOperations(BaseAsyncTestCase):
    """Test basic PresenceMap operations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.presence_map = PresenceMap(
            member_key_fn=lambda msg: msg.member_key
        )
        yield

    def test_put_enter_message(self):
        """Test RTP2d: ENTER message stored as PRESENT."""
        msg = PresenceMessage(
            id='connection123:0:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.ENTER,
            data='test'
        )
        result = self.presence_map.put(msg)
        assert result is True

        stored = self.presence_map.get('connection123:client1')
        assert stored is not None
        assert stored.action == PresenceAction.PRESENT
        assert stored.client_id == 'client1'
        assert stored.data == 'test'

    def test_put_update_message(self):
        """Test RTP2d: UPDATE message stored as PRESENT."""
        msg = PresenceMessage(
            id='connection123:0:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.UPDATE,
            data='updated'
        )
        result = self.presence_map.put(msg)
        assert result is True

        stored = self.presence_map.get('connection123:client1')
        assert stored.action == PresenceAction.PRESENT

    def test_put_rejects_older_message(self):
        """Test RTP2a: older messages are rejected."""
        newer = PresenceMessage(
            id='connection123:10:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.ENTER
        )
        older = PresenceMessage(
            id='connection123:5:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.UPDATE
        )

        # Add newer first
        self.presence_map.put(newer)
        # Try to add older - should be rejected
        result = self.presence_map.put(older)
        assert result is False

        # Should still have the newer one
        stored = self.presence_map.get('connection123:client1')
        assert stored.parse_id()['msgSerial'] == 10

    def test_put_accepts_newer_message(self):
        """Test RTP2a: newer messages replace older ones."""
        older = PresenceMessage(
            id='connection123:5:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.ENTER,
            data='old'
        )
        newer = PresenceMessage(
            id='connection123:10:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.UPDATE,
            data='new'
        )

        self.presence_map.put(older)
        result = self.presence_map.put(newer)
        assert result is True

        stored = self.presence_map.get('connection123:client1')
        assert stored.data == 'new'
        assert stored.parse_id()['msgSerial'] == 10

    def test_remove_member(self):
        """Test RTP2h1: LEAVE removes member outside of sync."""
        enter = PresenceMessage(
            id='connection123:0:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.ENTER
        )
        leave = PresenceMessage(
            id='connection123:1:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.LEAVE
        )

        self.presence_map.put(enter)
        result = self.presence_map.remove(leave)
        assert result is True

        # Member should be removed
        assert self.presence_map.get('connection123:client1') is None

    def test_remove_rejects_older_leave(self):
        """Test RTP2h: LEAVE must pass newness check."""
        newer = PresenceMessage(
            id='connection123:10:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        older_leave = PresenceMessage(
            id='connection123:5:0',
            connection_id='connection123',
            client_id='client1',
            action=PresenceAction.LEAVE
        )

        self.presence_map.put(newer)
        result = self.presence_map.remove(older_leave)
        assert result is False

        # Member should still be present
        assert self.presence_map.get('connection123:client1') is not None

    def test_values_excludes_absent(self):
        """Test that values() excludes ABSENT members."""
        msg1 = PresenceMessage(
            id='conn1:0:0',
            connection_id='conn1',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        msg2 = PresenceMessage(
            id='conn2:0:0',
            connection_id='conn2',
            client_id='client2',
            action=PresenceAction.PRESENT
        )

        self.presence_map.put(msg1)
        self.presence_map.put(msg2)

        # Manually add an ABSENT member (happens during sync)
        absent = PresenceMessage(
            id='conn3:0:0',
            connection_id='conn3',
            client_id='client3',
            action=PresenceAction.ABSENT
        )
        self.presence_map._map[absent.member_key] = absent

        values = self.presence_map.values()
        assert len(values) == 2
        assert all(msg.action == PresenceAction.PRESENT for msg in values)

    def test_list_with_client_id_filter(self):
        """Test RTP11c2: list with clientId filter."""
        msg1 = PresenceMessage(
            id='conn1:0:0',
            connection_id='conn1',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        msg2 = PresenceMessage(
            id='conn2:0:0',
            connection_id='conn2',
            client_id='client2',
            action=PresenceAction.PRESENT
        )

        self.presence_map.put(msg1)
        self.presence_map.put(msg2)

        result = self.presence_map.list(client_id='client1')
        assert len(result) == 1
        assert result[0].client_id == 'client1'

    def test_list_with_connection_id_filter(self):
        """Test RTP11c3: list with connectionId filter."""
        msg1 = PresenceMessage(
            id='conn1:0:0',
            connection_id='conn1',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        msg2 = PresenceMessage(
            id='conn1:0:1',
            connection_id='conn1',
            client_id='client2',
            action=PresenceAction.PRESENT
        )
        msg3 = PresenceMessage(
            id='conn2:0:0',
            connection_id='conn2',
            client_id='client3',
            action=PresenceAction.PRESENT
        )

        self.presence_map.put(msg1)
        self.presence_map.put(msg2)
        self.presence_map.put(msg3)

        result = self.presence_map.list(connection_id='conn1')
        assert len(result) == 2
        assert all(msg.connection_id == 'conn1' for msg in result)

    def test_clear(self):
        """Test RTP5a: clear removes all members."""
        msg1 = PresenceMessage(
            id='conn1:0:0',
            connection_id='conn1',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        self.presence_map.put(msg1)
        self.presence_map.clear()

        assert len(self.presence_map.values()) == 0
        assert not self.presence_map.sync_in_progress


class TestPresenceMapSyncOperations(BaseAsyncTestCase):
    """Test SYNC operations (RTP18, RTP19)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        self.presence_map = PresenceMap(
            member_key_fn=lambda msg: msg.member_key
        )
        yield

    def test_start_sync(self):
        """Test RTP18: start_sync captures residual members."""
        msg1 = PresenceMessage(
            id='conn1:0:0',
            connection_id='conn1',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        msg2 = PresenceMessage(
            id='conn2:0:0',
            connection_id='conn2',
            client_id='client2',
            action=PresenceAction.PRESENT
        )

        self.presence_map.put(msg1)
        self.presence_map.put(msg2)

        self.presence_map.start_sync()
        assert self.presence_map.sync_in_progress is True
        assert self.presence_map._residual_members is not None
        assert len(self.presence_map._residual_members) == 2

    def test_put_during_sync_removes_from_residual(self):
        """Test that members seen during sync are removed from residual."""
        msg1 = PresenceMessage(
            id='conn1:0:0',
            connection_id='conn1',
            client_id='client1',
            action=PresenceAction.PRESENT
        )

        self.presence_map.put(msg1)
        self.presence_map.start_sync()

        # Update the same member during sync
        msg1_update = PresenceMessage(
            id='conn1:1:0',
            connection_id='conn1',
            client_id='client1',
            action=PresenceAction.PRESENT,
            data='updated'
        )
        self.presence_map.put(msg1_update)

        # Member should be removed from residual
        assert 'conn1:client1' not in self.presence_map._residual_members

    def test_remove_during_sync_marks_absent(self):
        """Test RTP2h2: LEAVE during sync marks member as ABSENT."""
        msg1 = PresenceMessage(
            id='conn1:0:0',
            connection_id='conn1',
            client_id='client1',
            action=PresenceAction.PRESENT
        )

        self.presence_map.put(msg1)
        self.presence_map.start_sync()

        leave = PresenceMessage(
            id='conn1:1:0',
            connection_id='conn1',
            client_id='client1',
            action=PresenceAction.LEAVE
        )
        result = self.presence_map.remove(leave)
        assert result is True

        # Should be marked ABSENT, not removed
        stored = self.presence_map.get('conn1:client1')
        assert stored is not None
        assert stored.action == PresenceAction.ABSENT

    def test_end_sync_removes_absent_members(self):
        """Test RTP2h2b: end_sync removes ABSENT members."""
        msg1 = PresenceMessage(
            id='conn1:0:0',
            connection_id='conn1',
            client_id='client1',
            action=PresenceAction.PRESENT
        )

        self.presence_map.put(msg1)
        self.presence_map.start_sync()

        leave = PresenceMessage(
            id='conn1:1:0',
            connection_id='conn1',
            client_id='client1',
            action=PresenceAction.LEAVE
        )
        self.presence_map.remove(leave)

        residual, absent = self.presence_map.end_sync()

        # Member should be removed after sync
        assert self.presence_map.get('conn1:client1') is None
        assert not self.presence_map.sync_in_progress

    def test_end_sync_returns_residual_members(self):
        """Test RTP19: end_sync returns residual members for leave synthesis."""
        msg1 = PresenceMessage(
            id='conn1:0:0',
            connection_id='conn1',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        msg2 = PresenceMessage(
            id='conn2:0:0',
            connection_id='conn2',
            client_id='client2',
            action=PresenceAction.PRESENT
        )

        # Add two members
        self.presence_map.put(msg1)
        self.presence_map.put(msg2)

        self.presence_map.start_sync()

        # Only see msg1 during sync
        msg1_update = PresenceMessage(
            id='conn1:1:0',
            connection_id='conn1',
            client_id='client1',
            action=PresenceAction.PRESENT
        )
        self.presence_map.put(msg1_update)

        # End sync - msg2 should be in residual
        residual, absent = self.presence_map.end_sync()

        assert len(residual) == 1
        assert residual[0].client_id == 'client2'

        # msg2 should be removed from map
        assert self.presence_map.get('conn2:client2') is None
        # msg1 should still be present
        assert self.presence_map.get('conn1:client1') is not None

    def test_start_sync_multiple_times(self):
        """Test that start_sync can be called multiple times during sync."""
        msg1 = PresenceMessage(
            id='conn1:0:0',
            connection_id='conn1',
            client_id='client1',
            action=PresenceAction.PRESENT
        )

        self.presence_map.put(msg1)
        self.presence_map.start_sync()

        initial_residual = self.presence_map._residual_members

        # Call start_sync again - should not reset residual
        self.presence_map.start_sync()
        assert self.presence_map._residual_members is initial_residual

    def test_clear_invokes_sync_callbacks(self):
        """
        Test that clear() invokes pending sync callbacks to prevent hanging.

        This ensures that if get() is waiting for sync and the channel
        transitions to DETACHED/FAILED, the waiting Future is resolved
        and the caller is not left blocked.
        """
        msg1 = PresenceMessage(
            id='conn1:0:0',
            connection_id='conn1',
            client_id='client1',
            action=PresenceAction.PRESENT
        )

        self.presence_map.put(msg1)
        self.presence_map.start_sync()

        # Register a callback as if _wait_for_sync() was called
        callback_invoked = False

        def sync_callback():
            nonlocal callback_invoked
            callback_invoked = True

        self.presence_map.wait_sync(sync_callback)

        # Clear should invoke the callback
        self.presence_map.clear()

        assert callback_invoked, "clear() should invoke pending sync callbacks"
        assert not self.presence_map.sync_in_progress
        assert len(self.presence_map.values()) == 0
