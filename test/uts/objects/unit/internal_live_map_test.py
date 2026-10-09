"""Derived from uts/objects/unit/internal_live_map.md in ably/specification.

Spec points: RTLM1-RTLM9, RTLM14-RTLM16, RTLM18, RTLM19, RTLM22-RTLM25, RTLO3, RTLO4a, RTLO4e,
RTLO4g, RTLO4h, RTLO5, RTLO6

The specification drives an `InternalLiveMap` directly and reads the update from
`update = map.applyOperation(...)`, or `false` when the operation is rejected.
`apply_operation` returns whether the operation applied (RTLM15g) and emits the update
through `notify_updated` (RTLM15d1a and its siblings), so each test records the emitted
updates with `capture_updates` (shape deviation S-1): where the specification reads
`update`, the operation applied and emitted exactly one update, a no-op included; where
it reads `result == false` or `update == false`, the operation did not apply and emitted
nothing. `replace_data` returns its update (RTLM6h), and `diff` is the static
`InternalLiveMap.diff`, as the specification has them.

Where the specification passes a pool, the map under test reads it but is not the pool's
own root: `ObjectsPool()` creates that (RTO3b1), and the specification builds a second map
with the id `root` alongside it.
"""

from ably.pubsub.objects.enums import ObjectsOperationSource
from ably.pubsub.objects.livecounter import InternalLiveCounter
from ably.pubsub.objects.livemap import InternalLiveMap
from ably.pubsub.objects.objectmessage import ObjectData, ObjectsMapEntry, ObjectsMapSemantics
from ably.pubsub.objects.objectspool import ObjectsPool
from test.uts.objects.helpers.standard_test_pool import (
    LWW,
    build_counter_inc,
    build_map_clear,
    build_map_create,
    build_map_remove,
    build_map_set,
    build_object_delete,
    build_object_state,
    capture_updates,
    object_message,
)

CHANNEL = ObjectsOperationSource.CHANNEL


def _emitted_update(applied, updates):
    """S-1: the specification's `update = map.applyOperation(...)`.

    An operation that applies returns True and emits exactly one update, a no-op included.
    """
    assert applied is True, 'expected the operation to apply'
    assert len(updates) == 1, f'expected the operation to emit exactly one update, got {updates!r}'
    return updates[0]


def _assert_not_applied(applied, updates):
    """S-1: the specification's `result == false`: the operation did not apply and emitted nothing."""
    assert applied is False
    assert updates == []


def _references(child, parent_id, key):
    """Whether `child.parent_references` records the map `parent_id` referencing it at `key`.

    `not _references(...)` is the specification's
    `parent_id NOT IN child.parentReferences OR key NOT IN child.parentReferences[parent_id]`.
    """
    return key in child.parent_references.get(parent_id, set())


# UTS: objects/unit/RTLM4/zero-value-0
def test_rtlm4_zero_value():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)

    assert live_map.data == {}
    assert live_map.clear_timeserial is None
    assert live_map.is_tombstone is False
    assert live_map.create_operation_is_merged is False
    assert live_map.site_timeserials == {}


# UTS: objects/unit/RTLM7/map-set-new-entry-0
def test_rtlm7_map_set_new_entry():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    updates = capture_updates(live_map)

    msg = object_message(build_map_set('root', 'name', {'string': 'Alice'}, '01', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['name'].data == ObjectData(string='Alice')
    assert live_map.data['name'].timeserial == '01'
    assert live_map.data['name'].tombstone is False
    update = _emitted_update(applied, updates)
    assert update.update == {'name': 'updated'}
    assert update.object_message is msg


# UTS: objects/unit/RTLM7/map-set-update-entry-0
def test_rtlm7_map_set_update_entry():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial='01', tombstone=False),
    }
    updates = capture_updates(live_map)

    msg = object_message(build_map_set('root', 'name', {'string': 'Bob'}, '02', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['name'].data == ObjectData(string='Bob')
    assert live_map.data['name'].timeserial == '02'
    update = _emitted_update(applied, updates)
    assert update.update == {'name': 'updated'}
    assert update.object_message is msg


# UTS: objects/unit/RTLM9/lww-reject-stale-0
def test_rtlm9_lww_reject_stale():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial='05', tombstone=False),
    }
    updates = capture_updates(live_map)

    msg = object_message(build_map_set('root', 'name', {'string': 'Bob'}, '03', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['name'].data == ObjectData(string='Alice')
    update = _emitted_update(applied, updates)
    assert update.noop is True


# UTS: objects/unit/RTLM9/lww-reject-equal-0
def test_rtlm9_lww_reject_equal():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial='05', tombstone=False),
    }
    updates = capture_updates(live_map)

    msg = object_message(build_map_set('root', 'name', {'string': 'Bob'}, '05', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['name'].data == ObjectData(string='Alice')
    update = _emitted_update(applied, updates)
    assert update.noop is True


# UTS: objects/unit/RTLM9b/both-empty-reject-0
def test_rtlm9b_both_empty_reject():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial='', tombstone=False),
    }
    updates = capture_updates(live_map)

    msg = object_message(build_map_set('root', 'name', {'string': 'Bob'}, '', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['name'].data == ObjectData(string='Alice')
    # The empty ObjectMessage.serial fails the object-level gate (RTLO4a3) before the
    # entry-level RTLM9b comparison is reached, so apply_operation returns False (RTLM15b).
    _assert_not_applied(applied, updates)
    # RTLM9b itself, which apply_operation cannot reach: an empty or missing entry serial
    # and operation serial are equal, so the operation is not applied
    assert InternalLiveMap.can_apply_map_operation('', '') is False
    assert InternalLiveMap.can_apply_map_operation(None, None) is False


# UTS: objects/unit/RTLM9d/missing-entry-serial-allows-0
def test_rtlm9d_missing_entry_serial_allows():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial=None, tombstone=False),
    }
    updates = capture_updates(live_map)

    msg = object_message(build_map_set('root', 'name', {'string': 'Bob'}, '01', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['name'].data == ObjectData(string='Bob')
    update = _emitted_update(applied, updates)
    assert update.update == {'name': 'updated'}
    assert update.object_message is msg


# UTS: objects/unit/RTLM7h/map-set-clear-timeserial-floor-0
def test_rtlm7h_map_set_clear_timeserial_floor():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.clear_timeserial = '05'
    updates = capture_updates(live_map)

    msg = object_message(build_map_set('root', 'name', {'string': 'Alice'}, '03', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert 'name' not in live_map.data
    update = _emitted_update(applied, updates)
    assert update.noop is True


# UTS: objects/unit/RTLM7g/map-set-objectid-creates-zero-value-0
def test_rtlm7g_map_set_objectid_creates_zero_value():
    pool = ObjectsPool()
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW, pool=pool)

    msg = object_message(build_map_set('root', 'score', {'objectId': 'counter:new@2000'}, '01', 'site1'))
    live_map.apply_operation(msg, CHANNEL)

    assert 'counter:new@2000' in pool
    assert isinstance(pool['counter:new@2000'], InternalLiveCounter)
    assert pool['counter:new@2000'].data == 0


# UTS: objects/unit/RTLM8/map-remove-existing-0
def test_rtlm8_map_remove_existing():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial='01', tombstone=False),
    }
    updates = capture_updates(live_map)

    msg = object_message(build_map_remove('root', 'name', '02', 'site1', 1700000000000))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['name'].data is None
    assert live_map.data['name'].tombstone is True
    assert live_map.data['name'].timeserial == '02'
    assert live_map.data['name'].tombstoned_at == 1700000000000
    update = _emitted_update(applied, updates)
    assert update.update == {'name': 'removed'}
    assert update.object_message is msg


# UTS: objects/unit/RTLM8/map-remove-nonexistent-0
def test_rtlm8_map_remove_nonexistent():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    updates = capture_updates(live_map)

    msg = object_message(build_map_remove('root', 'ghost', '01', 'site1', 1700000000000))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['ghost'].tombstone is True
    assert live_map.data['ghost'].tombstoned_at == 1700000000000
    update = _emitted_update(applied, updates)
    assert update.update == {'ghost': 'removed'}
    assert update.object_message is msg


# UTS: objects/unit/RTLM8g/map-remove-clear-timeserial-floor-0
def test_rtlm8g_map_remove_clear_timeserial_floor():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.clear_timeserial = '05'
    live_map.data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial='04', tombstone=False),
    }
    updates = capture_updates(live_map)

    msg = object_message(build_map_remove('root', 'name', '03', 'site1', 1700000000000))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['name'].data == ObjectData(string='Alice')
    assert live_map.data['name'].tombstone is False
    update = _emitted_update(applied, updates)
    assert update.noop is True

    # UTS SPEC ERROR: the entry's own timeserial ('04') is later than the operation's ('03'),
    # so LWW (RTLM8a1, RTLM9e) rejects the remove with or without the clear floor, and the
    # steps above pass either way. A remove for a key with no entry, still at or below the
    # floor, reaches RTLM8g alone: without it the key would gain a tombstoned entry (RTLM8b).
    ghost_updates = capture_updates(live_map)
    ghost_msg = object_message(build_map_remove('root', 'ghost', '04', 'site1', 1700000000000))
    ghost_applied = live_map.apply_operation(ghost_msg, CHANNEL)

    assert 'ghost' not in live_map.data
    ghost_update = _emitted_update(ghost_applied, ghost_updates)
    assert ghost_update.noop is True


# UTS: objects/unit/RTLM24/map-clear-basic-0
def test_rtlm24_map_clear_basic():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.data = {
        'old': ObjectsMapEntry(data=ObjectData(string='old'), timeserial='02', tombstone=False),
        'new': ObjectsMapEntry(data=ObjectData(string='new'), timeserial='06', tombstone=False),
        'same': ObjectsMapEntry(data=ObjectData(string='same'), timeserial='04', tombstone=False),
    }
    updates = capture_updates(live_map)

    msg = object_message(build_map_clear('root', '04', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.clear_timeserial == '04'
    assert 'old' not in live_map.data
    # RTLM24e1: an entry is removed only if the clear serial is lexicographically greater
    # than the entry's timeserial; 'same' has the clear serial itself, so it is kept
    assert 'same' in live_map.data
    assert 'new' in live_map.data
    update = _emitted_update(applied, updates)
    assert update.update == {'old': 'removed'}
    assert update.object_message is msg


# UTS: objects/unit/RTLM24c/map-clear-stale-0
def test_rtlm24c_map_clear_stale():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.clear_timeserial = '10'
    updates = capture_updates(live_map)

    msg = object_message(build_map_clear('root', '05', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.clear_timeserial == '10'
    update = _emitted_update(applied, updates)
    assert update.noop is True


# UTS: objects/unit/RTLM16/map-create-merge-0
def test_rtlm16_map_create_merge():
    live_map = InternalLiveMap('map:test@1000', ObjectsMapSemantics.LWW)
    updates = capture_updates(live_map)

    msg = object_message(build_map_create('map:test@1000', {
        'semantics': LWW,
        'entries': {
            'name': {'data': {'string': 'Alice'}, 'timeserial': '01'},
            'removed_key': {'tombstone': True, 'timeserial': '01', 'serialTimestamp': 1700000000000},
        },
    }, '02', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['name'].data == ObjectData(string='Alice')
    assert live_map.data['removed_key'].tombstone is True
    assert live_map.create_operation_is_merged is True
    update = _emitted_update(applied, updates)
    assert update.update == {'name': 'updated', 'removed_key': 'removed'}
    assert update.object_message is msg


# UTS: objects/unit/RTLM16b/map-create-already-merged-0
def test_rtlm16b_map_create_already_merged():
    live_map = InternalLiveMap('map:test@1000', ObjectsMapSemantics.LWW)
    live_map.create_operation_is_merged = True
    live_map.site_timeserials = {'site1': '00'}
    updates = capture_updates(live_map)

    msg = object_message(build_map_create('map:test@1000', {
        'semantics': LWW,
        'entries': {'name': {'data': {'string': 'Bob'}, 'timeserial': '01'}},
    }, '01', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert 'name' not in live_map.data
    update = _emitted_update(applied, updates)
    assert update.noop is True


# UTS: objects/unit/RTLM15c/channel-source-updates-serials-0
def test_rtlm15c_channel_source_updates_serials():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)

    msg = object_message(build_map_set('root', 'x', {'number': 1}, '01', 'site1'))
    live_map.apply_operation(msg, CHANNEL)

    assert live_map.site_timeserials['site1'] == '01'


# UTS: objects/unit/RTLM15e/tombstoned-reject-ops-0
def test_rtlm15e_tombstoned_reject_ops():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.is_tombstone = True
    updates = capture_updates(live_map)

    msg = object_message(build_map_set('root', 'x', {'number': 1}, '01', 'site1'))
    result = live_map.apply_operation(msg, CHANNEL)

    _assert_not_applied(result, updates)
    assert live_map.data == {}


# UTS: objects/unit/RTLO5/object-delete-tombstones-map-0
def test_rtlo5_object_delete_tombstones_map():
    live_map = InternalLiveMap('map:test@1000', ObjectsMapSemantics.LWW)
    live_map.data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial='01', tombstone=False),
        'age': ObjectsMapEntry(data=ObjectData(number=30), timeserial='01', tombstone=False),
    }
    live_map.site_timeserials = {'site1': '00'}
    updates = capture_updates(live_map)

    msg = object_message(build_object_delete('map:test@1000', '01', 'site1', 1700000000000))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.is_tombstone is True
    assert live_map.data == {}
    update = _emitted_update(applied, updates)
    assert update.update == {'name': 'removed', 'age': 'removed'}
    assert update.tombstone is True
    assert update.object_message is msg


# UTS: objects/unit/RTLO5/tombstone-empty-map-emits-update-0
def test_rtlo5_tombstone_empty_map_emits_update():
    live_map = InternalLiveMap('map:test@1000', ObjectsMapSemantics.LWW)
    live_map.data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial='01', tombstone=True,
                                tombstoned_at=1600000000000),
        'age': ObjectsMapEntry(data=ObjectData(number=30), timeserial='01', tombstone=True,
                               tombstoned_at=1600000000000),
    }
    live_map.site_timeserials = {'site1': '00'}
    updates = capture_updates(live_map)

    msg = object_message(build_object_delete('map:test@1000', '01', 'site1', 1700000000000))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.is_tombstone is True
    assert live_map.data == {}
    update = _emitted_update(applied, updates)
    # The RTLM22c empty-diff exception does not apply to a tombstone diff (RTLO4e5)
    assert update.noop is False
    assert update.tombstone is True
    assert update.update == {}
    assert update.object_message is msg


# UTS: objects/unit/RTLO4e10/object-delete-root-noop-0
def test_rtlo4e10_object_delete_root_noop():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial='01', tombstone=False),
    }
    live_map.site_timeserials = {'site1': '00'}
    updates = capture_updates(live_map)

    msg = object_message(build_object_delete('root', '01', 'site1', 1700000000000))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.is_tombstone is False
    # The data is untouched
    assert live_map.data['name'].data.string == 'Alice'
    update = _emitted_update(applied, updates)
    assert update.noop is True


# UTS: objects/unit/RTLM14/tombstone-check-objectid-ref-0
def test_rtlm14_tombstone_check_objectid_ref():
    pool = ObjectsPool()
    tombstoned_counter = InternalLiveCounter('counter:dead@1000')
    tombstoned_counter.is_tombstone = True
    pool['counter:dead@1000'] = tombstoned_counter

    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW, pool=pool)
    live_map.data = {
        'alive': ObjectsMapEntry(data=ObjectData(string='ok'), timeserial='01', tombstone=False),
        'dead_entry': ObjectsMapEntry(data=None, timeserial='01', tombstone=True),
        'dead_ref': ObjectsMapEntry(data=ObjectData(object_id='counter:dead@1000'), timeserial='01',
                                    tombstone=False),
    }

    assert live_map.is_entry_tombstoned(live_map.data['alive']) is False
    assert live_map.is_entry_tombstoned(live_map.data['dead_entry']) is True
    assert live_map.is_entry_tombstoned(live_map.data['dead_ref']) is True


# UTS: objects/unit/RTLM6/replace-data-basic-0
def test_rtlm6_replace_data_basic():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.data = {
        'old': ObjectsMapEntry(data=ObjectData(string='old'), timeserial='01', tombstone=False),
    }
    live_map.create_operation_is_merged = True

    state_msg = object_message(build_object_state('root', {'site2': '05'}, map={
        'semantics': LWW,
        'clearTimeserial': '03',
        'entries': {
            'new': {'data': {'string': 'new'}, 'timeserial': '04', 'tombstone': False},
        },
    }))
    update = live_map.replace_data(state_msg)

    assert live_map.site_timeserials == {'site2': '05'}
    assert live_map.create_operation_is_merged is False
    assert live_map.clear_timeserial == '03'
    assert 'old' not in live_map.data
    assert live_map.data['new'].data == ObjectData(string='new')
    assert update.update == {'old': 'removed', 'new': 'updated'}
    assert update.object_message is state_msg


# UTS: objects/unit/RTLM6c1/replace-data-tombstoned-entries-0
def test_rtlm6c1_replace_data_tombstoned_entries():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)

    state_msg = object_message(build_object_state('root', {'site1': '01'}, map={
        'semantics': LWW,
        'entries': {
            'dead': {'tombstone': True, 'timeserial': '01', 'serialTimestamp': 1700000050000},
        },
    }))
    live_map.replace_data(state_msg)

    assert live_map.data['dead'].tombstoned_at == 1700000050000


# UTS: objects/unit/RTLM6d/replace-data-with-create-op-0
def test_rtlm6d_replace_data_with_create_op():
    live_map = InternalLiveMap('map:test@1000', ObjectsMapSemantics.LWW)

    state_msg = object_message(build_object_state('map:test@1000', {'site1': '01'}, map={
        'semantics': LWW,
        'entries': {
            'from_sync': {'data': {'string': 'synced'}, 'timeserial': '01'},
        },
    }, create_op={
        'mapCreate': {
            'semantics': LWW,
            'entries': {
                'from_create': {'data': {'string': 'created'}, 'timeserial': '00'},
            },
        },
    }))
    live_map.replace_data(state_msg)

    assert live_map.data['from_sync'].data == ObjectData(string='synced')
    assert live_map.data['from_create'].data == ObjectData(string='created')
    assert live_map.create_operation_is_merged is True


# UTS: objects/unit/RTLM6f/replace-data-tombstone-flag-0
def test_rtlm6f_replace_data_tombstone_flag():
    live_map = InternalLiveMap('map:test@1000', ObjectsMapSemantics.LWW)
    live_map.data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial='01', tombstone=False),
    }

    state_msg = object_message(build_object_state(
        'map:test@1000', {'site1': '01'}, map={'semantics': LWW, 'entries': {}}, tombstone=True))
    update = live_map.replace_data(state_msg)

    assert live_map.is_tombstone is True
    assert live_map.data == {}
    assert update.update == {'name': 'removed'}
    assert update.tombstone is True
    assert update.object_message is state_msg


# UTS: objects/unit/RTLO4e10/replace-data-tombstone-root-noop-0
def test_rtlo4e10_replace_data_tombstone_root_noop():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial='01', tombstone=False),
    }

    state_msg = object_message(build_object_state(
        'root', {'site1': '01'}, map={'semantics': LWW, 'entries': {}}, tombstone=True))
    update = live_map.replace_data(state_msg)

    assert live_map.is_tombstone is False
    # The data is untouched
    assert live_map.data['name'].data.string == 'Alice'
    assert update.noop is True


# UTS: objects/unit/RTLM19/gc-tombstoned-entries-0
def test_rtlm19_gc_tombstoned_entries():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    grace_period = 86400000
    now = 1700100000000

    live_map.data = {
        'recent_dead': ObjectsMapEntry(data=None, timeserial='01', tombstone=True, tombstoned_at=now - 1000),
        'old_dead': ObjectsMapEntry(data=None, timeserial='01', tombstone=True,
                                    tombstoned_at=now - grace_period - 1),
        'alive': ObjectsMapEntry(data=ObjectData(string='ok'), timeserial='01', tombstone=False),
    }

    live_map.gc_tombstoned_entries(grace_period, now)

    assert 'recent_dead' in live_map.data
    assert 'old_dead' not in live_map.data
    assert 'alive' in live_map.data


# UTS: objects/unit/RTLM22/diff-calculation-0
def test_rtlm22_diff_calculation():
    previous_data = {
        'removed': ObjectsMapEntry(data=ObjectData(string='gone'), timeserial='01', tombstone=False),
        'changed': ObjectsMapEntry(data=ObjectData(string='old'), timeserial='01', tombstone=False),
        'unchanged': ObjectsMapEntry(data=ObjectData(string='same'), timeserial='01', tombstone=False),
        'was_dead': ObjectsMapEntry(data=None, timeserial='01', tombstone=True),
    }
    new_data = {
        'added': ObjectsMapEntry(data=ObjectData(string='new'), timeserial='02', tombstone=False),
        'changed': ObjectsMapEntry(data=ObjectData(string='new_val'), timeserial='02', tombstone=False),
        'unchanged': ObjectsMapEntry(data=ObjectData(string='same'), timeserial='01', tombstone=False),
        'now_dead': ObjectsMapEntry(data=None, timeserial='02', tombstone=True),
    }

    update = InternalLiveMap.diff(previous_data, new_data)

    assert update.update['removed'] == 'removed'
    assert update.update['added'] == 'updated'
    assert update.update['changed'] == 'updated'
    assert 'unchanged' not in update.update
    assert 'was_dead' not in update.update
    assert 'now_dead' not in update.update


# UTS: objects/unit/RTLM22c/empty-diff-is-noop-0
def test_rtlm22c_empty_diff_is_noop():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.data = {
        'name': ObjectsMapEntry(data=ObjectData(string='alice'), timeserial='01', tombstone=False),
    }

    state_msg = object_message(build_object_state('root', {'site1': '02'}, map={
        'semantics': LWW,
        'entries': {
            'name': {'data': {'string': 'alice'}, 'timeserial': '02', 'tombstone': False},
        },
    }))
    update = live_map.replace_data(state_msg)

    assert update.noop is True
    assert live_map.data['name'].data == ObjectData(string='alice')


# UTS: objects/unit/RTLM15d4/unsupported-action-0
def test_rtlm15d4_unsupported_action():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    updates = capture_updates(live_map)

    msg = object_message(build_counter_inc('root', 5, '01', 'site1'))
    result = live_map.apply_operation(msg, CHANNEL)

    _assert_not_applied(result, updates)


# UTS: objects/unit/RTLM6i/replace-data-resets-clear-timeserial-0
def test_rtlm6i_replace_data_resets_clear_timeserial():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.clear_timeserial = '05'
    live_map.data = {
        'x': ObjectsMapEntry(data=ObjectData(number=1), timeserial='03', tombstone=False),
    }

    state_msg = object_message(build_object_state('root', {'site1': '01'}, map={
        'semantics': LWW,
        'entries': {
            'y': {'data': {'number': 2}, 'timeserial': '01'},
        },
    }))
    live_map.replace_data(state_msg)

    assert live_map.clear_timeserial is None
    assert 'y' in live_map.data


# UTS: objects/unit/RTLM14c/tombstoned-ref-yields-null-0
def test_rtlm14c_tombstoned_ref_yields_null():
    pool = ObjectsPool()
    tombstoned_counter = InternalLiveCounter('counter:dead@1000')
    tombstoned_counter.is_tombstone = True
    pool['counter:dead@1000'] = tombstoned_counter

    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW, pool=pool)
    live_map.data = {
        'ref': ObjectsMapEntry(data=ObjectData(object_id='counter:dead@1000'), timeserial='01', tombstone=False),
    }

    # The entry itself is not tombstoned, but the object it references is
    assert live_map.data['ref'].tombstone is False
    # RTLM14c makes the entry tombstoned, so size() does not count it
    assert live_map.size() == 0
    assert live_map.get('ref') is None


# UTS: objects/unit/RTLM7/map-set-revives-tombstoned-0
def test_rtlm7_map_set_revives_tombstoned():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.data = {
        'name': ObjectsMapEntry(data=None, timeserial='01', tombstone=True, tombstoned_at=1700000000000),
    }
    updates = capture_updates(live_map)

    msg = object_message(build_map_set('root', 'name', {'string': 'Alice'}, '02', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['name'].data == ObjectData(string='Alice')
    assert live_map.data['name'].tombstone is False
    assert live_map.data['name'].tombstoned_at is None
    update = _emitted_update(applied, updates)
    assert update.update == {'name': 'updated'}
    assert update.object_message is msg


# UTS: objects/unit/RTLM24/map-clear-preserves-newer-0
def test_rtlm24_map_clear_preserves_newer():
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW)
    live_map.data = {
        'before': ObjectsMapEntry(data=ObjectData(string='a'), timeserial='03', tombstone=False),
        'after': ObjectsMapEntry(data=ObjectData(string='b'), timeserial='07', tombstone=False),
        'no_ts': ObjectsMapEntry(data=ObjectData(string='c'), timeserial=None, tombstone=False),
    }
    updates = capture_updates(live_map)

    msg = object_message(build_map_clear('root', '05', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert 'before' not in live_map.data
    assert 'no_ts' not in live_map.data
    assert live_map.data['after'].data == ObjectData(string='b')
    update = _emitted_update(applied, updates)
    assert 'before' in update.update
    assert 'no_ts' in update.update
    assert 'after' not in update.update
    assert update.object_message is msg


# UTS: objects/unit/RTLM7a3/map-set-overwrite-objectid-parent-refs-0
def test_rtlm7a3_map_set_overwrite_objectid_parent_refs():
    pool = ObjectsPool()
    old_counter = InternalLiveCounter('counter:old@1000')
    new_counter = InternalLiveCounter('counter:new@2000')
    pool['counter:old@1000'] = old_counter
    pool['counter:new@2000'] = new_counter

    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW, pool=pool)
    live_map.data = {
        'ref': ObjectsMapEntry(data=ObjectData(object_id='counter:old@1000'), timeserial='01', tombstone=False),
    }
    # The existing reference, as the map would have recorded it
    old_counter.parent_references = {'root': {'ref'}}
    updates = capture_updates(live_map)

    msg = object_message(build_map_set('root', 'ref', {'objectId': 'counter:new@2000'}, '02', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['ref'].data == ObjectData(object_id='counter:new@2000')
    # removeParentReference was called on the old child
    assert not _references(old_counter, 'root', 'ref')
    # addParentReference was called on the new child
    assert 'root' in new_counter.parent_references
    assert 'ref' in new_counter.parent_references['root']
    update = _emitted_update(applied, updates)
    assert update.update == {'ref': 'updated'}
    assert update.object_message is msg


# UTS: objects/unit/RTLM7g2/map-set-new-entry-add-parent-ref-0
def test_rtlm7g2_map_set_new_entry_add_parent_ref():
    pool = ObjectsPool()
    child_counter = InternalLiveCounter('counter:child@1000')
    pool['counter:child@1000'] = child_counter

    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW, pool=pool)
    updates = capture_updates(live_map)

    msg = object_message(build_map_set('root', 'score', {'objectId': 'counter:child@1000'}, '01', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['score'].data == ObjectData(object_id='counter:child@1000')
    assert 'root' in child_counter.parent_references
    assert 'score' in child_counter.parent_references['root']
    update = _emitted_update(applied, updates)
    assert update.object_message is msg


# UTS: objects/unit/RTLM7/map-set-primitive-no-parent-refs-0
def test_rtlm7_map_set_primitive_no_parent_refs():
    pool = ObjectsPool()
    old_counter = InternalLiveCounter('counter:old@1000')
    pool['counter:old@1000'] = old_counter

    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW, pool=pool)
    live_map.data = {
        'ref': ObjectsMapEntry(data=ObjectData(object_id='counter:old@1000'), timeserial='01', tombstone=False),
    }
    old_counter.parent_references = {'root': {'ref'}}
    updates = capture_updates(live_map)

    msg = object_message(build_map_set('root', 'ref', {'string': 'plain_value'}, '02', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['ref'].data == ObjectData(string='plain_value')
    # removeParentReference was called on the old child, as the entry referenced it; the new
    # value is a primitive, so there is no child to call addParentReference on
    assert not _references(old_counter, 'root', 'ref')
    update = _emitted_update(applied, updates)
    assert update.update == {'ref': 'updated'}
    assert update.object_message is msg


# UTS: objects/unit/RTLM8a3/map-remove-objectid-parent-refs-0
def test_rtlm8a3_map_remove_objectid_parent_refs():
    pool = ObjectsPool()
    child_counter = InternalLiveCounter('counter:child@1000')
    pool['counter:child@1000'] = child_counter

    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW, pool=pool)
    live_map.data = {
        'score': ObjectsMapEntry(data=ObjectData(object_id='counter:child@1000'), timeserial='01',
                                 tombstone=False),
    }
    child_counter.parent_references = {'root': {'score'}}
    updates = capture_updates(live_map)

    msg = object_message(build_map_remove('root', 'score', '02', 'site1', 1700000000000))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['score'].tombstone is True
    # removeParentReference was called on the child
    assert not _references(child_counter, 'root', 'score')
    update = _emitted_update(applied, updates)
    assert update.update == {'score': 'removed'}
    assert update.object_message is msg


# UTS: objects/unit/RTLM8/map-remove-primitive-no-parent-refs-0
def test_rtlm8_map_remove_primitive_no_parent_refs():
    pool = ObjectsPool()
    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW, pool=pool)
    live_map.data = {
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial='01', tombstone=False),
    }
    updates = capture_updates(live_map)

    msg = object_message(build_map_remove('root', 'name', '02', 'site1', 1700000000000))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['name'].tombstone is True
    update = _emitted_update(applied, updates)
    assert update.update == {'name': 'removed'}
    assert update.object_message is msg


# UTS: objects/unit/RTLM24e1c/map-clear-parent-refs-0
def test_rtlm24e1c_map_clear_parent_refs():
    pool = ObjectsPool()
    counter_a = InternalLiveCounter('counter:a@1000')
    counter_b = InternalLiveCounter('counter:b@1000')
    pool['counter:a@1000'] = counter_a
    pool['counter:b@1000'] = counter_b

    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW, pool=pool)
    live_map.data = {
        'ref_a': ObjectsMapEntry(data=ObjectData(object_id='counter:a@1000'), timeserial='02', tombstone=False),
        'ref_b': ObjectsMapEntry(data=ObjectData(object_id='counter:b@1000'), timeserial='02', tombstone=False),
        'primitive': ObjectsMapEntry(data=ObjectData(string='hello'), timeserial='02', tombstone=False),
        'newer': ObjectsMapEntry(data=ObjectData(string='kept'), timeserial='09', tombstone=False),
    }
    counter_a.parent_references = {'root': {'ref_a'}}
    counter_b.parent_references = {'root': {'ref_b'}}
    updates = capture_updates(live_map)

    msg = object_message(build_map_clear('root', '05', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    # ref_a, ref_b and primitive are removed (timeserial '02' < '05'); newer is kept ('09' > '05')
    assert 'ref_a' not in live_map.data
    assert 'ref_b' not in live_map.data
    assert 'primitive' not in live_map.data
    assert 'newer' in live_map.data
    # removeParentReference was called on both child counters
    assert not _references(counter_a, 'root', 'ref_a')
    assert not _references(counter_b, 'root', 'ref_b')
    update = _emitted_update(applied, updates)
    assert update.update == {'ref_a': 'removed', 'ref_b': 'removed', 'primitive': 'removed'}
    assert update.object_message is msg


# UTS: objects/unit/RTLO4e9/tombstone-map-parent-refs-0
def test_rtlo4e9_tombstone_map_parent_refs():
    pool = ObjectsPool()
    child_counter = InternalLiveCounter('counter:child@1000')
    child_map = InternalLiveMap('map:child@1000', ObjectsMapSemantics.LWW)
    pool['counter:child@1000'] = child_counter
    pool['map:child@1000'] = child_map

    live_map = InternalLiveMap('map:test@1000', ObjectsMapSemantics.LWW, pool=pool)
    live_map.data = {
        'counter_ref': ObjectsMapEntry(data=ObjectData(object_id='counter:child@1000'), timeserial='01',
                                       tombstone=False),
        'map_ref': ObjectsMapEntry(data=ObjectData(object_id='map:child@1000'), timeserial='01', tombstone=False),
        'name': ObjectsMapEntry(data=ObjectData(string='Alice'), timeserial='01', tombstone=False),
    }
    live_map.site_timeserials = {'site1': '00'}
    child_counter.parent_references = {'map:test@1000': {'counter_ref'}}
    child_map.parent_references = {'map:test@1000': {'map_ref'}}
    updates = capture_updates(live_map)

    msg = object_message(build_object_delete('map:test@1000', '01', 'site1', 1700000000000))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.is_tombstone is True
    assert live_map.data == {}
    # removeParentReference was called on both children
    assert not _references(child_counter, 'map:test@1000', 'counter_ref')
    assert not _references(child_map, 'map:test@1000', 'map_ref')
    update = _emitted_update(applied, updates)
    assert update.update == {'counter_ref': 'removed', 'map_ref': 'removed', 'name': 'removed'}
    assert update.tombstone is True
    assert update.object_message is msg


# UTS: objects/unit/RTLM7a3/map-set-replace-objectid-both-refs-0
def test_rtlm7a3_map_set_replace_objectid_both_refs():
    pool = ObjectsPool()
    old_map = InternalLiveMap('map:old@1000', ObjectsMapSemantics.LWW)
    new_map = InternalLiveMap('map:new@2000', ObjectsMapSemantics.LWW)
    pool['map:old@1000'] = old_map
    pool['map:new@2000'] = new_map

    live_map = InternalLiveMap('root', ObjectsMapSemantics.LWW, pool=pool)
    live_map.data = {
        'child': ObjectsMapEntry(data=ObjectData(object_id='map:old@1000'), timeserial='01', tombstone=False),
    }
    old_map.parent_references = {'root': {'child'}}
    updates = capture_updates(live_map)

    msg = object_message(build_map_set('root', 'child', {'objectId': 'map:new@2000'}, '02', 'site1'))
    applied = live_map.apply_operation(msg, CHANNEL)

    assert live_map.data['child'].data == ObjectData(object_id='map:new@2000')
    # The old child no longer records the reference from root
    assert not _references(old_map, 'root', 'child')
    # The new child records it
    assert 'root' in new_map.parent_references
    assert 'child' in new_map.parent_references['root']
    update = _emitted_update(applied, updates)
    assert update.update == {'child': 'updated'}
    assert update.object_message is msg
