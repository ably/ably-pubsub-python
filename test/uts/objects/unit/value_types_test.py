"""Derived from uts/objects/unit/value_types.md in ably/specification.

Spec points: RTLCV1, RTLCV2, RTLCV3, RTLCV3a1, RTLCV3b, RTLCV3c, RTLCV3d, RTLCV4, RTLCV4a,
RTLCV4b1, RTLCV4c, RTLCV4d, RTLCV4f, RTLCV4g1, RTLCV4g2, RTLCV4g3, RTLCV4g4, RTLCV4g5,
RTLMV1, RTLMV2, RTLMV3, RTLMV3a1, RTLMV3b, RTLMV3d, RTLMV4, RTLMV4a, RTLMV4b, RTLMV4c,
RTLMV4d, RTLMV4d1, RTLMV4d2, RTLMV4d3, RTLMV4d4, RTLMV4d5, RTLMV4d6, RTLMV4d7, RTLMV4e1,
RTLMV4e2, RTLMV4f, RTLMV4g, RTLMV4i, RTLMV4j1, RTLMV4j3, RTLMV4j4, RTLMV4j5, RTLMV4k

Pure tests: no client and no mock. The blueprints' internal `count` and `entries` are
`_count` and `_entries`. The specification's `evaluate(vt)` is `evaluate(vt, timestamp_ms)`:
evaluation reads the server time (RTLCV4e, RTLMV4h), which the caller fetches and passes
in (S-3), so these tests pass a fixed one.

Where the specification reads `operation.counterCreate` or `operation.mapCreate` of an
evaluated message, it means the create retained alongside the `*CreateWithObjectId`
payload (RTLCV4g5, RTLMV4j5). The evaluated operation carries only the
`*CreateWithObjectId` payload, and the retained create is read through
`resolved_counter_create` / `resolved_map_create`, its `derived_from` (S-4). Its entries
hold decoded values, so a `bytes` entry holds bytes; the base64 form is in the
`initialValue` JSON, which is encoded for the JSON wire (RTLMV4f1).
"""

import json

import pytest

from ably.pubsub.objects.objectmessage import ObjectOperationAction, ObjectsMapSemantics
from ably.pubsub.objects.valuetypes import LiveCounter, LiveMap, evaluate
from ably.pubsub.util.exceptions import AblyException

# The server time evaluation generates object ids with (S-3)
SERVER_TIME_MS = 1_700_000_000_000


# UTS: objects/unit/RTLCV3/create-with-count-0
def test_rtlcv3_create_with_count():
    vt = LiveCounter.create(42)

    assert isinstance(vt, LiveCounter)
    assert vt._count == 42


# UTS: objects/unit/RTLCV3/create-default-zero-0
def test_rtlcv3_create_default_zero():
    vt = LiveCounter.create()

    assert vt._count == 0


# UTS: objects/unit/RTLCV3c/no-validation-at-create-0
def test_rtlcv3c_no_validation_at_create():
    # Does not raise
    vt = LiveCounter.create('not_a_number')

    assert isinstance(vt, LiveCounter)


# UTS: objects/unit/RTLCV4/evaluate-generates-message-0
def test_rtlcv4_evaluate_generates_message():
    vt = LiveCounter.create(42)
    messages = evaluate(vt, SERVER_TIME_MS)

    assert len(messages) == 1
    msg = messages[0]
    assert msg.operation.action == ObjectOperationAction.COUNTER_CREATE
    assert msg.operation.object_id.startswith('counter:')
    assert '@' in msg.operation.object_id
    assert msg.operation.counter_create_with_object_id is not None
    assert msg.operation.counter_create_with_object_id.nonce is not None
    assert len(msg.operation.counter_create_with_object_id.nonce) >= 16
    assert msg.operation.counter_create_with_object_id.initial_value is not None
    # RTLCV4c: the initial value is the JSON of the CounterCreate
    assert json.loads(msg.operation.counter_create_with_object_id.initial_value) == {'count': 42}


# UTS: objects/unit/RTLCV4g5/retains-local-counter-create-0
def test_rtlcv4g5_retains_local_counter_create():
    vt = LiveCounter.create(42)
    messages = evaluate(vt, SERVER_TIME_MS)

    msg = messages[0]
    # S-4: the specification's `operation.counterCreate` is the retained CounterCreate
    assert msg.operation.resolved_counter_create is not None
    assert msg.operation.resolved_counter_create.count == 42
    # The retained CounterCreate is local only and never sent (RTLCV4g5)
    assert 'counterCreate' not in msg.operation.to_dict()


# UTS: objects/unit/RTLCV4a/evaluate-validates-count-0
def test_rtlcv4a_evaluate_validates_count():
    vt = LiveCounter.create('not_a_number')

    with pytest.raises(AblyException) as excinfo:
        evaluate(vt, SERVER_TIME_MS)

    assert excinfo.value.code == 40003


# UTS: objects/unit/RTLCV4/evaluate-zero-count-0
def test_rtlcv4_evaluate_zero_count():
    vt = LiveCounter.create(0)
    messages = evaluate(vt, SERVER_TIME_MS)

    msg = messages[0]
    # S-4: the retained CounterCreate
    assert msg.operation.resolved_counter_create.count == 0


# UTS: objects/unit/RTLMV3/create-with-entries-0
def test_rtlmv3_create_with_entries():
    vt = LiveMap.create({
        'name': 'Alice',
        'age': 30,
    })

    assert isinstance(vt, LiveMap)
    assert vt._entries['name'] == 'Alice'
    assert vt._entries['age'] == 30


# UTS: objects/unit/RTLMV3/create-no-entries-0
def test_rtlmv3_create_no_entries():
    vt = LiveMap.create()

    assert isinstance(vt, LiveMap)


# UTS: objects/unit/RTLMV4/evaluate-generates-message-0
def test_rtlmv4_evaluate_generates_message():
    vt = LiveMap.create({'name': 'Alice'})
    messages = evaluate(vt, SERVER_TIME_MS)

    assert len(messages) == 1
    msg = messages[0]
    assert msg.operation.action == ObjectOperationAction.MAP_CREATE
    assert msg.operation.object_id.startswith('map:')
    assert msg.operation.map_create_with_object_id is not None
    assert len(msg.operation.map_create_with_object_id.nonce) >= 16
    assert msg.operation.map_create_with_object_id.initial_value is not None
    # RTLMV4f: the initial value is the JSON of the encoded MapCreate
    initial_value = json.loads(msg.operation.map_create_with_object_id.initial_value)
    assert initial_value['semantics'] == ObjectsMapSemantics.LWW
    assert initial_value['entries']['name']['data'] == {'string': 'Alice'}


# UTS: objects/unit/RTLMV4j5/retains-local-map-create-0
def test_rtlmv4j5_retains_local_map_create():
    vt = LiveMap.create({'name': 'Alice'})
    messages = evaluate(vt, SERVER_TIME_MS)

    msg = messages[0]
    # S-4: the specification's `operation.mapCreate` is the retained MapCreate
    assert msg.operation.resolved_map_create is not None
    assert msg.operation.resolved_map_create.semantics == ObjectsMapSemantics.LWW
    assert msg.operation.resolved_map_create.entries['name'].data.string == 'Alice'
    # The retained MapCreate is local only and never sent (RTLMV4j5)
    assert 'mapCreate' not in msg.operation.to_dict()


# UTS: objects/unit/RTLMV4d/entry-value-types-0
def test_rtlmv4d_entry_value_types():
    vt = LiveMap.create({
        'str': 'hello',
        'num': 42,
        'bool': True,
        'json_arr': [1, 2, 3],
        'json_obj': {'key': 'value'},
    })
    messages = evaluate(vt, SERVER_TIME_MS)

    msg = messages[0]
    # S-4: the retained MapCreate
    entries = msg.operation.resolved_map_create.entries
    assert entries['str'].data.string == 'hello'
    assert entries['num'].data.number == 42
    # `bool` is an `int` in Python, so a boolean is told apart from a number by identity
    assert entries['bool'].data.boolean is True
    assert entries['json_arr'].data.json == [1, 2, 3]
    assert entries['json_obj'].data.json == {'key': 'value'}


# UTS: objects/unit/RTLMV4d1/nested-value-types-0
def test_rtlmv4d1_nested_value_types():
    inner_counter = LiveCounter.create(10)
    inner_map = LiveMap.create({
        'nested_count': inner_counter,
    })
    outer = LiveMap.create({
        'child': inner_map,
    })
    messages = evaluate(outer, SERVER_TIME_MS)

    assert len(messages) == 3
    assert messages[0].operation.action == ObjectOperationAction.COUNTER_CREATE
    assert messages[0].operation.object_id.startswith('counter:')
    assert messages[1].operation.action == ObjectOperationAction.MAP_CREATE
    assert messages[1].operation.object_id.startswith('map:')
    assert messages[2].operation.action == ObjectOperationAction.MAP_CREATE
    assert messages[2].operation.object_id.startswith('map:')

    inner_counter_id = messages[0].operation.object_id
    inner_map_id = messages[1].operation.object_id

    # S-4: the retained MapCreates
    assert messages[1].operation.resolved_map_create.entries['nested_count'].data.object_id == inner_counter_id
    assert messages[2].operation.resolved_map_create.entries['child'].data.object_id == inner_map_id


# UTS: objects/unit/RTLMV4a/evaluate-validates-entries-0
def test_rtlmv4a_evaluate_validates_entries():
    # The specification's input is `LiveMap.create(null)`. `LiveMap.create` takes None as its
    # default, so `None` cannot be told apart from an omitted argument and the null input is
    # not applicable. The other half of RTLMV4a, entries that are not a dict, is the
    # reachable failure.
    vt = LiveMap.create(['not', 'a', 'dict'])

    with pytest.raises(AblyException) as excinfo:
        evaluate(vt, SERVER_TIME_MS)

    assert excinfo.value.code == 40003

    # `None` is the omitted argument, and evaluates as an empty map (RTLMV4e2)
    messages = evaluate(LiveMap.create(None), SERVER_TIME_MS)
    assert messages[-1].operation.resolved_map_create.entries == {}


# UTS: objects/unit/RTLMV4b/evaluate-validates-keys-0
def test_rtlmv4b_evaluate_validates_keys():
    vt = LiveMap.create({123: 'value'})

    with pytest.raises(AblyException) as excinfo:
        evaluate(vt, SERVER_TIME_MS)

    assert excinfo.value.code == 40003


# UTS: objects/unit/RTLMV4c/evaluate-validates-values-0
def test_rtlmv4c_evaluate_validates_values():
    vt = LiveMap.create({'fn': lambda: None})

    with pytest.raises(AblyException) as excinfo:
        evaluate(vt, SERVER_TIME_MS)

    assert excinfo.value.code == 40013


# UTS: objects/unit/RTLMV4e2/empty-entries-0
def test_rtlmv4e2_empty_entries():
    vt = LiveMap.create()
    messages = evaluate(vt, SERVER_TIME_MS)

    msg = messages[0]
    # S-4: the retained MapCreate
    assert msg.operation.resolved_map_create.entries == {}


# The specification's `expected_value` for the bytes row, "AQID", is the JSON-wire form of
# bytes([1, 2, 3]). The retained MapCreate holds the decoded bytes, and the base64 is what the
# `initialValue` JSON carries, so the test asserts both.
MAP_SET_TYPE_SCENARIOS = [
    pytest.param('hello', 'string', 'hello', id='string'),
    pytest.param(42, 'number', 42, id='number-42'),
    pytest.param(3.14, 'number', 3.14, id='number-3.14'),
    pytest.param(0, 'number', 0, id='number-0'),
    pytest.param(-1, 'number', -1, id='number-minus-1'),
    pytest.param(True, 'boolean', True, id='boolean-true'),
    pytest.param(False, 'boolean', False, id='boolean-false'),
    pytest.param([1, 'a', None], 'json', [1, 'a', None], id='json-array'),
    pytest.param({'k': 'v'}, 'json', {'k': 'v'}, id='json-object'),
    pytest.param(bytes([1, 2, 3]), 'bytes', bytes([1, 2, 3]), id='bytes'),
]


# UTS: objects/unit/RTLMV4d/map-set-all-types-table-0
@pytest.mark.parametrize('value,expected_field,expected_value', MAP_SET_TYPE_SCENARIOS)
def test_rtlmv4d_map_set_all_types_table(value, expected_field, expected_value):
    vt = LiveMap.create({'test_key': value})
    messages = evaluate(vt, SERVER_TIME_MS)

    # S-4: the retained MapCreate
    entry = messages[0].operation.resolved_map_create.entries['test_key']
    actual = getattr(entry.data, expected_field)
    if isinstance(expected_value, bool):
        # `bool` is an `int` in Python, so a boolean is told apart from a number by identity
        assert actual is expected_value
    else:
        assert actual == expected_value

    if expected_field == 'bytes':
        initial_value = json.loads(messages[0].operation.map_create_with_object_id.initial_value)
        assert initial_value['entries']['test_key']['data']['bytes'] == 'AQID'
