"""The behaviour every live object shares (RTLO*), and the updates objects emit."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from ably.pubsub.objects.defaults import ROOT_OBJECT_ID
from ably.pubsub.objects.subscription import Subscription
from ably.pubsub.util.clock import Clock

if TYPE_CHECKING:
    from ably.pubsub.objects.enums import ObjectsOperationSource
    from ably.pubsub.objects.livemap import InternalLiveMap
    from ably.pubsub.objects.objectmessage import ObjectMessage
    from ably.pubsub.objects.objectspool import ObjectsPool
    from ably.pubsub.objects.realtimeobject import RealtimeObject

log = logging.getLogger(__name__)

# RTLM18b: the change recorded against a map key in a LiveMapUpdate
MAP_KEY_UPDATED = 'updated'
MAP_KEY_REMOVED = 'removed'


@dataclass
class LiveObjectUpdate:
    """RTLO4b4: a change to a live object's data, as the object emits it."""

    update: Any = None  # RTLO4b4a
    noop: bool = False  # RTLO4b4b
    object_message: ObjectMessage | None = None  # RTLO4b4d
    tombstone: bool = False  # RTLO4b4e


@dataclass
class CounterUpdate:
    """RTLC11b: what a counter update changed."""

    amount: float  # RTLC11b1


@dataclass
class LiveCounterUpdate(LiveObjectUpdate):
    """RTLC11: an update emitted by an `InternalLiveCounter`.

    `update` is a `CounterUpdate`, or None on a no-op.
    """

    update: CounterUpdate | None = None


@dataclass
class LiveMapUpdate(LiveObjectUpdate):
    """RTLM18: an update emitted by an `InternalLiveMap`.

    `update` maps each changed key to `'updated'` or `'removed'` (RTLM18b).
    """

    update: dict[str, str] = field(default_factory=dict)


class LiveObject(ABC):
    """RTLO1: the state and behaviour `InternalLiveCounter` and `InternalLiveMap` share.

    A live object is constructible on its own, with no channel, so that its CRDT
    behaviour can be driven directly. `pool` is the `ObjectsPool` it reads other objects
    from (RTLM5d2f, RTLM14c, RTLO4f); an object added to a pool with `pool[object_id] = obj`
    is adopted by it. `clock` is what RTLO6b reads the local time from; without one the
    object uses its pool's clock, and with neither, the system clock.
    """

    # The update type this object emits, which a no-op it returns is also an instance of
    _update_type: type[LiveObjectUpdate] = LiveObjectUpdate

    def __init__(self, object_id: str, *, pool: ObjectsPool | None = None, clock: Clock | None = None):
        self.object_id: str = object_id  # RTLO3a
        self.site_timeserials: dict[str, str] = {}  # RTLO3b
        self.create_operation_is_merged: bool = False  # RTLO3c
        self.is_tombstone: bool = False  # RTLO3d
        self.tombstoned_at: int | None = None  # RTLO3e
        self.parent_references: dict[str, set[str]] = {}  # RTLO3f
        self.pool: ObjectsPool | None = pool
        self.data: Any = None
        self._clock: Clock | None = clock
        # (token, listener) for each subscribe call, so that one registration can be removed
        # even when the same listener is registered more than once
        self._listeners: list[tuple[object, Callable[[LiveObjectUpdate], None]]] = []

    @property
    def clock(self) -> Clock:
        """The clock RTLO6b reads the local time from."""
        if self._clock is not None:
            return self._clock
        if self.pool is not None:
            return self.pool.clock
        return Clock()

    @property
    def realtime_object(self) -> RealtimeObject | None:
        """The `RealtimeObject` this object's pool belongs to, if any."""
        return self.pool.realtime_object if self.pool is not None else None

    def subscribe(self, listener: Callable[[LiveObjectUpdate], None]) -> Subscription:
        """RTLO4b: registers `listener` for the updates this object emits.

        Listeners are called synchronously from `notify_updated`, in registration order.
        """
        token = object()
        self._listeners.append((token, listener))

        def deregister() -> None:
            self._listeners = [entry for entry in self._listeners if entry[0] is not token]

        return Subscription(deregister)

    def notify_updated(self, update: LiveObjectUpdate) -> None:
        """RTLO4b4c: emits `update`.

        Every update an operation produces passes through here, a no-op included, and a
        no-op stops here (RTLO4b4c1). Otherwise the `subscribe` listeners are called
        (RTLO4b4c3a), path subscriptions are dispatched through the `RealtimeObject`, if
        there is one (RTLO4b4c3b), and a tombstone update then deregisters the `subscribe`
        listeners (RTLO4b4c3c).
        """
        if update.noop:
            return

        for _, listener in list(self._listeners):
            try:
                listener(update)
            except Exception:
                log.exception(f'LiveObject.notify_updated(): a subscription listener raised; '
                              f'object_id={self.object_id}')

        realtime_object = self.realtime_object
        if realtime_object is not None:
            realtime_object._path_object_subscription_register.dispatch(self, update)

        if update.tombstone:
            self._listeners = []

    def can_apply_operation(self, object_message: ObjectMessage) -> bool:
        """RTLO4a: whether `object_message`'s serial is newer than this object's for its site."""
        serial = object_message.serial
        site_code = object_message.site_code
        # RTLO4a3
        if not isinstance(serial, str) or not serial or not isinstance(site_code, str) or not site_code:
            log.warning(f'LiveObject.can_apply_operation(): object operation message has invalid serial '
                        f'values, skipping it; serial={serial!r}, site_code={site_code!r}, '
                        f'object_id={self.object_id}')
            return False

        site_serial = self.site_timeserials.get(site_code)  # RTLO4a4
        if not site_serial:
            return True  # RTLO4a5
        return serial > site_serial  # RTLO4a6

    @abstractmethod
    def apply_operation(self, object_message: ObjectMessage, source: ObjectsOperationSource) -> bool:
        """RTLC7, RTLM15: applies `object_message.operation`, returning whether it was applied.

        The resulting update is emitted through `notify_updated`, not returned.
        """

    @abstractmethod
    def replace_data(self, object_message: ObjectMessage) -> LiveObjectUpdate:
        """RTLC6, RTLM6: replaces this object's data with `object_message.object`.

        The update is returned, not emitted; the caller emits it (RTO5c7).
        """

    def tombstone(self, object_message: ObjectMessage) -> LiveObjectUpdate:
        """RTLO4e: tombstones this object, returning the resulting update.

        The update has `tombstone` set and `object_message` populated, and is never a no-op,
        except for the root object, which is never tombstoned (RTLO4e10).
        """
        if self.object_id == ROOT_OBJECT_ID:
            log.warning(f'LiveObject.tombstone(): attempt to tombstone the root object was rejected; '
                        f'serial={object_message.serial}, site_code={object_message.site_code}, '
                        f'message id={object_message.id}')
            return self._update_type(noop=True)

        self.is_tombstone = True  # RTLO4e2
        self.tombstoned_at = self._tombstoned_at(object_message.serial_timestamp)  # RTLO4e3
        previous_data = self.data
        self.clear_data()  # RTLO4e9, RTLO4e4
        update = self.diff(previous_data, self.data, for_tombstone=True)  # RTLO4e5
        update.tombstone = True  # RTLO4e6
        update.object_message = object_message  # RTLO4e7
        return update

    @abstractmethod
    def clear_data(self) -> None:
        """RTO27a1: resets this object's data to that of a new empty object, emitting nothing."""

    @staticmethod
    @abstractmethod
    def diff(previous_data: Any, new_data: Any, *, for_tombstone: bool = False) -> LiveObjectUpdate:
        """RTLC14, RTLM22: the update between two versions of this type of object's data."""

    def add_parent_reference(self, parent: InternalLiveMap, key: str) -> None:
        """RTLO4g: records that `parent` references this object at `key`."""
        self.parent_references.setdefault(parent.object_id, set()).add(key)

    def remove_parent_reference(self, parent: InternalLiveMap, key: str) -> None:
        """RTLO4h: removes the record that `parent` references this object at `key`."""
        keys = self.parent_references.get(parent.object_id)
        if keys is None:
            return  # RTLO4h1
        keys.discard(key)  # RTLO4h2
        if not keys:
            del self.parent_references[parent.object_id]  # RTLO4h3

    def get_full_paths(self) -> list[list[str]]:
        """RTLO4f: every key-path from the root map to this object, each once, in no set order.

        Parents are looked up by object id in this object's pool.
        """
        paths: list[list[str]] = []
        seen: set[tuple[str, ...]] = set()
        # Each item is an object, the keys from it down to this object, and the ids of the
        # objects already on that path, which a simple path does not revisit (RTLO4f2)
        stack: list[tuple[LiveObject, list[str], frozenset[str]]] = [(self, [], frozenset())]
        while stack:
            live_object, path, visited = stack.pop()
            if live_object.object_id in visited:
                continue
            if live_object.object_id == ROOT_OBJECT_ID:
                if tuple(path) not in seen:
                    seen.add(tuple(path))
                    paths.append(path)
                continue
            if self.pool is None:
                continue
            visited = visited | {live_object.object_id}
            for parent_id, keys in live_object.parent_references.items():
                parent = self.pool.get(parent_id)
                if parent is None:
                    continue
                for key in keys:
                    stack.append((parent, [key, *path], visited))
        return paths

    def _tombstoned_at(self, serial_timestamp: int | None) -> int:
        """RTLO6: the time something is tombstoned at, given the operation's `serial_timestamp`."""
        if serial_timestamp is not None:
            return serial_timestamp  # RTLO6a
        # RTLO6b, RTLO6b1
        log.debug(f'LiveObject._tombstoned_at(): no serial_timestamp for the operation, using the local '
                  f'clock instead; object_id={self.object_id}')
        return self.clock.now_ms()
