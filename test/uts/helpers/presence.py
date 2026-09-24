"""Presence fixtures the presence specifications build their test steps from.

The three white-box specifications (`presence_map.md`, `presence_sync.md`,
`local_presence_map.md`) drive a `PresenceMap` and a `RealtimePresence` directly, and
the channel-state and `get` specifications build presence wire messages by hand. Both
shapes were written the same way in every file that needed them, so they live here.
"""

from types import SimpleNamespace

from ably.realtime.presence import RealtimePresence
from ably.realtime.presencemap import PresenceMap
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.presence import PresenceAction, PresenceMessage

#: The lowercase action names `RealtimePresence` emits its events under, which come
#: from `PresenceAction._action_name` and exist only once `presence.py` is imported.
PRESENCE_EVENT_NAMES = ('absent', 'present', 'enter', 'leave', 'update')


def presence_map():
    """The specification's `PresenceMap()`: the map keyed by memberKey (TP3h)."""
    return PresenceMap(member_key_fn=lambda msg: msg.member_key)


def presence_message(action, client_id, connection_id, id, timestamp, data=None):
    """A `PresenceMessage` as the specification's test steps construct one."""
    return PresenceMessage(
        action=action,
        client_id=client_id,
        connection_id=connection_id,
        id=id,
        timestamp=timestamp,
        data=data,
    )


def subscribed_presence(connection_id='conn-1', name='presence-test'):
    """A `RealtimePresence` over a stub channel, with every presence event recorded.

    Returns the presence object and the list of `(event_name, message)` pairs its
    subscribers receive. One listener is registered per event name because
    `EventEmitter` keys its wrappers on the listener alone.
    """
    channel = SimpleNamespace(
        name=name,
        ably=SimpleNamespace(
            connection=SimpleNamespace(
                connection_manager=SimpleNamespace(connection_id=connection_id),
            ),
        ),
    )
    presence = RealtimePresence(channel)
    events = []

    for event_name in PRESENCE_EVENT_NAMES:
        def listener(message, event_name=event_name):
            events.append((event_name, message))

        presence._subscriptions.on(event_name, listener)

    return presence, events


def present_member(client_id, connection_id, id, **fields):
    """One entry of a PRESENCE or SYNC protocol message's `presence` array."""
    return {
        'action': PresenceAction.PRESENT,
        'clientId': client_id,
        'connectionId': connection_id,
        'id': id,
        'timestamp': 100,
        **fields,
    }


def sync_message(channel_name, channel_serial, presence):
    """A SYNC protocol message carrying `presence` under `channel_serial`."""
    return {
        'action': int(ProtocolMessageAction.SYNC),
        'channel': channel_name,
        'channelSerial': channel_serial,
        'presence': presence,
    }
