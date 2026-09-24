"""Derived from uts/realtime/unit/presence/presence_sync.md in ably/specification.

Spec points: RTP18, RTP18a, RTP18b, RTP18c, RTP19, RTP19a, RTP2h2a, RTP2h2b

The specification's `endSync()` answers with the synthesized LEAVE events.
`ably/realtime/presencemap.py` answers with a `(residual, absent)` pair of the stored
members and `RealtimePresence.set_presence()` builds the LEAVE events from them, so a
test reading only the count and the clientId works through `end_sync_leaves()` below,
while a test reading the LEAVE itself drives a `RealtimePresence` with the same
messages. See test/uts/deviations.md.
"""

from datetime import datetime, timezone

from ably.types.presence import PresenceAction
from test.uts.helpers.deviations import deviation
from test.uts.helpers.presence import presence_map, presence_message, subscribed_presence


def end_sync_leaves(members):
    """The members `end_sync` hands back for RTP19's synthesized LEAVE events.

    `RealtimePresence.set_presence` synthesizes one LEAVE per member across both lists,
    so their concatenation is the specification's `endSync() -> List<PresenceMessage>`.
    """
    residual, absent = members.end_sync()
    return residual + absent


def leaves(events):
    """The LEAVE messages out of a recorded `(event_name, message)` list."""
    return [message for name, message in events if name == 'leave']


# UTS: realtime/unit/RTP18a/startsync-sets-flag-0
def test_rtp18a_startsync_sets_flag():
    members = presence_map()

    assert members.sync_in_progress is False

    members.start_sync()

    assert members.sync_in_progress is True


# UTS: realtime/unit/RTP18b/endsync-clears-flag-0
def test_rtp18b_endsync_clears_flag():
    members = presence_map()

    members.start_sync()
    assert members.sync_in_progress is True

    members.end_sync()

    assert members.sync_in_progress is False


# UTS: realtime/unit/RTP19/stale-members-leave-after-sync-0
def test_rtp19_stale_members_leave_after_sync():
    presence, events = subscribed_presence()

    presence.set_presence([
        presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 100),
        presence_message(PresenceAction.ENTER, 'bob', 'c2', 'c2:0:0', 100),
    ], is_sync=False)

    assert len(presence.members.values()) == 2

    events.clear()
    # A sync in which only alice appears
    presence.set_presence([
        presence_message(PresenceAction.PRESENT, 'alice', 'c1', 'c1:1:0', 200),
    ], is_sync=True)

    leave_events = leaves(events)
    assert len(leave_events) == 1
    assert leave_events[0].client_id == 'bob'
    assert leave_events[0].action == PresenceAction.LEAVE

    assert len(presence.members.values()) == 1
    assert presence.members.get('c1:alice') is not None
    assert presence.members.get('c2:bob') is None


# UTS: realtime/unit/RTP19/synth-leave-null-id-timestamp-1
def test_rtp19_synth_leave_null_id_timestamp():
    presence, events = subscribed_presence()

    presence.set_presence([
        presence_message(PresenceAction.ENTER, 'bob', 'c2', 'c2:0:0', 100, data='bob-data'),
    ], is_sync=False)

    before_time = datetime.now(timezone.utc)

    events.clear()
    # A sync carrying no members for bob
    presence.set_presence([], is_sync=True)

    after_time = datetime.now(timezone.utc)

    leave_events = leaves(events)
    assert len(leave_events) == 1

    leave = leave_events[0]
    assert leave.action == PresenceAction.LEAVE
    assert leave.client_id == 'bob'
    assert leave.connection_id == 'c2'
    assert leave.data == 'bob-data'
    assert leave.id is None
    assert before_time <= leave.timestamp <= after_time


# UTS: realtime/unit/RTP19/updated-members-survive-sync-2
def test_rtp19_updated_members_survive_sync():
    members = presence_map()

    members.put(presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 100))
    members.put(presence_message(PresenceAction.ENTER, 'bob', 'c2', 'c2:0:0', 100))
    members.put(presence_message(PresenceAction.ENTER, 'carol', 'c3', 'c3:0:0', 100))

    members.start_sync()

    # Alice arrives in the SYNC data
    members.put(presence_message(PresenceAction.PRESENT, 'alice', 'c1', 'c1:1:0', 200))
    # Bob arrives as a PRESENCE message during the sync
    members.put(presence_message(
        PresenceAction.UPDATE, 'bob', 'c2', 'c2:1:0', 200, data='new-data'))
    # Carol does not appear during the sync

    leave_events = end_sync_leaves(members)

    assert len(leave_events) == 1
    assert leave_events[0].client_id == 'carol'

    assert len(members.values()) == 2
    assert members.get('c1:alice') is not None
    assert members.get('c2:bob') is not None
    assert members.get('c2:bob').data == 'new-data'


# UTS: realtime/unit/RTP18a/new-sync-discards-previous-1
def test_rtp18a_new_sync_discards_previous():
    members = presence_map()

    members.put(presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 100))
    members.put(presence_message(PresenceAction.ENTER, 'bob', 'c2', 'c2:0:0', 100))

    # A first sync in which only alice appears
    members.start_sync()
    members.put(presence_message(PresenceAction.PRESENT, 'alice', 'c1', 'c1:1:0', 200))

    # A new sequence identifier starts a fresh sync before the first one ended.
    # `start_sync` while a sync is running keeps the first sync's residual set rather
    # than re-snapshotting the map, which this test cannot tell apart because the
    # second sync delivers every member; see test/uts/deviations.md.
    members.start_sync()

    members.put(presence_message(PresenceAction.PRESENT, 'alice', 'c1', 'c1:2:0', 300))
    members.put(presence_message(PresenceAction.PRESENT, 'bob', 'c2', 'c2:1:0', 300))

    leave_events = end_sync_leaves(members)

    assert len(leave_events) == 0
    assert len(members.values()) == 2
    assert members.get('c1:alice') is not None
    assert members.get('c2:bob') is not None


# UTS: realtime/unit/RTP18c/single-message-sync-0
def test_rtp18c_single_message_sync():
    presence, events = subscribed_presence()

    presence.set_presence([
        presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 100),
        presence_message(PresenceAction.ENTER, 'bob', 'c2', 'c2:0:0', 100),
    ], is_sync=False)

    events.clear()
    # A SYNC with no channelSerial carries the whole sync in one ProtocolMessage
    presence.set_presence([
        presence_message(PresenceAction.PRESENT, 'alice', 'c1', 'c1:1:0', 200),
    ], is_sync=True, sync_channel_serial=None)

    leave_events = leaves(events)
    assert len(leave_events) == 1
    assert leave_events[0].client_id == 'bob'
    assert leave_events[0].action == PresenceAction.LEAVE

    assert len(presence.members.values()) == 1
    assert presence.members.get('c1:alice') is not None
    assert presence.members.sync_in_progress is False


# UTS: realtime/unit/RTP19a/no-has-presence-clears-members-0
async def test_rtp19a_no_has_presence_clears_members():
    # The members are given connectionIds other than the connection's own, so that
    # RTP17i's re-entry of the internal presence map has nothing to do here.
    presence, events = subscribed_presence()

    presence.set_presence([
        presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 100, data='a'),
        presence_message(PresenceAction.ENTER, 'bob', 'c2', 'c2:0:0', 100, data='b'),
        presence_message(PresenceAction.ENTER, 'carol', 'c3', 'c3:0:0', 100, data='c'),
    ], is_sync=False)

    events.clear()
    presence.on_attached(has_presence=False)

    leave_events = leaves(events)
    assert len(leave_events) == 3

    by_client = {leave.client_id: leave for leave in leave_events}

    alice_leave = by_client.get('alice')
    bob_leave = by_client.get('bob')
    carol_leave = by_client.get('carol')

    assert alice_leave is not None
    assert alice_leave.action == PresenceAction.LEAVE
    assert alice_leave.data == 'a'
    assert alice_leave.id is None

    assert bob_leave is not None
    assert bob_leave.action == PresenceAction.LEAVE
    assert bob_leave.data == 'b'
    assert bob_leave.id is None

    assert carol_leave is not None
    assert carol_leave.action == PresenceAction.LEAVE
    assert carol_leave.data == 'c'
    assert carol_leave.id is None

    assert len(presence.members.values()) == 0


# UTS: realtime/unit/RTP2h2a/leave-during-sync-absent-cleanup-0
@deviation
def test_rtp2h2a_leave_during_sync_absent_cleanup():
    presence, events = subscribed_presence()

    presence.set_presence([
        presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 100),
        presence_message(PresenceAction.ENTER, 'bob', 'c2', 'c2:0:0', 100),
    ], is_sync=False)

    events.clear()
    # A sync whose cursor is not yet empty: alice appears, bob leaves
    presence.set_presence([
        presence_message(PresenceAction.PRESENT, 'alice', 'c1', 'c1:1:0', 200),
        presence_message(PresenceAction.LEAVE, 'bob', 'c2', 'c2:1:0', 200),
    ], is_sync=True, sync_channel_serial='seq-1:cursor-1')

    # RTP2h2a: bob is stored as ABSENT rather than emitted or deleted
    assert leaves(events) == []
    assert presence.members.get('c2:bob') is not None
    assert presence.members.get('c2:bob').action == PresenceAction.ABSENT

    # The empty cursor completes the sync
    presence.set_presence([], is_sync=True, sync_channel_serial='seq-1:')

    # RTP2h2b: the ABSENT entry is deleted with no LEAVE event, because RTP19's
    # synthesized LEAVEs are only for members that were never seen during the sync
    assert leaves(events) == []
    assert presence.members.get('c2:bob') is None

    assert len(presence.members.values()) == 1
    assert presence.members.get('c1:alice') is not None


# UTS: realtime/unit/RTP19/empty-map-sync-no-leaves-3
def test_rtp19_empty_map_sync_no_leaves():
    members = presence_map()

    members.start_sync()
    members.put(presence_message(PresenceAction.PRESENT, 'alice', 'c1', 'c1:0:0', 100))
    leave_events = end_sync_leaves(members)

    assert len(leave_events) == 0
    assert len(members.values()) == 1
    assert members.get('c1:alice') is not None


# UTS: realtime/unit/RTP18/endsync-without-startsync-noop-0
def test_rtp18_endsync_without_startsync_noop():
    members = presence_map()

    members.put(presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 100))

    leave_events = end_sync_leaves(members)

    assert len(leave_events) == 0
    assert len(members.values()) == 1
    assert members.get('c1:alice') is not None
    assert members.sync_in_progress is False


# UTS: realtime/unit/RTP19/stale-sync-removes-from-residuals-4
def test_rtp19_stale_sync_removes_from_residuals():
    members = presence_map()

    members.put(presence_message(
        PresenceAction.ENTER, 'alice', 'c1', 'c1:5:0', 500, data='original'))

    members.start_sync()

    # A SYNC message with an older id for a member already in the map
    result = members.put(presence_message(
        PresenceAction.PRESENT, 'alice', 'c1', 'c1:3:0', 300, data='stale'))

    leave_events = end_sync_leaves(members)

    assert result is False

    # Alice was seen during the sync, so she is not a residual
    assert len(leave_events) == 0
    assert len(members.values()) == 1
    assert members.get('c1:alice') is not None
    assert members.get('c1:alice').data == 'original'


# UTS: realtime/unit/RTP19/presence-echoes-then-sync-preserves-5
def test_rtp19_presence_echoes_then_sync_preserves():
    members = presence_map()

    # The server echoes a PRESENCE event for each member entered
    members.put(presence_message(PresenceAction.ENTER, 'user-0', 'c1', 'c1:0:0', 100, data='data-0'))
    members.put(presence_message(PresenceAction.ENTER, 'user-1', 'c1', 'c1:1:0', 100, data='data-1'))
    members.put(presence_message(PresenceAction.ENTER, 'user-2', 'c1', 'c1:2:0', 100, data='data-2'))

    assert len(members.values()) == 3

    members.start_sync()

    # The SYNC repeats the ids the echoes already carried
    members.put(presence_message(PresenceAction.PRESENT, 'user-0', 'c1', 'c1:0:0', 100, data='data-0'))
    members.put(presence_message(PresenceAction.PRESENT, 'user-1', 'c1', 'c1:1:0', 100, data='data-1'))
    members.put(presence_message(PresenceAction.PRESENT, 'user-2', 'c1', 'c1:2:0', 100, data='data-2'))

    leave_events = end_sync_leaves(members)

    assert len(leave_events) == 0
    assert len(members.values()) == 3

    for i in range(3):
        member = members.get(f'c1:user-{i}')
        assert member is not None
        assert member.data == f'data-{i}'


# UTS: realtime/unit/RTP19/new-member-during-sync-survives-6
def test_rtp19_new_member_during_sync_survives():
    members = presence_map()

    members.put(presence_message(PresenceAction.ENTER, 'alice', 'c1', 'c1:0:0', 100))

    members.start_sync()

    members.put(presence_message(PresenceAction.PRESENT, 'alice', 'c1', 'c1:1:0', 200))
    # Bob enters through a PRESENCE message during the sync
    members.put(presence_message(PresenceAction.ENTER, 'bob', 'c2', 'c2:0:0', 200))

    leave_events = end_sync_leaves(members)

    assert len(leave_events) == 0
    assert len(members.values()) == 2
    assert members.get('c1:alice') is not None
    assert members.get('c2:bob') is not None
