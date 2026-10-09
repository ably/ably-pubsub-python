"""The handles a subscribe call returns, and the registry of listeners behind them."""

from __future__ import annotations

from typing import Callable, Generic, TypeVar

T = TypeVar('T')


class _Handle:
    """Calls `deregister` the first time the handle is released, and never again."""

    def __init__(self, deregister: Callable[[], None]):
        self._deregister: Callable[[], None] | None = deregister

    def _release(self) -> None:
        deregister, self._deregister = self._deregister, None
        if deregister is not None:
            deregister()


class Subscription(_Handle):
    """SUB1: a registration for receiving events from a `subscribe` call."""

    def unsubscribe(self) -> None:
        """SUB2a: deregisters the listener. Calling it again does nothing (SUB2b)."""
        self._release()


class StatusSubscription(_Handle):
    """RTO18f: the registration `RealtimeObject.on` returns."""

    def off(self) -> None:
        """RTO18f1, RTO18f2: deregisters the listener the corresponding `on` call registered."""
        self._release()


class Registration(Generic[T]):
    """One registration of `item` in a `Registry`, `active` until it is removed."""

    def __init__(self, item: T):
        self.item = item
        self.active = True


class Registry(Generic[T]):
    """The listeners, or other items, that `subscribe`-style calls register, in registration order.

    Registering one item twice makes two registrations, each removed on its own. A dispatch
    iterates one `snapshot()` and skips each registration no longer `active` when it is
    reached, so that one made during the dispatch is not called by it, and one removed during
    it is not called again.
    """

    def __init__(self) -> None:
        self._registrations: list[Registration[T]] = []

    def __bool__(self) -> bool:
        return bool(self._registrations)

    def register(self, item: T) -> Callable[[], None]:
        """Registers `item`, returning the function that removes this one registration."""
        registration = Registration(item)
        self._registrations.append(registration)
        return lambda: self._remove(lambda entry: entry is registration)

    def deregister(self, item: T) -> None:
        """Removes every registration of `item`."""
        self._remove(lambda entry: entry.item == item)

    def clear(self) -> None:
        """Removes every registration."""
        self._remove(lambda entry: True)

    def snapshot(self) -> list[Registration[T]]:
        """The registrations as they stand, for a dispatch to iterate."""
        return list(self._registrations)

    def _remove(self, matches: Callable[[Registration[T]], bool]) -> None:
        kept = []
        for registration in self._registrations:
            if matches(registration):
                registration.active = False
            else:
                kept.append(registration)
        self._registrations = kept
