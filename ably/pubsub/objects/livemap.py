"""The last-write-wins map CRDT (RTLM*)."""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, Any

from ably.pubsub.objects.enums import ObjectsOperationSource
from ably.pubsub.objects.liveobject import MAP_KEY_REMOVED, MAP_KEY_UPDATED, LiveMapUpdate, LiveObject
from ably.pubsub.objects.objectmessage import (
    MapRemove,
    MapSet,
    ObjectData,
    ObjectMessage,
    ObjectOperation,
    ObjectOperationAction,
    ObjectsMapEntry,
    ObjectsMapSemantics,
)
from ably.pubsub.objects.valuetypes import LiveCounter, LiveMap, evaluate, primitive_to_object_data, validate_key
from ably.pubsub.util.clock import Clock
from ably.pubsub.util.exceptions import AblyException

if TYPE_CHECKING:
    from ably.pubsub.objects.objectspool import ObjectsPool
    from ably.pubsub.objects.realtimeobject import RealtimeObject
    from ably.pubsub.objects.valuetypes import LiveMapValue

log = logging.getLogger(__name__)


class InternalLiveMap(LiveObject):
    """RTLM1: a map of `ObjectsMapEntry` values by key, with per-entry last-write-wins (RTLM3).

    A new map has empty `data` and no `clear_timeserial` (RTLM4). A value read from the
    map is a primitive, an `InternalLiveMap` or `InternalLiveCounter` looked up in `pool`,
    or None.
    """

    _update_type = LiveMapUpdate

    def __init__(self, object_id: str, semantics: ObjectsMapSemantics = ObjectsMapSemantics.LWW, *,
                 pool: ObjectsPool | None = None, clock: Clock | None = None):
        super().__init__(object_id, pool=pool, clock=clock)
        self.semantics: ObjectsMapSemantics = semantics  # RTLM4b
        self.data: dict[str, ObjectsMapEntry] = {}  # RTLM3, RTLM4c
        self.clear_timeserial: str | None = None  # RTLM25, RTLM4d

    def get(self, key: str) -> Any:
        """RTLM5: the value at `key`, or None if there is none, it is tombstoned, or this map is."""
        if self.is_tombstone:
            return None  # RTLM5e
        entry = self.data.get(key)
        if entry is None:
            return None  # RTLM5d1
        if self.is_entry_tombstoned(entry):
            return None  # RTLM5d2h
        return self._resolve(entry.data)

    def size(self) -> int:
        """RTLM10: the number of entries that are not tombstoned (RTLM14)."""
        return sum(1 for entry in self.data.values() if not self.is_entry_tombstoned(entry))  # RTLM10d

    def entries(self) -> list[tuple[str, Any]]:
        """RTLM11: `(key, value)` for each entry that is not tombstoned, values as `get` returns them."""
        # RTLM11d1, RTLM11d3; a value that resolves to None is still returned (RTLM11d3a)
        return [(key, self._resolve(entry.data)) for key, entry in self.data.items()
                if not self.is_entry_tombstoned(entry)]

    def keys(self) -> list[str]:
        """RTLM12: the keys `entries` returns."""
        return [key for key, _ in self.entries()]

    def values(self) -> list[Any]:
        """RTLM13: the values `entries` returns."""
        return [value for _, value in self.entries()]

    async def set(self, key: str, value: LiveMapValue) -> None:
        """RTLM20: publishes a MAP_SET, preceded by the creates a `LiveMap` or `LiveCounter` value
        evaluates to, through `RealtimeObject._publish_and_apply`.

        Raises AblyException 40003 for a key that is not a string and 40013 for a value of
        an unsupported type (RTLM20e1, RTLMV4b, RTLMV4c).
        """
        validate_key(key)  # RTLM20e1
        object_messages: list[ObjectMessage] = []
        if isinstance(value, (LiveCounter, LiveMap)):
            # RTLM20e7g1: the creates the blueprint evaluates to, its contents validated as it is (RTLMV4c)
            server_time_ms = await self._publishing_realtime_object()._get_server_time_ms()
            object_messages = evaluate(value, server_time_ms)
            data = ObjectData(object_id=object_messages[-1].operation.object_id)  # RTLM20e7g2
        else:
            data = primitive_to_object_data(value)  # RTLM20e1, RTLM20e7b-RTLM20e7f

        object_messages.append(ObjectMessage(operation=ObjectOperation(
            action=ObjectOperationAction.MAP_SET,  # RTLM20e2
            object_id=self.object_id,  # RTLM20e3
            map_set=MapSet(key=key, value=data),  # RTLM20e6, RTLM20e7
        )))
        await self._publishing_realtime_object()._publish_and_apply(object_messages)  # RTLM20h1, RTLM20h2

    async def remove(self, key: str) -> None:
        """RTLM21: publishes a MAP_REMOVE through `RealtimeObject._publish_and_apply`.

        Raises AblyException 40003 for a key that is not a string (RTLM21e1).
        """
        validate_key(key)  # RTLM21e1
        realtime_object = self._publishing_realtime_object()
        object_message = ObjectMessage(operation=ObjectOperation(
            action=ObjectOperationAction.MAP_REMOVE,  # RTLM21e2
            object_id=self.object_id,  # RTLM21e3
            map_remove=MapRemove(key=key),  # RTLM21e5
        ))
        await realtime_object._publish_and_apply([object_message])  # RTLM21g

    def _publishing_realtime_object(self) -> RealtimeObject:
        realtime_object = self.realtime_object
        if realtime_object is None:
            raise AblyException('Unable to update a map that is not on a channel', 400, 40000)
        return realtime_object

    def is_entry_tombstoned(self, entry: ObjectsMapEntry) -> bool:
        """RTLM14: whether `entry` is tombstoned, or references a tombstoned object in `pool`."""
        if entry.tombstone:
            return True  # RTLM14a
        referenced = self._referenced_object(entry.data)
        return referenced is not None and referenced.is_tombstone  # RTLM14c, RTLM14b

    def apply_operation(self, object_message: ObjectMessage, source: ObjectsOperationSource) -> bool:
        """RTLM15: applies `object_message.operation`, returning whether it was applied (RTLM15g).

        The update is emitted through `notify_updated` (RTLM15d1a and its siblings).
        """
        if not self.can_apply_operation(object_message):
            # RTLM15b; an operation with invalid serials has already been logged by can_apply_operation
            if object_message.serial and object_message.site_code:
                log.debug(f'InternalLiveMap.apply_operation(): skipping an operation whose serial is not '
                          f'newer than the one recorded for its site; serial={object_message.serial}, '
                          f'site_code={object_message.site_code}, object_id={self.object_id}')
            return False

        if source == ObjectsOperationSource.CHANNEL:
            # RTLM15c: the serial is recorded whether or not the operation then applies
            self.site_timeserials[object_message.site_code] = object_message.serial

        if self.is_tombstone:
            return False  # RTLM15e

        operation = object_message.operation
        action = operation.action
        if action == ObjectOperationAction.MAP_CREATE:
            update = self.apply_map_create(operation, object_message)  # RTLM15d1
        elif action == ObjectOperationAction.MAP_SET:
            map_set = operation.map_set
            if map_set is None or map_set.key is None or map_set.value is None:
                self._log_missing_payload(action)
                return False
            update = self.apply_map_set(map_set, object_message.serial, object_message)  # RTLM15d6
        elif action == ObjectOperationAction.MAP_REMOVE:
            map_remove = operation.map_remove
            if map_remove is None or map_remove.key is None:
                self._log_missing_payload(action)
                return False
            update = self.apply_map_remove(map_remove, object_message.serial, object_message.serial_timestamp,
                                           object_message)  # RTLM15d7
        elif action == ObjectOperationAction.OBJECT_DELETE:
            update = self.tombstone(object_message)  # RTLM15d5, RTLO5
        elif action == ObjectOperationAction.MAP_CLEAR:
            update = self.apply_map_clear(object_message.serial, object_message)  # RTLM15d8
        else:
            # RTLM15d4
            log.warning(f'InternalLiveMap.apply_operation(): skipping an object operation message with an '
                        f'unsupported action; action={action!r}, object_id={self.object_id}')
            return False

        self.notify_updated(update)  # RTLM15d1a, RTLM15d6a, RTLM15d7a, RTLM15d5c, RTLM15d8a
        return True  # RTLM15d1b, RTLM15d6b, RTLM15d7b, RTLM15d5b, RTLM15d8b

    def replace_data(self, object_message: ObjectMessage) -> LiveMapUpdate:
        """RTLM6: replaces this map's data with `object_message.object`, returning the diff."""
        object_state = object_message.object
        self.site_timeserials = dict(object_state.site_timeserials)  # RTLM6a

        if self.is_tombstone:
            return LiveMapUpdate(noop=True)  # RTLM6e, RTLM6e1

        if object_state.tombstone:
            return self.tombstone(object_message)  # RTLM6f, RTLM6f2

        previous_data = self.data  # RTLM6g
        self.create_operation_is_merged = False  # RTLM6b
        objects_map = object_state.map
        self.clear_timeserial = objects_map.clear_timeserial if objects_map is not None else None  # RTLM6i
        entries = objects_map.entries if objects_map is not None and objects_map.entries is not None else {}
        # RTLM6c. Each entry is copied, so that applying operations to this map never alters the
        # ObjectState it was replaced from.
        self.data = {}
        for key, entry in entries.items():
            entry = dataclasses.replace(entry, tombstoned_at=None)
            if entry.tombstone:
                entry.tombstoned_at = self._tombstoned_at(entry.serial_timestamp)  # RTLM6c1
            self.data[key] = entry
        if object_state.create_op is not None:
            self.merge_initial_value(object_state.create_op, object_message)  # RTLM6d

        update = self.diff(previous_data, self.data)  # RTLM6h
        update.object_message = object_message
        return update

    def apply_map_create(self, operation: ObjectOperation, object_message: ObjectMessage) -> LiveMapUpdate:
        """RTLM16: applies a MAP_CREATE."""
        if self.create_operation_is_merged:
            # RTLM16b
            log.debug(f'InternalLiveMap.apply_map_create(): skipping a MAP_CREATE for a map whose create '
                      f'operation is already merged; object_id={self.object_id}')
            return LiveMapUpdate(noop=True)
        return self.merge_initial_value(operation, object_message)  # RTLM16d, RTLM16f

    def apply_map_set(self, map_set: MapSet, serial: str | None, object_message: ObjectMessage) -> LiveMapUpdate:
        """RTLM7: applies a MAP_SET for `map_set.key`."""
        key = map_set.key
        if self._is_at_or_before_clear(serial):
            # RTLM7h
            log.debug(f'InternalLiveMap.apply_map_set(): skipping a MAP_SET at or before the map\'s clear '
                      f'serial; key={key!r}, serial={serial}, clear_timeserial={self.clear_timeserial}, '
                      f'object_id={self.object_id}')
            return LiveMapUpdate(noop=True)

        entry = self.data.get(key)
        if entry is not None:
            if not self.can_apply_map_operation(entry.timeserial, serial):
                # RTLM7a1
                log.debug(f'InternalLiveMap.apply_map_set(): skipping a MAP_SET not newer than the entry; '
                          f'key={key!r}, serial={serial}, entry serial={entry.timeserial}, '
                          f'object_id={self.object_id}')
                return LiveMapUpdate(noop=True)
            self._release_reference(entry.data, key)  # RTLM7a3
            entry.data = map_set.value  # RTLM7a2e
            entry.timeserial = serial  # RTLM7a2b
            entry.tombstone = False  # RTLM7a2c
            entry.tombstoned_at = None  # RTLM7a2d
        else:
            # RTLM7b4, RTLM7b2, RTLM7b3
            self.data[key] = ObjectsMapEntry(data=map_set.value, timeserial=serial, tombstone=False,
                                             tombstoned_at=None)

        value = map_set.value
        if value is not None and value.object_id and self.pool is not None:
            # RTLM7g
            referenced = self.pool.create_zero_value_object_if_not_exists(value.object_id)  # RTLM7g1
            if referenced is not None:
                referenced.add_parent_reference(self, key)  # RTLM7g2

        return LiveMapUpdate(update={key: MAP_KEY_UPDATED}, object_message=object_message)  # RTLM7f

    def apply_map_remove(self, map_remove: MapRemove, serial: str | None, serial_timestamp: int | None,
                         object_message: ObjectMessage) -> LiveMapUpdate:
        """RTLM8: applies a MAP_REMOVE for `map_remove.key`."""
        key = map_remove.key
        if self._is_at_or_before_clear(serial):
            # RTLM8g
            log.debug(f'InternalLiveMap.apply_map_remove(): skipping a MAP_REMOVE at or before the map\'s '
                      f'clear serial; key={key!r}, serial={serial}, clear_timeserial={self.clear_timeserial}, '
                      f'object_id={self.object_id}')
            return LiveMapUpdate(noop=True)

        entry = self.data.get(key)
        if entry is not None:
            if not self.can_apply_map_operation(entry.timeserial, serial):
                # RTLM8a1
                log.debug(f'InternalLiveMap.apply_map_remove(): skipping a MAP_REMOVE not newer than the '
                          f'entry; key={key!r}, serial={serial}, entry serial={entry.timeserial}, '
                          f'object_id={self.object_id}')
                return LiveMapUpdate(noop=True)
            self._release_reference(entry.data, key)  # RTLM8a3
            entry.data = None  # RTLM8a2a
            entry.timeserial = serial  # RTLM8a2b
            entry.tombstone = True  # RTLM8a2c
            entry.tombstoned_at = self._tombstoned_at(serial_timestamp)  # RTLM8a2d
        else:
            # RTLM8b1, RTLM8b2, RTLM8b3
            self.data[key] = ObjectsMapEntry(data=None, timeserial=serial, tombstone=True,
                                             tombstoned_at=self._tombstoned_at(serial_timestamp))

        return LiveMapUpdate(update={key: MAP_KEY_REMOVED}, object_message=object_message)  # RTLM8e

    def apply_map_clear(self, serial: str | None, object_message: ObjectMessage) -> LiveMapUpdate:
        """RTLM24: applies a MAP_CLEAR."""
        if not serial:
            # A MAP_CLEAR with no serial cannot be ordered against the map's entries
            log.warning(f'InternalLiveMap.apply_map_clear(): skipping a MAP_CLEAR with no serial; '
                        f'object_id={self.object_id}')
            return LiveMapUpdate(noop=True)

        if self.clear_timeserial is not None and self.clear_timeserial > serial:
            # RTLM24c
            log.debug(f'InternalLiveMap.apply_map_clear(): skipping a MAP_CLEAR older than the map\'s clear '
                      f'serial; serial={serial}, clear_timeserial={self.clear_timeserial}, '
                      f'object_id={self.object_id}')
            return LiveMapUpdate(noop=True)

        self.clear_timeserial = serial  # RTLM24d
        removed: dict[str, str] = {}
        for key, entry in list(self.data.items()):
            # RTLM24e1
            if entry.timeserial is None or serial > entry.timeserial:
                self._release_reference(entry.data, key)  # RTLM24e1c
                del self.data[key]  # RTLM24e1a
                removed[key] = MAP_KEY_REMOVED  # RTLM24e1b

        return LiveMapUpdate(update=removed, object_message=object_message)  # RTLM24f

    def merge_initial_value(self, operation: ObjectOperation, object_message: ObjectMessage) -> LiveMapUpdate:
        """RTLM23: merges the initial entries of a create operation into this map.

        The `MapCreate` is `operation.resolved_map_create`.
        """
        map_create = operation.resolved_map_create
        merged: dict[str, str] = {}
        entries = map_create.entries if map_create is not None else {}
        for key, entry in entries.items():
            # The serial an entry is applied with is the entry's own, not the message's
            if entry.tombstone:
                # RTLM23a2
                update = self.apply_map_remove(MapRemove(key=key), entry.timeserial, entry.serial_timestamp,
                                               object_message)
            else:
                # RTLM23a1
                update = self.apply_map_set(MapSet(key=key, value=entry.data), entry.timeserial, object_message)
            if not update.noop:
                merged.update(update.update)  # RTLM23c

        self.create_operation_is_merged = True  # RTLM23b
        return LiveMapUpdate(update=merged, object_message=object_message)  # RTLM23c

    def gc_tombstoned_entries(self, grace_period_ms: int, now_ms: int) -> None:
        """RTLM19: removes tombstoned entries whose `tombstoned_at` is `grace_period_ms` or more
        before `now_ms`."""
        for key, entry in list(self.data.items()):
            # RTLM19a1
            if (entry.tombstone and entry.tombstoned_at is not None
                    and now_ms - entry.tombstoned_at >= grace_period_ms):
                del self.data[key]

    def clear_data(self) -> None:
        """RTO27a1: resets `data` to empty and `clear_timeserial` to None, emitting nothing.

        Each object an entry references stops recording this map as a parent (RTLO4e9).
        """
        for key, entry in self.data.items():
            self._release_reference(entry.data, key)
        self.data = {}  # RTLM4c
        self.clear_timeserial = None  # RTLM4d

    @staticmethod
    def can_apply_map_operation(entry_serial: str | None, operation_serial: str | None) -> bool:
        """RTLM9: whether an operation with `operation_serial` may replace an entry with `entry_serial`."""
        if not entry_serial and not operation_serial:
            return False  # RTLM9b
        if not entry_serial:
            return True  # RTLM9d
        if not operation_serial:
            return False  # RTLM9c
        return operation_serial > entry_serial  # RTLM9a, RTLM9e

    @staticmethod
    def diff(previous_data: dict[str, ObjectsMapEntry], new_data: dict[str, ObjectsMapEntry], *,
             for_tombstone: bool = False) -> LiveMapUpdate:
        """RTLM22: the update between two versions of a map's data.

        Only entries whose own `tombstone` flag is false are compared. An empty diff is a
        no-op (RTLM22c), unless it is computed for a tombstone (`for_tombstone`, RTLO4e5).
        """
        previous_live = {key: entry for key, entry in previous_data.items() if not entry.tombstone}
        new_live = {key: entry for key, entry in new_data.items() if not entry.tombstone}
        update: dict[str, str] = {}
        for key in previous_live:
            if key not in new_live:
                update[key] = MAP_KEY_REMOVED  # RTLM22b1
        for key, entry in new_live.items():
            if key not in previous_live or previous_live[key].data != entry.data:
                update[key] = MAP_KEY_UPDATED  # RTLM22b2, RTLM22b3

        if not update and not for_tombstone:
            return LiveMapUpdate(noop=True)  # RTLM22c
        return LiveMapUpdate(update=update)

    def _resolve(self, data: ObjectData | None) -> Any:
        """RTLM5d2: the value `data` holds: a primitive, the object it references, or None."""
        if data is None:
            return None
        # RTLM5d2b-RTLM5d2e, and a JSON value (OD2g)
        primitive = data.value
        if primitive is not None:
            return primitive
        if data.object_id is not None:
            return self._referenced_object(data)  # RTLM5d2f1, RTLM5d2f2
        return None  # RTLM5d2g

    def _referenced_object(self, data: ObjectData | None) -> LiveObject | None:
        """The object in `pool` that `data` references, if there is one."""
        if data is None or data.object_id is None or self.pool is None:
            return None
        return self.pool.get(data.object_id)

    def _release_reference(self, data: ObjectData | None, key: str) -> None:
        """RTLM7a3, RTLM8a3, RTLM24e1c, RTLO4e9: removes this map at `key` from the parent references of
        the object `data` references, if it is in `pool`."""
        referenced = self._referenced_object(data)
        if referenced is not None:
            referenced.remove_parent_reference(self, key)

    def _is_at_or_before_clear(self, serial: str | None) -> bool:
        """RTLM7h, RTLM8g: whether an operation with `serial` is no later than the map's last MAP_CLEAR."""
        return self.clear_timeserial is not None and (not serial or self.clear_timeserial >= serial)

    def _log_missing_payload(self, action: ObjectOperationAction) -> None:
        log.warning(f'InternalLiveMap.apply_operation(): skipping a {action.name} operation with no key or '
                    f'value; object_id={self.object_id}')
