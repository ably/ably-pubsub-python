"""Derived from uts/objects/unit/internal_live_counter.md in ably/specification.

Spec points: RTLC1, RTLC3, RTLC4, RTLC6, RTLC7, RTLC8, RTLC9, RTLC14, RTLC16, RTLO3, RTLO4a,
RTLO4b4d, RTLO4b4e, RTLO4e, RTLO5, RTLO6

The specification drives an `InternalLiveCounter` directly and reads the update from
`update = counter.applyOperation(...)`, or `false` when the operation is rejected.
`apply_operation` returns whether the operation applied (RTLC7g) and emits the update
through `notify_updated` (RTLC7d1a, RTLC7d5a, RTLC7d4c), so each test records the
emitted updates with `capture_updates` (shape deviation S-1): where the specification
reads `update`, the operation applied and emitted exactly one update, a no-op included;
where it reads `result == false`, the operation did not apply and emitted nothing.
`replace_data` returns its update (RTLC6h), as the specification has it.
"""

from ably.pubsub.objects.enums import ObjectsOperationSource
from ably.pubsub.objects.livecounter import InternalLiveCounter
from ably.pubsub.objects.objectmessage import ObjectOperationAction
from test.uts.helpers.clock import FakeClock
from test.uts.objects.helpers.standard_test_pool import (
    build_counter_create,
    build_counter_inc,
    build_map_set,
    build_object_delete,
    build_object_state,
    capture_updates,
    object_message,
)

COUNTER_ID = 'counter:abc@1000'

CHANNEL = ObjectsOperationSource.CHANNEL
LOCAL = ObjectsOperationSource.LOCAL


def _emitted_update(applied, updates):
    """S-1: the specification's `update = counter.applyOperation(...)`.

    An operation that applies returns True and emits exactly one update, a no-op included.
    """
    assert applied is True, 'expected the operation to apply'
    assert len(updates) == 1, f'expected the operation to emit exactly one update, got {updates!r}'
    return updates[0]


def _assert_not_applied(applied, updates):
    """S-1: the specification's `result == false`: the operation did not apply and emitted nothing."""
    assert applied is False
    assert updates == []


# UTS: objects/unit/RTLC4/zero-value-0
def test_rtlc4_zero_value():
    counter = InternalLiveCounter(COUNTER_ID)

    assert counter.data == 0
    assert counter.object_id == COUNTER_ID
    assert counter.is_tombstone is False
    assert counter.tombstoned_at is None
    assert counter.create_operation_is_merged is False
    assert counter.site_timeserials == {}


# UTS: objects/unit/RTLC9/counter-inc-basic-0
def test_rtlc9_counter_inc_basic():
    counter = InternalLiveCounter(COUNTER_ID)
    updates = capture_updates(counter)

    msg = object_message(build_counter_inc(COUNTER_ID, 5, '01', 'site1'))
    applied = counter.apply_operation(msg, CHANNEL)

    assert counter.data == 5
    update = _emitted_update(applied, updates)
    assert update.noop is False
    assert update.update.amount == 5
    assert update.object_message is msg


# UTS: objects/unit/RTLC9/counter-inc-negative-0
def test_rtlc9_counter_inc_negative():
    counter = InternalLiveCounter(COUNTER_ID)
    counter.data = 10
    counter.site_timeserials = {'site1': '00'}
    updates = capture_updates(counter)

    msg = object_message(build_counter_inc(COUNTER_ID, -3, '01', 'site1'))
    applied = counter.apply_operation(msg, CHANNEL)

    assert counter.data == 7
    update = _emitted_update(applied, updates)
    assert update.update.amount == -3
    assert update.object_message is msg


# UTS: objects/unit/RTLC9/counter-inc-missing-number-0
def test_rtlc9_counter_inc_missing_number():
    counter = InternalLiveCounter(COUNTER_ID)
    counter.data = 10
    updates = capture_updates(counter)

    msg = object_message({
        'serial': '01',
        'siteCode': 'site1',
        'operation': {
            'action': int(ObjectOperationAction.COUNTER_INC),
            'objectId': COUNTER_ID,
            'counterInc': {},
        },
    })
    applied = counter.apply_operation(msg, CHANNEL)

    assert counter.data == 10
    update = _emitted_update(applied, updates)
    assert update.noop is True


# UTS: objects/unit/RTLC9/counter-inc-accumulate-0
def test_rtlc9_counter_inc_accumulate():
    counter = InternalLiveCounter(COUNTER_ID)

    counter.apply_operation(object_message(build_counter_inc(COUNTER_ID, 10, '01', 'site1')), CHANNEL)
    counter.apply_operation(object_message(build_counter_inc(COUNTER_ID, 20, '02', 'site1')), CHANNEL)
    counter.apply_operation(object_message(build_counter_inc(COUNTER_ID, -5, '01', 'site2')), CHANNEL)

    assert counter.data == 25


# UTS: objects/unit/RTLC8/counter-create-merge-0
def test_rtlc8_counter_create_merge():
    counter = InternalLiveCounter(COUNTER_ID)
    updates = capture_updates(counter)

    msg = object_message(build_counter_create(COUNTER_ID, {'count': 42}, '01', 'site1'))
    applied = counter.apply_operation(msg, CHANNEL)

    assert counter.data == 42
    assert counter.create_operation_is_merged is True
    update = _emitted_update(applied, updates)
    assert update.update.amount == 42
    assert update.object_message is msg


# UTS: objects/unit/RTLC8/counter-create-already-merged-0
def test_rtlc8_counter_create_already_merged():
    counter = InternalLiveCounter(COUNTER_ID)
    counter.data = 42
    counter.create_operation_is_merged = True
    counter.site_timeserials = {'site1': '00'}
    updates = capture_updates(counter)

    msg = object_message(build_counter_create(COUNTER_ID, {'count': 99}, '01', 'site1'))
    applied = counter.apply_operation(msg, CHANNEL)

    assert counter.data == 42
    update = _emitted_update(applied, updates)
    assert update.noop is True


# UTS: objects/unit/RTLC16/counter-create-no-count-0
def test_rtlc16_counter_create_no_count():
    counter = InternalLiveCounter(COUNTER_ID)
    updates = capture_updates(counter)

    msg = object_message(build_counter_create(COUNTER_ID, {}, '01', 'site1'))
    applied = counter.apply_operation(msg, CHANNEL)

    assert counter.data == 0
    assert counter.create_operation_is_merged is True
    update = _emitted_update(applied, updates)
    assert update.noop is True


# UTS: objects/unit/RTLO4a/apply-empty-site-serial-0
def test_rtlo4a_apply_empty_site_serial():
    counter = InternalLiveCounter(COUNTER_ID)

    msg = object_message(build_counter_inc(COUNTER_ID, 5, '01', 'site1'))
    result = counter.apply_operation(msg, CHANNEL)

    # S-1: the specification's `result IS NOT false` is a True return
    assert result is True
    assert counter.data == 5


# UTS: objects/unit/RTLO4a/reject-stale-serial-0
def test_rtlo4a_reject_stale_serial():
    counter = InternalLiveCounter(COUNTER_ID)
    counter.site_timeserials = {'site1': '05'}
    counter.data = 10
    updates = capture_updates(counter)

    msg = object_message(build_counter_inc(COUNTER_ID, 99, '03', 'site1'))
    result = counter.apply_operation(msg, CHANNEL)

    _assert_not_applied(result, updates)
    assert counter.data == 10


# UTS: objects/unit/RTLO4a/reject-equal-serial-0
def test_rtlo4a_reject_equal_serial():
    counter = InternalLiveCounter(COUNTER_ID)
    counter.site_timeserials = {'site1': '05'}
    counter.data = 10
    updates = capture_updates(counter)

    msg = object_message(build_counter_inc(COUNTER_ID, 99, '05', 'site1'))
    result = counter.apply_operation(msg, CHANNEL)

    _assert_not_applied(result, updates)
    assert counter.data == 10


# UTS: objects/unit/RTLO4a/warn-invalid-serial-0
def test_rtlo4a_warn_invalid_serial():
    counter = InternalLiveCounter(COUNTER_ID)
    updates = capture_updates(counter)

    msg_no_serial = object_message(build_counter_inc(COUNTER_ID, 5, '', 'site1'))
    result1 = counter.apply_operation(msg_no_serial, CHANNEL)

    msg_no_site = object_message(build_counter_inc(COUNTER_ID, 5, '01', ''))
    result2 = counter.apply_operation(msg_no_site, CHANNEL)

    assert counter.data == 0
    assert result1 is False
    assert result2 is False
    # S-1: neither rejected operation emitted an update
    assert updates == []


# UTS: objects/unit/RTLC7c/channel-source-updates-serials-0
def test_rtlc7c_channel_source_updates_serials():
    counter = InternalLiveCounter(COUNTER_ID)

    msg = object_message(build_counter_inc(COUNTER_ID, 5, '01', 'site1'))
    counter.apply_operation(msg, CHANNEL)

    assert counter.site_timeserials['site1'] == '01'


# UTS: objects/unit/RTLC7c/local-source-no-serial-update-0
def test_rtlc7c_local_source_no_serial_update():
    counter = InternalLiveCounter(COUNTER_ID)

    msg = object_message(build_counter_inc(COUNTER_ID, 5, '01', 'site1'))
    counter.apply_operation(msg, LOCAL)

    assert counter.site_timeserials == {}
    assert counter.data == 5


# UTS: objects/unit/RTLC7g/apply-returns-true-0
def test_rtlc7g_apply_returns_true():
    counter = InternalLiveCounter(COUNTER_ID)

    msg = object_message(build_counter_inc(COUNTER_ID, 5, '01', 'site1'))
    result = counter.apply_operation(msg, CHANNEL)

    assert result is True


# UTS: objects/unit/RTLO5/object-delete-tombstones-0
def test_rtlo5_object_delete_tombstones():
    counter = InternalLiveCounter(COUNTER_ID)
    counter.data = 42
    counter.site_timeserials = {'site1': '00'}
    updates = capture_updates(counter)

    msg = object_message(build_object_delete(COUNTER_ID, '01', 'site1', 1700000000000))
    applied = counter.apply_operation(msg, CHANNEL)

    assert counter.is_tombstone is True
    assert counter.data == 0
    assert counter.tombstoned_at == 1700000000000
    update = _emitted_update(applied, updates)
    assert update.update.amount == -42
    assert update.tombstone is True
    assert update.object_message is msg


# UTS: objects/unit/RTLO5/tombstone-zero-value-counter-emits-update-0
def test_rtlo5_tombstone_zero_value_counter_emits_update():
    counter = InternalLiveCounter(COUNTER_ID)
    counter.data = 0
    counter.site_timeserials = {'site1': '00'}
    updates = capture_updates(counter)

    msg = object_message(build_object_delete(COUNTER_ID, '01', 'site1', 1700000000000))
    applied = counter.apply_operation(msg, CHANNEL)

    assert counter.is_tombstone is True
    assert counter.data == 0
    update = _emitted_update(applied, updates)
    # The RTLC14c zero-delta exception does not apply to a tombstone diff (RTLO4e5)
    assert update.noop is False
    assert update.tombstone is True
    assert update.update.amount == 0
    assert update.object_message is msg


# UTS: objects/unit/RTLC7e/tombstoned-reject-ops-0
def test_rtlc7e_tombstoned_reject_ops():
    counter = InternalLiveCounter(COUNTER_ID)
    counter.is_tombstone = True
    counter.tombstoned_at = 1700000000000
    updates = capture_updates(counter)

    msg = object_message(build_counter_inc(COUNTER_ID, 5, '01', 'site1'))
    result = counter.apply_operation(msg, CHANNEL)

    _assert_not_applied(result, updates)
    assert counter.data == 0


# UTS: objects/unit/RTLO6/tombstoned-at-from-serial-timestamp-0
def test_rtlo6_tombstoned_at_from_serial_timestamp():
    counter = InternalLiveCounter(COUNTER_ID)

    msg = object_message(build_object_delete(COUNTER_ID, '01', 'site1', 1700000050000))
    counter.apply_operation(msg, CHANNEL)

    assert counter.tombstoned_at == 1700000050000


# UTS: objects/unit/RTLO6/tombstoned-at-local-clock-0
def test_rtlo6_tombstoned_at_local_clock():
    # The local clock is the counter's own. A fake one, at an epoch no fixture uses, holds
    # still between the two readings, so the bounds pin the value RTLO6b must take.
    clock = FakeClock(epoch_ms=1_700_000_123_456)
    counter = InternalLiveCounter(COUNTER_ID, clock=clock)
    before_time = clock.now_ms()

    msg = object_message(build_object_delete(COUNTER_ID, '01', 'site1'))
    counter.apply_operation(msg, CHANNEL)

    after_time = clock.now_ms()
    assert counter.tombstoned_at >= before_time
    assert counter.tombstoned_at <= after_time


# UTS: objects/unit/RTLC7d3/unsupported-action-0
def test_rtlc7d3_unsupported_action():
    counter = InternalLiveCounter(COUNTER_ID)
    updates = capture_updates(counter)

    msg = object_message(build_map_set(COUNTER_ID, 'x', {'string': 'y'}, '01', 'site1'))
    result = counter.apply_operation(msg, CHANNEL)

    _assert_not_applied(result, updates)
    assert counter.data == 0


# UTS: objects/unit/RTLC6/replace-data-basic-0
def test_rtlc6_replace_data_basic():
    counter = InternalLiveCounter(COUNTER_ID)
    counter.data = 10
    counter.create_operation_is_merged = True
    counter.site_timeserials = {'site1': '00'}

    state_msg = object_message(build_object_state(COUNTER_ID, {'site2': '05'}, counter={'count': 50}))
    update = counter.replace_data(state_msg)

    assert counter.data == 50
    assert counter.site_timeserials == {'site2': '05'}
    assert counter.create_operation_is_merged is False
    assert update.update.amount == 40
    assert update.object_message is state_msg


# UTS: objects/unit/RTLC6/replace-data-with-create-op-0
def test_rtlc6_replace_data_with_create_op():
    counter = InternalLiveCounter(COUNTER_ID)

    state_msg = object_message(build_object_state(
        COUNTER_ID, {'site1': '01'}, counter={'count': 100}, create_op={'counterCreate': {'count': 50}}))
    update = counter.replace_data(state_msg)

    assert counter.data == 150
    assert counter.create_operation_is_merged is True
    assert update.update.amount == 150
    assert update.object_message is state_msg


# UTS: objects/unit/RTLC6e/replace-data-tombstoned-noop-0
def test_rtlc6e_replace_data_tombstoned_noop():
    counter = InternalLiveCounter(COUNTER_ID)
    counter.is_tombstone = True
    counter.tombstoned_at = 1700000000000
    counter.data = 0

    state_msg = object_message(build_object_state(COUNTER_ID, {'site1': '01'}, counter={'count': 999}))
    update = counter.replace_data(state_msg)

    assert counter.data == 0
    assert update.noop is True


# UTS: objects/unit/RTLC6f/replace-data-tombstone-flag-0
def test_rtlc6f_replace_data_tombstone_flag():
    counter = InternalLiveCounter(COUNTER_ID)
    counter.data = 30

    state_msg = object_message(build_object_state(
        COUNTER_ID, {'site1': '01'}, counter={'count': 0}, tombstone=True))
    update = counter.replace_data(state_msg)

    assert counter.is_tombstone is True
    assert counter.data == 0
    assert update.update.amount == -30
    assert update.tombstone is True
    assert update.object_message is state_msg


# UTS: objects/unit/RTLC6/replace-data-missing-count-0
def test_rtlc6_replace_data_missing_count():
    counter = InternalLiveCounter(COUNTER_ID)
    counter.data = 42

    state_msg = object_message(build_object_state(COUNTER_ID, {'site1': '01'}, counter={}))
    update = counter.replace_data(state_msg)

    assert counter.data == 0
    assert update.update.amount == -42
    assert update.object_message is state_msg


# UTS: objects/unit/RTLC14/diff-calculation-0
def test_rtlc14_diff_calculation():
    counter = InternalLiveCounter(COUNTER_ID)
    counter.data = 20

    state_msg = object_message(build_object_state(COUNTER_ID, {'site1': '01'}, counter={'count': 75}))
    update = counter.replace_data(state_msg)

    assert update.update.amount == 55
    assert update.object_message is state_msg


# UTS: objects/unit/RTLC14c/zero-delta-diff-is-noop-0
def test_rtlc14c_zero_delta_diff_is_noop():
    counter = InternalLiveCounter(COUNTER_ID)
    counter.data = 100

    state_msg = object_message(build_object_state(COUNTER_ID, {'site1': '01'}, counter={'count': 100}))
    update = counter.replace_data(state_msg)

    assert update.noop is True
    assert counter.data == 100


# UTS: objects/unit/RTLC8/create-then-inc-0
def test_rtlc8_create_then_inc():
    counter = InternalLiveCounter(COUNTER_ID)

    counter.apply_operation(
        object_message(build_counter_create(COUNTER_ID, {'count': 100}, '01', 'site1')), CHANNEL)
    counter.apply_operation(object_message(build_counter_inc(COUNTER_ID, 25, '02', 'site1')), CHANNEL)

    assert counter.data == 125
    assert counter.create_operation_is_merged is True


# UTS: objects/unit/RTLO3/live-object-init-properties-0
def test_rtlo3_live_object_init_properties():
    counter = InternalLiveCounter('counter:test@2000')

    assert counter.object_id == 'counter:test@2000'
    assert counter.site_timeserials == {}
    assert counter.create_operation_is_merged is False
    assert counter.is_tombstone is False
    assert counter.tombstoned_at is None
