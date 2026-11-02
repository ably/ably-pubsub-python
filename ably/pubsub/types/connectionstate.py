from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ably.pubsub.util.exceptions import AblyException


class ConnectionState(str, Enum):
    INITIALIZED = 'initialized'
    CONNECTING = 'connecting'
    CONNECTED = 'connected'
    DISCONNECTED = 'disconnected'
    CLOSING = 'closing'
    CLOSED = 'closed'
    FAILED = 'failed'
    SUSPENDED = 'suspended'


class ConnectionEvent(str, Enum):
    INITIALIZED = 'initialized'
    CONNECTING = 'connecting'
    CONNECTED = 'connected'
    DISCONNECTED = 'disconnected'
    CLOSING = 'closing'
    CLOSED = 'closed'
    FAILED = 'failed'
    SUSPENDED = 'suspended'
    UPDATE = 'update'


@dataclass
class ConnectionStateChange:
    previous: ConnectionState
    current: ConnectionState
    event: ConnectionEvent
    reason: Optional[AblyException] = None  # RTN4f
