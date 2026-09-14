"""
RealtimePresence - Manages presence operations on a realtime channel.

This module implements presence functionality for realtime channels,
including enter/leave operations, presence state management, and SYNC handling.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.realtime.presencemap import PresenceMap
from ably.pubsub.types.channelstate import ChannelState, ChannelStateChange
from ably.pubsub.types.presence import PresenceAction, PresenceMessage
from ably.pubsub.util.eventemitter import EventEmitter
from ably.pubsub.util.exceptions import AblyException

if TYPE_CHECKING:
    from ably.pubsub.realtime.channel import RealtimeChannel

log = logging.getLogger(__name__)


def _get_client_id(presence: RealtimePresence) -> str | None:
    """Get the clientId for the current connection."""
    # Use auth.client_id if available (set after CONNECTED),
    # otherwise fall back to auth_options.client_id
    return presence.channel.ably.auth.client_id or presence.channel.ably.auth.auth_options.client_id


def _is_anonymous_or_wildcard(presence: RealtimePresence) -> bool:
    """Check if the client is anonymous or has wildcard clientId (RTP8j)."""
    realtime = presence.channel.ably
    client_id = _get_client_id(presence)

    # If not currently connected, we can't assume we're anonymous
    if realtime.connection.state != ConnectionState.CONNECTED:
        return False

    return not client_id or client_id == '*'


class RealtimePresence(EventEmitter):
    """
    Manages presence operations on a realtime channel.

    Enables clients to subscribe to presence events and to enter, update,
    and leave presence on a channel.

    Attributes
    ----------
    channel : RealtimeChannel
        The channel this presence object belongs to
    sync_complete : bool
        True if the initial SYNC operation has completed (RTP13)
    """

    def __init__(self, channel: RealtimeChannel):
        """
        Initialize a new RealtimePresence instance.

        Args:
            channel: The RealtimeChannel this presence belongs to
        """
        super().__init__()
        self.channel = channel
        self.sync_complete = False

        # RTP2: Main presence map keyed by memberKey (connectionId:clientId)
        self.members = PresenceMap(
            member_key_fn=lambda msg: msg.member_key
        )

        # RTP17: Internal presence map for own members, keyed by clientId only
        self._my_members = PresenceMap(
            member_key_fn=lambda msg: msg.client_id
        )

        # EventEmitter for presence subscriptions
        self._subscriptions = EventEmitter()

        # RTP16: Queue for pending presence messages
        self._pending_presence: list[dict] = []

    async def enter(self, data: Any = None) -> None:
        """
        Enter this client into the channel's presence (RTP8).

        Args:
            data: Optional data to associate with this presence member

        Raises:
            AblyException: If clientId is not specified or channel state prevents entering
        """
        # RTP8j: Check for anonymous or wildcard client
        if _is_anonymous_or_wildcard(self):
            raise AblyException(
                'clientId must be specified to enter a presence channel',
                400, 40012
            )

        return await self._enter_or_update_client(None, None, data, PresenceAction.ENTER)

    async def update(self, data: Any = None) -> None:
        """
        Update this client's presence data (RTP9).

        If the client is not already entered, this will enter the client.

        Args:
            data: Optional data to associate with this presence member

        Raises:
            AblyException: If clientId is not specified or channel state prevents updating
        """
        # RTP9e: In all other ways, identical to enter
        if _is_anonymous_or_wildcard(self):
            raise AblyException(
                'clientId must be specified to update presence data',
                400, 40012
            )

        return await self._enter_or_update_client(None, None, data, PresenceAction.UPDATE)

    async def leave(self, data: Any = None) -> None:
        """
        Leave this client from the channel's presence (RTP10).

        Args:
            data: Optional data to send with the leave message

        Raises:
            AblyException: If clientId is not specified or channel state prevents leaving
        """
        if _is_anonymous_or_wildcard(self):
            raise AblyException(
                'clientId must have been specified to enter or leave a presence channel',
                400, 40012
            )

        return await self._leave_client(None, data)

    async def enter_client(self, client_id: str, data: Any = None) -> None:
        """
        Enter into presence on behalf of another clientId (RTP14).

        This allows a single client with suitable permissions to register
        presence on behalf of multiple clients.

        Args:
            client_id: The clientId to enter
            data: Optional data to associate with this presence member

        Raises:
            AblyException: If channel state prevents entering or clientId mismatch
        """
        return await self._enter_or_update_client(None, client_id, data, PresenceAction.ENTER)

    async def update_client(self, client_id: str, data: Any = None) -> None:
        """
        Update presence on behalf of another clientId (RTP15).

        Args:
            client_id: The clientId to update
            data: Optional data to associate with this presence member

        Raises:
            AblyException: If channel state prevents updating or clientId mismatch
        """
        return await self._enter_or_update_client(None, client_id, data, PresenceAction.UPDATE)

    async def leave_client(self, client_id: str, data: Any = None) -> None:
        """
        Leave presence on behalf of another clientId (RTP15).

        Args:
            client_id: The clientId to leave
            data: Optional data to send with the leave message

        Raises:
            AblyException: If channel state prevents leaving or clientId mismatch
        """
        return await self._leave_client(client_id, data)

    async def _enter_or_update_client(
        self,
        id: str | None,
        client_id: str | None,
        data: Any,
        action: int
    ) -> None:
        """
        Internal method to handle enter/update operations.

        Args:
            id: Optional presence message id
            client_id: Optional clientId (if None, uses connection's clientId)
            data: Optional data payload
            action: The presence action (ENTER or UPDATE)

        Raises:
            AblyException: If connection/channel state prevents operation or clientId mismatch
        """
        channel = self.channel

        # Check connection state
        if channel.ably.connection.state not in [
            ConnectionState.CONNECTING,
            ConnectionState.CONNECTED,
            ConnectionState.DISCONNECTED
        ]:
            raise AblyException(
                f'Unable to {PresenceAction._action_name(action).lower()} presence channel; '
                f'connection state = {channel.ably.connection.state}',
                400, 90001
            )

        action_name = PresenceAction._action_name(action).lower()

        log.info(
            f'RealtimePresence.{action_name}(): '
            f'channel = {channel.name}, '
            f'clientId = {client_id or "(implicit) " + str(_get_client_id(self))}'
        )

        # RTP15f: Check clientId mismatch (wildcard '*' is allowed to enter on behalf of any client)
        if client_id is not None and not self.channel.ably.auth.can_assume_client_id(client_id):
            raise AblyException(
                f'Unable to {action_name} presence channel with clientId {client_id} '
                f'as it does not match the current clientId {self.channel.ably.auth.client_id}',
                400, 40012
            )

        # RTP8c: Use connection's clientId if not explicitly provided
        effective_client_id = client_id if client_id is not None else _get_client_id(self)

        # Create presence message
        presence_msg = PresenceMessage(
            id=id,
            action=action,
            client_id=effective_client_id,
            data=data
        )

        # Encrypt if cipher is configured
        if channel.cipher:
            presence_msg.encrypt(channel.cipher)

        # Convert to wire format
        wire_msg = presence_msg.to_encoded(binary=channel.ably.options.use_binary_protocol)

        # RTP8d/RTP8g: Handle based on channel state
        if channel.state == ChannelState.ATTACHED:
            # Send immediately
            return await self._send_presence([wire_msg])
        elif channel.state in [ChannelState.INITIALIZED, ChannelState.DETACHED]:
            # RTP8d: Implicitly attach
            asyncio.create_task(channel.attach())
            # Queue the message
            return await self._queue_presence(wire_msg)
        elif channel.state == ChannelState.ATTACHING:
            # Queue the message
            return await self._queue_presence(wire_msg)
        else:
            # RTP8g: DETACHED, FAILED, etc.
            raise AblyException(
                f'Unable to {action_name} presence channel while in {channel.state} state',
                400, 90001
            )

    async def _leave_client(self, client_id: str | None, data: Any = None) -> None:
        """
        Internal method to handle leave operations.

        Args:
            client_id: Optional clientId (if None, uses connection's clientId)
            data: Optional data payload

        Raises:
            AblyException: If connection/channel state prevents operation or clientId mismatch
        """
        channel = self.channel

        # Check connection state
        if channel.ably.connection.state not in [
            ConnectionState.CONNECTING,
            ConnectionState.CONNECTED,
            ConnectionState.DISCONNECTED
        ]:
            raise AblyException(
                f'Unable to leave presence channel; '
                f'connection state = {channel.ably.connection.state}',
                400, 90001
            )

        log.info(
            f'RealtimePresence.leave(): '
            f'channel = {channel.name}, '
            f'clientId = {client_id or _get_client_id(self)}'
        )

        # RTP15f: Check clientId mismatch (wildcard '*' is allowed to leave on behalf of any client)
        if client_id is not None and not self.channel.ably.auth.can_assume_client_id(client_id):
            raise AblyException(
                f'Unable to leave presence channel with clientId {client_id} '
                f'as it does not match the current clientId {self.channel.ably.auth.client_id}',
                400, 40012
            )

        # RTP10c: Use connection's clientId if not explicitly provided
        effective_client_id = client_id if client_id is not None else _get_client_id(self)

        # Create presence message
        presence_msg = PresenceMessage(
            action=PresenceAction.LEAVE,
            client_id=effective_client_id,
            data=data
        )

        # Encrypt if cipher is configured
        if channel.cipher:
            presence_msg.encrypt(channel.cipher)

        # Convert to wire format
        wire_msg = presence_msg.to_encoded(binary=channel.ably.options.use_binary_protocol)

        # RTP10e: Handle based on channel state
        if channel.state == ChannelState.ATTACHED:
            # Send immediately
            return await self._send_presence([wire_msg])
        elif channel.state == ChannelState.ATTACHING:
            # Queue the message
            return await self._queue_presence(wire_msg)
        elif channel.state in [ChannelState.INITIALIZED, ChannelState.FAILED]:
            # RTP10e: Don't attach just to leave
            raise AblyException(
                'Unable to leave presence channel (incompatible state)',
                400, 90001
            )
        else:
            raise AblyException(
                f'Unable to leave presence channel while in {channel.state} state',
                400, 90001
            )

    async def _send_presence(self, presence_messages: list[dict]) -> None:
        """
        Send presence messages to the server.

        Args:
            presence_messages: List of encoded presence messages to send
        """
        from ably.pubsub.transport.websockettransport import ProtocolMessageAction

        protocol_msg = {
            'action': ProtocolMessageAction.PRESENCE,
            'channel': self.channel.name,
            'presence': presence_messages
        }

        await self.channel.ably.connection.connection_manager.send_protocol_message(protocol_msg)

    async def _queue_presence(self, wire_msg: dict) -> None:
        """
        Queue a presence message to be sent when channel attaches.

        Args:
            wire_msg: Encoded presence message to queue
        """
        future = asyncio.Future()

        self._pending_presence.append({
            'presence': wire_msg,
            'future': future
        })

        return await future

    async def get(
        self,
        wait_for_sync: bool = True,
        client_id: str | None = None,
        connection_id: str | None = None
    ) -> list[PresenceMessage]:
        """
        Get the current presence members on this channel (RTP11).

        Args:
            wait_for_sync: If True, waits for SYNC to complete before returning (default: True)
            client_id: Optional filter by clientId
            connection_id: Optional filter by connectionId

        Returns:
            List of current presence members

        Raises:
            AblyException: If channel state prevents getting presence
        """
        # RTP11d: Handle SUSPENDED state
        if self.channel.state == ChannelState.SUSPENDED:
            if wait_for_sync:
                raise AblyException(
                    'Presence state is out of sync due to channel being in the SUSPENDED state',
                    400, 91005
                )
            else:
                # Return current members without waiting
                return self.members.list(client_id=client_id, connection_id=connection_id)

        # RTP11b: Implicitly attach if needed
        if self.channel.state in [ChannelState.INITIALIZED, ChannelState.DETACHED]:
            await self.channel.attach()
        elif self.channel.state in [ChannelState.DETACHING, ChannelState.FAILED]:
            raise AblyException(
                f'Unable to get presence; channel state = {self.channel.state}',
                400, 90001
            )

        # If channel is still attaching, wait for it to become ATTACHED
        if self.channel.state == ChannelState.ATTACHING:
            # Wait for channel to reach ATTACHED state
            state_change = await self.channel._RealtimeChannel__internal_state_emitter.once_async()
            if state_change.current != ChannelState.ATTACHED:
                raise AblyException(
                    f'Unable to get presence; channel state = {state_change.current}',
                    400, 90001
                )

        # Wait for sync if requested and a sync is actually in progress
        # If sync_complete is already True OR no sync is in progress, don't wait
        if wait_for_sync and not self.sync_complete and self.members.sync_in_progress:
            await self._wait_for_sync()

        return self.members.list(client_id=client_id, connection_id=connection_id)

    async def _wait_for_sync(self) -> None:
        """Wait for presence SYNC to complete."""
        if self.sync_complete:
            return

        # Use the PresenceMap's wait_sync mechanism
        future = asyncio.Future()

        def on_sync_complete():
            if not future.done():
                future.set_result(None)

        self.members.wait_sync(on_sync_complete)

        # Wait for the sync to complete
        await future

    async def subscribe(self, *args) -> None:
        """
        Subscribe to presence events on this channel (RTP6).

        Args:
            *args: Either (listener) or (event, listener) or (events, listener)
                - listener: Callback for all presence events
                - event: Specific event name ('enter', 'leave', 'update', 'present')
                - events: List of event names
                - listener: Callback for specified events

        Raises:
            AblyException: If channel state prevents subscription
        """
        # Parse arguments: similar to channel subscribe
        if len(args) == 1:
            # subscribe(listener)
            listener = args[0]
            self._subscriptions.on(listener)
        elif len(args) == 2:
            # subscribe(event, listener)
            event = args[0]
            listener = args[1]
            self._subscriptions.on(event, listener)
        else:
            raise ValueError('Invalid subscribe arguments')

        # RTP6d: Implicitly attach
        if self.channel.state in [ChannelState.INITIALIZED, ChannelState.DETACHED, ChannelState.DETACHING]:
            await self.channel.attach()

    def unsubscribe(self, *args) -> None:
        """
        Unsubscribe from presence events on this channel (RTP7).

        Args:
            *args: Either (), (listener), or (event, listener)
                - (): Unsubscribe all listeners
                - listener: Unsubscribe this specific listener
                - event, listener: Unsubscribe listener for specific event
        """
        if len(args) == 0:
            # unsubscribe() - remove all
            self._subscriptions.off()
        elif len(args) == 1:
            # unsubscribe(listener)
            listener = args[0]
            self._subscriptions.off(listener)
        elif len(args) == 2:
            # unsubscribe(event, listener)
            event = args[0]
            listener = args[1]
            self._subscriptions.off(event, listener)
        else:
            raise ValueError('Invalid unsubscribe arguments')

    def set_presence(
        self,
        presence_set: list[PresenceMessage],
        is_sync: bool,
        sync_channel_serial: str | None = None
    ) -> None:
        """
        Process incoming presence messages from the server (Phase 3 - RTP2, RTP18).

        Args:
            presence_set: List of presence messages received
            is_sync: True if this is part of a SYNC operation
            sync_channel_serial: Optional sync cursor for tracking sync progress
        """
        log.info(
            f'RealtimePresence.set_presence(): '
            f'received presence for {len(presence_set)} members; '
            f'syncChannelSerial = {sync_channel_serial}'
        )

        conn_id = self.channel.ably.connection.connection_manager.connection_id
        broadcast_messages = []

        # RTP18: Handle SYNC
        if is_sync:
            self.members.start_sync()
            # Parse sync cursor if present
            if sync_channel_serial:
                # Format: <sync_seq_id>:<cursor>
                parts = sync_channel_serial.split(':', 1)
                sync_cursor = parts[1] if len(parts) > 1 else None
            else:
                sync_cursor = None
        else:
            sync_cursor = None

        # Process each presence message
        for presence in presence_set:
            if presence.action == PresenceAction.LEAVE:
                # RTP2h: Handle LEAVE
                if self.members.remove(presence):
                    broadcast_messages.append(presence)

                # RTP17b: Update internal presence map (not synthesized)
                if presence.connection_id == conn_id and not presence.is_synthesized():
                    self._my_members.remove(presence)

            elif presence.action in (
                PresenceAction.ENTER,
                PresenceAction.PRESENT,
                PresenceAction.UPDATE
            ):
                # RTP2d: Handle ENTER/PRESENT/UPDATE
                if self.members.put(presence):
                    broadcast_messages.append(presence)

                # RTP17b: Update internal presence map
                if presence.connection_id == conn_id:
                    self._my_members.put(presence)

        # RTP18b/RTP18c: End sync if cursor is empty or no channelSerial
        if is_sync and (not sync_channel_serial or not sync_cursor):
            residual, absent = self.members.end_sync()
            self.sync_complete = True

            # RTP19: Emit synthesized leave events for residual members
            for member in residual + absent:
                synthesized_leave = PresenceMessage(
                    action=PresenceAction.LEAVE,
                    client_id=member.client_id,
                    connection_id=member.connection_id,
                    data=member.data,
                    encoding=member.encoding,
                    timestamp=datetime.now(timezone.utc)
                )
                broadcast_messages.append(synthesized_leave)

        # Broadcast messages to subscribers
        for presence in broadcast_messages:
            action_name = PresenceAction._action_name(presence.action).lower()
            self._subscriptions._emit(action_name, presence)

    def on_attached(self, has_presence: bool = False) -> None:
        """
        Handle channel ATTACHED event (RTP5b).

        Args:
            has_presence: True if server will send SYNC
        """
        log.info(
            f'RealtimePresence.on_attached(): '
            f'channel = {self.channel.name}, hasPresence = {has_presence}'
        )

        # RTP1: Handle presence sync flag
        if has_presence:
            self.members.start_sync()
            self.sync_complete = False
        else:
            # RTP19a: No presence on channel, synthesize leaves for existing members
            self._synthesize_leaves(self.members.values())
            self.members.clear()
            self.sync_complete = True
            # Also end sync in case one was started
            if self.members.sync_in_progress:
                self.members.end_sync()

        # RTP17i: Re-enter own members
        self._ensure_my_members_present()

        # RTP5b: Send pending presence messages
        asyncio.create_task(self._send_pending_presence())

    def _ensure_my_members_present(self) -> None:
        """
        Re-enter own presence members after attach (RTP17g).
        """
        conn_id = self.channel.ably.connection.connection_manager.connection_id

        for _client_id, entry in list(self._my_members._map.items()):
            log.info(
                f'RealtimePresence._ensure_my_members_present(): '
                f'auto-reentering clientId "{entry.client_id}"'
            )

            # RTP17g1: Suppress id if connectionId has changed
            msg_id = entry.id if entry.connection_id == conn_id else None

            # Create task to re-enter - use default args to bind loop variables
            asyncio.create_task(
                self._reenter_member(msg_id, entry.client_id, entry.data)
            )

    async def _reenter_member(self, msg_id: str | None, client_id: str, data: Any) -> None:
        """
        Helper method to re-enter a member (RTP17g).

        Args:
            msg_id: Optional message ID
            client_id: The client ID to re-enter
            data: The presence data
        """
        try:
            await self._enter_or_update_client(
                msg_id,
                client_id,
                data,
                PresenceAction.ENTER
            )
        except AblyException as e:
            log.error(
                f'RealtimePresence._reenter_member(): '
                f'auto-reenter failed: {e}'
            )
            # RTP17e: Emit update event with error
            state_change = ChannelStateChange(
                previous=self.channel.state,
                current=self.channel.state,
                resumed=False,
                reason=e
            )
            self.channel._emit("update", state_change)

    async def _send_pending_presence(self) -> None:
        """
        Send pending presence messages after channel attaches (RTP5b).
        """
        if not self._pending_presence:
            return

        log.info(
            f'RealtimePresence._send_pending_presence(): '
            f'sending {len(self._pending_presence)} queued messages'
        )

        pending = self._pending_presence
        self._pending_presence = []

        # Send all pending messages
        presence_array = [item['presence'] for item in pending]

        try:
            await self._send_presence(presence_array)
            # Resolve all futures AFTER send completes
            for item in pending:
                if not item['future'].done():
                    item['future'].set_result(None)
        except Exception as e:
            # Reject all futures
            for item in pending:
                if not item['future'].done():
                    item['future'].set_exception(e)

    def _synthesize_leaves(self, members: list[PresenceMessage]) -> None:
        """
        Emit synthesized leave events for members (RTP19, RTP19a).

        Args:
            members: List of members to synthesize leaves for
        """
        for member in members:
            synthesized_leave = PresenceMessage(
                action=PresenceAction.LEAVE,
                client_id=member.client_id,
                connection_id=member.connection_id,
                data=member.data,
                encoding=member.encoding,
                timestamp=datetime.now(timezone.utc)
            )
            self._subscriptions._emit('leave', synthesized_leave)

    def act_on_channel_state(
        self,
        state: ChannelState,
        has_presence: bool = False,
        error: AblyException | None = None
    ) -> None:
        """
        React to channel state changes (RTP5).

        Args:
            state: The new channel state
            has_presence: Whether the channel has presence (for ATTACHED)
            error: Optional error associated with state change
        """
        if state == ChannelState.ATTACHED:
            self.on_attached(has_presence)
        elif state in (ChannelState.DETACHED, ChannelState.FAILED):
            # RTP5a: Clear maps and fail pending
            self._my_members.clear()
            self.members.clear()
            self.sync_complete = False
            self._fail_pending_presence(error)
        elif state == ChannelState.SUSPENDED:
            # RTP5f: Fail pending but keep members, reset sync state
            self.sync_complete = False  # Sync state is no longer valid
            self._fail_pending_presence(error)

    def _fail_pending_presence(self, error: AblyException | None = None) -> None:
        """
        Fail all pending presence messages.

        Args:
            error: The error to reject with
        """
        if not self._pending_presence:
            return

        log.info(
            f'RealtimePresence._fail_pending_presence(): '
            f'failing {len(self._pending_presence)} queued messages'
        )

        pending = self._pending_presence
        self._pending_presence = []

        exception = error or AblyException('Presence operation failed', 400, 90001)

        for item in pending:
            if not item['future'].done():
                item['future'].set_exception(exception)


# Helper for PresenceAction to convert action to string
def _action_name_impl(action: int) -> str:
    """Convert presence action to string name."""
    names = {
        PresenceAction.ABSENT: 'absent',
        PresenceAction.PRESENT: 'present',
        PresenceAction.ENTER: 'enter',
        PresenceAction.LEAVE: 'leave',
        PresenceAction.UPDATE: 'update',
    }
    return names.get(action, f'unknown({action})')


# Monkey-patch the helper onto PresenceAction
PresenceAction._action_name = staticmethod(_action_name_impl)
