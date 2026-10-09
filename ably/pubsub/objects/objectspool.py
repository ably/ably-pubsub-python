"""The objects held for a channel (RTO3)."""

from __future__ import annotations

import logging
from collections.abc import Iterator, MutableMapping
from typing import TYPE_CHECKING

from ably.pubsub.objects.defaults import ROOT_OBJECT_ID
from ably.pubsub.objects.livecounter import InternalLiveCounter
from ably.pubsub.objects.livemap import InternalLiveMap
from ably.pubsub.objects.liveobject import LiveObject
from ably.pubsub.objects.objectid import object_type_of
from ably.pubsub.util.clock import Clock

if TYPE_CHECKING:
    from ably.pubsub.objects.realtimeobject import RealtimeObject

log = logging.getLogger(__name__)


class ObjectsPool(MutableMapping):
    """RTO3: the live objects on a channel, by object id (RTO3a).

    A pool always holds an `InternalLiveMap` with id `root`, created with the pool
    (RTO3b1). It is a mutable mapping, so `pool[object_id]`, `object_id in pool`,
    `len(pool)` and `pool.keys()` work as they do on a dict. Setting `pool[object_id] = obj`
    adopts `obj`: its `pool` becomes this pool.

    A pool is constructible on its own. `realtime_object` is None for a pool built without
    one, in which case objects in it dispatch no path subscriptions and publish nothing.
    """

    def __init__(self, realtime_object: RealtimeObject | None = None, *, clock: Clock | None = None):
        self.realtime_object: RealtimeObject | None = realtime_object
        self.clock: Clock = clock if clock is not None else Clock()
        self._objects: dict[str, LiveObject] = {}
        self[ROOT_OBJECT_ID] = InternalLiveMap(ROOT_OBJECT_ID, pool=self)

    @property
    def root(self) -> InternalLiveMap:
        """The root map (RTO3b)."""
        return self._objects[ROOT_OBJECT_ID]

    def __getitem__(self, object_id: str) -> LiveObject:
        return self._objects[object_id]

    def __setitem__(self, object_id: str, live_object: LiveObject) -> None:
        live_object.pool = self
        self._objects[object_id] = live_object

    def __delitem__(self, object_id: str) -> None:
        del self._objects[object_id]

    def __iter__(self) -> Iterator[str]:
        return iter(self._objects)

    def __len__(self) -> int:
        return len(self._objects)

    def __repr__(self) -> str:
        return f'ObjectsPool({list(self._objects)!r})'

    def create_zero_value_object_if_not_exists(self, object_id: str) -> LiveObject | None:
        """RTO6: the object with `object_id`, created empty from the type its id names if absent.

        Returns None, creating nothing, for an id that names neither a map nor a counter.
        """
        existing = self._objects.get(object_id)
        if existing is not None:
            return existing  # RTO6a

        object_type = object_type_of(object_id) if isinstance(object_id, str) else None  # RTO6b1
        if object_type == 'map':
            live_object: LiveObject = InternalLiveMap(object_id)  # RTO6b2
        elif object_type == 'counter':
            live_object = InternalLiveCounter(object_id)  # RTO6b3
        else:
            log.warning(f'ObjectsPool.create_zero_value_object_if_not_exists(): cannot create an object for '
                        f'an id of unknown type; object_id={object_id!r}')
            return None

        self[object_id] = live_object
        return live_object

    def clear_all_data(self) -> None:
        """RTO27a1: resets every object's data to empty, keeping the objects, emitting nothing."""
        for live_object in list(self._objects.values()):
            live_object.clear_data()

    def rebuild_parent_references(self) -> None:
        """RTO5c10: clears every object's `parent_references` and rebuilds them from the map entries."""
        for live_object in self._objects.values():
            live_object.parent_references = {}  # RTO5c10a

        # RTO5c10b
        for live_object in list(self._objects.values()):
            if not isinstance(live_object, InternalLiveMap):
                continue
            for key, value in live_object.entries():
                if isinstance(value, LiveObject):
                    value.add_parent_reference(live_object, key)

    def collect_garbage(self, grace_period_ms: int, now_ms: int) -> None:
        """RTO10c: releases tombstoned map entries (RTLM19) and objects tombstoned `grace_period_ms`
        or more before `now_ms`, never the root (RTO10c1b1)."""
        for object_id, live_object in list(self._objects.items()):
            # RTO10c1b, RTO10c1b1
            if (object_id != ROOT_OBJECT_ID and live_object.is_tombstone and live_object.tombstoned_at is not None
                    and now_ms - live_object.tombstoned_at >= grace_period_ms):
                del self._objects[object_id]
                continue
            if isinstance(live_object, InternalLiveMap):
                live_object.gc_tombstoned_entries(grace_period_ms, now_ms)  # RTO10c1a
