from ably.pubsub.types.connectionstate import ConnectionState
from ably.pubsub.util.exceptions import AblyException

ConnectionErrors = {
    ConnectionState.DISCONNECTED: AblyException(
        'Connection to server temporarily unavailable',
        400,
        80003,
    ),
    ConnectionState.SUSPENDED: AblyException(
        'Connection to server unavailable',
        400,
        80002,
    ),
    ConnectionState.FAILED: AblyException(
        'Connection failed or disconnected by server',
        400,
        80000,
    ),
    ConnectionState.CLOSING: AblyException(
        'Connection closing',
        400,
        80017,
    ),
    ConnectionState.CLOSED: AblyException(
        'Connection closed',
        400,
        80017,
    ),
}
