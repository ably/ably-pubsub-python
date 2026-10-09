"""Batched writes, published as one message (RTPO20, RTINS17, RTBC*).

`batch()` on a typed path or instance returns a `Batch`, an async context manager whose
`__aenter__` checks the write preconditions and resolves the target (RTPO20b-d,
RTINS17b-d) and returns the matching `BatchContext`. The context's write methods are
synchronous and only queue; `__aexit__` publishes everything queued as one message
(RTBC16d) when the block exits without raising, and closes the batch either way
(RTPO20g). Any use of a context after its batch has closed raises `AblyException` 40000
(RTBC16e).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable, Generic, TypeVar, overload

if TYPE_CHECKING:
    from ably.pubsub.objects.instance import Instance
    from ably.pubsub.objects.objectmessage import ObjectMessage
    from ably.pubsub.objects.realtimeobject import RealtimeObject
    from ably.pubsub.objects.valuetypes import LiveMapValue, Primitive, T

C = TypeVar('C', bound='BatchContext')


class Batch(Generic[C]):
    """RTBC16: the `async with` block a `batch()` call returns."""

    def __init__(self, realtime_object: RealtimeObject, resolve: Callable[[], Instance]):
        self._realtime_object = realtime_object
        # Resolves the batch's target when the block is entered (RTPO20c, RTINS17c)
        self._resolve = resolve
        self._root_context: RootBatchContext | None = None

    async def __aenter__(self) -> C:
        """RTPO20b-d, RTINS17b-d: checks the write preconditions, resolves the target and opens
        the batch."""
        raise NotImplementedError

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """RTPO20f, RTPO20g, RTBC16d: publishes the queued writes unless the block raised, and
        closes the batch either way."""
        raise NotImplementedError


class RootBatchContext:
    """RTBC16: the state one batch shares across every context opened from it."""

    def __init__(self, realtime_object: RealtimeObject, instance: Instance):
        self.realtime_object = realtime_object
        self.instance = instance
        self.wrapped_instances: dict[str, BatchContext] = {}  # RTBC16a
        self.queued_message_constructors: list[Callable[[], Awaitable[list[ObjectMessage]]]] = []  # RTBC16b
        self.closed = False

    def wrap_instance(self, instance: Instance) -> BatchContext:
        """RTBC16c: the context for `instance`, one per object id."""
        raise NotImplementedError

    async def flush(self) -> None:
        """RTBC16d: closes the batch, builds the queued messages and publishes them as one message,
        if there are any."""
        raise NotImplementedError

    def close(self) -> None:
        """RTBC16e: closes the batch, so that every later use of its contexts raises 40000."""
        raise NotImplementedError


class BatchContext:
    """RTBC1: a synchronous view of an `Instance` inside a batch (RTBC2a)."""

    def __init__(self, root_context: RootBatchContext, instance: Instance):
        self._root_context = root_context  # RTBC2b
        self._instance = instance  # RTBC2a

    @property
    def id(self) -> str | None:
        """RTBC3: the wrapped object's id."""
        raise NotImplementedError

    def get(self, key: str) -> BatchContext | None:
        """RTBC4: the context for the value at `key` of the wrapped map, or None."""
        raise NotImplementedError

    def compact(self) -> Any:
        """RTBC10: `Instance.compact` on the wrapped instance."""
        raise NotImplementedError

    def compact_json(self) -> Any:
        """RTBC11: `Instance.compact_json` on the wrapped instance."""
        raise NotImplementedError

    def as_live_map(self) -> LiveMapBatchContext:
        """RTBC1a: this context as a map. Raises AblyException 92007 if it wraps something else."""
        raise NotImplementedError

    def as_live_counter(self) -> LiveCounterBatchContext:
        """RTBC1a: this context as a counter. Raises AblyException 92007 if it wraps something else."""
        raise NotImplementedError

    def as_primitive(self) -> PrimitiveBatchContext:
        """RTBC1a: this context as a primitive. Raises AblyException 92007 if it wraps something else."""
        raise NotImplementedError


class LiveMapBatchContext(BatchContext):
    """RTBC1a: a batch context wrapping a map."""

    def entries(self) -> list[tuple[str, BatchContext]]:
        """RTBC6: `(key, context)` for each entry of the map."""
        raise NotImplementedError

    def keys(self) -> list[str]:
        """RTBC7: the keys of the map."""
        raise NotImplementedError

    def values(self) -> list[BatchContext]:
        """RTBC8: a context for each entry of the map."""
        raise NotImplementedError

    def size(self) -> int | None:
        """RTBC9: the number of entries in the map."""
        raise NotImplementedError

    def set(self, key: str, value: LiveMapValue) -> None:
        """RTBC12: queues a MAP_SET of `key`."""
        raise NotImplementedError

    def remove(self, key: str) -> None:
        """RTBC13: queues a MAP_REMOVE of `key`."""
        raise NotImplementedError


class LiveCounterBatchContext(BatchContext):
    """RTBC1a: a batch context wrapping a counter."""

    def value(self) -> float:
        """RTBC5: the counter's value."""
        raise NotImplementedError

    def increment(self, amount: float = 1) -> None:
        """RTBC14: queues a COUNTER_INC of `amount`."""
        raise NotImplementedError

    def decrement(self, amount: float = 1) -> None:
        """RTBC15: queues a COUNTER_INC of `-amount`."""
        raise NotImplementedError


class PrimitiveBatchContext(BatchContext):
    """RTBC1a: a batch context wrapping a primitive."""

    @overload
    def value(self) -> Primitive: ...

    @overload
    def value(self, expected: type[T]) -> T | None: ...

    def value(self, expected: type | None = None) -> Any:
        """RTBC5: the wrapped primitive; with `expected`, only if it is of that type."""
        raise NotImplementedError
