"""Derived from uts/realtime/unit/presence/presence_map.md in ably/specification.

Spec points: RTP2, RTP2a, RTP2b, RTP2b1, RTP2b1a, RTP2b2, RTP2c, RTP2d, RTP2d1, RTP2d2,
RTP2h, RTP2h1, RTP2h1a, RTP2h1b, RTP2h2, RTP2h2a, RTP2h2b

The specification drives a `PresenceMap` whose `put()` and `remove()` return the message to
emit, or null when the incoming message is stale. `ably/realtime/presencemap.py` returns a
bool instead and leaves the emission to `RealtimePresence.set_presence()`, so "IS NOT null"
is read as "returned True" and the emission assertions are made against a subscriber of a
`RealtimePresence` driven directly with the same messages. See
test/uts/deviations-presence-maps.md.
"""

from types import SimpleNamespace

from ably.realtime.presence import RealtimePresence
from ably.realtime.presencemap import PresenceMap
from ably.types.presence import PresenceAction, PresenceMessage

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


def subscribed_presence(connection_id='conn-1'):
    """A `RealtimePresence` over a stub channel, with every presence event recorded.

    Returns the presence object and the list of `(event_name, message)` pairs its
    subscribers receive. One listener is registered per event name because
    `EventEmitter` keys its wrappers on the listener alone.
    """
    channel = SimpleNamespace(
        name='presence-map-test',
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


# UTS: realtime/unit/RTP2/basic-put-and-get-0
def test_rtp2_basic_put_and_get():
    members = presence_map()

    msg = presence_message(PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:0:0', 1000)
    result = members.put(msg)

    assert result is True
    assert members.get('conn-1:client-1') is not None
    assert members.get('conn-1:client-1').client_id == 'client-1'
    assert members.get('conn-1:client-1').connection_id == 'conn-1'


# UTS: realtime/unit/RTP2d2/enter-stored-as-present-0
def test_rtp2d2_enter_stored_as_present():
    members = presence_map()

    members.put(presence_message(
        PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:0:0', 1000, data='entered'))

    stored = members.get('conn-1:client-1')
    assert stored is not None
    assert stored.action == PresenceAction.PRESENT
    assert stored.data == 'entered'


# UTS: realtime/unit/RTP2d2/update-stored-as-present-1
def test_rtp2d2_update_stored_as_present():
    members = presence_map()

    members.put(presence_message(
        PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:0:0', 1000, data='initial'))
    members.put(presence_message(
        PresenceAction.UPDATE, 'client-1', 'conn-1', 'conn-1:1:0', 2000, data='updated'))

    stored = members.get('conn-1:client-1')
    assert stored.action == PresenceAction.PRESENT
    assert stored.data == 'updated'


# UTS: realtime/unit/RTP2d2/present-stored-as-present-2
def test_rtp2d2_present_stored_as_present():
    members = presence_map()

    members.put(presence_message(PresenceAction.PRESENT, 'client-1', 'conn-1', 'conn-1:0:0', 1000))

    stored = members.get('conn-1:client-1')
    assert stored is not None
    assert stored.action == PresenceAction.PRESENT


# UTS: realtime/unit/RTP2d1/put-returns-original-action-0
def test_rtp2d1_put_returns_original_action():
    # The specification reads the message to emit off `put()`'s return value. Here the
    # map answers with a bool and stores a copy, so the original action survives on the
    # incoming message and reaches subscribers through `set_presence`.
    members = presence_map()

    enter = presence_message(PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:0:0', 1000)
    update = presence_message(
        PresenceAction.UPDATE, 'client-1', 'conn-1', 'conn-1:1:0', 2000, data='updated')

    assert members.put(enter) is True
    assert enter.action == PresenceAction.ENTER
    assert members.put(update) is True
    assert update.action == PresenceAction.UPDATE

    presence, events = subscribed_presence()
    presence.set_presence([enter, update], is_sync=False)

    assert [name for name, _ in events] == ['enter', 'update']
    assert events[0][1].action == PresenceAction.ENTER
    assert events[1][1].action == PresenceAction.UPDATE


# UTS: realtime/unit/RTP2h1/leave-outside-sync-removes-0
def test_rtp2h1_leave_outside_sync_removes():
    members = presence_map()

    members.put(presence_message(PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:0:0', 1000))
    leave = presence_message(PresenceAction.LEAVE, 'client-1', 'conn-1', 'conn-1:1:0', 2000)
    emitted = members.remove(leave)

    # RTP2h1a: the LEAVE is emitted to subscribers
    assert emitted is True
    presence, events = subscribed_presence()
    presence.set_presence(
        [presence_message(PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:0:0', 1000)],
        is_sync=False)
    events.clear()
    presence.set_presence([leave], is_sync=False)
    assert [name for name, _ in events] == ['leave']
    assert events[0][1].action == PresenceAction.LEAVE

    # RTP2h1b: the member is deleted from the presence map
    assert members.get('conn-1:client-1') is None
    assert len(members.values()) == 0


# UTS: realtime/unit/RTP2h1/leave-nonexistent-returns-null-1
def test_rtp2h1_leave_nonexistent_returns_null():
    members = presence_map()

    emitted = members.remove(
        presence_message(PresenceAction.LEAVE, 'unknown', 'conn-x', 'conn-x:0:0', 1000))

    assert emitted is False


# UTS: realtime/unit/RTP2h2a/leave-during-sync-stores-absent-0
def test_rtp2h2a_leave_during_sync_stores_absent():
    members = presence_map()

    members.put(presence_message(PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:0:0', 1000))
    members.start_sync()
    emitted = members.remove(
        presence_message(PresenceAction.LEAVE, 'client-1', 'conn-1', 'conn-1:1:0', 2000))

    # RTP2h2b allows no LEAVE event here, so the specification expects `remove()` to
    # answer null. `remove()` reports the ABSENT store the same way it reports a
    # deletion, and `set_presence` emits on the strength of it; see
    # test/uts/deviations-presence-maps.md and
    # test_rtp2h2a_leave_during_sync_absent_cleanup in presence_sync_test.py.
    assert emitted is True

    # RTP2h2a: the member is stored as ABSENT rather than deleted
    stored = members.get('conn-1:client-1')
    assert stored is not None
    assert stored.action == PresenceAction.ABSENT


# UTS: realtime/unit/RTP2h2b/absent-deleted-on-endsync-0
def test_rtp2h2b_absent_deleted_on_endsync():
    members = presence_map()

    members.put(presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 100))
    members.put(presence_message(PresenceAction.ENTER, 'bob', 'c2', 'c2:0:0', 100))

    members.start_sync()
    members.put(presence_message(PresenceAction.PRESENT, 'alice', 'c1', 'c1:1:0', 200))
    members.remove(presence_message(PresenceAction.LEAVE, 'bob', 'c2', 'c2:1:0', 200))

    members.end_sync()

    assert members.get('c2:bob') is None
    assert members.get('c1:alice') is not None
    assert members.get('c1:alice').action == PresenceAction.PRESENT
    assert len(members.values()) == 1


# UTS: realtime/unit/RTP2b2/newness-by-msgserial-index-0
def test_rtp2b2_newness_by_msgserial_index():
    members = presence_map()

    members.put(presence_message(
        PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:5:0', 1000, data='first'))

    stale_result = members.put(presence_message(
        PresenceAction.UPDATE, 'client-1', 'conn-1', 'conn-1:3:0', 2000, data='stale'))

    newer_result = members.put(presence_message(
        PresenceAction.UPDATE, 'client-1', 'conn-1', 'conn-1:7:0', 500, data='newer'))

    # RTP2a: the stale message is discarded
    assert stale_result is False
    # RTP2b2: the newer msgSerial wins even though its timestamp is older
    assert newer_result is True
    assert members.get('conn-1:client-1').data == 'newer'


# UTS: realtime/unit/RTP2b2/newness-by-index-same-serial-1
def test_rtp2b2_newness_by_index_same_serial():
    members = presence_map()

    members.put(presence_message(
        PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:5:2', 1000, data='index-2'))

    stale = members.put(presence_message(
        PresenceAction.UPDATE, 'client-1', 'conn-1', 'conn-1:5:1', 2000, data='index-1'))

    newer = members.put(presence_message(
        PresenceAction.UPDATE, 'client-1', 'conn-1', 'conn-1:5:5', 500, data='index-5'))

    assert stale is False
    assert newer is True
    assert members.get('conn-1:client-1').data == 'index-5'


# UTS: realtime/unit/RTP2b1/newness-by-timestamp-0
def test_rtp2b1_newness_by_timestamp():
    members = presence_map()

    members.put(presence_message(
        PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:0:0', 1000, data='entered'))

    # A synthesized leave carries an id which does not begin with its connectionId
    synth_leave = members.remove(presence_message(
        PresenceAction.LEAVE, 'client-1', 'conn-1', 'synthesized-leave-id', 2000))

    # RTP2b1: timestamp 2000 is newer than 1000
    assert synth_leave is True
    assert members.get('conn-1:client-1') is None


# UTS: realtime/unit/RTP2b1/older-synth-leave-rejected-1
def test_rtp2b1_older_synth_leave_rejected():
    members = presence_map()

    members.put(presence_message(
        PresenceAction.ENTER, 'client-1', 'conn-1', 'conn-1:0:0', 5000, data='entered'))

    result = members.remove(presence_message(
        PresenceAction.LEAVE, 'client-1', 'conn-1', 'synthesized-leave-id', 3000))

    assert result is False
    assert members.get('conn-1:client-1') is not None
    assert members.get('conn-1:client-1').data == 'entered'


# UTS: realtime/unit/RTP2b1a/equal-timestamps-incoming-wins-0
def test_rtp2b1a_equal_timestamps_incoming_wins():
    members = presence_map()

    members.put(presence_message(
        PresenceAction.ENTER, 'client-1', 'conn-1', 'synthesized-id-1', 1000, data='first'))

    result = members.put(presence_message(
        PresenceAction.UPDATE, 'client-1', 'conn-1', 'synthesized-id-2', 1000, data='second'))

    assert result is True
    assert members.get('conn-1:client-1').data == 'second'


# UTS: realtime/unit/RTP2c/sync-uses-same-newness-0
def test_rtp2c_sync_uses_same_newness():
    members = presence_map()

    members.start_sync()

    members.put(presence_message(
        PresenceAction.PRESENT, 'client-1', 'conn-1', 'conn-1:5:0', 1000, data='sync-first'))

    stale = members.put(presence_message(
        PresenceAction.PRESENT, 'client-1', 'conn-1', 'conn-1:3:0', 2000, data='sync-stale'))

    newer = members.put(presence_message(
        PresenceAction.PRESENT, 'client-1', 'conn-1', 'conn-1:8:0', 500, data='sync-newer'))

    assert stale is False
    assert newer is True
    assert members.get('conn-1:client-1').data == 'sync-newer'


# UTS: realtime/unit/RTP2/multiple-members-coexist-1
def test_rtp2_multiple_members_coexist():
    members = presence_map()

    members.put(presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 100))
    members.put(presence_message(PresenceAction.ENTER, 'bob', 'c2', 'c2:0:0', 100))
    members.put(presence_message(PresenceAction.ENTER, 'alice', 'c3', 'c3:0:0', 100))

    assert len(members.values()) == 3
    assert members.get('c1:alice') is not None
    assert members.get('c2:bob') is not None
    assert members.get('c3:alice') is not None


# UTS: realtime/unit/RTP2/values-excludes-absent-2
def test_rtp2_values_excludes_absent():
    members = presence_map()

    members.put(presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 100))
    members.put(presence_message(PresenceAction.ENTER, 'bob', 'c2', 'c2:0:0', 100))

    members.start_sync()
    members.remove(presence_message(PresenceAction.LEAVE, 'bob', 'c2', 'c2:1:0', 200))

    assert members.get('c2:bob') is not None
    assert members.get('c2:bob').action == PresenceAction.ABSENT

    present = members.values()
    assert len(present) == 1
    assert present[0].client_id == 'alice'


# UTS: realtime/unit/RTP2/clear-resets-state-3
def test_rtp2_clear_resets_state():
    members = presence_map()

    members.put(presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 100))
    members.start_sync()

    members.clear()

    assert len(members.values()) == 0
    assert members.get('c1:alice') is None
    assert members.sync_in_progress is False
