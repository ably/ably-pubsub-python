"""Identity-addressed views onto a channel's objects (RTINS*, RTTS7-RTTS10).

An `Instance` wraps one resolved value, a live object or a primitive, and follows that
object wherever it sits in the graph. Every instance is one of `LiveMapInstance`,
`LiveCounterInstance` or `PrimitiveInstance`, matching the value it wraps. The view
helpers are checked: asking for a type the instance does not wrap raises `AblyException`
92007 (RTTS9d).

The module also holds what the path and instance views share about resolved values:
their `ValueType`, the type filter `value(expected)` applies, and compaction.
"""

from __future__ import annotations

import base64
import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, overload

from ably.pubsub.objects.enums import ValueType
from ably.pubsub.objects.livecounter import InternalLiveCounter
from ably.pubsub.objects.livemap import InternalLiveMap
from ably.pubsub.objects.liveobject import LiveObject
from ably.pubsub.objects.publicmessage import ObjectMessage
from ably.pubsub.util.exceptions import AblyException

if TYPE_CHECKING:
    from ably.pubsub.objects.batch import Batch, LiveCounterBatchContext, LiveMapBatchContext
    from ably.pubsub.objects.liveobject import LiveObjectUpdate
    from ably.pubsub.objects.realtimeobject import RealtimeObject
    from ably.pubsub.objects.subscription import Subscription
    from ably.pubsub.objects.valuetypes import LiveMapValue, Primitive, T

# The types `value(expected)` accepts as `expected`, and the category each one selects
_EXPECTED_VALUE_TYPES: tuple[tuple[type, ValueType], ...] = (
    (str, ValueType.STRING),
    (float, ValueType.NUMBER),
    (bool, ValueType.BOOLEAN),
    (bytes, ValueType.BINARY),
    (list, ValueType.JSON_ARRAY),
    (dict, ValueType.JSON_OBJECT),
)

_PRIMITIVE_VALUE_TYPES = frozenset(value_type for _, value_type in _EXPECTED_VALUE_TYPES)


def value_type_of(value: Any) -> ValueType:
    """RTTS2: the category of a resolved value, `UNKNOWN` for one in no known category (RTTS2a9).

    A boolean is never a number.
    """
    if isinstance(value, InternalLiveMap):
        return ValueType.LIVE_MAP
    if isinstance(value, InternalLiveCounter):
        return ValueType.LIVE_COUNTER
    if isinstance(value, bool):
        return ValueType.BOOLEAN
    if isinstance(value, (int, float)):
        return ValueType.NUMBER
    if isinstance(value, str):
        return ValueType.STRING
    if isinstance(value, (bytes, bytearray)):
        return ValueType.BINARY
    if isinstance(value, dict):
        return ValueType.JSON_OBJECT
    if isinstance(value, list):
        return ValueType.JSON_ARRAY
    return ValueType.UNKNOWN


def expected_value_type(expected: type | None) -> ValueType | None:
    """The category `value(expected)` filters on, or None for no filter.

    Raises TypeError for an `expected` other than `str`, `float`, `bool`, `bytes`, `list`
    or `dict`.
    """
    if expected is None:
        return None
    for python_type, value_type in _EXPECTED_VALUE_TYPES:
        if expected is python_type:
            return value_type
    raise TypeError(f'expected must be one of str, float, bool, bytes, list or dict, not {expected!r}')


def primitive_value(value: Any, value_type: ValueType | None = None) -> Any:
    """RTPO7d, RTTS6c: `value` if it is a primitive, of category `value_type` when one is given,
    else None.

    A number is a float, and a JSON object or array is a copy, so that changing it leaves
    the object it was read from unchanged.
    """
    if value is None:
        return None
    actual_type = value_type_of(value)
    if actual_type not in _PRIMITIVE_VALUE_TYPES or (value_type is not None and actual_type is not value_type):
        return None
    if actual_type is ValueType.NUMBER:
        return float(value)
    if actual_type is ValueType.BINARY:
        return bytes(value)
    if actual_type in (ValueType.JSON_OBJECT, ValueType.JSON_ARRAY):
        return copy.deepcopy(value)
    return value


def compact_value(value: Any, *, for_json: bool = False) -> Any:
    """RTPO13, RTPO14: a plain snapshot of a resolved value.

    A map becomes a dict of its entries that are not tombstoned (RTPO13c1), nested maps
    becoming nested dicts (RTPO13c2) and counters their values (RTPO13c3). Maps are visited
    depth first in entry order, and a map reached again in the same snapshot, through a
    cycle or a second reference, is the dict already built for it (RTPO13c5). With
    `for_json` it is `{'objectId': id}` instead (RTPO14b2), and binary is a base64 string
    (RTPO14b1), so that the result is JSON-serializable.
    """
    if not isinstance(value, InternalLiveMap):
        return _compact_leaf(value, for_json)

    result: dict[str, Any] = {}
    built: dict[str, dict[str, Any]] = {value.object_id: result}
    # A stack in place of recursion, so that the depth of the tree is not limited by the
    # interpreter's. Each item is a dict being built and the entries of its map still to add.
    stack = [(result, iter(value.entries()))]
    while stack:
        target, entries = stack[-1]
        for key, entry_value in entries:
            if not isinstance(entry_value, InternalLiveMap):
                target[key] = _compact_leaf(entry_value, for_json)
                continue
            seen = built.get(entry_value.object_id)
            if seen is not None:
                target[key] = {'objectId': entry_value.object_id} if for_json else seen
                continue
            child: dict[str, Any] = {}
            built[entry_value.object_id] = child
            target[key] = child
            stack.append((child, iter(entry_value.entries())))
            break
        else:
            stack.pop()
    return result


def _compact_leaf(value: Any, for_json: bool) -> Any:
    """RTPO13c3, RTPO13c4, RTPO13d, RTPO13e, RTPO14b1: the snapshot of a value that is not a map."""
    if isinstance(value, InternalLiveCounter):
        return value.value()
    if for_json and isinstance(value, (bytes, bytearray)):
        return base64.b64encode(value).decode('ascii')
    if isinstance(value, (dict, list)):
        return copy.deepcopy(value)
    return value


@dataclass
class InstanceSubscriptionEvent:
    """RTINS16e: what an `Instance.subscribe` listener receives."""

    object: Instance  # RTINS16e1
    message: ObjectMessage | None = None  # RTINS16e2


class Instance:
    """RTINS1, RTTS7: a reference to a specific live object or primitive value."""

    def __init__(self, realtime_object: RealtimeObject, value: LiveObject | Primitive):
        self._realtime_object = realtime_object
        self._value = value  # RTINS2a

    def __repr__(self) -> str:
        if isinstance(self._value, LiveObject):
            return f'{type(self).__name__}(id={self._value.object_id!r})'
        return f'{type(self).__name__}({self._value!r})'

    @staticmethod
    def _wrap(realtime_object: RealtimeObject, value: LiveObject | Primitive) -> Instance:
        """The `Instance` subclass matching `value`."""
        if isinstance(value, InternalLiveMap):
            return LiveMapInstance(realtime_object, value)
        if isinstance(value, InternalLiveCounter):
            return LiveCounterInstance(realtime_object, value)
        return PrimitiveInstance(realtime_object, value)

    @property
    def id(self) -> str | None:
        """RTINS3: the wrapped object's id, or None for a primitive."""
        if isinstance(self._value, LiveObject):
            return self._value.object_id  # RTINS3a
        return None  # RTINS3b

    @property
    def type(self) -> ValueType:
        """RTTS8a: the type of the wrapped value."""
        return value_type_of(self._value)

    def get(self, key: str) -> Instance | None:
        """RTINS5: an instance wrapping the value at `key` of the wrapped map, or None.

        Raises AblyException 40003 if `key` is not a string.
        """
        self._realtime_object._check_access_preconditions()  # RTINS5b
        if not isinstance(key, str):
            raise AblyException(f'Map key must be a string, not {type(key).__name__}', 400, 40003)
        if not isinstance(self._value, InternalLiveMap):
            return None  # RTINS5d
        value = self._value.get(key)
        if value is None:
            return None
        return Instance._wrap(self._realtime_object, value)  # RTINS5c

    def compact(self) -> Any:
        """RTINS10: a plain snapshot of the wrapped value."""
        self._realtime_object._check_access_preconditions()  # RTINS10a
        return compact_value(self._value)  # RTINS10b

    def compact_json(self) -> Any:
        """RTINS11: `compact`, with binary as base64 and cycles as `{'objectId': ...}`. Never None."""
        self._realtime_object._check_access_preconditions()  # RTINS11a
        return compact_value(self._value, for_json=True)  # RTINS11b

    def as_live_map(self) -> LiveMapInstance:
        """RTTS9a: this instance as a map. Raises AblyException 92007 if it wraps something else."""
        if not isinstance(self._value, InternalLiveMap):
            raise self._view_mismatch('a map')  # RTTS9d
        if isinstance(self, LiveMapInstance):
            return self
        return LiveMapInstance(self._realtime_object, self._value)

    def as_live_counter(self) -> LiveCounterInstance:
        """RTTS9b: this instance as a counter. Raises AblyException 92007 if it wraps something else."""
        if not isinstance(self._value, InternalLiveCounter):
            raise self._view_mismatch('a counter')  # RTTS9d
        if isinstance(self, LiveCounterInstance):
            return self
        return LiveCounterInstance(self._realtime_object, self._value)

    def as_primitive(self) -> PrimitiveInstance:
        """RTTS9c: this instance as a primitive. Raises AblyException 92007 if it wraps something else."""
        if isinstance(self._value, LiveObject):
            raise self._view_mismatch('a primitive')  # RTTS9d
        if isinstance(self, PrimitiveInstance):
            return self
        return PrimitiveInstance(self._realtime_object, self._value)

    def _view_mismatch(self, requested: str) -> AblyException:
        return AblyException(f'Cannot view an instance of type {self.type.value} as {requested}', 400, 92007)


class LiveMapInstance(Instance):
    """RTTS10a: an instance wrapping an `InternalLiveMap`."""

    _value: InternalLiveMap

    @property
    def id(self) -> str:
        """RTINS3a: the wrapped map's id."""
        return self._value.object_id

    def batch(self) -> Batch[LiveMapBatchContext]:
        """RTINS17: a block whose queued writes are published as one message when it exits.

        Entering checks the write preconditions (RTINS17b).
        """
        # Imported here, as the batch module builds on this one
        from ably.pubsub.objects.batch import Batch, LiveMapBatchContext

        return Batch(self._realtime_object, lambda: self._value, LiveMapBatchContext, f'object {self.id!r}')

    def entries(self) -> list[tuple[str, Instance]]:
        """RTINS6: `(key, instance)` for each entry of the map.

        An entry referencing an object this client does not hold has no value to wrap, and
        is left out.
        """
        self._realtime_object._check_access_preconditions()  # RTINS6a
        # RTINS6b
        return [(key, Instance._wrap(self._realtime_object, value))
                for key, value in self._value.entries() if value is not None]

    def keys(self) -> list[str]:
        """RTINS7: the keys of the map."""
        self._realtime_object._check_access_preconditions()  # RTINS7a
        return self._value.keys()  # RTINS7b

    def values(self) -> list[Instance]:
        """RTINS8: an instance for each entry of the map, as `entries` wraps them."""
        return [instance for _, instance in self.entries()]  # RTINS8a, RTINS8b

    def size(self) -> int:
        """RTINS9: the number of entries in the map."""
        self._realtime_object._check_access_preconditions()  # RTINS9a
        return self._value.size()  # RTINS9b

    async def set(self, key: str, value: LiveMapValue) -> None:
        """RTINS12: sets `key` in the wrapped map."""
        self._realtime_object._check_write_preconditions()  # RTINS12b
        await self._value.set(key, value)  # RTINS12c

    async def remove(self, key: str) -> None:
        """RTINS13: removes `key` from the wrapped map."""
        self._realtime_object._check_write_preconditions()  # RTINS13b
        await self._value.remove(key)  # RTINS13c

    def subscribe(self, listener: Callable[[InstanceSubscriptionEvent], None]) -> Subscription:
        """RTINS16: calls `listener` for each update to the wrapped map, wherever it sits (RTINS16g)."""
        self._realtime_object._check_access_preconditions()  # RTINS16b
        return _subscribe(self, listener)


class LiveCounterInstance(Instance):
    """RTTS10b: an instance wrapping an `InternalLiveCounter`."""

    _value: InternalLiveCounter

    @property
    def id(self) -> str:
        """RTINS3a: the wrapped counter's id."""
        return self._value.object_id

    def batch(self) -> Batch[LiveCounterBatchContext]:
        """RTINS17: a block whose queued writes are published as one message when it exits.

        Entering checks the write preconditions (RTINS17b).
        """
        # Imported here, as the batch module builds on this one
        from ably.pubsub.objects.batch import Batch, LiveCounterBatchContext

        return Batch(self._realtime_object, lambda: self._value, LiveCounterBatchContext, f'object {self.id!r}')

    def value(self) -> float:
        """RTINS4b: the wrapped counter's value."""
        self._realtime_object._check_access_preconditions()  # RTINS4a
        return self._value.value()

    async def increment(self, amount: float = 1) -> None:
        """RTINS14: increments the wrapped counter by `amount`."""
        self._realtime_object._check_write_preconditions()  # RTINS14b
        await self._value.increment(amount)  # RTINS14c

    async def decrement(self, amount: float = 1) -> None:
        """RTINS15: decrements the wrapped counter by `amount`."""
        self._realtime_object._check_write_preconditions()  # RTINS15b
        await self._value.decrement(amount)  # RTINS15c

    def subscribe(self, listener: Callable[[InstanceSubscriptionEvent], None]) -> Subscription:
        """RTINS16: calls `listener` for each update to the wrapped counter, wherever it sits (RTINS16g)."""
        self._realtime_object._check_access_preconditions()  # RTINS16b
        return _subscribe(self, listener)


class PrimitiveInstance(Instance):
    """RTTS10c, RTTS10d: an instance wrapping a primitive value. It has no `subscribe` (RTTS7b)."""

    @overload
    def value(self) -> Primitive: ...

    @overload
    def value(self, expected: type[T]) -> T | None: ...

    def value(self, expected: type | None = None) -> Any:
        """RTINS4c: the wrapped primitive; with `expected`, only if it is of that type, as for
        `PrimitivePathObject.value`."""
        value_type = expected_value_type(expected)
        self._realtime_object._check_access_preconditions()  # RTINS4a
        return primitive_value(self._value, value_type)


def _subscribe(instance: LiveMapInstance | LiveCounterInstance,
               listener: Callable[[InstanceSubscriptionEvent], None]) -> Subscription:
    """RTINS16d: subscribes `listener` to the updates of the live object `instance` wraps.

    The live object calls its listeners synchronously, logging any that raises, and drops
    them once it is tombstoned (RTLO4b4c3c).
    """
    realtime_object = instance._realtime_object

    def on_update(update: LiveObjectUpdate) -> None:
        object_message = update.object_message
        message = None
        if object_message is not None and object_message.operation is not None:
            message = ObjectMessage._from_internal(object_message, realtime_object._channel_name)  # RTINS16e2
        listener(InstanceSubscriptionEvent(instance, message))  # RTINS16e1

    return instance._value.subscribe(on_update)
