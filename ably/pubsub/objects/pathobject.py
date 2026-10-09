"""Path-addressed views onto a channel's objects (RTPO*, RTTS3-RTTS6).

A `PathObject` holds a path from the root map and resolves it each time a method reads
or writes through it, so it follows whatever object is at that path at the time. The
base class carries what does not depend on the type at the path, navigation included;
`as_live_map()`, `as_live_counter()` and `as_primitive()` return the typed views, without
checking what the path resolves to (RTTS5d).

Reads never raise for a path that does not resolve or that resolves to another type:
they return None, or an empty list for the collection methods (RTPO3c1, RTTS5d1). Writes
raise `AblyException` 92005 for a path that does not resolve and 92007 for one that
resolves to the wrong type (RTPO3c2, RTTS5d2). Every read except `path`, `get` and `at`
checks the access preconditions (RTO25), and every write the write preconditions (RTO26).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Sequence, overload

if TYPE_CHECKING:
    from ably.pubsub.objects.batch import Batch, LiveCounterBatchContext, LiveMapBatchContext
    from ably.pubsub.objects.enums import ValueType
    from ably.pubsub.objects.instance import Instance
    from ably.pubsub.objects.livemap import InternalLiveMap
    from ably.pubsub.objects.publicmessage import ObjectMessage
    from ably.pubsub.objects.realtimeobject import RealtimeObject
    from ably.pubsub.objects.subscription import Subscription
    from ably.pubsub.objects.valuetypes import LiveMapValue, Primitive, T


@dataclass
class PathObjectSubscriptionEvent:
    """RTPO19e: what a `PathObject.subscribe` listener receives."""

    object: PathObject  # RTPO19e1: the path where the change occurred
    message: ObjectMessage | None = None  # RTPO19e2


class PathObject:
    """RTPO1, RTTS3: a lazy reference to whatever is at a path from the root map."""

    def __init__(self, realtime_object: RealtimeObject, root: InternalLiveMap, path: Sequence[str]):
        self._realtime_object = realtime_object
        self._root = root  # RTPO2b
        self._path: list[str] = list(path)  # RTPO2a

    def path(self) -> str:
        """RTPO4: the path as a dotted string, with dots in segments escaped as `\\.`."""
        raise NotImplementedError

    def type(self) -> ValueType | None:
        """RTTS4b: the type of what the path resolves to, or None if it resolves to nothing."""
        raise NotImplementedError

    def exists(self) -> bool:
        """RTTS4a: whether the path resolves to anything."""
        raise NotImplementedError

    def get(self, key: str) -> PathObject:
        """RTPO5: the path one key further down. Navigational only (RTPO5d).

        Raises AblyException 40003 if `key` is not a string (RTPO5b).
        """
        raise NotImplementedError

    def at(self, path: str | Sequence[str]) -> PathObject:
        """RTPO6: the path further down by a dotted string, `\\.` escaping a literal dot (RTPO6b),
        or by a sequence of segments taken as they are.

        Raises AblyException 40003 for anything else.
        """
        raise NotImplementedError

    def instance(self) -> Instance | None:
        """RTPO8: an `Instance` wrapping what the path resolves to, or None if it resolves to nothing.

        The instance is the subclass matching the resolved value (`LiveMapInstance`,
        `LiveCounterInstance` or `PrimitiveInstance`).
        """
        raise NotImplementedError

    def compact(self) -> Any:
        """RTPO13: a plain snapshot of what the path resolves to, or None."""
        raise NotImplementedError

    def compact_json(self) -> Any:
        """RTPO14: `compact`, with binary as base64 and cycles as `{'objectId': ...}`."""
        raise NotImplementedError

    def subscribe(self, listener: Callable[[PathObjectSubscriptionEvent], None], *,
                  depth: int | None = None) -> Subscription:
        """RTPO19: calls `listener` for changes at this path or, within `depth` levels, below it.

        Raises AblyException 40003 if `depth` is given and is not a positive integer
        (RTPO19c1a). Has no effect on the channel (RTPO19g).
        """
        raise NotImplementedError

    def as_live_map(self) -> LiveMapPathObject:
        """RTTS5a: this path, viewed as a map."""
        raise NotImplementedError

    def as_live_counter(self) -> LiveCounterPathObject:
        """RTTS5b: this path, viewed as a counter."""
        raise NotImplementedError

    def as_primitive(self) -> PrimitivePathObject:
        """RTTS5c, RTTS6h: this path, viewed as a primitive."""
        raise NotImplementedError


class LiveMapPathObject(PathObject):
    """RTTS6a: a path expected to resolve to a map."""

    def batch(self) -> Batch[LiveMapBatchContext]:
        """RTPO20: a block whose queued writes are published as one message when it exits.

        Entering raises AblyException 92007 if the path does not resolve to a live object
        (RTPO20c).
        """
        raise NotImplementedError

    def entries(self) -> list[tuple[str, PathObject]]:
        """RTPO9: `(key, path)` for each key of the map, or `[]`."""
        raise NotImplementedError

    def keys(self) -> list[str]:
        """RTPO10: the keys of the map, or `[]`."""
        raise NotImplementedError

    def values(self) -> list[PathObject]:
        """RTPO11: a path for each key of the map, or `[]`."""
        raise NotImplementedError

    def size(self) -> int | None:
        """RTPO12: the number of entries in the map, or None."""
        raise NotImplementedError

    async def set(self, key: str, value: LiveMapValue) -> None:
        """RTPO15: sets `key` in the map at this path."""
        raise NotImplementedError

    async def remove(self, key: str) -> None:
        """RTPO16: removes `key` from the map at this path."""
        raise NotImplementedError


class LiveCounterPathObject(PathObject):
    """RTTS6b: a path expected to resolve to a counter."""

    def batch(self) -> Batch[LiveCounterBatchContext]:
        """RTPO20: a block whose queued writes are published as one message when it exits."""
        raise NotImplementedError

    def value(self) -> float | None:
        """RTTS6b: the counter's value, or None if the path does not resolve to a counter."""
        raise NotImplementedError

    async def increment(self, amount: float = 1) -> None:
        """RTPO17: increments the counter at this path by `amount`."""
        raise NotImplementedError

    async def decrement(self, amount: float = 1) -> None:
        """RTPO18: decrements the counter at this path by `amount`."""
        raise NotImplementedError


class PrimitivePathObject(PathObject):
    """RTTS6c, RTTS6h: a path expected to resolve to a primitive."""

    @overload
    def value(self) -> Primitive | None: ...

    @overload
    def value(self, expected: type[T]) -> T | None: ...

    def value(self, expected: type | None = None) -> Any:
        """RTPO7, RTTS6c: the primitive at this path, or None.

        With `expected` (one of `str`, `float`, `bool`, `bytes`, `list`, `dict`) the value is
        returned only if it is of that type, judged by its wire type, so a boolean is never
        a number. Any other `expected` raises TypeError.
        """
        raise NotImplementedError
