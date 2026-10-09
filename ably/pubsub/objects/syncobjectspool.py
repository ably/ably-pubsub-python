"""The object states accumulated during an objects sync sequence (RTO5f)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ably.pubsub.objects.objectmessage import ObjectMessage

log = logging.getLogger(__name__)


class SyncObjectsPool:
    """RTO5f: one `ObjectMessage` per object id, received over OBJECT_SYNC and not yet applied.

    A partial map state for an id already held is merged into it (RTO5f2).
    """

    def __init__(self):
        self.entries: dict[str, ObjectMessage] = {}

    def apply_object_sync_messages(self, object_messages: list[ObjectMessage]) -> None:
        """RTO5f: stores each message with an `object`, merging partial map states (RTO5f2a) and
        skipping messages with neither `map` nor `counter` (RTO5f3) and partial counter states
        (RTO5f2b)."""
        for object_message in object_messages:
            object_state = object_message.object
            if object_state is None:
                # RTO5d: only this message is skipped, so the rest of the sequence still applies
                log.warning(f'SyncObjectsPool.apply_object_sync_messages(): skipping an OBJECT_SYNC message '
                            f'with no object; message id={object_message.id}')
                continue

            if object_state.map is None and object_state.counter is None:
                # RTO5f3
                log.warning(f'SyncObjectsPool.apply_object_sync_messages(): skipping an OBJECT_SYNC message '
                            f'with an unsupported object type; object_id={object_state.object_id}, '
                            f'message id={object_message.id}')
                continue

            existing = self.entries.get(object_state.object_id)
            if existing is None:
                self.entries[object_state.object_id] = object_message  # RTO5f1
                continue

            # RTO5f2: a partial state of an object split across several OBJECT_SYNC messages
            if object_state.map is not None:
                self._merge_partial_map_state(existing, object_message)  # RTO5f2a
            else:
                # RTO5f2b
                log.error(f'SyncObjectsPool.apply_object_sync_messages(): skipping an unexpected partial '
                          f'state for a counter; object_id={object_state.object_id}, '
                          f'message id={object_message.id}')

    def clear(self) -> None:
        """RTO5a2a, RTO5c4, RTO27a2: discards every stored message."""
        self.entries.clear()

    def _merge_partial_map_state(self, existing: ObjectMessage, object_message: ObjectMessage) -> None:
        """RTO5f2a: merges the partial map state in `object_message` into the stored `existing`."""
        object_state = object_message.object
        if object_state.tombstone:
            self.entries[object_state.object_id] = object_message  # RTO5f2a1
            return

        existing_map = existing.object.map
        if existing_map is None:
            log.error(f'SyncObjectsPool.apply_object_sync_messages(): skipping a partial map state for an '
                      f'object first received as a counter; object_id={object_state.object_id}, '
                      f'message id={object_message.id}')
            return

        # RTO5f2a2: no two partial states of one map carry the same key
        if existing_map.entries is None:
            existing_map.entries = {}
        existing_map.entries.update(object_state.map.entries or {})

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, object_id: object) -> bool:
        return object_id in self.entries
