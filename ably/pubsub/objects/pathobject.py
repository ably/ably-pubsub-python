"""Path-addressed views onto a channel's objects (RTPO*, RTTS3-RTTS6).

A `PathObject` holds a path from the root map and resolves it each time a method reads
or writes through it, so it follows whatever object is at that path at the time. The
base class carries what does not depend on the type at the path, navigation included;
`as_live_map()`, `as_live_counter()` and `as_primitive()` return the typed views, without
checking what the path resolves to (RTTS5d).

Reads never raise for a path that does not resolve or that resolves to another type:
they return None, or an empty list for the collection methods (RTPO3c1, RTTS5d1). Writes
raise `AblyException` 92005 for a path that does not resolve and 92007 for one that
resolves to the wrong type (RTPO3c2, RTTS5d2). Every read and `subscribe` checks the
access preconditions (RTO25), and every write the write preconditions (RTO26), before
resolving the path; navigation and the view helpers check nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, overload

from ably.pubsub.objects.batch import Batch, LiveCounterBatchContext, LiveMapBatchContext
from ably.pubsub.objects.instance import (
    Instance,
    compact_value,
    expected_value_type,
    primitive_value,
    value_type_of,
)
from ably.pubsub.objects.livecounter import InternalLiveCounter
from ably.pubsub.objects.livemap import InternalLiveMap
from ably.pubsub.util.exceptions import AblyException

if TYPE_CHECKING:
    from ably.pubsub.objects.enums import ValueType
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

    def __repr__(self) -> str:
        return f'{type(self).__name__}({self.path()!r})'

    def path(self) -> str:
        """RTPO4: the path as a dotted string, with dots in segments escaped as `\\.`."""
        # RTPO4a, RTPO4b; the empty path is the empty string (RTPO4c)
        return '.'.join(segment.replace('.', '\\.') for segment in self._path)

    def type(self) -> ValueType | None:
        """RTTS4b: the type of what the path resolves to, or None if it resolves to nothing."""
        self._realtime_object._check_access_preconditions()  # RTTS4b1
        resolved = self._resolve()  # RTTS4b2
        return value_type_of(resolved) if resolved is not None else None  # RTTS4b3

    def exists(self) -> bool:
        """RTTS4a: whether the path resolves to anything."""
        self._realtime_object._check_access_preconditions()  # RTTS4a1
        return self._resolve() is not None  # RTTS4a2, RTTS4a3

    def get(self, key: str) -> PathObject:
        """RTPO5: the path one key further down. Navigational only (RTPO5d).

        Raises AblyException 40003 if `key` is not a string (RTPO5b).
        """
        if not isinstance(key, str):
            raise AblyException(f'Path key must be a string, not {type(key).__name__}', 400, 40003)
        return PathObject(self._realtime_object, self._root, [*self._path, key])  # RTPO5c

    def at(self, path: str | Sequence[str]) -> PathObject:
        """RTPO6: the path further down by a dotted string, `\\.` escaping a literal dot (RTPO6b),
        or by a sequence of segments taken as they are.

        Raises AblyException 40003 for anything else.
        """
        if isinstance(path, str):
            segments = _parse_path(path)  # RTPO6b
        elif (isinstance(path, Sequence) and not isinstance(path, (bytes, bytearray))
              and all(isinstance(segment, str) for segment in path)):
            segments = list(path)
        else:
            raise AblyException(f'Path must be a string or a sequence of strings, not {type(path).__name__}',
                                400, 40003)
        return PathObject(self._realtime_object, self._root, [*self._path, *segments])  # RTPO6c

    def instance(self) -> Instance | None:
        """RTPO8: an `Instance` wrapping what the path resolves to, or None if it resolves to nothing.

        The instance is the subclass matching the resolved value (`LiveMapInstance`,
        `LiveCounterInstance` or `PrimitiveInstance`).
        """
        self._realtime_object._check_access_preconditions()  # RTPO8a
        resolved = self._resolve()  # RTPO8b
        if resolved is None:
            return None  # RTPO8e
        return Instance._wrap(self._realtime_object, resolved)  # RTPO8c, RTPO8f

    def compact(self) -> Any:
        """RTPO13: a plain snapshot of what the path resolves to, or None."""
        self._realtime_object._check_access_preconditions()  # RTPO13a
        resolved = self._resolve()  # RTPO13b
        if resolved is None:
            return None  # RTPO13f
        return compact_value(resolved)  # RTPO13c, RTPO13d, RTPO13e

    def compact_json(self) -> Any:
        """RTPO14: `compact`, with binary as base64 and cycles as `{'objectId': ...}`."""
        self._realtime_object._check_access_preconditions()  # RTPO14a
        resolved = self._resolve()
        if resolved is None:
            return None
        return compact_value(resolved, for_json=True)  # RTPO14b

    def subscribe(self, listener: Callable[[PathObjectSubscriptionEvent], None], *,
                  depth: int | None = None) -> Subscription:
        """RTPO19: calls `listener` for changes at this path or, within `depth` levels, below it.

        Raises AblyException 40003 if `depth` is given and is not a positive integer
        (RTPO19c1a). Has no effect on the channel (RTPO19g).
        """
        self._realtime_object._check_access_preconditions()  # RTPO19b
        if depth is not None and (isinstance(depth, bool) or not isinstance(depth, int) or depth < 1):
            # RTPO19c1a
            raise AblyException(f'Subscription depth must be a positive integer, or None for any depth; '
                                f'got {depth!r}', 400, 40003)
        register = self._realtime_object._path_object_subscription_register
        return register.subscribe(self._path, listener, depth)  # RTPO19f

    def as_live_map(self) -> LiveMapPathObject:
        """RTTS5a: this path, viewed as a map."""
        return LiveMapPathObject(self._realtime_object, self._root, self._path)

    def as_live_counter(self) -> LiveCounterPathObject:
        """RTTS5b: this path, viewed as a counter."""
        return LiveCounterPathObject(self._realtime_object, self._root, self._path)

    def as_primitive(self) -> PrimitivePathObject:
        """RTTS5c, RTTS6h: this path, viewed as a primitive."""
        return PrimitivePathObject(self._realtime_object, self._root, self._path)

    def _resolve(self) -> Any:
        """RTPO3: what the path resolves to, or None if it does not resolve (RTPO3c)."""
        current: Any = self._root  # RTPO3b
        for segment in self._path:  # RTPO3a
            if not isinstance(current, InternalLiveMap):
                return None  # RTPO3a1
            current = current.get(segment)  # RTPO3a2, RTPO3a3
            if current is None:
                return None
        return current

    def _resolve_for_write(self, expected_type: type, description: str) -> Any:
        """RTPO3c2, RTTS5d2: what the path resolves to, for a write that requires an `expected_type`.

        Raises AblyException 92005 if the path does not resolve and 92007 if it resolves to
        something else.
        """
        resolved = self._resolve()
        if resolved is None:
            raise AblyException(f'Could not resolve a value at path {self.path()!r}', 400, 92005)
        if not isinstance(resolved, expected_type):
            raise AblyException(f'Cannot write to the value at path {self.path()!r} as {description}: it is of '
                                f'type {value_type_of(resolved).value}', 400, 92007)
        return resolved


class LiveMapPathObject(PathObject):
    """RTTS6a: a path expected to resolve to a map."""

    def batch(self) -> Batch[LiveMapBatchContext]:
        """RTPO20: a block whose queued writes are published as one message when it exits.

        Entering checks the write preconditions (RTPO20b) and raises AblyException 92007 if
        the path does not resolve to a map (RTPO20c).
        """
        return Batch(self._realtime_object, self._resolve, LiveMapBatchContext, f'path {self.path()!r}')

    def entries(self) -> list[tuple[str, PathObject]]:
        """RTPO9: `(key, path)` for each key of the map, or `[]`."""
        self._realtime_object._check_access_preconditions()  # RTPO9a
        resolved = self._resolve()  # RTPO9b
        if not isinstance(resolved, InternalLiveMap):
            return []  # RTPO9d
        return [(key, self.get(key)) for key in resolved.keys()]  # RTPO9c

    def keys(self) -> list[str]:
        """RTPO10: the keys of the map, or `[]`."""
        self._realtime_object._check_access_preconditions()  # RTPO10a
        resolved = self._resolve()  # RTPO10b
        if not isinstance(resolved, InternalLiveMap):
            return []  # RTPO10d
        return resolved.keys()  # RTPO10c

    def values(self) -> list[PathObject]:
        """RTPO11: a path for each key of the map, or `[]`."""
        return [path_object for _, path_object in self.entries()]  # RTPO11a-RTPO11d

    def size(self) -> int | None:
        """RTPO12: the number of entries in the map, or None."""
        self._realtime_object._check_access_preconditions()  # RTPO12a
        resolved = self._resolve()  # RTPO12b
        if not isinstance(resolved, InternalLiveMap):
            return None  # RTPO12d
        return resolved.size()  # RTPO12c

    async def set(self, key: str, value: LiveMapValue) -> None:
        """RTPO15: sets `key` in the map at this path."""
        self._realtime_object._check_write_preconditions()  # RTPO15b
        live_map = self._resolve_for_write(InternalLiveMap, 'a map')  # RTPO15c, RTPO15e
        await live_map.set(key, value)  # RTPO15d

    async def remove(self, key: str) -> None:
        """RTPO16: removes `key` from the map at this path."""
        self._realtime_object._check_write_preconditions()  # RTPO16b
        live_map = self._resolve_for_write(InternalLiveMap, 'a map')  # RTPO16c, RTPO16e
        await live_map.remove(key)  # RTPO16d


class LiveCounterPathObject(PathObject):
    """RTTS6b: a path expected to resolve to a counter."""

    def batch(self) -> Batch[LiveCounterBatchContext]:
        """RTPO20: a block whose queued writes are published as one message when it exits.

        Entering checks the write preconditions (RTPO20b) and raises AblyException 92007 if
        the path does not resolve to a counter (RTPO20c).
        """
        return Batch(self._realtime_object, self._resolve, LiveCounterBatchContext, f'path {self.path()!r}')

    def value(self) -> float | None:
        """RTTS6b: the counter's value, or None if the path does not resolve to a counter."""
        self._realtime_object._check_access_preconditions()  # RTPO7a
        resolved = self._resolve()  # RTPO7b
        if not isinstance(resolved, InternalLiveCounter):
            return None  # RTPO7f, RTTS6b
        return resolved.value()  # RTPO7c

    async def increment(self, amount: float = 1) -> None:
        """RTPO17: increments the counter at this path by `amount`."""
        self._realtime_object._check_write_preconditions()  # RTPO17b
        counter = self._resolve_for_write(InternalLiveCounter, 'a counter')  # RTPO17c, RTPO17e
        await counter.increment(amount)  # RTPO17d

    async def decrement(self, amount: float = 1) -> None:
        """RTPO18: decrements the counter at this path by `amount`."""
        self._realtime_object._check_write_preconditions()  # RTPO18b
        counter = self._resolve_for_write(InternalLiveCounter, 'a counter')  # RTPO18c, RTPO18e
        await counter.decrement(amount)  # RTPO18d


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
        value_type = expected_value_type(expected)
        self._realtime_object._check_access_preconditions()  # RTPO7a
        return primitive_value(self._resolve(), value_type)  # RTPO7b, RTPO7d-RTPO7f, RTTS6c


def _parse_path(path: str) -> list[str]:
    """RTPO6b: the segments of a dotted path, in which `\\.` is a literal dot.

    A backslash before anything other than a dot is kept as it is.
    """
    segments: list[str] = []
    segment: list[str] = []
    escaping = False
    for char in path:
        if escaping:
            if char != '.':
                segment.append('\\')
            segment.append(char)
            escaping = False
        elif char == '\\':
            escaping = True
        elif char == '.':
            segments.append(''.join(segment))
            segment = []
        else:
            segment.append(char)
    if escaping:
        segment.append('\\')
    segments.append(''.join(segment))
    return segments
