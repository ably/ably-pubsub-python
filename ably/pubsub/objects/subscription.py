"""The handles a subscribe call returns."""

from __future__ import annotations

from typing import Callable


class Subscription:
    """SUB1: a registration for receiving events from a `subscribe` call."""

    def __init__(self, deregister: Callable[[], None]):
        self._deregister: Callable[[], None] | None = deregister

    def unsubscribe(self) -> None:
        """SUB2a: deregisters the listener. Calling it again does nothing (SUB2b)."""
        deregister, self._deregister = self._deregister, None
        if deregister is not None:
            deregister()


class StatusSubscription:
    """RTO18f: the registration `RealtimeObject.on` returns."""

    def __init__(self, deregister: Callable[[], None]):
        self._deregister: Callable[[], None] | None = deregister

    def off(self) -> None:
        """RTO18f1, RTO18f2: deregisters the listener the corresponding `on` call registered."""
        deregister, self._deregister = self._deregister, None
        if deregister is not None:
            deregister()
