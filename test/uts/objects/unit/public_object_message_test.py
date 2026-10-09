"""Derived from uts/objects/unit/public_object_message.md in ably/specification.

Spec points: PAOM1, PAOM2, PAOM3, PAOOP1, PAOOP2, PAOOP3

The specification's `PublicObjectMessage.fromObjectMessage(source, channel)` is
`publicmessage.ObjectMessage._from_internal(source, channel_name)`, which takes the
channel's name rather than the channel (PAOM3b reads only `channel.name`), and
`PublicObjectOperation.fromObjectOperation(op)` is
`publicmessage.ObjectOperation._from_internal(op)`. The public types share their names with
the internal wire types, so the public pair is reached through the `publicmessage` module.

Each source is built as the internal dataclasses directly. An attribute the specification
writes as `null` or omitted is None, operation actions are `ObjectOperationAction` members
and map semantics `ObjectsMapSemantics` members.

The specification gives `mapCreateWithObjectId` and `counterCreateWithObjectId` the fields
of the payload they were derived from (`objectId`, `semantics`, `entries`, `count`), which
those payloads do not carry: MCRO2 and CCRO2 define only `initialValue` and `nonce`. Here
they carry those two, with `initialValue` the JSON encoding of the derived payload as
RTLMV4f and RTLCV4c produce it, and the derived payload in `derived_from` (RTLMV4j5,
RTLCV4g5).
"""

import json

from ably.pubsub.objects import publicmessage
from ably.pubsub.objects.objectmessage import (
    CounterCreate,
    CounterCreateWithObjectId,
    CounterInc,
    MapClear,
    MapCreate,
    MapCreateWithObjectId,
    MapRemove,
    MapSet,
    ObjectData,
    ObjectDelete,
    ObjectMessage,
    ObjectOperation,
    ObjectOperationAction,
    ObjectsMapEntry,
    ObjectsMapSemantics,
)

NONCE = 'test-nonce-1234567890'


# UTS: objects/unit/PAOM3/construction-all-fields-0
def test_paom3_construction_all_fields():
    source = ObjectMessage(
        id='msg-id-1',
        client_id='client-1',
        connection_id='conn-1',
        timestamp=1700000000000,
        serial='01',
        serial_timestamp=1700000001000,
        site_code='site1',
        extras={'key': 'value'},
        operation=ObjectOperation(
            action=ObjectOperationAction.MAP_SET,
            object_id='map:abc@1000',
            map_set=MapSet(key='name', value=ObjectData(string='Alice')),
        ),
    )

    public_msg = publicmessage.ObjectMessage._from_internal(source, 'test-channel')

    assert isinstance(public_msg, publicmessage.ObjectMessage)
    assert public_msg.id == 'msg-id-1'
    assert public_msg.client_id == 'client-1'
    assert public_msg.connection_id == 'conn-1'
    assert public_msg.timestamp == 1700000000000
    assert public_msg.channel == 'test-channel'
    assert public_msg.serial == '01'
    assert public_msg.serial_timestamp == 1700000001000
    assert public_msg.site_code == 'site1'
    assert public_msg.extras == {'key': 'value'}
    assert public_msg.operation is not None
    assert isinstance(public_msg.operation, publicmessage.ObjectOperation)
    assert public_msg.operation.action == ObjectOperationAction.MAP_SET
    assert public_msg.operation.object_id == 'map:abc@1000'
    assert public_msg.operation.map_set.key == 'name'
    assert public_msg.operation.map_set.value.string == 'Alice'


# UTS: objects/unit/PAOM3/construction-optional-fields-missing-0
def test_paom3_construction_optional_fields_missing():
    source = ObjectMessage(
        operation=ObjectOperation(
            action=ObjectOperationAction.COUNTER_INC,
            object_id='counter:abc@1000',
            counter_inc=CounterInc(number=5.0),
        ),
    )

    public_msg = publicmessage.ObjectMessage._from_internal(source, 'my-channel')

    assert public_msg.id is None
    assert public_msg.client_id is None
    assert public_msg.connection_id is None
    assert public_msg.timestamp is None
    assert public_msg.channel == 'my-channel'
    assert public_msg.serial is None
    assert public_msg.serial_timestamp is None
    assert public_msg.site_code is None
    assert public_msg.extras is None
    assert public_msg.operation is not None
    assert public_msg.operation.action == ObjectOperationAction.COUNTER_INC


# UTS: objects/unit/PAOM3/channel-from-channel-name-0
def test_paom3_channel_from_channel_name():
    source = ObjectMessage(
        operation=ObjectOperation(
            action=ObjectOperationAction.OBJECT_DELETE,
            object_id='counter:abc@1000',
        ),
    )

    public_msg = publicmessage.ObjectMessage._from_internal(source, 'different-channel-name')

    assert public_msg.channel == 'different-channel-name'


# UTS: objects/unit/PAOOP3/map-set-copies-fields-0
def test_paoop3_map_set_copies_fields():
    source_operation = ObjectOperation(
        action=ObjectOperationAction.MAP_SET,
        object_id='map:abc@1000',
        map_set=MapSet(key='color', value=ObjectData(string='blue')),
    )

    public_op = publicmessage.ObjectOperation._from_internal(source_operation)

    assert public_op.action == ObjectOperationAction.MAP_SET
    assert public_op.object_id == 'map:abc@1000'
    assert public_op.map_set.key == 'color'
    assert public_op.map_set.value.string == 'blue'
    assert public_op.map_create is None
    assert public_op.map_remove is None
    assert public_op.counter_create is None
    assert public_op.counter_inc is None
    assert public_op.object_delete is None
    assert public_op.map_clear is None


# UTS: objects/unit/PAOOP3/map-remove-copies-fields-0
def test_paoop3_map_remove_copies_fields():
    source_operation = ObjectOperation(
        action=ObjectOperationAction.MAP_REMOVE,
        object_id='map:abc@1000',
        map_remove=MapRemove(key='old-key'),
    )

    public_op = publicmessage.ObjectOperation._from_internal(source_operation)

    assert public_op.action == ObjectOperationAction.MAP_REMOVE
    assert public_op.object_id == 'map:abc@1000'
    assert public_op.map_remove.key == 'old-key'
    assert public_op.map_create is None
    assert public_op.map_set is None
    assert public_op.counter_create is None
    assert public_op.counter_inc is None
    assert public_op.object_delete is None
    assert public_op.map_clear is None


# UTS: objects/unit/PAOOP3/counter-inc-copies-fields-0
def test_paoop3_counter_inc_copies_fields():
    source_operation = ObjectOperation(
        action=ObjectOperationAction.COUNTER_INC,
        object_id='counter:abc@1000',
        counter_inc=CounterInc(number=42.0),
    )

    public_op = publicmessage.ObjectOperation._from_internal(source_operation)

    assert public_op.action == ObjectOperationAction.COUNTER_INC
    assert public_op.object_id == 'counter:abc@1000'
    assert public_op.counter_inc.number == 42
    assert public_op.map_create is None
    assert public_op.map_set is None
    assert public_op.map_remove is None
    assert public_op.counter_create is None
    assert public_op.object_delete is None
    assert public_op.map_clear is None


# UTS: objects/unit/PAOOP3/object-delete-copies-fields-0
def test_paoop3_object_delete_copies_fields():
    source_operation = ObjectOperation(
        action=ObjectOperationAction.OBJECT_DELETE,
        object_id='counter:abc@1000',
        object_delete=ObjectDelete(),
    )

    public_op = publicmessage.ObjectOperation._from_internal(source_operation)

    assert public_op.action == ObjectOperationAction.OBJECT_DELETE
    assert public_op.object_id == 'counter:abc@1000'
    assert public_op.object_delete is not None
    assert public_op.map_create is None
    assert public_op.map_set is None
    assert public_op.map_remove is None
    assert public_op.counter_create is None
    assert public_op.counter_inc is None
    assert public_op.map_clear is None


# UTS: objects/unit/PAOOP3/map-clear-copies-fields-0
def test_paoop3_map_clear_copies_fields():
    source_operation = ObjectOperation(
        action=ObjectOperationAction.MAP_CLEAR,
        object_id='map:abc@1000',
        map_clear=MapClear(),
    )

    public_op = publicmessage.ObjectOperation._from_internal(source_operation)

    assert public_op.action == ObjectOperationAction.MAP_CLEAR
    assert public_op.object_id == 'map:abc@1000'
    assert public_op.map_clear is not None
    assert public_op.map_create is None
    assert public_op.map_set is None
    assert public_op.map_remove is None
    assert public_op.counter_create is None
    assert public_op.counter_inc is None
    assert public_op.object_delete is None


# UTS: objects/unit/PAOOP3/map-create-direct-0
def test_paoop3_map_create_direct():
    source_operation = ObjectOperation(
        action=ObjectOperationAction.MAP_CREATE,
        object_id='map:new@2000',
        map_create=MapCreate(
            semantics=ObjectsMapSemantics.LWW,
            entries={'key1': ObjectsMapEntry(data=ObjectData(string='val1'))},
        ),
    )

    public_op = publicmessage.ObjectOperation._from_internal(source_operation)

    assert public_op.action == ObjectOperationAction.MAP_CREATE
    assert public_op.object_id == 'map:new@2000'
    assert public_op.map_create is not None
    assert public_op.map_create.semantics == ObjectsMapSemantics.LWW
    assert public_op.map_create.entries['key1'].data.string == 'val1'
    assert public_op.counter_create is None


# UTS: objects/unit/PAOOP3/map-create-from-with-object-id-0
def test_paoop3_map_create_from_with_object_id():
    derived_map_create = MapCreate(
        semantics=ObjectsMapSemantics.LWW,
        entries={'x': ObjectsMapEntry(data=ObjectData(number=10.0))},
    )

    # The specification also lists `objectId`, `semantics` and `entries` inside
    # `mapCreateWithObjectId`, which MCRO2 does not define; see the module docstring
    source_operation = ObjectOperation(
        action=ObjectOperationAction.MAP_CREATE,
        object_id='map:derived@3000',
        map_create_with_object_id=MapCreateWithObjectId(
            initial_value=json.dumps(derived_map_create.to_dict()),
            nonce=NONCE,
            derived_from=derived_map_create,
        ),
    )

    public_op = publicmessage.ObjectOperation._from_internal(source_operation)

    assert public_op.action == ObjectOperationAction.MAP_CREATE
    assert public_op.object_id == 'map:derived@3000'
    assert public_op.map_create is not None
    assert public_op.map_create.semantics == ObjectsMapSemantics.LWW
    assert public_op.map_create.entries['x'].data.number == 10
    assert public_op.counter_create is None
    # PAOOP1: the public operation carries the derived payload, never the WithObjectId one
    assert public_op.map_create == derived_map_create
    assert not hasattr(public_op, 'map_create_with_object_id')


# UTS: objects/unit/PAOOP3/counter-create-from-with-object-id-0
def test_paoop3_counter_create_from_with_object_id():
    derived_counter_create = CounterCreate(count=100.0)

    # The specification also lists `objectId` and `count` inside
    # `counterCreateWithObjectId`, which CCRO2 does not define; see the module docstring
    source_operation = ObjectOperation(
        action=ObjectOperationAction.COUNTER_CREATE,
        object_id='counter:derived@3000',
        counter_create_with_object_id=CounterCreateWithObjectId(
            initial_value=json.dumps(derived_counter_create.to_dict()),
            nonce=NONCE,
            derived_from=derived_counter_create,
        ),
    )

    public_op = publicmessage.ObjectOperation._from_internal(source_operation)

    assert public_op.action == ObjectOperationAction.COUNTER_CREATE
    assert public_op.object_id == 'counter:derived@3000'
    assert public_op.counter_create is not None
    assert public_op.counter_create.count == 100
    assert public_op.map_create is None
    # PAOOP1: the public operation carries the derived payload, never the WithObjectId one
    assert public_op.counter_create == derived_counter_create
    assert not hasattr(public_op, 'counter_create_with_object_id')


# UTS: objects/unit/PAOOP3/create-payloads-omitted-0
def test_paoop3_create_payloads_omitted():
    source_operation = ObjectOperation(
        action=ObjectOperationAction.MAP_SET,
        object_id='map:abc@1000',
        map_set=MapSet(key='k', value=ObjectData(string='v')),
    )

    public_op = publicmessage.ObjectOperation._from_internal(source_operation)

    assert public_op.map_create is None
    assert public_op.counter_create is None


# UTS: objects/unit/PAOOP3/only-relevant-field-per-action-0
def test_paoop3_only_relevant_field_per_action():
    source_operation = ObjectOperation(
        action=ObjectOperationAction.COUNTER_CREATE,
        object_id='counter:new@2000',
        counter_create=CounterCreate(count=50.0),
    )

    public_op = publicmessage.ObjectOperation._from_internal(source_operation)

    assert public_op.action == ObjectOperationAction.COUNTER_CREATE
    assert public_op.object_id == 'counter:new@2000'
    assert public_op.counter_create is not None
    assert public_op.counter_create.count == 50
    assert public_op.map_create is None
    assert public_op.map_set is None
    assert public_op.map_remove is None
    assert public_op.counter_inc is None
    assert public_op.object_delete is None
    assert public_op.map_clear is None
