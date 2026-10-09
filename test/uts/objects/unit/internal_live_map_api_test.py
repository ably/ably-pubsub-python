"""Derived from uts/objects/unit/internal_live_map_api.md in ably/specification.

Spec points: RTLM5, RTLM5d2, RTLM10, RTLM10d, RTLM11, RTLM11d, RTLM12, RTLM20, RTLM20a3,
RTLM20e1, RTLM20e2, RTLM20e3, RTLM20e6, RTLM20e7b, RTLM20e7c, RTLM20e7d, RTLM20e7e,
RTLM20e7f, RTLM20e7g, RTLM20e7g1, RTLM20e7g2, RTLM20h1, RTLM20h2, RTLM21, RTLM21e1,
RTLM21e2, RTLM21e5, RTLMV4c, RTLMV4d1, RTLMV4d2, RTLCV4

The specification reaches `InternalLiveMap` through the untyped `PathObject`; ably-python
partitions it by type (RTTS). `root` is already a `LiveMapPathObject`, so `size`,
`entries`, `keys`, `set` and `remove` are called on it directly, and a primitive or counter
below it is read through `as_primitive()` or `as_live_counter()`.

The tests that capture what the client sends use the standard synced-channel mock, which
is the specification's hand-written one: it records each OBJECT message and then ACKs it
with `ack_serial(msgSerial, i)`, so every awaited write resolves (RTO20). Captured messages
are the decoded JSON wire, where a `json` value is a JSON-encoded string (OD2g), a `bytes`
value is base64, and an action is its number. Each captured operation is also checked
against the whole protocol v6 shape: a primitive MAP_SET or a MAP_REMOVE is compared
exactly, and a create carries only its `*CreateWithObjectId` payload, the `CounterCreate`
or `MapCreate` it was derived from staying local (RTLCV4g5, RTLMV4j5).
"""

import json

import pytest

from ably.pubsub.objects.objectmessage import ObjectOperationAction
from ably.pubsub.objects.valuetypes import LiveCounter, LiveMap
from ably.pubsub.util.exceptions import AblyException
from test.uts.objects.helpers.standard_test_pool import (
    LWW,
    objects_connected_message,
    setup_synced_channel,
    standard_mock_websocket,
)


def _capturing_mock_websocket(captured):
    """The specification's capturing mock: the standard synced-channel conversation, with each
    OBJECT message the client sends appended to `captured` before it is ACKed."""
    return standard_mock_websocket(
        on_object=captured.append,
        connected=objects_connected_message(connection_key='key-1'),
    )


def _map_set_operation(object_id, key, value):
    """The v6 wire form of a MAP_SET operation; `value` is the `ObjectData` wire dictionary."""
    return {
        'action': int(ObjectOperationAction.MAP_SET),
        'objectId': object_id,
        'mapSet': {'key': key, 'value': value},
    }


def _assert_create_wire_shape(operation, payload_name):
    """Asserts that a captured create carries only its v6 `*CreateWithObjectId` payload, with
    an `initialValue` string and a nonce, and returns the decoded initial value."""
    assert set(operation) == {'action', 'objectId', payload_name}
    payload = operation[payload_name]
    assert set(payload) == {'initialValue', 'nonce'}
    assert isinstance(payload['nonce'], str)
    assert isinstance(payload['initialValue'], str)
    return json.loads(payload['initialValue'])


# UTS: objects/unit/RTLM5/get-string-value-0
async def test_rtlm5_get_string_value():
    ctx = await setup_synced_channel('test')

    assert ctx.root.get('name').as_primitive().value() == 'Alice'
    assert ctx.root.get('age').as_primitive().value() == 30
    assert ctx.root.get('active').as_primitive().value() is True


# UTS: objects/unit/RTLM5/get-nonexistent-key-0
async def test_rtlm5_get_nonexistent_key():
    ctx = await setup_synced_channel('test')

    # The specification's untyped `value()`: a path that resolves to nothing answers None
    # through every typed view (RTTS5d1)
    assert ctx.root.get('nonexistent').as_primitive().value() is None
    assert ctx.root.get('nonexistent').as_live_counter().value() is None


# UTS: objects/unit/RTLM5/get-objectid-reference-0
async def test_rtlm5_get_objectid_reference():
    ctx = await setup_synced_channel('test')

    assert ctx.root.get('score').as_live_counter().value() == 100
    assert ctx.root.get('profile').get('email').as_primitive().value() == 'alice@example.com'


# UTS: objects/unit/RTLM10/size-non-tombstoned-0
async def test_rtlm10_size_non_tombstoned():
    ctx = await setup_synced_channel('test')

    assert ctx.root.size() == 7


# UTS: objects/unit/RTLM11/entries-yields-pairs-0
async def test_rtlm11_entries_yields_pairs():
    ctx = await setup_synced_channel('test')

    entries = []
    for key, _path_object in ctx.root.entries():
        entries.append(key)

    assert 'name' in entries
    assert 'age' in entries
    assert 'active' in entries
    assert 'score' in entries
    assert 'profile' in entries
    assert 'data' in entries
    assert 'avatar' in entries
    assert len(entries) == 7


# UTS: objects/unit/RTLM12/keys-0
async def test_rtlm12_keys():
    ctx = await setup_synced_channel('test')

    keys = list(ctx.root.keys())

    assert len(keys) == 7
    assert 'name' in keys


# UTS: objects/unit/RTLM20/set-sends-map-set-0
async def test_rtlm20_set_sends_map_set():
    captured = []
    ctx = await setup_synced_channel('test', mock_ws=_capturing_mock_websocket(captured))

    await ctx.root.set('name', 'Bob')

    assert len(captured) == 1
    obj_msg = captured[0]['state'][0]
    assert obj_msg['operation']['action'] == ObjectOperationAction.MAP_SET
    assert obj_msg['operation']['objectId'] == 'root'
    assert obj_msg['operation']['mapSet']['key'] == 'name'
    assert obj_msg['operation']['mapSet']['value']['string'] == 'Bob'
    assert obj_msg['operation'] == _map_set_operation('root', 'name', {'string': 'Bob'})


# UTS: objects/unit/RTLM20/set-value-types-0
async def test_rtlm20_set_value_types():
    captured = []
    ctx = await setup_synced_channel('test', mock_ws=_capturing_mock_websocket(captured))

    await ctx.root.set('num_key', 42)
    await ctx.root.set('bool_key', False)
    await ctx.root.set('json_key', {'nested': True})

    assert captured[0]['state'][0]['operation']['mapSet']['value']['number'] == 42
    assert captured[1]['state'][0]['operation']['mapSet']['value']['boolean'] is False
    # A `json` value travels as a JSON-encoded string (OD2g); the specification compares the
    # decoded value
    json_value = captured[2]['state'][0]['operation']['mapSet']['value']
    assert json.loads(json_value['json']) == {'nested': True}

    assert captured[0]['state'][0]['operation'] == _map_set_operation('root', 'num_key', {'number': 42})
    assert captured[1]['state'][0]['operation'] == _map_set_operation('root', 'bool_key', {'boolean': False})
    assert set(json_value) == {'json'}
    assert isinstance(json_value['json'], str)


# UTS: objects/unit/RTLM20e7g/set-counter-value-type-0
async def test_rtlm20e7g_set_counter_value_type():
    captured = []
    ctx = await setup_synced_channel('test', mock_ws=_capturing_mock_websocket(captured))

    await ctx.root.set('new_counter', LiveCounter.create(50))

    assert len(captured) == 1
    state = captured[0]['state']
    assert len(state) == 2
    assert state[0]['operation']['action'] == ObjectOperationAction.COUNTER_CREATE
    assert state[0]['operation']['objectId'].startswith('counter:')
    assert state[1]['operation']['action'] == ObjectOperationAction.MAP_SET
    assert state[1]['operation']['mapSet']['value']['objectId'] == state[0]['operation']['objectId']

    initial_value = _assert_create_wire_shape(state[0]['operation'], 'counterCreateWithObjectId')
    assert initial_value == {'count': 50}
    assert state[1]['operation'] == _map_set_operation(
        'root', 'new_counter', {'objectId': state[0]['operation']['objectId']})


# UTS: objects/unit/RTLM20e7g/set-map-value-type-0
async def test_rtlm20e7g_set_map_value_type():
    captured = []
    ctx = await setup_synced_channel('test', mock_ws=_capturing_mock_websocket(captured))

    await ctx.root.set('nested_map', LiveMap.create({'key1': 'value1'}))

    assert len(captured) == 1
    state = captured[0]['state']
    assert len(state) == 2
    assert state[0]['operation']['action'] == ObjectOperationAction.MAP_CREATE
    assert state[0]['operation']['objectId'].startswith('map:')
    assert state[1]['operation']['action'] == ObjectOperationAction.MAP_SET
    assert state[1]['operation']['mapSet']['key'] == 'nested_map'
    assert state[1]['operation']['mapSet']['value']['objectId'] == state[0]['operation']['objectId']

    initial_value = _assert_create_wire_shape(state[0]['operation'], 'mapCreateWithObjectId')
    assert initial_value['semantics'] == LWW
    assert set(initial_value['entries']) == {'key1'}
    assert initial_value['entries']['key1']['data'] == {'string': 'value1'}
    assert state[1]['operation'] == _map_set_operation(
        'root', 'nested_map', {'objectId': state[0]['operation']['objectId']})


# UTS: objects/unit/RTLM20h1/set-nested-value-types-0
async def test_rtlm20h1_set_nested_value_types():
    captured = []
    ctx = await setup_synced_channel('test', mock_ws=_capturing_mock_websocket(captured))

    await ctx.root.set('stats', LiveMap.create({
        'count': LiveCounter.create(0),
        'label': 'test',
    }))

    assert len(captured) == 1
    state = captured[0]['state']
    # COUNTER_CREATE, MAP_CREATE, MAP_SET: depth-first, then the MAP_SET at root
    assert len(state) == 3
    assert state[0]['operation']['action'] == ObjectOperationAction.COUNTER_CREATE
    assert state[0]['operation']['objectId'].startswith('counter:')
    assert state[1]['operation']['action'] == ObjectOperationAction.MAP_CREATE
    assert state[1]['operation']['objectId'].startswith('map:')
    assert state[2]['operation']['action'] == ObjectOperationAction.MAP_SET
    assert state[2]['operation']['mapSet']['key'] == 'stats'
    assert state[2]['operation']['mapSet']['value']['objectId'] == state[1]['operation']['objectId']

    counter_initial_value = _assert_create_wire_shape(state[0]['operation'], 'counterCreateWithObjectId')
    assert counter_initial_value == {'count': 0}
    # RTLMV4d1: the nested counter's entry references the counter the first message creates
    map_initial_value = _assert_create_wire_shape(state[1]['operation'], 'mapCreateWithObjectId')
    assert map_initial_value['entries']['count']['data'] == {'objectId': state[0]['operation']['objectId']}
    assert map_initial_value['entries']['label']['data'] == {'string': 'test'}
    assert state[2]['operation'] == _map_set_operation(
        'root', 'stats', {'objectId': state[1]['operation']['objectId']})


# UTS: objects/unit/RTLM21/remove-sends-map-remove-0
async def test_rtlm21_remove_sends_map_remove():
    captured = []
    ctx = await setup_synced_channel('test', mock_ws=_capturing_mock_websocket(captured))

    await ctx.root.remove('name')

    obj_msg = captured[0]['state'][0]
    assert obj_msg['operation']['action'] == ObjectOperationAction.MAP_REMOVE
    assert obj_msg['operation']['objectId'] == 'root'
    assert obj_msg['operation']['mapRemove']['key'] == 'name'
    assert obj_msg['operation'] == {
        'action': int(ObjectOperationAction.MAP_REMOVE),
        'objectId': 'root',
        'mapRemove': {'key': 'name'},
    }


# UTS: objects/unit/RTLM20/set-applies-locally-0
async def test_rtlm20_set_applies_locally():
    ctx = await setup_synced_channel('test')

    await ctx.root.set('name', 'Bob')

    assert ctx.root.get('name').as_primitive().value() == 'Bob'


# The specification's rows are JavaScript values. Their Python counterparts: a function is a
# lambda, `undefined` is `None`, and a symbol is an arbitrary `object()`. None of them is a
# value a map entry can hold (RTLM20a3).
INVALID_VALUES = [
    pytest.param(lambda: None, id='function'),
    pytest.param(None, id='undefined'),
    pytest.param(object(), id='symbol'),
]


# UTS: objects/unit/RTLM20/set-invalid-values-table-0
@pytest.mark.parametrize('value', INVALID_VALUES)
async def test_rtlm20_set_invalid_values_table(value):
    ctx = await setup_synced_channel('test')

    with pytest.raises(AblyException) as excinfo:
        await ctx.root.set('key', value)

    assert excinfo.value.code == 40013


# UTS: objects/unit/RTLM20/set-bytes-value-0
async def test_rtlm20_set_bytes_value():
    captured = []
    ctx = await setup_synced_channel('test', mock_ws=_capturing_mock_websocket(captured))

    await ctx.root.set('binary_data', bytes([1, 2, 3]))

    assert captured[0]['state'][0]['operation']['mapSet']['value']['bytes'] == 'AQID'
    assert captured[0]['state'][0]['operation'] == _map_set_operation('root', 'binary_data', {'bytes': 'AQID'})
