"""The register of path subscriptions a channel's `RealtimeObject` keeps (RTO24)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from ably.pubsub.objects.liveobject import LiveMapUpdate
from ably.pubsub.objects.pathobject import PathObject, PathObjectSubscriptionEvent
from ably.pubsub.objects.publicmessage import ObjectMessage
from ably.pubsub.objects.subscription import Registry, Subscription

if TYPE_CHECKING:
    from ably.pubsub.objects.liveobject import LiveObject, LiveObjectUpdate
    from ably.pubsub.objects.realtimeobject import RealtimeObject

log = logging.getLogger(__name__)


class _PathSubscription:
    """One `PathObject.subscribe` registration."""

    def __init__(self, path: list[str], listener: Callable[[PathObjectSubscriptionEvent], None],
                 depth: int | None):
        self.path = path
        self.listener = listener
        self.depth = depth


class PathObjectSubscriptionRegister:
    """RTO24: every subscription made through `PathObject.subscribe` on one channel (RTO24a)."""

    def __init__(self, realtime_object: RealtimeObject):
        self.realtime_object = realtime_object
        self._subscriptions: Registry[_PathSubscription] = Registry()

    def subscribe(self, path: list[str], listener: Callable[[PathObjectSubscriptionEvent], None],
                  depth: int | None = None) -> Subscription:
        """RTPO19f: registers `listener` for changes covered by `path` and `depth` (RTO24c1)."""
        return Subscription(self._subscriptions.register(_PathSubscription(list(path), listener, depth)))

    def dispatch(self, live_object: LiveObject, update: LiveObjectUpdate) -> None:
        """RTO24b: calls each subscription once for each path to `live_object` that it covers.

        A listener that raises is logged and does not stop the others (RTO24b2c). A
        subscription made during a dispatch is not called by it, for any path, and one removed
        during a dispatch is not called again.
        """
        if not self._subscriptions:
            return
        registrations = self._subscriptions.snapshot()

        realtime_object = self.realtime_object
        root = realtime_object._objects_pool.root
        object_message = update.object_message
        # RTO24b2b2: an update from a sync carries the object's state, not an operation
        has_operation = object_message is not None and object_message.operation is not None
        updated_keys = list(update.update) if isinstance(update, LiveMapUpdate) else []

        for path_to_this in live_object.get_full_paths():  # RTO24b1, RTO24b2
            # RTO24b2a1, RTO24b2a2
            candidate_paths = [path_to_this, *([*path_to_this, key] for key in updated_keys)]
            for registration in registrations:
                if not registration.active:
                    continue
                subscription = registration.item
                # RTO24b2b
                event_path = next((candidate for candidate in candidate_paths
                                   if self.covers(subscription.path, subscription.depth, candidate)), None)
                if event_path is None:
                    continue
                try:
                    message = None
                    if has_operation:
                        message = ObjectMessage._from_internal(object_message, realtime_object._channel_name)
                    event = PathObjectSubscriptionEvent(PathObject(realtime_object, root, event_path), message)
                    subscription.listener(event)
                except Exception:
                    # RTO24b2c
                    log.exception(f'PathObjectSubscriptionRegister.dispatch(): a path subscription listener '
                                  f'raised; path={event_path}, channel={realtime_object._channel_name}')

    @staticmethod
    def covers(subscription_path: list[str], depth: int | None, event_path: list[str]) -> bool:
        """RTO24c1: whether a subscription at `subscription_path` with `depth` covers `event_path`."""
        prefix_length = len(subscription_path)
        if len(event_path) < prefix_length or list(event_path[:prefix_length]) != list(subscription_path):
            return False
        return depth is None or len(event_path) - prefix_length + 1 <= depth
