"""The enumerations LiveObjects shares across its modules."""

from enum import Enum


class ObjectsSyncState(str, Enum):
    """RTO17a: the state of synchronising a channel's objects with Ably."""

    INITIALIZED = 'initialized'  # RTO17a1
    SYNCING = 'syncing'  # RTO17a2
    SYNCED = 'synced'  # RTO17a3


class ObjectsEvent(str, Enum):
    """RTO18b: the sync state events `RealtimeObject.on` registers listeners for."""

    SYNCING = 'syncing'  # RTO18b1
    SYNCED = 'synced'  # RTO18b2


class ObjectsOperationSource(str, Enum):
    """RTO22: where an operation being applied came from."""

    LOCAL = 'local'  # RTO22a: applied on receipt of the ACK for a local publish
    CHANNEL = 'channel'  # RTO22b: received over the channel


class ValueType(Enum):
    """RTTS2: the category of value a path or an instance holds."""

    STRING = 'string'  # RTTS2a1
    NUMBER = 'number'  # RTTS2a2
    BOOLEAN = 'boolean'  # RTTS2a3
    BINARY = 'binary'  # RTTS2a4
    JSON_OBJECT = 'json_object'  # RTTS2a5
    JSON_ARRAY = 'json_array'  # RTTS2a6
    LIVE_MAP = 'live_map'  # RTTS2a7
    LIVE_COUNTER = 'live_counter'  # RTTS2a8
    UNKNOWN = 'unknown'  # RTTS2a9
