"""Identity-addressed views onto a channel's objects (RTINS*, RTTS7-RTTS10).

An `Instance` wraps one resolved value, a live object or a primitive, and follows that
object wherever it sits in the graph. Every instance is one of `LiveMapInstance`,
`LiveCounterInstance` or `PrimitiveInstance`, matching the value it wraps. The view
helpers are checked: asking for a type the instance does not wrap raises `AblyException`
92007 (RTTS9d).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, overload

if TYPE_CHECKING:
    from ably.pubsub.objects.batch import Batch, LiveCounterBatchContext, LiveMapBatchContext
    from ably.pubsub.objects.enums import ValueType
    from ably.pubsub.objects.liveobject import LiveObject
    from ably.pubsub.objects.publicmessage import ObjectMessage
    from ably.pubsub.objects.realtimeobject import RealtimeObject
    from ably.pubsub.objects.subscription import Subscription
    from ably.pubsub.objects.valuetypes import LiveMapValue, Primitive, T


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

    @staticmethod
    def _wrap(realtime_object: RealtimeObject, value: LiveObject | Primitive) -> Instance:
        """The `Instance` subclass matching `value`."""
        raise NotImplementedError

    @property
    def id(self) -> str | None:
        """RTINS3: the wrapped object's id, or None for a primitive."""
        raise NotImplementedError

    @property
    def type(self) -> ValueType:
        """RTTS8a: the type of the wrapped value."""
        raise NotImplementedError

    def get(self, key: str) -> Instance | None:
        """RTINS5: an instance wrapping the value at `key` of the wrapped map, or None."""
        raise NotImplementedError

    def compact(self) -> Any:
        """RTINS10: a plain snapshot of the wrapped value."""
        raise NotImplementedError

    def compact_json(self) -> Any:
        """RTINS11: `compact`, with binary as base64 and cycles as `{'objectId': ...}`. Never None."""
        raise NotImplementedError

    def as_live_map(self) -> LiveMapInstance:
        """RTTS9a: this instance as a map. Raises AblyException 92007 if it wraps something else."""
        raise NotImplementedError

    def as_live_counter(self) -> LiveCounterInstance:
        """RTTS9b: this instance as a counter. Raises AblyException 92007 if it wraps something else."""
        raise NotImplementedError

    def as_primitive(self) -> PrimitiveInstance:
        """RTTS9c: this instance as a primitive. Raises AblyException 92007 if it wraps something else."""
        raise NotImplementedError


class LiveMapInstance(Instance):
    """RTTS10a: an instance wrapping an `InternalLiveMap`."""

    @property
    def id(self) -> str:
        """RTINS3a: the wrapped map's id."""
        raise NotImplementedError

    def batch(self) -> Batch[LiveMapBatchContext]:
        """RTINS17: a block whose queued writes are published as one message when it exits."""
        raise NotImplementedError

    def entries(self) -> list[tuple[str, Instance]]:
        """RTINS6: `(key, instance)` for each entry of the map."""
        raise NotImplementedError

    def keys(self) -> list[str]:
        """RTINS7: the keys of the map."""
        raise NotImplementedError

    def values(self) -> list[Instance]:
        """RTINS8: an instance for each entry of the map."""
        raise NotImplementedError

    def size(self) -> int:
        """RTINS9: the number of entries in the map."""
        raise NotImplementedError

    async def set(self, key: str, value: LiveMapValue) -> None:
        """RTINS12: sets `key` in the wrapped map."""
        raise NotImplementedError

    async def remove(self, key: str) -> None:
        """RTINS13: removes `key` from the wrapped map."""
        raise NotImplementedError

    def subscribe(self, listener: Callable[[InstanceSubscriptionEvent], None]) -> Subscription:
        """RTINS16: calls `listener` for each update to the wrapped map, wherever it sits (RTINS16g)."""
        raise NotImplementedError


class LiveCounterInstance(Instance):
    """RTTS10b: an instance wrapping an `InternalLiveCounter`."""

    @property
    def id(self) -> str:
        """RTINS3a: the wrapped counter's id."""
        raise NotImplementedError

    def batch(self) -> Batch[LiveCounterBatchContext]:
        """RTINS17: a block whose queued writes are published as one message when it exits."""
        raise NotImplementedError

    def value(self) -> float:
        """RTINS4b: the wrapped counter's value."""
        raise NotImplementedError

    async def increment(self, amount: float = 1) -> None:
        """RTINS14: increments the wrapped counter by `amount`."""
        raise NotImplementedError

    async def decrement(self, amount: float = 1) -> None:
        """RTINS15: decrements the wrapped counter by `amount`."""
        raise NotImplementedError

    def subscribe(self, listener: Callable[[InstanceSubscriptionEvent], None]) -> Subscription:
        """RTINS16: calls `listener` for each update to the wrapped counter, wherever it sits (RTINS16g)."""
        raise NotImplementedError


class PrimitiveInstance(Instance):
    """RTTS10c, RTTS10d: an instance wrapping a primitive value. It has no `subscribe` (RTTS7b)."""

    @overload
    def value(self) -> Primitive: ...

    @overload
    def value(self, expected: type[T]) -> T | None: ...

    def value(self, expected: type | None = None) -> Any:
        """RTINS4c: the wrapped primitive; with `expected`, only if it is of that type, as for
        `PrimitivePathObject.value`."""
        raise NotImplementedError
