from typing import Generic, List, TypeVar

from ably.pubsub.types.presence import PresenceMessage
from ably.pubsub.util.exceptions import AblyException

T = TypeVar('T')


class BatchResult(Generic[T]):
    """The results of a batch operation, one per channel (BAR2)."""

    def __init__(self, success_count: int, failure_count: int, results: List[T]):
        self.__success_count = success_count
        self.__failure_count = failure_count
        self.__results = results

    @property
    def success_count(self) -> int:
        """The number of successful operations (BAR2a)."""
        return self.__success_count

    @property
    def failure_count(self) -> int:
        """The number of unsuccessful operations (BAR2b)."""
        return self.__failure_count

    @property
    def results(self) -> List[T]:
        """The result of each operation in the batch (BAR2c)."""
        return self.__results

    @staticmethod
    def from_dict(obj, result_from_dict):
        """Create a BatchResult from a response envelope, building each result with `result_from_dict`."""
        return BatchResult(
            success_count=obj.get('successCount'),
            failure_count=obj.get('failureCount'),
            results=[result_from_dict(result) for result in obj.get('results') or []],
        )


class BatchPublishSpec:
    """The messages a batch publish sends, and the channels it sends every one of them to (BSP2)."""

    def __init__(self, channels, messages):
        """
        Args:
            channels: The names of the channels to publish the messages to (BSP2a).
            messages: The `Message` objects to publish to each channel (BSP2b).
        """
        self.__channels = channels
        self.__messages = messages

    @property
    def channels(self):
        return self.__channels

    @property
    def messages(self):
        return self.__messages

    def as_dict(self, binary=False):
        """Convert BatchPublishSpec to the wire format, encoding each message per RSL4."""
        return {
            'channels': list(self.channels),
            'messages': [message.as_dict(binary=binary) for message in self.messages],
        }

    @classmethod
    def factory(cls, spec):
        """A BatchPublishSpec from either an instance or a dict with `channels` and `messages` keys."""
        if isinstance(spec, cls):
            return spec
        if isinstance(spec, dict):
            return cls(channels=spec.get('channels'), messages=spec.get('messages'))
        raise TypeError(f'Unexpected {type(spec)} batch publish spec, expected a BatchPublishSpec or a dict')


class BatchPublishSuccessResult:
    """The result of publishing a spec's messages to one channel (BPR2)."""

    def __init__(self, channel, message_id, serials):
        """
        Args:
            channel: The name of the channel (BPR2a).
            message_id: The id prefix shared by the published messages (BPR2b).
            serials: The serial of each published message, or None where a conflation rule discarded it (BPR2c).
        """
        self.__channel = channel
        self.__message_id = message_id
        self.__serials = serials

    @property
    def channel(self):
        return self.__channel

    @property
    def message_id(self):
        return self.__message_id

    @property
    def serials(self):
        return self.__serials

    @staticmethod
    def from_dict(obj):
        return BatchPublishSuccessResult(
            channel=obj.get('channel'),
            message_id=obj.get('messageId'),
            serials=obj.get('serials') or [],
        )


class BatchPublishFailureResult:
    """The reason a spec's messages could not be published to one channel (BPF2)."""

    def __init__(self, channel, error):
        """
        Args:
            channel: The name of the channel (BPF2a).
            error: An `AblyException` describing why the publish failed (BPF2b).
        """
        self.__channel = channel
        self.__error = error

    @property
    def channel(self):
        return self.__channel

    @property
    def error(self):
        return self.__error

    @staticmethod
    def from_dict(obj):
        return BatchPublishFailureResult(
            channel=obj.get('channel'),
            error=AblyException.from_dict(obj['error']),
        )


class BatchPresenceSuccessResult:
    """The members present on one channel of a batch presence request (BGR2)."""

    def __init__(self, channel, presence):
        """
        Args:
            channel: The name of the channel (BGR2a).
            presence: A `PresenceMessage` for each member present on the channel (BGR2b).
        """
        self.__channel = channel
        self.__presence = presence

    @property
    def channel(self):
        return self.__channel

    @property
    def presence(self):
        return self.__presence

    @staticmethod
    def from_dict(obj):
        # The server leaves `presence` out for a channel with no members
        return BatchPresenceSuccessResult(
            channel=obj.get('channel'),
            presence=PresenceMessage.from_encoded_array(obj.get('presence') or []),
        )


class BatchPresenceFailureResult:
    """The reason the members of one channel of a batch presence request could not be retrieved (BGF2)."""

    def __init__(self, channel, error):
        """
        Args:
            channel: The name of the channel (BGF2a).
            error: An `AblyException` describing why the request failed for the channel (BGF2b).
        """
        self.__channel = channel
        self.__error = error

    @property
    def channel(self):
        return self.__channel

    @property
    def error(self):
        return self.__error

    @staticmethod
    def from_dict(obj):
        return BatchPresenceFailureResult(
            channel=obj.get('channel'),
            error=AblyException.from_dict(obj['error']),
        )


def batch_publish_result_from_dict(obj):
    if obj.get('error') is not None:
        return BatchPublishFailureResult.from_dict(obj)
    return BatchPublishSuccessResult.from_dict(obj)


def batch_presence_result_from_dict(obj):
    if obj.get('error') is not None:
        return BatchPresenceFailureResult.from_dict(obj)
    return BatchPresenceSuccessResult.from_dict(obj)
