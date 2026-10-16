"""Derived from uts/objects/unit/objects_pool.md in ably/specification.

Spec points: RTO3, RTO3a, RTO3b, RTO3b1, RTO4, RTO4a, RTO4b, RTO4b1, RTO4b2, RTO4b2a, RTO4b4,
RTO4c, RTO4d, RTO5, RTO5a1, RTO5a2, RTO5a2a, RTO5a4, RTO5a5, RTO5a6, RTO5c, RTO5c2, RTO5c2a,
RTO5c6, RTO5c7, RTO5c8, RTO5c9, RTO5c10, RTO5c10a, RTO5c10b, RTO5d, RTO5e, RTO5f1, RTO5f2,
RTO5f2a2, RTO5f2b, RTO5f3, RTO6, RTO6a, RTO6b1, RTO6b2, RTO6b3, RTO7, RTO7a, RTO8a, RTO8b,
RTO9a1, RTO9a2a4, RTO9a2b, RTO9a3, RTLM23

A pure unit specification: nothing is mocked and nothing is connected. The specification
puts the sync and apply state machine on `ObjectsPool` (`processAttached`,
`processObjectSync`, `processObjectMessage`, `applyObjectMessages`, `syncState`). Here, as
in features.md (RTO4-RTO9, RTO17), it is `RealtimeObject`'s, and the pool is a mapping of
object ids to objects (RTO3a); this is shape deviation S-2. A test that builds only
`pool = ObjectsPool()` and then drives the state machine works on the pool a standalone
`RealtimeObject()` holds (`_driven_pool()` below); one that builds
`RealtimeObject(pool: pool)` does the same with `RealtimeObject(pool=pool)`. The
`_process_*` helpers below are the specification's three `process*` calls.

The channel hands `RealtimeObject` an ATTACHED's HAS_OBJECTS flag and nothing else (RTO4),
so the `channelSerial` the specification gives its ATTACHED messages goes no further than
the message dictionary. An OBJECT_SYNC's `channelSerial` is the sync cursor (RTO5a1) and is
passed on.

Updates are emitted synchronously (`LiveObject.notify_updated`), so a listener registered
with `subscribe` has seen every update by the time the call that caused it returns. The
tests that drive a `RealtimeObject` are coroutines only so that an implementation is free to
touch the event loop.
"""

from ably.pubsub.objects.enums import ObjectsOperationSource, ObjectsSyncState
from ably.pubsub.objects.livecounter import InternalLiveCounter
from ably.pubsub.objects.livemap import InternalLiveMap
from ably.pubsub.objects.objectmessage import ObjectData, ObjectOperationAction, ObjectsMapEntry
from ably.pubsub.objects.objectspool import ObjectsPool
from ably.pubsub.objects.realtimeobject import RealtimeObject
from test.uts.objects.helpers.standard_test_pool import (
    ATTACHED,
    HAS_OBJECTS,
    LWW,
    build_counter_inc,
    build_map_set,
    build_object_message,
    build_object_state,
    build_object_sync_message,
    object_message,
    object_messages,
    objects_attached_message,
)


def _driven_pool():
    """The specification's `pool = ObjectsPool()`, in a test that then drives the sync state machine.

    S-2: the state machine is `RealtimeObject`'s, so the pool is the one a standalone
    `RealtimeObject` holds. Returns `(realtime_object, pool)`.
    """
    realtime_object = RealtimeObject()
    return realtime_object, realtime_object._objects_pool


def _process_attached(realtime_object, attached):
    """The specification's `pool.processAttached(attached)` (S-2).

    `RealtimeObject` is given the ATTACHED's HAS_OBJECTS flag; a message with no `flags`
    has the flag unset (RTO4b).
    """
    realtime_object._on_attached(has_objects=bool(attached.get('flags', 0) & HAS_OBJECTS))


def _process_object_sync(realtime_object, protocol_message):
    """The specification's `pool.processObjectSync(protocol_message)` (S-2)."""
    realtime_object._handle_object_sync_messages(
        object_messages(protocol_message), protocol_message.get('channelSerial'))


def _process_object_message(realtime_object, protocol_message):
    """The specification's `pool.processObjectMessage(protocol_message)` (S-2)."""
    realtime_object._handle_object_messages(object_messages(protocol_message))


def _empty_root_state():
    """The root state most syncs carry: an empty LWW map whose create operation adds nothing."""
    return build_object_state('root', {'aaa': 't:0'}, map={'semantics': LWW, 'entries': {}},
                              create_op={'mapCreate': {'semantics': LWW, 'entries': {}}})


# UTS: objects/unit/RTO3/pool-init-root-0
def test_rto3_pool_init_root():
    pool = ObjectsPool()

    assert 'root' in pool
    assert isinstance(pool['root'], InternalLiveMap)
    assert pool['root'].data == {}
    assert pool['root'].object_id == 'root'


# UTS: objects/unit/RTO4/attached-has-objects-syncing-0
async def test_rto4_attached_has_objects_syncing():
    realtime_object, pool = _driven_pool()

    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    assert realtime_object._sync_state == ObjectsSyncState.SYNCING


# UTS: objects/unit/RTO4b/attached-no-objects-synced-0
async def test_rto4b_attached_no_objects_synced():
    realtime_object, pool = _driven_pool()
    pool['counter:abc@1000'] = InternalLiveCounter('counter:abc@1000')
    pool['root'].data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial='01', tombstone=False),
    }
    root = pool['root']

    updates = []
    pool['root'].subscribe(updates.append)

    _process_attached(realtime_object, {'action': ATTACHED, 'channel': 'test', 'flags': 0})

    assert realtime_object._sync_state == ObjectsSyncState.SYNCED
    assert 'counter:abc@1000' not in pool
    assert 'root' in pool
    # RTO4b2: the root map's data is cleared in place; the root is never replaced
    assert pool['root'] is root
    assert pool['root'].data == {}
    assert len(updates) >= 1
    assert updates[0].update == {'name': 'removed'}
    assert updates[0].object_message is None


# UTS: objects/unit/RTO4b2a/reset-of-empty-root-emits-no-update-0
async def test_rto4b2a_reset_of_empty_root_emits_no_update():
    realtime_object, pool = _driven_pool()
    pool['counter:abc@1000'] = InternalLiveCounter('counter:abc@1000')
    # The root is already empty, the zero value of RTLM4c
    pool['root'].data = {}

    updates = []
    pool['root'].subscribe(updates.append)

    _process_attached(realtime_object, {'action': ATTACHED, 'channel': 'test', 'flags': 0})

    assert realtime_object._sync_state == ObjectsSyncState.SYNCED
    # RTO4b1: the objects other than the root are still removed
    assert 'counter:abc@1000' not in pool
    assert 'root' in pool
    assert pool['root'].data == {}
    # RTO4b2a: no key was removed, so the update has no changed keys, is a no-op and is
    # not delivered
    assert len(updates) == 0

    # Liveness control: a reset that does remove a key is delivered, so the count of zero
    # above is the empty root's no-op and not a dead subscription. Emission is synchronous
    # at this tier, so there is nothing to wait for.
    realtime_object2, pool2 = _driven_pool()
    pool2['root'].data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial='01', tombstone=False),
    }
    control = []
    pool2['root'].subscribe(control.append)
    _process_attached(realtime_object2, {'action': ATTACHED, 'channel': 'test', 'flags': 0})
    assert len(control) >= 1
    assert control[0].update == {'name': 'removed'}


# UTS: objects/unit/RTO5/sync-complete-sequence-0
async def test_rto5_sync_complete_sequence():
    realtime_object, pool = _driven_pool()
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [
        build_object_state('root', {'aaa': 't:0'}, map={
            'semantics': LWW,
            'entries': {'name': {'data': {'string': 'Alice'}, 'timeserial': 't:0'}},
        }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
        build_object_state('counter:abc@1000', {'aaa': 't:0'}, counter={'count': 0},
                           create_op={'counterCreate': {'count': 42}}),
    ]))

    assert realtime_object._sync_state == ObjectsSyncState.SYNCED
    assert 'root' in pool
    assert 'counter:abc@1000' in pool
    assert pool['root'].data['name'].data == ObjectData(string='Alice')
    assert pool['counter:abc@1000'].data == 42


# UTS: objects/unit/RTO5a2/new-sequence-discards-old-0
async def test_rto5a2_new_sequence_discards_old():
    realtime_object, pool = _driven_pool()
    _process_attached(realtime_object, objects_attached_message('test', 'seq1:cursor', flags=HAS_OBJECTS))
    _process_object_sync(realtime_object, build_object_sync_message('test', 'seq1:more', [
        build_object_state('counter:old@1000', {'aaa': 't:0'}, counter={'count': 10}),
    ]))

    _process_object_sync(realtime_object, build_object_sync_message('test', 'seq2:', [
        _empty_root_state(),
        build_object_state('counter:new@1000', {'aaa': 't:0'}, counter={'count': 99}),
    ]))

    assert realtime_object._sync_state == ObjectsSyncState.SYNCED
    assert 'counter:old@1000' not in pool
    assert 'counter:new@1000' in pool


# UTS: objects/unit/RTO5a5/absent-channel-serial-0
async def test_rto5a5_absent_channel_serial():
    realtime_object, pool = _driven_pool()
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    # No channelSerial: the whole sync is contained in this one message (RTO5a5)
    _process_object_sync(realtime_object, build_object_sync_message('test', None, [
        build_object_state('counter:new@1000', {'aaa': 't:0'}, counter={'count': 99}),
    ]))

    assert realtime_object._sync_state == ObjectsSyncState.SYNCED
    assert 'counter:new@1000' in pool


# UTS: objects/unit/RTO5a6/malformed-channel-serial-treated-as-absent-0
async def test_rto5a6_malformed_channel_serial_treated_as_absent():
    realtime_object, pool = _driven_pool()
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    # 'malformedserialnocolon' has no ':' separator, so it cannot be parsed per RTO5a1;
    # RTO5a6 handles it as if the channelSerial were absent (RTO5a5)
    _process_object_sync(realtime_object, build_object_sync_message('test', 'malformedserialnocolon', [
        build_object_state('counter:new@1000', {'aaa': 't:0'}, counter={'count': 99}),
    ]))

    # Treated as absent (RTO5a5): the message was applied and the sync ended
    assert realtime_object._sync_state == ObjectsSyncState.SYNCED
    assert 'counter:new@1000' in pool


# UTS: objects/unit/RTO5f2a/partial-map-merge-0
async def test_rto5f2a_partial_map_merge():
    realtime_object, pool = _driven_pool()
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:more', [
        build_object_state('root', {'aaa': 't:0'}, map={
            'semantics': LWW,
            'entries': {'name': {'data': {'string': 'Alice'}, 'timeserial': 't:0'}},
        }),
    ]))
    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [
        build_object_state('root', {'aaa': 't:0'}, map={
            'semantics': LWW,
            'entries': {'age': {'data': {'number': 30}, 'timeserial': 't:0'}},
        }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
    ]))

    assert pool['root'].data['name'].data == ObjectData(string='Alice')
    assert pool['root'].data['age'].data == ObjectData(number=30)


# UTS: objects/unit/RTO5c2/remove-absent-objects-0
async def test_rto5c2_remove_absent_objects():
    realtime_object, pool = _driven_pool()
    pool['counter:old@1000'] = InternalLiveCounter('counter:old@1000')
    pool['counter:old@1000'].data = 99
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [_empty_root_state()]))

    assert 'counter:old@1000' not in pool
    assert 'root' in pool


# UTS: objects/unit/RTO5c9/clear-applied-on-ack-serials-0
async def test_rto5c9_clear_applied_on_ack_serials():
    pool = ObjectsPool()
    realtime_object = RealtimeObject(pool=pool)
    realtime_object._applied_on_ack_serials = {'serial-1', 'serial-2'}
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [_empty_root_state()]))

    # The specification's `{}` is the empty set
    assert realtime_object._applied_on_ack_serials == set()


# UTS: objects/unit/RTO8a/buffer-during-syncing-0
async def test_rto8a_buffer_during_syncing():
    pool = ObjectsPool()
    realtime_object = RealtimeObject(pool=pool)
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    _process_object_message(realtime_object, build_object_message('test', [
        build_counter_inc('counter:abc@1000', 5, '01', 'site1'),
    ]))

    assert realtime_object._sync_state == ObjectsSyncState.SYNCING
    assert len(realtime_object._buffered_object_operations) == 1
    assert 'counter:abc@1000' not in pool


# UTS: objects/unit/RTO5c6/apply-buffered-on-sync-0
async def test_rto5c6_apply_buffered_on_sync():
    pool = ObjectsPool()
    realtime_object = RealtimeObject(pool=pool)
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))
    _process_object_message(realtime_object, build_object_message('test', [
        build_counter_inc('counter:abc@1000', 10, '02', 'site1'),
    ]))

    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [
        _empty_root_state(),
        build_object_state('counter:abc@1000', {'aaa': 't:0'}, counter={'count': 0},
                           create_op={'counterCreate': {'count': 100}}),
    ]))

    assert pool['counter:abc@1000'].data == 110
    assert len(realtime_object._buffered_object_operations) == 0


# UTS: objects/unit/RTO9a1/null-operation-warning-0
async def test_rto9a1_null_operation_warning():
    realtime_object, pool = _driven_pool()
    realtime_object._sync_state = ObjectsSyncState.SYNCED

    # The specification's `ObjectMessage(serial: "01", siteCode: "site1", operation: null)`
    _process_object_message(realtime_object, build_object_message('test', [
        {'serial': '01', 'siteCode': 'site1'},
    ]))

    assert len(pool) == 1


# UTS: objects/unit/RTO9a3/dedup-applied-on-ack-0
async def test_rto9a3_dedup_applied_on_ack():
    pool = ObjectsPool()
    realtime_object = RealtimeObject(pool=pool)
    realtime_object._sync_state = ObjectsSyncState.SYNCED
    pool['counter:abc@1000'] = InternalLiveCounter('counter:abc@1000')
    pool['counter:abc@1000'].data = 10
    realtime_object._applied_on_ack_serials = {'echo-serial-1'}

    _process_object_message(realtime_object, build_object_message('test', [
        {
            'serial': 'echo-serial-1',
            'siteCode': 'site1',
            'operation': {
                'action': int(ObjectOperationAction.COUNTER_INC),
                'objectId': 'counter:abc@1000',
                'counterInc': {'number': 5},
            },
        },
    ]))

    assert pool['counter:abc@1000'].data == 10
    assert 'echo-serial-1' not in realtime_object._applied_on_ack_serials


# UTS: objects/unit/RTO9a2a4/local-source-adds-serial-0
async def test_rto9a2a4_local_source_adds_serial():
    pool = ObjectsPool()
    realtime_object = RealtimeObject(pool=pool)
    realtime_object._sync_state = ObjectsSyncState.SYNCED
    pool['counter:abc@1000'] = InternalLiveCounter('counter:abc@1000')

    realtime_object._apply_object_messages([
        object_message(build_counter_inc('counter:abc@1000', 5, 'local-serial-1', 'test-site')),
    ], ObjectsOperationSource.LOCAL)

    assert 'local-serial-1' in realtime_object._applied_on_ack_serials
    assert pool['counter:abc@1000'].data == 5


# UTS: objects/unit/RTO9a2b/unsupported-action-warning-0
async def test_rto9a2b_unsupported_action_warning():
    realtime_object, pool = _driven_pool()
    realtime_object._sync_state = ObjectsSyncState.SYNCED

    # The specification's `action: "UNKNOWN_ACTION"`: 99 is no ObjectOperationAction, so it
    # decodes to UNKNOWN (OOP2a)
    _process_object_message(realtime_object, build_object_message('test', [
        {'serial': '01', 'siteCode': 'site1', 'operation': {'action': 99, 'objectId': 'counter:abc@1000'}},
    ]))

    assert len(pool) == 1


# UTS: objects/unit/RTO6/zero-value-from-prefix-0
async def test_rto6_zero_value_from_prefix():
    realtime_object, pool = _driven_pool()
    realtime_object._sync_state = ObjectsSyncState.SYNCED

    _process_object_message(realtime_object, build_object_message('test', [
        build_counter_inc('counter:new@2000', 5, '01', 'site1'),
    ]))
    _process_object_message(realtime_object, build_object_message('test', [
        build_map_set('map:new@2000', 'key', {'string': 'val'}, '01', 'site1'),
    ]))

    assert 'counter:new@2000' in pool
    assert isinstance(pool['counter:new@2000'], InternalLiveCounter)
    assert pool['counter:new@2000'].data == 5

    assert 'map:new@2000' in pool
    assert isinstance(pool['map:new@2000'], InternalLiveMap)
    assert pool['map:new@2000'].data['key'].data == ObjectData(string='val')


# UTS: objects/unit/RTO5d/null-object-skipped-0
async def test_rto5d_null_object_skipped():
    realtime_object, pool = _driven_pool()
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    # The specification's `ObjectMessage(object: null)` is the empty message `{}`
    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [
        {},
        _empty_root_state(),
    ]))

    assert realtime_object._sync_state == ObjectsSyncState.SYNCED


# UTS: objects/unit/RTO5f3/unsupported-type-skipped-0
async def test_rto5f3_unsupported_type_skipped():
    realtime_object, pool = _driven_pool()
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [
        _empty_root_state(),
        {'object': {'objectId': 'unknown:xyz@1000', 'siteTimeserials': {}}},
    ]))

    assert realtime_object._sync_state == ObjectsSyncState.SYNCED
    assert 'unknown:xyz@1000' not in pool


# UTS: objects/unit/RTO5e/object-sync-transitions-syncing-0
async def test_rto5e_object_sync_transitions_syncing():
    realtime_object, pool = _driven_pool()

    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:more', [
        build_object_state('root', {'aaa': 't:0'}, map={'semantics': LWW, 'entries': {}}),
    ]))

    assert realtime_object._sync_state == ObjectsSyncState.SYNCING


# UTS: objects/unit/RTO5c7/sync-emits-updates-0
async def test_rto5c7_sync_emits_updates():
    realtime_object, pool = _driven_pool()
    pool['root'].data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Old'), timeserial='01', tombstone=False),
    }

    updates = []
    pool['root'].subscribe(updates.append)

    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [
        build_object_state('root', {'aaa': 't:0'}, map={
            'semantics': LWW,
            'entries': {'name': {'data': {'string': 'New'}, 'timeserial': 't:0'}},
        }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
    ]))

    assert len(updates) >= 1
    assert 'name' in updates[0].update
    assert updates[0].update['name'] == 'updated'


# UTS: objects/unit/RTO5f2b/partial-counter-error-0
async def test_rto5f2b_partial_counter_error():
    realtime_object, pool = _driven_pool()
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:more', [
        build_object_state('counter:abc@1000', {'aaa': 't:0'}, counter={'count': 10}),
    ]))
    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [
        _empty_root_state(),
        build_object_state('counter:abc@1000', {'aaa': 't:0'}, counter={'count': 5}),
    ]))

    assert pool['counter:abc@1000'].data == 10


# UTS: objects/unit/RTO4d/attached-clears-buffer-0
async def test_rto4d_attached_clears_buffer():
    pool = ObjectsPool()
    realtime_object = RealtimeObject(pool=pool)
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))
    _process_object_message(realtime_object, build_object_message('test', [
        build_counter_inc('counter:abc@1000', 5, '01', 'site1'),
    ]))
    assert len(realtime_object._buffered_object_operations) == 1

    _process_attached(realtime_object, objects_attached_message('test', 'sync2:cursor', flags=HAS_OBJECTS))

    assert len(realtime_object._buffered_object_operations) == 0


# UTS: objects/unit/RTO4-RTO5/attached-during-syncing-resets-0
async def test_rto4_rto5_attached_during_syncing_resets():
    realtime_object, pool = _driven_pool()
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))
    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:more', [
        build_object_state('counter:old@1000', {'aaa': 't:0'}, counter={'count': 10}),
    ]))
    assert realtime_object._sync_state == ObjectsSyncState.SYNCING

    _process_attached(realtime_object, objects_attached_message('test', 'sync2:cursor', flags=HAS_OBJECTS))
    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync2:', [
        _empty_root_state(),
        build_object_state('counter:new@1000', {'aaa': 't:0'}, counter={'count': 99}),
    ]))

    assert realtime_object._sync_state == ObjectsSyncState.SYNCED
    assert 'counter:old@1000' not in pool
    assert 'counter:new@1000' in pool


# UTS: objects/unit/RTO5-RTO7/new-sync-keeps-buffer-0
async def test_rto5_rto7_new_sync_keeps_buffer():
    pool = ObjectsPool()
    realtime_object = RealtimeObject(pool=pool)
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))
    _process_object_message(realtime_object, build_object_message('test', [
        build_counter_inc('counter:abc@1000', 5, '01', 'site1'),
    ]))
    assert len(realtime_object._buffered_object_operations) == 1

    _process_object_sync(realtime_object, build_object_sync_message('test', 'seq2:', [
        _empty_root_state(),
        build_object_state('counter:abc@1000', {'aaa': 't:0'}, counter={'count': 0},
                           create_op={'counterCreate': {'count': 100}}),
    ]))

    assert realtime_object._sync_state == ObjectsSyncState.SYNCED
    assert pool['counter:abc@1000'].data == 105


# UTS: objects/unit/RTO7-RTO8/buffer-without-attached-0
async def test_rto7_rto8_buffer_without_attached():
    pool = ObjectsPool()
    realtime_object = RealtimeObject(pool=pool)
    assert realtime_object._sync_state == ObjectsSyncState.INITIALIZED

    _process_object_message(realtime_object, build_object_message('test', [
        build_counter_inc('counter:abc@1000', 5, '01', 'site1'),
    ]))

    assert len(realtime_object._buffered_object_operations) == 1


# UTS: objects/unit/RTO5c-RTLM23/sync-clear-timeserial-hides-create-entries-0
async def test_rto5c_rtlm23_sync_clear_timeserial_hides_create_entries():
    realtime_object, pool = _driven_pool()
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [
        build_object_state('root', {'aaa': 't:0'}, map={
            'semantics': LWW,
            'entries': {},
            'clearTimeserial': '05',
        }, create_op={'mapCreate': {
            'semantics': LWW,
            'entries': {
                'old_key': {'data': {'string': 'old'}, 'timeserial': '03'},
                'new_key': {'data': {'string': 'new'}, 'timeserial': '07'},
            },
        }}),
    ]))

    assert realtime_object._sync_state == ObjectsSyncState.SYNCED
    assert 'old_key' not in pool['root'].data
    assert pool['root'].data['new_key'].data == ObjectData(string='new')


# UTS: objects/unit/RTO5c10/sync-rebuilds-parent-refs-0
async def test_rto5c10_sync_rebuilds_parent_refs():
    realtime_object, pool = _driven_pool()
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [
        build_object_state('root', {'aaa': 't:0'}, map={
            'semantics': LWW,
            'entries': {
                'score': {'data': {'objectId': 'counter:score@1000'}, 'timeserial': 't:0'},
                'profile': {'data': {'objectId': 'map:profile@1000'}, 'timeserial': 't:0'},
                'name': {'data': {'string': 'Alice'}, 'timeserial': 't:0'},
            },
        }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
        build_object_state('counter:score@1000', {'aaa': 't:0'}, counter={'count': 0},
                           create_op={'counterCreate': {'count': 100}}),
        build_object_state('map:profile@1000', {'aaa': 't:0'}, map={
            'semantics': LWW,
            'entries': {
                'nested_counter': {'data': {'objectId': 'counter:nested@1000'}, 'timeserial': 't:0'},
            },
        }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
        build_object_state('counter:nested@1000', {'aaa': 't:0'}, counter={'count': 0},
                           create_op={'counterCreate': {'count': 5}}),
    ]))

    # root is not referenced by any parent
    assert pool['root'].parent_references == {}
    # counter:score@1000 is referenced by root at key 'score'
    assert pool['counter:score@1000'].parent_references == {'root': {'score'}}
    # map:profile@1000 is referenced by root at key 'profile'
    assert pool['map:profile@1000'].parent_references == {'root': {'profile'}}
    # counter:nested@1000 is referenced by map:profile@1000 at key 'nested_counter'
    assert pool['counter:nested@1000'].parent_references == {'map:profile@1000': {'nested_counter'}}
    # The primitive-valued entry 'name' appears in no parent_references, which the
    # equalities above already establish


# UTS: objects/unit/RTO5c10/resync-rebuilds-parent-refs-0
async def test_rto5c10_resync_rebuilds_parent_refs():
    realtime_object, pool = _driven_pool()
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))

    # First sync: counter:abc@1000 is a child of root
    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [
        build_object_state('root', {'aaa': 't:0'}, map={
            'semantics': LWW,
            'entries': {
                'counter_key': {'data': {'objectId': 'counter:abc@1000'}, 'timeserial': 't:0'},
            },
        }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
        build_object_state('counter:abc@1000', {'aaa': 't:0'}, counter={'count': 0},
                           create_op={'counterCreate': {'count': 10}}),
    ]))
    assert pool['counter:abc@1000'].parent_references == {'root': {'counter_key'}}

    # Second sync: counter:abc@1000 is a child of map:wrapper@1000, not of root
    _process_attached(realtime_object, objects_attached_message('test', 'sync2:cursor', flags=HAS_OBJECTS))
    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync2:', [
        build_object_state('root', {'aaa': 't:1'}, map={
            'semantics': LWW,
            'entries': {
                'wrapper': {'data': {'objectId': 'map:wrapper@1000'}, 'timeserial': 't:1'},
            },
        }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
        build_object_state('map:wrapper@1000', {'aaa': 't:1'}, map={
            'semantics': LWW,
            'entries': {
                'moved_counter': {'data': {'objectId': 'counter:abc@1000'}, 'timeserial': 't:1'},
            },
        }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
        build_object_state('counter:abc@1000', {'aaa': 't:1'}, counter={'count': 0},
                           create_op={'counterCreate': {'count': 20}}),
    ]))

    assert realtime_object._sync_state == ObjectsSyncState.SYNCED
    # root is not referenced by any parent
    assert pool['root'].parent_references == {}
    # map:wrapper@1000 is a child of root at key 'wrapper'
    assert pool['map:wrapper@1000'].parent_references == {'root': {'wrapper'}}
    # counter:abc@1000 is a child of map:wrapper@1000, and no longer of root
    assert pool['counter:abc@1000'].parent_references == {'map:wrapper@1000': {'moved_counter'}}


# UTS: objects/unit/RTO5c10/empty-sync-parent-refs-0
async def test_rto5c10_empty_sync_parent_refs():
    realtime_object, pool = _driven_pool()

    # A normal sync first, to populate parent_references
    _process_attached(realtime_object, objects_attached_message('test', 'sync1:cursor', flags=HAS_OBJECTS))
    _process_object_sync(realtime_object, build_object_sync_message('test', 'sync1:', [
        build_object_state('root', {'aaa': 't:0'}, map={
            'semantics': LWW,
            'entries': {
                'child': {'data': {'objectId': 'counter:child@1000'}, 'timeserial': 't:0'},
            },
        }, create_op={'mapCreate': {'semantics': LWW, 'entries': {}}}),
        build_object_state('counter:child@1000', {'aaa': 't:0'}, counter={'count': 0},
                           create_op={'counterCreate': {'count': 1}}),
    ]))
    assert pool['counter:child@1000'].parent_references == {'root': {'child'}}

    # An empty sync: ATTACHED without HAS_OBJECTS
    _process_attached(realtime_object, {'action': ATTACHED, 'channel': 'test', 'flags': 0})

    assert realtime_object._sync_state == ObjectsSyncState.SYNCED
    # counter:child@1000 was removed from the pool (RTO4b1)
    assert 'counter:child@1000' not in pool
    # root remains, with empty data and empty parent_references
    assert 'root' in pool
    assert pool['root'].data == {}
    assert pool['root'].parent_references == {}
