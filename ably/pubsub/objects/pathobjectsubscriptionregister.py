"""The register of path subscriptions a channel's `RealtimeObject` keeps (RTO24)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ably.pubsub.objects.liveobject import LiveObject, LiveObjectUpdate
    from ably.pubsub.objects.pathobject import PathObjectSubscriptionEvent
    from ably.pubsub.objects.realtimeobject import RealtimeObject
    from ably.pubsub.objects.subscription import Subscription


class PathObjectSubscriptionRegister:
    """RTO24: every subscription made through `PathObject.subscribe` on one channel (RTO24a)."""

    def __init__(self, realtime_object: RealtimeObject):
        self.realtime_object = realtime_object

    def subscribe(self, path: list[str], listener: Callable[[PathObjectSubscriptionEvent], None],
                  depth: int | None = None) -> Subscription:
        """RTPO19f: registers `listener` for changes covered by `path` and `depth` (RTO24c1)."""
        raise NotImplementedError

    def dispatch(self, live_object: LiveObject, update: LiveObjectUpdate) -> None:
        """RTO24b: calls each subscription covering a path to `live_object` once.

        A listener that raises is logged and does not stop the others (RTO24b2c).
        """
        raise NotImplementedError

    @staticmethod
    def covers(subscription_path: list[str], depth: int | None, event_path: list[str]) -> bool:
        """RTO24c1: whether a subscription at `subscription_path` with `depth` covers `event_path`."""
        raise NotImplementedError
