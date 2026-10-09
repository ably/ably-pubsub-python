"""Batched writes, published as one message (RTPO20, RTINS17, RTBC*).

`batch()` on a typed path or instance returns a `Batch`, an async context manager whose
`__aenter__` checks the write preconditions and resolves the target (RTPO20b-d,
RTINS17b-d) and returns the matching `BatchContext`. Inside the block every context
method is synchronous: reads resolve against the objects as they are held locally, so
they do not see the writes queued before them, and writes only queue. `__aexit__`
publishes everything queued as one message (RTBC16d) when the block exits without
raising, and closes the batch either way (RTPO20g). Any use of a context after its batch
has closed raises `AblyException` 40000 (RTBC16e).

A write validates its arguments when it is called, so an invalid one raises inside the
block and nothing is published. A `LiveMap` or `LiveCounter` value is evaluated when the
batch is published, because its object id needs the server time (RTO16): an invalid
value inside one raises from the end of the block, and nothing is published then either.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable, Generic, TypeVar, overload

from ably.pubsub.objects.enums import ValueType
from ably.pubsub.objects.instance import (
    Instance,
    LiveCounterInstance,
    LiveMapInstance,
    PrimitiveInstance,
    expected_value_type,
    primitive_value,
    value_type_of,
)
from ably.pubsub.objects.livecounter import _validate_amount
from ably.pubsub.objects.objectmessage import (
    CounterInc,
    MapRemove,
    MapSet,
    ObjectData,
    ObjectMessage,
    ObjectOperation,
    ObjectOperationAction,
)
from ably.pubsub.objects.valuetypes import LiveCounter, LiveMap, evaluate, primitive_to_object_data, validate_key
from ably.pubsub.util.exceptions import AblyException

if TYPE_CHECKING:
    from ably.pubsub.objects.realtimeobject import RealtimeObject
    from ably.pubsub.objects.valuetypes import LiveMapValue, Primitive, T

    # RTBC16b: builds the ObjectMessages of one queued write when the batch is flushed
    MessageConstructor = Callable[[], Awaitable[list[ObjectMessage]]]

C = TypeVar('C', bound='BatchContext')
V = TypeVar('V', bound='BatchContext')


class Batch(Generic[C]):
    """RTBC16: the `async with` block a `batch()` call returns.

    `resolve` returns the value the batch acts on, or None, and is called when the block
    is entered; the value must be the live object a `context_type` wraps. `description`
    names the target in the error raised when it is not. A `Batch` opens one batch, so it
    can be entered once.
    """

    def __init__(self, realtime_object: RealtimeObject, resolve: Callable[[], Any], context_type: type[C],
                 description: str):
        self._realtime_object = realtime_object
        self._resolve = resolve
        self._context_type = context_type
        self._description = description
        self._root_context: RootBatchContext | None = None

    async def __aenter__(self) -> C:
        """RTPO20b-d, RTINS17b-d: checks the write preconditions, resolves the target and opens
        the batch.

        Raises AblyException 92007 if the target is not a live object of the type the batch
        was taken on (RTPO20c, RTINS17c), and RuntimeError if this batch was entered before.
        """
        if self._root_context is not None:
            raise RuntimeError('This batch has already been entered; call batch() again for another')
        self._realtime_object._check_write_preconditions()  # RTPO20b, RTINS17b

        value = self._resolve()
        expected = self._context_type._value_type
        actual = value_type_of(value) if value is not None else None
        if actual is not expected:
            # RTPO20c, RTINS17c: nothing, a primitive or a live object of another type
            reason = 'it does not resolve' if actual is None else f'it is of type {actual.value}'
            raise AblyException(f'Cannot batch operations on {self._description} as a {expected.value}: '
                                f'{reason}', 400, 92007)

        instance = Instance._wrap(self._realtime_object, value)
        self._root_context = RootBatchContext(self._realtime_object, instance)  # RTPO20d, RTINS17d
        return self._root_context.wrap_instance(instance)

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """RTPO20f, RTPO20g, RTBC16d: publishes the queued writes unless the block raised, and
        closes the batch either way.

        An exception raised in the block propagates, and nothing is published.
        """
        if exc_type is not None:
            self._root_context.close()  # RTPO20g
            return
        await self._root_context.flush()  # RTPO20f, RTINS17f


class RootBatchContext:
    """RTBC16: the state one batch shares across every context opened from it."""

    def __init__(self, realtime_object: RealtimeObject, instance: Instance):
        self.realtime_object = realtime_object
        self.instance = instance
        self.wrapped_instances: dict[str, BatchContext] = {}  # RTBC16a
        self.queued_message_constructors: list[MessageConstructor] = []  # RTBC16b
        self.closed = False

    def wrap_instance(self, instance: Instance) -> BatchContext:
        """RTBC16c: the context for `instance`, one per object id.

        The context is the subclass matching the `Instance` subclass, so a `LiveMapInstance`
        is wrapped in a `LiveMapBatchContext`.
        """
        object_id = instance.id
        if object_id is not None:
            context = self.wrapped_instances.get(object_id)
            if context is not None:
                return context

        context = _context_type_for(instance)(self, instance)
        if object_id is not None:
            self.wrapped_instances[object_id] = context
        return context

    def queue_message_constructor(self, constructor: MessageConstructor) -> None:
        """RTBC16b: queues `constructor`, which builds the ObjectMessages of one write when the
        batch is flushed."""
        self.queued_message_constructors.append(constructor)

    async def flush(self) -> None:
        """RTBC16d: closes the batch, builds the queued messages in the order they were queued and
        publishes them in one message through `RealtimeObject._publish_and_apply`, if there are
        any.

        Raises whatever building or publishing the messages raises. Nothing is published if
        building any of them fails.
        """
        try:
            self.close()
            if self.queued_message_constructors:
                # The block may have awaited since its writes checked the write preconditions (RTO26)
                self.realtime_object._check_write_preconditions()
            object_messages: list[ObjectMessage] = []
            for construct in self.queued_message_constructors:
                object_messages.extend(await construct())
            if object_messages:
                await self.realtime_object._publish_and_apply(object_messages)
        finally:
            self.wrapped_instances.clear()
            self.queued_message_constructors.clear()

    def close(self) -> None:
        """RTBC16e: closes the batch, so that every later use of its contexts raises 40000."""
        self.closed = True


class BatchContext:
    """RTBC1: a synchronous view of an `Instance` inside a batch (RTBC2a).

    As on an `Instance`, the view helpers are checked: asking for a type the context does
    not wrap raises `AblyException` 92007 (RTBC1a, RTTS9d). Reads check the access
    preconditions (RTO25), and writes the write preconditions (RTO26), before checking
    that the batch is still open.
    """

    # The type of live object that a batch opening this subclass of context acts on
    _value_type: ValueType | None = None

    def __init__(self, root_context: RootBatchContext, instance: Instance):
        self._root_context = root_context  # RTBC2b
        self._instance = instance  # RTBC2a

    @property
    def id(self) -> str | None:
        """RTBC3: the wrapped object's id, or None for a primitive."""
        self._throw_if_closed()  # RTBC3b
        return self._instance.id  # RTBC3a

    def get(self, key: str) -> BatchContext | None:
        """RTBC4: the context for the value at `key` of the wrapped map, or None.

        Raises AblyException 40003 if `key` is not a string.
        """
        self._realtime_object._check_access_preconditions()  # RTBC4b
        self._throw_if_closed()  # RTBC4c
        instance = self._instance.get(key)  # RTBC4d
        if instance is None:
            return None
        return self._root_context.wrap_instance(instance)  # RTBC4e

    def compact(self) -> Any:
        """RTBC10: `Instance.compact` on the wrapped instance."""
        self._realtime_object._check_access_preconditions()  # RTBC10a
        self._throw_if_closed()  # RTBC10b
        return self._instance.compact()  # RTBC10c

    def compact_json(self) -> Any:
        """RTBC11: `Instance.compact_json` on the wrapped instance."""
        self._realtime_object._check_access_preconditions()  # RTBC11a
        self._throw_if_closed()  # RTBC11b
        return self._instance.compact_json()  # RTBC11c

    def as_live_map(self) -> LiveMapBatchContext:
        """RTBC1a: this context as a map. Raises AblyException 92007 if it wraps something else."""
        self._throw_if_closed()  # RTBC16e
        return self._view(LiveMapBatchContext, self._instance.as_live_map())  # RTTS9d

    def as_live_counter(self) -> LiveCounterBatchContext:
        """RTBC1a: this context as a counter. Raises AblyException 92007 if it wraps something else."""
        self._throw_if_closed()  # RTBC16e
        return self._view(LiveCounterBatchContext, self._instance.as_live_counter())  # RTTS9d

    def as_primitive(self) -> PrimitiveBatchContext:
        """RTBC1a: this context as a primitive. Raises AblyException 92007 if it wraps something else."""
        self._throw_if_closed()  # RTBC16e
        return self._view(PrimitiveBatchContext, self._instance.as_primitive())  # RTTS9d

    @property
    def _realtime_object(self) -> RealtimeObject:
        return self._root_context.realtime_object

    def _view(self, context_type: type[V], instance: Instance) -> V:
        """This context if it is a `context_type`, else a `context_type` wrapping `instance`."""
        if isinstance(self, context_type):
            return self
        return context_type(self._root_context, instance)

    def _throw_if_closed(self) -> None:
        """RTBC16e: raises AblyException 40000 once the batch has closed."""
        if self._root_context.closed:
            raise AblyException('Batch is closed: a batch context can only be used inside its batch block',
                                400, 40000)

    def _queue(self, *object_messages: ObjectMessage) -> None:
        """Queues a write whose ObjectMessages are already built."""
        async def construct() -> list[ObjectMessage]:
            return list(object_messages)

        self._root_context.queue_message_constructor(construct)


class LiveMapBatchContext(BatchContext):
    """RTBC1a: a batch context wrapping a map.

    A context of this type only ever wraps a map, so its writes never find another type
    (RTBC12d, RTBC13d).
    """

    _instance: LiveMapInstance
    _value_type = ValueType.LIVE_MAP

    def entries(self) -> list[tuple[str, BatchContext]]:
        """RTBC6: `(key, context)` for each entry of the map, as `LiveMapInstance.entries` gives them."""
        self._realtime_object._check_access_preconditions()  # RTBC6a
        self._throw_if_closed()  # RTBC6b
        wrap_instance = self._root_context.wrap_instance
        return [(key, wrap_instance(instance)) for key, instance in self._instance.entries()]  # RTBC6c, RTBC6d

    def keys(self) -> list[str]:
        """RTBC7: the keys of the map."""
        self._realtime_object._check_access_preconditions()  # RTBC7a
        self._throw_if_closed()  # RTBC7b
        return self._instance.keys()  # RTBC7c

    def values(self) -> list[BatchContext]:
        """RTBC8: a context for each entry of the map, as `entries` wraps them."""
        return [context for _, context in self.entries()]  # RTBC8a-RTBC8c

    def size(self) -> int | None:
        """RTBC9: the number of entries in the map."""
        self._realtime_object._check_access_preconditions()  # RTBC9a
        self._throw_if_closed()  # RTBC9b
        return self._instance.size()  # RTBC9c

    def set(self, key: str, value: LiveMapValue) -> None:
        """RTBC12: queues a MAP_SET of `key`, preceded by the creates a `LiveMap` or `LiveCounter`
        value evaluates to.

        Raises AblyException 40003 for a key that is not a string and 40013 for a value of
        an unsupported type (RTLM20e1). A `LiveMap` or `LiveCounter` value is evaluated when
        the batch is flushed, so it is the end of the block that raises for an invalid value
        inside one (RTLMV4).
        """
        realtime_object = self._realtime_object
        realtime_object._check_write_preconditions()  # RTBC12b
        self._throw_if_closed()  # RTBC12c
        validate_key(key)  # RTLM20e1
        object_id = self._instance.id

        if not isinstance(value, (LiveCounter, LiveMap)):
            self._queue(_map_set(object_id, key, primitive_to_object_data(value)))  # RTBC12e, RTLM20e7b-f
            return

        async def construct() -> list[ObjectMessage]:
            # RTLM20e7g1: the creates the value evaluates to, their object ids from the server time
            server_time_ms = await realtime_object._get_server_time_ms()
            object_messages = evaluate(value, server_time_ms)
            data = ObjectData(object_id=object_messages[-1].operation.object_id)  # RTLM20e7g2
            return [*object_messages, _map_set(object_id, key, data)]

        self._root_context.queue_message_constructor(construct)  # RTBC12e

    def remove(self, key: str) -> None:
        """RTBC13: queues a MAP_REMOVE of `key`.

        Raises AblyException 40003 for a key that is not a string (RTLM21e1).
        """
        self._realtime_object._check_write_preconditions()  # RTBC13b
        self._throw_if_closed()  # RTBC13c
        validate_key(key)  # RTLM21e1
        # RTBC13e
        self._queue(ObjectMessage(operation=ObjectOperation(
            action=ObjectOperationAction.MAP_REMOVE,  # RTLM21e2
            object_id=self._instance.id,  # RTLM21e3
            map_remove=MapRemove(key=key),  # RTLM21e5
        )))


class LiveCounterBatchContext(BatchContext):
    """RTBC1a: a batch context wrapping a counter.

    A context of this type only ever wraps a counter, so its writes never find another
    type (RTBC14d, RTBC15d).
    """

    _instance: LiveCounterInstance
    _value_type = ValueType.LIVE_COUNTER

    def value(self) -> float:
        """RTBC5: the counter's value."""
        self._realtime_object._check_access_preconditions()  # RTBC5a
        self._throw_if_closed()  # RTBC5b
        return self._instance.value()  # RTBC5c

    def increment(self, amount: float = 1) -> None:
        """RTBC14: queues a COUNTER_INC of `amount`.

        Raises AblyException 40003 unless `amount` is a finite number (RTLC12e1); a bool is
        not a number.
        """
        self._realtime_object._check_write_preconditions()  # RTBC14b
        self._throw_if_closed()  # RTBC14c
        # RTBC14e
        self._queue(ObjectMessage(operation=ObjectOperation(
            action=ObjectOperationAction.COUNTER_INC,  # RTLC12e2
            object_id=self._instance.id,  # RTLC12e3
            counter_inc=CounterInc(number=_validate_amount(amount)),  # RTLC12e1, RTLC12e5
        )))

    def decrement(self, amount: float = 1) -> None:
        """RTBC15: queues a COUNTER_INC of `-amount`, after the same validation as `increment`."""
        self._realtime_object._check_write_preconditions()  # RTBC15b
        self._throw_if_closed()  # RTBC15c
        self.increment(-_validate_amount(amount))  # RTBC15e


class PrimitiveBatchContext(BatchContext):
    """RTBC1a: a batch context wrapping a primitive."""

    @overload
    def value(self) -> Primitive: ...

    @overload
    def value(self, expected: type[T]) -> T | None: ...

    def value(self, expected: type | None = None) -> Any:
        """RTBC5: the wrapped primitive; with `expected`, only if it is of that type, as for
        `PrimitiveInstance.value`."""
        value_type = expected_value_type(expected)
        self._realtime_object._check_access_preconditions()  # RTBC5a
        self._throw_if_closed()  # RTBC5b
        return primitive_value(self._instance._value, value_type)  # RTBC5c


def _context_type_for(instance: Instance) -> type[BatchContext]:
    """RTBC1a: the `BatchContext` subclass matching the `Instance` subclass of `instance`."""
    if isinstance(instance, LiveMapInstance):
        return LiveMapBatchContext
    if isinstance(instance, LiveCounterInstance):
        return LiveCounterBatchContext
    if isinstance(instance, PrimitiveInstance):
        return PrimitiveBatchContext
    return BatchContext


def _map_set(object_id: str, key: str, data: ObjectData) -> ObjectMessage:
    """RTLM20e: the ObjectMessage setting `key` of the map `object_id` to `data`."""
    return ObjectMessage(operation=ObjectOperation(
        action=ObjectOperationAction.MAP_SET,  # RTLM20e2
        object_id=object_id,  # RTLM20e3
        map_set=MapSet(key=key, value=data),  # RTLM20e6, RTLM20e7
    ))
