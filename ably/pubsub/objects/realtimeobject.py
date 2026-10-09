"""The LiveObjects entry point for a channel (RTO*), reached as `channel.object`."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from ably.pubsub.objects.defaults import GC_GRACE_PERIOD_MS, GC_INTERVAL_MS, ROOT_OBJECT_ID
from ably.pubsub.objects.enums import ObjectsEvent, ObjectsOperationSource, ObjectsSyncState
from ably.pubsub.objects.livecounter import InternalLiveCounter
from ably.pubsub.objects.livemap import InternalLiveMap
from ably.pubsub.objects.liveobject import LiveObject, LiveObjectUpdate
from ably.pubsub.objects.objectmessage import (
    WIRE_FORMAT_JSON,
    WIRE_FORMAT_MSGPACK,
    ObjectOperationAction,
    ObjectsMapSemantics,
)
from ably.pubsub.objects.objectspool import ObjectsPool
from ably.pubsub.objects.pathobjectsubscriptionregister import PathObjectSubscriptionRegister
from ably.pubsub.objects.subscription import StatusSubscription
from ably.pubsub.objects.syncobjectspool import SyncObjectsPool
from ably.pubsub.util.clock import Clock, select_clock

if TYPE_CHECKING:
    from ably.pubsub.objects.objectmessage import ObjectMessage
    from ably.pubsub.objects.pathobject import LiveMapPathObject
    from ably.pubsub.realtime.channel import RealtimeChannel
    from ably.pubsub.types.channelmode import ChannelMode
    from ably.pubsub.types.channelstate import ChannelState
    from ably.pubsub.types.operations import PublishResult
    from ably.pubsub.util.exceptions import AblyException
    from ably.pubsub.util.helper import Timer

log = logging.getLogger(__name__)

# RTO9a2a: the operation actions `_apply_object_messages` applies
_SUPPORTED_ACTIONS = frozenset((
    ObjectOperationAction.MAP_CREATE,
    ObjectOperationAction.MAP_SET,
    ObjectOperationAction.MAP_REMOVE,
    ObjectOperationAction.COUNTER_CREATE,
    ObjectOperationAction.COUNTER_INC,
    ObjectOperationAction.OBJECT_DELETE,
    ObjectOperationAction.MAP_CLEAR,
))

# RTO17b: the event each sync state emits when it is entered
_SYNC_STATE_EVENTS = {
    ObjectsSyncState.SYNCING: ObjectsEvent.SYNCING,
    ObjectsSyncState.SYNCED: ObjectsEvent.SYNCED,
}


class RealtimeObject:
    """RTO*: the objects on one channel, and the entry point to them.

    Each `RealtimeChannel` builds one, reachable as `channel.object`. One can also be built
    with no channel, so that its sync and apply behaviour can be driven directly; such a
    `RealtimeObject` publishes nothing, checks no channel preconditions and schedules no
    timers. `pool` adopts an existing `ObjectsPool`; `clock` defaults to the channel's
    client's clock.

    Construction is cheap and needs no running event loop: the GC timer (RTO10) is
    scheduled on the first ATTACHED, not here.
    """

    def __init__(self, channel: RealtimeChannel | None = None, *, pool: ObjectsPool | None = None,
                 clock: Clock | None = None):
        self._channel = channel
        if clock is None:
            clock = select_clock(channel.ably.options) if channel is not None else Clock()
        self._clock: Clock = clock
        if pool is None:
            pool = ObjectsPool(self, clock=clock)
        else:
            pool.realtime_object = self
        self._objects_pool: ObjectsPool = pool  # RTO3
        self._sync_objects_pool = SyncObjectsPool()  # RTO5f
        self._sync_state = ObjectsSyncState.INITIALIZED  # RTO17a1
        self._buffered_object_operations: list[ObjectMessage] = []  # RTO7a, RTO7a1
        self._applied_on_ack_serials: set[str] = set()  # RTO7b, RTO7b1
        self._current_sync_id: str | None = None  # RTO5a1
        self._current_sync_cursor: str | None = None  # RTO5a1
        self._path_object_subscription_register = PathObjectSubscriptionRegister(self)  # RTO24a
        self._gc_interval_ms: int = GC_INTERVAL_MS  # RTO10a, read each time the GC timer is scheduled
        self._gc_timer: Timer | None = None
        self._last_gc_grace_period_ms: int = GC_GRACE_PERIOD_MS  # RTO10b
        # RTO18: (token, callback) for each `on` call, by event, so that a callback registered
        # twice is called twice (RTO18d) and each StatusSubscription removes only its own
        self._sync_state_listeners: dict[ObjectsEvent, list[tuple[object, Callable[[], None]]]] = {
            event: [] for event in ObjectsEvent
        }

    # Public API

    async def get(self) -> LiveMapPathObject:
        """RTO23: the root of the channel's objects, once they have synced.

        Requires the OBJECT_SUBSCRIBE mode (RTO23a, 40024), attaches the channel if it is not
        attached (RTO23e, RTL33), and waits for the sync state to reach SYNCED (RTO23c).
        Raises AblyException 92008 if the channel enters DETACHED, SUSPENDED or FAILED while
        waiting (RTO23c1), and 90001 if the channel is FAILED (RTL33c).
        """
        raise NotImplementedError

    def on(self, event: ObjectsEvent, callback: Callable[[], None]) -> StatusSubscription:
        """RTO18: calls `callback`, with no arguments, whenever the sync state reaches `event`.

        Registering one callback twice calls it twice (RTO18d).
        """
        event = ObjectsEvent(event)
        token = object()
        self._sync_state_listeners[event].append((token, callback))  # RTO18c

        def deregister() -> None:
            self._sync_state_listeners[event] = [
                entry for entry in self._sync_state_listeners[event] if entry[0] is not token]

        return StatusSubscription(deregister)  # RTO18f

    def off(self, event: ObjectsEvent, callback: Callable[[], None]) -> None:
        """RTO19: deregisters `callback` from `event`, however many times it was registered."""
        event = ObjectsEvent(event)
        self._sync_state_listeners[event] = [
            entry for entry in self._sync_state_listeners[event] if entry[1] != callback]

    # Internal API: inbound protocol messages and channel state

    @property
    def _channel_name(self) -> str | None:
        """The channel's name, which PAOM3b puts on every public message."""
        return self._channel.name if self._channel is not None else None

    @property
    def _wire_format(self) -> str:
        """The wire format the channel's connection decodes with."""
        if self._channel is not None and self._channel.ably.options.use_binary_protocol:
            return WIRE_FORMAT_MSGPACK
        return WIRE_FORMAT_JSON

    def _on_attached(self, has_objects: bool) -> None:
        """RTO4: handles an ATTACHED ProtocolMessage, whatever the channel's state was.

        `has_objects` is the HAS_OBJECTS flag. Starts the GC timer if it is not running
        and there is a channel (RTO10).
        """
        log.debug(f'RealtimeObject._on_attached(): channel={self._channel_name}, has_objects={has_objects}')
        self._set_sync_state(ObjectsSyncState.SYNCING)  # RTO4c
        self._buffered_object_operations = []  # RTO4d
        # The objects an ATTACHED announces arrive in a sync sequence of their own (RTO4a), so a
        # sequence still in flight from before it is abandoned
        self._start_sync_sequence(None)

        if not has_objects:
            # RTO4b
            pool = self._objects_pool
            for object_id in list(pool):
                if object_id != ROOT_OBJECT_ID:
                    del pool[object_id]  # RTO4b1

            # RTO4b2: the root is cleared in place, never replaced
            root = pool.root
            previous_data = root.data
            root.clear_data()
            # RTO4b2a: the removed keys, with no object message; a no-op if the root was empty
            root.notify_updated(InternalLiveMap.diff(previous_data, root.data))

            self._sync_objects_pool.clear()  # RTO4b3
            self._complete_sync()  # RTO4b4

        self._schedule_gc_timer()  # RTO10a

    def _handle_object_sync_messages(self, object_messages: list[ObjectMessage],
                                     sync_channel_serial: str | None) -> None:
        """RTO5: handles the decoded `state` of an OBJECT_SYNC ProtocolMessage."""
        sync_id, sync_cursor = self._parse_sync_channel_serial(sync_channel_serial)  # RTO5a
        self._set_sync_state(ObjectsSyncState.SYNCING)  # RTO5e

        # RTO5a2: a new sequence id starts a new sequence. A message with no sequence id holds a
        # whole sync of its own (RTO5a5), so it too discards anything accumulated before it.
        if sync_id is None or sync_id != self._current_sync_id:
            self._start_sync_sequence(sync_id)
        self._current_sync_cursor = sync_cursor

        self._sync_objects_pool.apply_object_sync_messages(object_messages)  # RTO5f

        # RTO5a4, RTO5a5: the sequence is complete once its cursor is empty
        if not sync_cursor:
            self._complete_sync()

    def _handle_object_messages(self, object_messages: list[ObjectMessage]) -> None:
        """RTO8: handles the decoded `state` of an OBJECT ProtocolMessage, buffering while not SYNCED."""
        if self._sync_state != ObjectsSyncState.SYNCED:
            self._buffered_object_operations.extend(object_messages)  # RTO8a
            return
        self._apply_object_messages(object_messages, ObjectsOperationSource.CHANNEL)  # RTO8b

    def _apply_object_messages(self, object_messages: list[ObjectMessage],
                               source: ObjectsOperationSource) -> None:
        """RTO9: applies operations to the pool, recording LOCAL serials in `_applied_on_ack_serials`."""
        for object_message in object_messages:
            operation = object_message.operation
            if operation is None:
                # RTO9a1
                log.warning(f'RealtimeObject._apply_object_messages(): skipping an object message with no '
                            f'operation; message id={object_message.id}, channel={self._channel_name}')
                continue

            serial = object_message.serial
            if serial is not None and serial in self._applied_on_ack_serials:
                # RTO9a3
                log.debug(f'RealtimeObject._apply_object_messages(): skipping an operation already applied '
                          f'on ACK; serial={serial}, channel={self._channel_name}')
                self._applied_on_ack_serials.discard(serial)
                continue

            if operation.action not in _SUPPORTED_ACTIONS:
                # RTO9a2b
                log.warning(f'RealtimeObject._apply_object_messages(): skipping an object message with an '
                            f'unsupported action; action={operation.action!r}, '
                            f'message id={object_message.id}, channel={self._channel_name}')
                continue

            # RTO9a2a1, RTO9a2a2
            live_object = self._objects_pool.create_zero_value_object_if_not_exists(operation.object_id)
            if live_object is None:
                continue
            applied = live_object.apply_operation(object_message, source)  # RTO9a2a3
            if source == ObjectsOperationSource.LOCAL and applied:
                self._applied_on_ack_serials.add(serial)  # RTO9a2a4

    def _act_on_channel_state(self, state: ChannelState, reason: AblyException | None = None) -> None:
        """RTO27: handles the channel entering `state`, for every state but ATTACHED.

        DETACHED and FAILED clear every object's data (RTO27a); every other state keeps it
        (RTO27b). DETACHED, SUSPENDED and FAILED fail a `get` or a `_publish_and_apply`
        waiting for SYNCED with 92008 (RTO23c1, RTO20e1), with the channel's `error_reason`
        as the cause.
        """
        raise NotImplementedError

    def _set_sync_state(self, state: ObjectsSyncState) -> None:
        """RTO17: moves to `state`, emitting the matching `ObjectsEvent` to `on` listeners (RTO17b)."""
        if state == self._sync_state:
            return
        self._sync_state = state

        event = _SYNC_STATE_EVENTS.get(state)
        if event is None:
            return
        for _, callback in list(self._sync_state_listeners[event]):
            try:
                callback()  # RTO18e
            except Exception:
                log.exception(f'RealtimeObject._set_sync_state(): a {event.value} listener raised; '
                              f'channel={self._channel_name}')

    # Internal API: the sync sequence

    @staticmethod
    def _parse_sync_channel_serial(sync_channel_serial: str | None) -> tuple[str | None, str | None]:
        """RTO5a1: the `(sequence id, cursor)` of an OBJECT_SYNC's `channelSerial`.

        Both are None when the serial is absent (RTO5a5) or has no `:` separator (RTO5a6).
        """
        if sync_channel_serial is None:
            return None, None
        sync_id, separator, sync_cursor = sync_channel_serial.partition(':')
        if not separator:
            log.warning(f'RealtimeObject._parse_sync_channel_serial(): handling an OBJECT_SYNC whose '
                        f'channelSerial has no ":" as having none; channelSerial={sync_channel_serial!r}')
            return None, None
        return sync_id, sync_cursor

    def _start_sync_sequence(self, sync_id: str | None) -> None:
        """RTO5a2: discards whatever an earlier sync sequence accumulated and starts `sync_id`."""
        self._sync_objects_pool.clear()  # RTO5a2a
        self._current_sync_id = sync_id
        self._current_sync_cursor = None

    def _complete_sync(self) -> None:
        """RTO5c: applies the objects the sync sequence delivered, then the operations buffered meanwhile."""
        pool = self._objects_pool
        received_object_ids: set[str] = set()
        updates: list[tuple[LiveObject, LiveObjectUpdate]] = []

        # RTO5c1
        for object_id, object_message in self._sync_objects_pool.entries.items():
            received_object_ids.add(object_id)
            existing = pool.get(object_id)
            if existing is not None:
                # RTO5c1a1, RTO5c1a2
                updates.append((existing, existing.replace_data(object_message)))
                continue

            # RTO5c1b1
            object_state = object_message.object
            if object_state.counter is not None:
                live_object: LiveObject = InternalLiveCounter(object_id)  # RTO5c1b1a
            else:
                semantics = object_state.map.semantics
                live_object = InternalLiveMap(
                    object_id, semantics if semantics is not None else ObjectsMapSemantics.LWW)  # RTO5c1b1b
            pool[object_id] = live_object
            live_object.replace_data(object_message)

        # RTO5c2, RTO5c2a
        for object_id in list(pool):
            if object_id not in received_object_ids and object_id != ROOT_OBJECT_ID:
                del pool[object_id]

        pool.rebuild_parent_references()  # RTO5c10

        # RTO5c7: emitted once every object is in place, so that listeners see the synced state
        for live_object, update in updates:
            live_object.notify_updated(update)

        self._apply_object_messages(self._buffered_object_operations, ObjectsOperationSource.CHANNEL)  # RTO5c6

        self._current_sync_id = None  # RTO5c3
        self._current_sync_cursor = None  # RTO5c3
        self._sync_objects_pool.clear()  # RTO5c4
        self._buffered_object_operations = []  # RTO5c5
        self._applied_on_ack_serials.clear()  # RTO5c9
        self._set_sync_state(ObjectsSyncState.SYNCED)  # RTO5c8

    # Internal API: publishing

    async def _publish(self, object_messages: list[ObjectMessage]) -> PublishResult:
        """RTO15: sends `object_messages` in one OBJECT ProtocolMessage and returns the ACK's result."""
        raise NotImplementedError

    async def _publish_and_apply(self, object_messages: list[ObjectMessage]) -> None:
        """RTO20: publishes `object_messages`, then applies them locally with the serials the ACK
        assigned, as LOCAL operations, once synced."""
        raise NotImplementedError

    async def _get_server_time_ms(self) -> int:
        """RTO16: the current server time, from a persisted offset where one is known (RTO16a)."""
        raise NotImplementedError

    # Internal API: preconditions

    def _throw_if_missing_channel_mode(self, mode: ChannelMode) -> None:
        """RTO2: raises AblyException 40024 if `mode` is neither granted nor, before ATTACHED, requested."""
        raise NotImplementedError

    def _check_access_preconditions(self) -> None:
        """RTO25: OBJECT_SUBSCRIBE (40024), and 90001 if the channel is DETACHED or FAILED."""
        raise NotImplementedError

    def _check_write_preconditions(self) -> None:
        """RTO26: OBJECT_PUBLISH (40024), 90001 if the channel is DETACHED, FAILED or SUSPENDED,
        and 40000 if `echo_messages` is disabled."""
        raise NotImplementedError

    # Internal API: garbage collection

    @property
    def _gc_grace_period_ms(self) -> int:
        """RTO10b: `ConnectionDetails.objects_gc_grace_period` from the latest CONNECTED, or the default."""
        connection_details = None
        if self._channel is not None:
            connection_details = self._channel.ably.connection.connection_details
        if connection_details is not None:
            # RTO10b1, RTO10b2, RTO10b3
            grace_period_ms = connection_details.objects_gc_grace_period
            self._last_gc_grace_period_ms = grace_period_ms if grace_period_ms is not None else GC_GRACE_PERIOD_MS
        return self._last_gc_grace_period_ms

    def _schedule_gc_timer(self) -> None:
        """RTO10a: schedules `_on_gc_interval` on the clock, `_gc_interval_ms` from now, if there is a
        channel and no sweep is scheduled already.

        A `RealtimeObject` with no channel schedules nothing.
        """
        if self._channel is None:
            return
        raise NotImplementedError

    def _on_gc_interval(self) -> None:
        """RTO10c: releases what has been tombstoned for the grace period, and reschedules itself."""
        self._gc_timer = None
        self._objects_pool.collect_garbage(self._gc_grace_period_ms, self._clock.now_ms())
        self._schedule_gc_timer()
