import asyncio
import logging

from pyee.asyncio import AsyncIOEventEmitter

from ably.pubsub.util.helper import is_callable_or_coroutine

# pyee's event emitter doesn't support attaching a listener to all events
# so to patch it, we create a wrapper which uses two event emitters, one
# is used to listen to all events and this arbitrary string is the event name
# used to emit all events on that listener
_all_event = 'all'

log = logging.getLogger(__name__)


def _is_named_event_args(*args):
    return len(args) == 2 and is_callable_or_coroutine(args[1])


def _is_all_event_args(*args):
    return len(args) == 1 and is_callable_or_coroutine(args[0])


class EventEmitter:
    """
    A generic interface for event registration and delivery used in a number of the types in the Realtime client
    library. For example, the Connection object emits events for connection state using the EventEmitter pattern.

    Methods
    -------
    on(*args)
        Attach to channel
    once(*args)
        Detach from channel
    off()
        Subscribe to messages on a channel
    """

    def __init__(self):
        self.__named_event_emitter = AsyncIOEventEmitter()
        self.__all_event_emitter = AsyncIOEventEmitter()
        self.__wrapped_listeners = {}

    def on(self, *args):
        """
        Registers the provided listener for the specified event, if provided, and otherwise for all events.
        If on() is called more than once with the same listener and event, the listener is added multiple times to
        its listener registry. Therefore, as an example, assuming the same listener is registered twice using
        on(), and an event is emitted once, the listener would be invoked twice.

        Parameters
        ----------
        name : str
            The named event to listen for.
        listener : callable
            The event listener.
        """
        if _is_all_event_args(*args):
            event = _all_event
            listener = args[0]
            emitter = self.__all_event_emitter
            # self.__all_event_emitter.add_listener(_all_event, args[0])
        elif _is_named_event_args(*args):
            event = args[0]
            listener = args[1]
            emitter = self.__named_event_emitter
            # self.__named_event_emitter.add_listener(args[0], args[1])
        else:
            raise ValueError("EventEmitter.on(): invalid args")

        if asyncio.iscoroutinefunction(listener):
            async def wrapped_listener(*args, **kwargs):
                try:
                    await listener(*args, **kwargs)
                except Exception as err:
                    log.exception(f'EventEmitter.emit(): uncaught listener exception: {err}')
        else:
            def wrapped_listener(*args, **kwargs):
                try:
                    listener(*args, **kwargs)
                except Exception as err:
                    log.exception(f'EventEmitter.emit(): uncaught listener exception: {err}')

        self.__wrapped_listeners[listener] = wrapped_listener

        emitter.add_listener(event, wrapped_listener)

    def once(self, *args):
        """
        Registers the provided listener for the first event that is emitted. If once() is called more than once
        with the same listener, the listener is added multiple times to its listener registry. Therefore, as an
        example, assuming the same listener is registered twice using once(), and an event is emitted once, the
        listener would be invoked twice. However, all subsequent events emitted would not invoke the listener as
        once() ensures that each registration is only invoked once.

        Parameters
        ----------
        name : str
            The named event to listen for.
        listener : callable
            The event listener.
        """
        if _is_all_event_args(*args):
            event = _all_event
            listener = args[0]
            emitter = self.__all_event_emitter
            # self.__all_event_emitter.add_listener(_all_event, args[0])
        elif _is_named_event_args(*args):
            event = args[0]
            listener = args[1]
            emitter = self.__named_event_emitter
            # self.__named_event_emitter.add_listener(args[0], args[1])
        else:
            raise ValueError("EventEmitter.on(): invalid args")

        if asyncio.iscoroutinefunction(listener):
            async def wrapped_listener(*args, **kwargs):
                try:
                    await listener(*args, **kwargs)
                except Exception as err:
                    log.exception(f'EventEmitter.emit(): uncaught listener exception: {err}')
        else:
            def wrapped_listener(*args, **kwargs):
                try:
                    listener(*args, **kwargs)
                except Exception as err:
                    log.exception(f'EventEmitter.emit(): uncaught listener exception: {err}')

        self.__wrapped_listeners[listener] = wrapped_listener

        emitter.once(event, wrapped_listener)

    def off(self, *args):
        """
        Removes all registrations that match both the specified listener and, if provided, the specified event.
        If called with no arguments, deregisters all registrations, for all events and listeners.

        Parameters
        ----------
        name : str
            The named event to listen for.
        listener : callable
            The event listener.
        """
        if len(args) == 0:
            self.__all_event_emitter.remove_all_listeners()
            self.__named_event_emitter.remove_all_listeners()
            return
        elif _is_all_event_args(*args):
            event = _all_event
            listener = args[0]
            emitter = self.__all_event_emitter
        elif _is_named_event_args(*args):
            event = args[0]
            listener = args[1]
            emitter = self.__named_event_emitter
        else:
            raise ValueError("EventEmitter.once(): invalid args")

        wrapped_listener = self.__wrapped_listeners.get(listener)

        if wrapped_listener is None:
            return

        emitter.remove_listener(event, wrapped_listener)
        self.__wrapped_listeners[listener] = None

    async def once_async(self, state=None):
        future = asyncio.Future()

        def on_state_change(*args):
            future.set_result(*args)

        if state is not None:
            self.once(state, on_state_change)
        else:
            self.once(on_state_change)

        state_change = await future

        return state_change

    def _emit(self, *args):
        self.__named_event_emitter.emit(*args)
        self.__all_event_emitter.emit(_all_event, *args[1:])
