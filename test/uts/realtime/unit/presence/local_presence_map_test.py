"""Derived from uts/realtime/unit/presence/local_presence_map.md in ably/specification.

Spec points: RTP17, RTP17b, RTP17h, RTP2d2, RTP5a

The specification's `LocalPresenceMap` is, in this SDK, the same `PresenceMap` class built
with `client_id` as its key function - `RealtimePresence._my_members`
(`ably/realtime/presence.py:79-81`). RTP17b's filtering of synthesized LEAVE events lives
one level up, in `RealtimePresence.set_presence()`, which the specification's
implementation note permits; the test for it therefore drives a `RealtimePresence`. See
test/uts/deviations-presence-maps.md.
"""

from types import SimpleNamespace

from ably.realtime.presence import RealtimePresence
from ably.realtime.presencemap import PresenceMap
from ably.types.presence import PresenceAction, PresenceMessage
from test.uts.helpers.deviations import deviation

PRESENCE_EVENT_NAMES = ('absent', 'present', 'enter', 'leave', 'update')


def local_presence_map():
    """The specification's `LocalPresenceMap()`: the RTP17 map keyed by clientId."""
    return PresenceMap(member_key_fn=lambda msg: msg.client_id)


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


def subscribed_presence(connection_id='conn-1'):
    """A `RealtimePresence` over a stub channel, with every presence event recorded.

    Returns the presence object and the list of `(event_name, message)` pairs its
    subscribers receive. One listener is registered per event name because
    `EventEmitter` keys its wrappers on the listener alone.
    """
    channel = SimpleNamespace(
        name='local-presence-map-test',
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


# UTS: realtime/unit/RTP17h/keyed-by-clientid-0
@deviation
def test_rtp17h_keyed_by_clientid():
    members = local_presence_map()

    msg1 = presence_message(
        PresenceAction.ENTER, 'user-1', 'conn-A', 'conn-A:0:0', 1000, data='first')
    msg2 = presence_message(
        PresenceAction.ENTER, 'user-1', 'conn-B', 'conn-B:0:0', 2000, data='second')

    members.put(msg1)
    members.put(msg2)

    # Keyed by clientId, so the entry for the newer connection replaces the older one
    assert len(members.values()) == 1
    assert members.get('user-1') is not None
    assert members.get('user-1').data == 'second'
    assert members.get('user-1').connection_id == 'conn-B'


# UTS: realtime/unit/RTP17b/enter-adds-to-map-0
def test_rtp17b_enter_adds_to_map():
    members = local_presence_map()

    members.put(presence_message(
        PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:0:0', 1000, data='hello'))

    assert members.get('client-1') is not None
    # RTP2d2: the stored action is always PRESENT
    assert members.get('client-1').action == PresenceAction.PRESENT
    assert members.get('client-1').data == 'hello'
    assert len(members.values()) == 1


# UTS: realtime/unit/RTP17b/update-adds-to-map-1
def test_rtp17b_update_adds_to_map():
    members = local_presence_map()

    members.put(presence_message(
        PresenceAction.UPDATE, 'client-1', 'conn-1', 'conn-1:0:0', 1000, data='from-update'))

    assert members.get('client-1') is not None
    assert members.get('client-1').action == PresenceAction.PRESENT
    assert members.get('client-1').data == 'from-update'
    assert len(members.values()) == 1


# UTS: realtime/unit/RTP17b/enter-overwrites-enter-2
def test_rtp17b_enter_overwrites_enter():
    members = local_presence_map()

    members.put(presence_message(
        PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:0:0', 1000, data='first'))
    members.put(presence_message(
        PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:1:0', 2000, data='second'))

    assert len(members.values()) == 1
    assert members.get('client-1').action == PresenceAction.PRESENT
    assert members.get('client-1').data == 'second'


# UTS: realtime/unit/RTP17b/update-overwrites-enter-3
def test_rtp17b_update_overwrites_enter():
    members = local_presence_map()

    members.put(presence_message(
        PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:0:0', 1000, data='initial'))
    members.put(presence_message(
        PresenceAction.UPDATE, 'client-1', 'conn-1', 'conn-1:1:0', 2000, data='updated'))

    assert len(members.values()) == 1
    assert members.get('client-1').action == PresenceAction.PRESENT
    assert members.get('client-1').data == 'updated'


# UTS: realtime/unit/RTP17b/present-adds-to-map-4
def test_rtp17b_present_adds_to_map():
    members = local_presence_map()

    members.put(presence_message(
        PresenceAction.PRESENT, 'client-1', 'conn-1', 'conn-1:0:0', 1000, data='present'))

    assert members.get('client-1') is not None
    assert members.get('client-1').action == PresenceAction.PRESENT
    assert members.get('client-1').data == 'present'


# UTS: realtime/unit/RTP17b/non-synthesized-leave-removes-5
def test_rtp17b_non_synthesized_leave_removes():
    members = local_presence_map()

    members.put(presence_message(PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:0:0', 1000))

    assert members.get('client-1') is not None

    # A non-synthesized LEAVE: connectionId "conn-1" is an initial substring of "conn-1:1:0"
    result = members.remove(
        presence_message(PresenceAction.LEAVE, 'client-1', 'conn-1', 'conn-1:1:0', 2000))

    assert result is True
    assert members.get('client-1') is None
    assert len(members.values()) == 0


# UTS: realtime/unit/RTP17b/synthesized-leave-ignored-6
def test_rtp17b_synthesized_leave_ignored():
    # The specification's implementation note allows the synthesized-LEAVE filter to sit
    # at the calling level, which is where this SDK keeps it, so the test drives
    # `set_presence` rather than the map.
    presence, _events = subscribed_presence('conn-1')

    presence.set_presence([
        presence_message(
            PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:0:0', 1000, data='entered'),
    ], is_sync=False)

    assert presence._my_members.get('client-1') is not None

    # A synthesized LEAVE: connectionId "conn-1" is not an initial substring of
    # "synthesized-leave-id"
    presence.set_presence([
        presence_message(
            PresenceAction.LEAVE, 'client-1', 'conn-1', 'synthesized-leave-id', 2000),
    ], is_sync=False)

    # The synthesized leave was not applied to the RTP17 map
    assert presence._my_members.get('client-1') is not None
    assert presence._my_members.get('client-1').data == 'entered'
    assert len(presence._my_members.values()) == 1


# UTS: realtime/unit/RTP17/multiple-clientids-coexist-0
def test_rtp17_multiple_clientids_coexist():
    members = local_presence_map()

    members.put(presence_message(
        PresenceAction.ENTER, 'alice', 'conn-1', 'conn-1:0:0', 100, data='alice-data'))
    members.put(presence_message(
        PresenceAction.ENTER, 'bob', 'conn-1', 'conn-1:0:1', 100, data='bob-data'))
    members.put(presence_message(
        PresenceAction.ENTER, 'carol', 'conn-1', 'conn-1:0:2', 100, data='carol-data'))

    assert len(members.values()) == 3
    assert members.get('alice') is not None
    assert members.get('bob') is not None
    assert members.get('carol') is not None
    assert members.get('alice').data == 'alice-data'
    assert members.get('bob').data == 'bob-data'
    assert members.get('carol').data == 'carol-data'


# UTS: realtime/unit/RTP17/remove-one-of-multiple-1
def test_rtp17_remove_one_of_multiple():
    members = local_presence_map()

    members.put(presence_message(PresenceAction.ENTER, 'alice', 'conn-1', 'conn-1:0:0', 100))
    members.put(presence_message(PresenceAction.ENTER, 'bob', 'conn-1', 'conn-1:0:1', 100))

    members.remove(presence_message(PresenceAction.LEAVE, 'alice', 'conn-1', 'conn-1:1:0', 200))

    assert members.get('alice') is None
    assert members.get('bob') is not None
    assert len(members.values()) == 1


# UTS: realtime/unit/RTP17/clear-resets-state-2
def test_rtp17_clear_resets_state():
    members = local_presence_map()

    members.put(presence_message(PresenceAction.ENTER, 'alice', 'conn-1', 'conn-1:0:0', 100))
    members.put(presence_message(PresenceAction.ENTER, 'bob', 'conn-1', 'conn-1:0:1', 100))

    assert len(members.values()) == 2

    members.clear()

    assert len(members.values()) == 0
    assert members.get('alice') is None
    assert members.get('bob') is None


# UTS: realtime/unit/RTP17/get-null-unknown-clientid-3
def test_rtp17_get_null_unknown_clientid():
    members = local_presence_map()

    result = members.get('nonexistent')

    assert result is None


# UTS: realtime/unit/RTP17/remove-unknown-noop-4
def test_rtp17_remove_unknown_noop():
    members = local_presence_map()

    members.put(presence_message(PresenceAction.ENTER, 'alice', 'conn-1', 'conn-1:0:0', 100))

    members.remove(presence_message(
        PresenceAction.LEAVE, 'nonexistent', 'conn-1', 'conn-1:1:0', 200))

    assert members.get('alice') is not None
    assert len(members.values()) == 1
