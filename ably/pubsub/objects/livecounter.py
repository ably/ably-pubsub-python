"""The counter CRDT (RTLC*)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ably.pubsub.objects.enums import ObjectsOperationSource
from ably.pubsub.objects.liveobject import CounterUpdate, LiveCounterUpdate, LiveObject
from ably.pubsub.objects.objectmessage import CounterInc, ObjectMessage, ObjectOperation, ObjectOperationAction
from ably.pubsub.objects.valuetypes import validate_amount
from ably.pubsub.util.clock import Clock
from ably.pubsub.util.exceptions import AblyException

if TYPE_CHECKING:
    from ably.pubsub.objects.objectspool import ObjectsPool

log = logging.getLogger(__name__)


class InternalLiveCounter(LiveObject):
    """RTLC1: a counter holding a 64-bit float (RTLC3).

    A new counter has `data` 0 (RTLC4).
    """

    _update_type = LiveCounterUpdate

    def __init__(self, object_id: str, *, pool: ObjectsPool | None = None, clock: Clock | None = None):
        super().__init__(object_id, pool=pool, clock=clock)
        self.data: float = 0.0  # RTLC3, RTLC4b

    def value(self) -> float:
        """RTLC5: the current count."""
        return self.data  # RTLC5c

    async def increment(self, amount: float) -> None:
        """RTLC12: publishes a COUNTER_INC of `amount` through `RealtimeObject._publish_and_apply`.

        Raises AblyException 40003 if `amount` is not a finite number (RTLC12e1); a bool
        is not a number.
        """
        await self._publish_counter_inc(validate_amount(amount))

    async def decrement(self, amount: float) -> None:
        """RTLC13: `increment` by `-amount`, after the same validation (RTLC13c)."""
        await self._publish_counter_inc(-validate_amount(amount))  # RTLC13b, RTLC13c

    async def _publish_counter_inc(self, number: float) -> None:
        realtime_object = self.realtime_object
        if realtime_object is None:
            raise AblyException('Unable to increment a counter that is not on a channel', 400, 40000)
        await realtime_object._publish_and_apply([counter_inc_message(self.object_id, number)])  # RTLC12g

    def apply_operation(self, object_message: ObjectMessage, source: ObjectsOperationSource) -> bool:
        """RTLC7: applies `object_message.operation`, returning whether it was applied (RTLC7g).

        The update is emitted through `notify_updated` (RTLC7d1a, RTLC7d5a, RTLC7d4c).
        """
        if not self.can_apply_operation(object_message):
            # RTLC7b; an operation with invalid serials has already been logged by can_apply_operation
            if object_message.serial and object_message.site_code:
                log.debug(f'InternalLiveCounter.apply_operation(): skipping an operation whose serial is not '
                          f'newer than the one recorded for its site; serial={object_message.serial}, '
                          f'site_code={object_message.site_code}, object_id={self.object_id}')
            return False

        if source == ObjectsOperationSource.CHANNEL:
            # RTLC7c: the serial is recorded whether or not the operation then applies
            self.site_timeserials[object_message.site_code] = object_message.serial

        if self.is_tombstone:
            return False  # RTLC7e

        operation = object_message.operation
        if operation.action == ObjectOperationAction.COUNTER_CREATE:
            update = self.apply_counter_create(operation, object_message)  # RTLC7d1
        elif operation.action == ObjectOperationAction.COUNTER_INC:
            update = self.apply_counter_inc(operation.counter_inc, object_message)  # RTLC7d5
        elif operation.action == ObjectOperationAction.OBJECT_DELETE:
            update = self.tombstone(object_message)  # RTLC7d4, RTLO5
        else:
            # RTLC7d3
            log.warning(f'InternalLiveCounter.apply_operation(): skipping an object operation message with '
                        f'an unsupported action; action={operation.action!r}, object_id={self.object_id}')
            return False

        self.notify_updated(update)  # RTLC7d1a, RTLC7d5a, RTLC7d4c
        return True  # RTLC7d1b, RTLC7d5b, RTLC7d4b

    def replace_data(self, object_message: ObjectMessage) -> LiveCounterUpdate:
        """RTLC6: replaces this counter's data with `object_message.object`, returning the diff."""
        object_state = object_message.object
        self.site_timeserials = dict(object_state.site_timeserials)  # RTLC6a

        if self.is_tombstone:
            return LiveCounterUpdate(noop=True)  # RTLC6e, RTLC6e1

        if object_state.tombstone:
            return self.tombstone(object_message)  # RTLC6f, RTLC6f2

        previous_data = self.data  # RTLC6g
        self.create_operation_is_merged = False  # RTLC6b
        count = object_state.counter.count if object_state.counter is not None else None
        self.data = count if count is not None else 0.0  # RTLC6c
        if object_state.create_op is not None:
            self.merge_initial_value(object_state.create_op, object_message)  # RTLC6d

        update = self.diff(previous_data, self.data)  # RTLC6h
        update.object_message = object_message
        return update

    def apply_counter_create(self, operation: ObjectOperation, object_message: ObjectMessage) -> LiveCounterUpdate:
        """RTLC8: applies a COUNTER_CREATE."""
        if self.create_operation_is_merged:
            # RTLC8b
            log.debug(f'InternalLiveCounter.apply_counter_create(): skipping a COUNTER_CREATE for a counter '
                      f'whose create operation is already merged; object_id={self.object_id}')
            return LiveCounterUpdate(noop=True)
        return self.merge_initial_value(operation, object_message)  # RTLC8c, RTLC8e

    def apply_counter_inc(self, counter_inc: CounterInc | None,
                          object_message: ObjectMessage) -> LiveCounterUpdate:
        """RTLC9: applies a COUNTER_INC.

        A COUNTER_INC with no `number`, or with no payload at all, is a no-op (RTLC9h).
        """
        number = counter_inc.number if counter_inc is not None else None
        if number is None:
            return LiveCounterUpdate(noop=True)  # RTLC9h

        self.data += number  # RTLC9f
        return LiveCounterUpdate(update=CounterUpdate(amount=number), object_message=object_message)  # RTLC9g

    def merge_initial_value(self, operation: ObjectOperation, object_message: ObjectMessage) -> LiveCounterUpdate:
        """RTLC16: merges the initial value of a create operation into this counter.

        The `CounterCreate` is `operation.resolved_counter_create`.
        """
        counter_create = operation.resolved_counter_create
        count = counter_create.count if counter_create is not None else None
        self.create_operation_is_merged = True  # RTLC16b
        if count is None:
            return LiveCounterUpdate(noop=True)  # RTLC16d

        self.data += count  # RTLC16a
        return LiveCounterUpdate(update=CounterUpdate(amount=count), object_message=object_message)  # RTLC16c

    def clear_data(self) -> None:
        """RTO27a1: resets `data` to 0, emitting nothing."""
        self.data = 0.0  # RTLC4b

    @staticmethod
    def diff(previous_data: float, new_data: float, *, for_tombstone: bool = False) -> LiveCounterUpdate:
        """RTLC14: the update between two counter values.

        A zero difference is a no-op (RTLC14c), unless the diff is computed for a tombstone
        (`for_tombstone`, RTLO4e5).
        """
        amount = new_data - previous_data  # RTLC14b
        if amount == 0 and not for_tombstone:
            return LiveCounterUpdate(noop=True)  # RTLC14c
        return LiveCounterUpdate(update=CounterUpdate(amount=amount))


def counter_inc_message(object_id: str, number: float) -> ObjectMessage:
    """RTLC12e: the COUNTER_INC of the counter `object_id` by `number`, a validated amount
    (`validate_amount`)."""
    return ObjectMessage(operation=ObjectOperation(
        action=ObjectOperationAction.COUNTER_INC,  # RTLC12e2
        object_id=object_id,  # RTLC12e3
        counter_inc=CounterInc(number=number),  # RTLC12e5
    ))
