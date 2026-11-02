"""
PresenceMap - Manages the state of presence members on a channel.

This module implements RTP2 presence map requirements from the Ably specification.
"""

import logging
from typing import Callable, Dict, List, Optional, Tuple

from ably.pubsub.types.presence import PresenceAction, PresenceMessage

logger = logging.getLogger(__name__)


def _is_newer(item: PresenceMessage, existing: PresenceMessage) -> bool:
    """
    Compare two presence messages for newness (RTP2b).

    RTP2b1: If either presence message has a connectionId which is not an initial
    substring of its id, compare them by timestamp numerically. This will be the
    case when one of them is a 'synthesized leave' event.

    RTP2b1a: If the timestamps compare equal, the newly-incoming message is
    considered newer than the existing one.

    RTP2b2: Else split the id of both presence messages (format: connid:msgSerial:index)
    and compare them first by msgSerial numerically, then by index numerically,
    larger being newer in both cases.

    Args:
        item: The incoming presence message
        existing: The existing presence message in the map

    Returns:
        True if item is newer than existing, False otherwise

    Raises:
        ValueError: If message ids cannot be parsed for comparison
    """
    # RTP2b1: if either is synthesized, compare by timestamp
    if item.is_synthesized() or existing.is_synthesized():
        # RTP2b1a: if equal, prefer the newly-arrived one (item)
        if item.timestamp is None and existing.timestamp is None:
            return True
        if item.timestamp is None:
            return False
        if existing.timestamp is None:
            return True
        return item.timestamp >= existing.timestamp

    # RTP2b2: compare by msgSerial and index
    # parse_id will raise ValueError if id format is invalid
    item_parts = item.parse_id()
    existing_parts = existing.parse_id()

    if item_parts['msgSerial'] == existing_parts['msgSerial']:
        return item_parts['index'] > existing_parts['index']
    else:
        return item_parts['msgSerial'] > existing_parts['msgSerial']


class PresenceMap:
    """
    Manages the state of presence members on a channel.

    Maintains a map of members keyed by memberKey (connectionId:clientId).
    Handles newness comparison, SYNC operations, and member filtering.

    Implements RTP2 specification requirements.
    """

    def __init__(
        self,
        member_key_fn: Callable[[PresenceMessage], str],
        is_newer_fn: Optional[Callable[[PresenceMessage, PresenceMessage], bool]] = None,
        logger_instance: Optional[logging.Logger] = None
    ):
        """
        Initialize a new PresenceMap.

        Args:
            member_key_fn: Function to extract member key from a PresenceMessage
            is_newer_fn: Optional custom function for newness comparison (default: _is_newer)
            logger_instance: Optional logger instance (default: module logger)
        """
        self._map: Dict[str, PresenceMessage] = {}
        self._residual_members: Optional[Dict[str, PresenceMessage]] = None
        self._sync_in_progress = False
        self._member_key_fn = member_key_fn
        self._is_newer_fn = is_newer_fn or _is_newer
        self._logger = logger_instance or logger
        self._sync_complete_callbacks: List[Callable[[], None]] = []

    @property
    def sync_in_progress(self) -> bool:
        """Returns True if a SYNC operation is currently in progress."""
        return self._sync_in_progress

    def get(self, key: str) -> Optional[PresenceMessage]:
        """
        Get a presence member by key.

        Args:
            key: The member key (connectionId:clientId)

        Returns:
            The PresenceMessage if found, None otherwise
        """
        return self._map.get(key)

    def put(self, item: PresenceMessage) -> bool:
        """
        Add or update a presence member (RTP2d).

        For ENTER, UPDATE, or PRESENT actions, the message is stored in the map
        with action set to PRESENT (if it passes the newness check).

        Args:
            item: The presence message to add/update

        Returns:
            True if the item was added/updated, False if rejected due to newness check
        """
        # RTP2d: ENTER, UPDATE, PRESENT all get stored as PRESENT
        if item.action in (PresenceAction.ENTER, PresenceAction.UPDATE, PresenceAction.PRESENT):
            # Create a copy with action set to PRESENT
            item_to_store = PresenceMessage(
                id=item.id,
                action=PresenceAction.PRESENT,
                client_id=item.client_id,
                connection_id=item.connection_id,
                data=item.data,
                encoding=item.encoding,
                timestamp=item.timestamp,
                extras=item.extras
            )
        else:
            item_to_store = item

        key = self._member_key_fn(item_to_store)
        if not key:
            self._logger.warning("PresenceMap.put: item has no member key, ignoring")
            return False

        # If we're in a sync, mark this member as seen (remove from residual)
        if self._residual_members is not None and key in self._residual_members:
            del self._residual_members[key]

        # Check newness against existing member
        existing = self._map.get(key)
        if existing and not self._is_newer_fn(item_to_store, existing):
            self._logger.debug(f"PresenceMap.put: incoming message for {key} is not newer, ignoring")
            return False

        self._map[key] = item_to_store
        self._logger.debug(f"PresenceMap.put: added/updated member {key}")
        return True

    def remove(self, item: PresenceMessage) -> bool:
        """
        Remove a presence member (RTP2h).

        During a SYNC, the member is marked as ABSENT rather than removed.
        Outside of SYNC, the member is removed from the map.

        Args:
            item: The presence message with LEAVE action

        Returns:
            True if a member was removed/marked absent, False if no action taken
        """
        key = self._member_key_fn(item)
        if not key:
            return False

        existing = self._map.get(key)
        if not existing:
            return False

        # Check newness (RTP2h requires newness check)
        if not self._is_newer_fn(item, existing):
            self._logger.debug(f"PresenceMap.remove: incoming message for {key} is not newer, ignoring")
            return False

        # RTP2h2: During SYNC, mark as ABSENT instead of removing
        if self._sync_in_progress:
            absent_item = PresenceMessage(
                id=item.id,
                action=PresenceAction.ABSENT,
                client_id=item.client_id,
                connection_id=item.connection_id,
                data=item.data,
                encoding=item.encoding,
                timestamp=item.timestamp,
                extras=item.extras
            )
            self._map[key] = absent_item
            self._logger.debug(f"PresenceMap.remove: marked member {key} as ABSENT (sync in progress)")
        else:
            # RTP2h1: Outside of SYNC, remove the member
            del self._map[key]
            self._logger.debug(f"PresenceMap.remove: removed member {key}")

        return True

    def values(self) -> List[PresenceMessage]:
        """
        Get all presence members (excluding ABSENT members).

        Returns:
            List of all PRESENT members
        """
        return [
            msg for msg in self._map.values()
            if msg.action != PresenceAction.ABSENT
        ]

    def list(
        self,
        client_id: Optional[str] = None,
        connection_id: Optional[str] = None
    ) -> List[PresenceMessage]:
        """
        Get presence members with optional filtering (RTP11).

        Args:
            client_id: Optional filter by client ID
            connection_id: Optional filter by connection ID

        Returns:
            List of matching PRESENT members
        """
        result = []
        for msg in self._map.values():
            # Skip ABSENT members
            if msg.action == PresenceAction.ABSENT:
                continue

            # Apply filters
            if client_id and msg.client_id != client_id:
                continue
            if connection_id and msg.connection_id != connection_id:
                continue

            result.append(msg)

        return result

    def start_sync(self) -> None:
        """
        Start a SYNC operation (RTP18).

        Captures current members as residual members to track which ones
        are not seen during the sync.
        """
        self._logger.info(f"PresenceMap.start_sync: starting sync (in_progress={self._sync_in_progress})")

        # May be called multiple times while a sync is in progress
        if not self._sync_in_progress:
            # Copy current map as residual members
            self._residual_members = dict(self._map)
            self._sync_in_progress = True
            self._logger.debug(f"PresenceMap.start_sync: captured {len(self._residual_members)} residual members")

    def end_sync(self) -> Tuple[List[PresenceMessage], List[PresenceMessage]]:
        """
        End a SYNC operation (RTP18, RTP19).

        Removes ABSENT members and returns lists of members that should have
        synthesized leave events emitted.

        Returns:
            Tuple of (residual_members, absent_members) that need LEAVE events
        """
        self._logger.info(f"PresenceMap.end_sync: ending sync (in_progress={self._sync_in_progress})")

        residual_list: List[PresenceMessage] = []
        absent_list: List[PresenceMessage] = []

        if self._sync_in_progress:
            # Collect ABSENT members and remove them from map (RTP2h2b)
            keys_to_remove = []
            for key, msg in self._map.items():
                if msg.action == PresenceAction.ABSENT:
                    absent_list.append(msg)
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._map[key]

            # Collect residual members (members present at start but not seen during sync)
            # These need synthesized LEAVE events (RTP19)
            if self._residual_members:
                residual_list = list(self._residual_members.values())
                # Remove residual members from map
                for key in self._residual_members.keys():
                    if key in self._map:
                        del self._map[key]

            self._residual_members = None
            self._sync_in_progress = False
            self._logger.debug(
                f"PresenceMap.end_sync: removed {len(absent_list)} absent members, "
                f"{len(residual_list)} residual members"
            )

            # Notify callbacks that sync is complete
            for callback in self._sync_complete_callbacks:
                try:
                    callback()
                except Exception as e:
                    self._logger.error(f"Error in sync complete callback: {e}")
            self._sync_complete_callbacks.clear()

        return residual_list, absent_list

    def wait_sync(self, callback: Callable[[], None]) -> None:
        """
        Wait for SYNC to complete, calling callback when done.

        If sync is not in progress, callback is called immediately.

        Args:
            callback: Function to call when sync completes
        """
        if not self._sync_in_progress:
            callback()
        else:
            self._sync_complete_callbacks.append(callback)

    def clear(self) -> None:
        """
        Clear all members and reset sync state.

        Used when channel enters DETACHED or FAILED state (RTP5a).
        Invokes any pending sync callbacks before clearing to ensure
        waiting Futures are resolved and callers are not left blocked.
        """
        # Notify any callbacks waiting for sync to complete
        # This ensures Futures created by _wait_for_sync() are resolved
        for callback in self._sync_complete_callbacks:
            try:
                callback()
            except Exception as e:
                self._logger.error(f"Error in sync complete callback during clear: {e}")

        self._map.clear()
        self._residual_members = None
        self._sync_in_progress = False
        self._sync_complete_callbacks.clear()
        self._logger.debug("PresenceMap.clear: cleared all members")
