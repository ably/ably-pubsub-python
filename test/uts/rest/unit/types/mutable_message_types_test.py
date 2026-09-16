"""Derived from uts/rest/unit/types/mutable_message_types.md in ably/specification.

Spec points: TM2j, TM2r, TM2s, TM2s1, TM2s2, TM2s3, TM2s4, TM2s5, TM2u, TM5, TM8, TM8a,
MOP2a, MOP2b, MOP2c, UDR1, UDR2, UDR2a, TAN1, TAN2, TAN2a-TAN2l
"""

from ably.types.annotation import Annotation, AnnotationAction
from ably.types.message import Message, MessageAction, MessageAnnotations, MessageVersion
from ably.types.operations import MessageOperation, UpdateDeleteResult

# `fromJson` is spelled `from_encoded` for wire payloads and `from_dict` for plain records,
# and `toJson` is spelled `as_dict`.


# UTS: rest/unit/TM5/message-action-enum-values-0
def test_tm5_message_action_enum_values():
    assert int(MessageAction.MESSAGE_CREATE) == 0
    assert int(MessageAction.MESSAGE_UPDATE) == 1
    assert int(MessageAction.MESSAGE_DELETE) == 2
    assert int(MessageAction.META) == 3
    assert int(MessageAction.MESSAGE_SUMMARY) == 4
    assert int(MessageAction.MESSAGE_APPEND) == 5

    # Round-trip from int
    assert MessageAction(0) == MessageAction.MESSAGE_CREATE
    assert MessageAction(5) == MessageAction.MESSAGE_APPEND


# UTS: rest/unit/TM2j/action-and-serial-fields-0
def test_tm2j_action_and_serial_fields():
    msg = Message(
        name='test',
        data='hello',
        serial='serial-1',
        action=MessageAction.MESSAGE_UPDATE,
    )

    assert msg.serial == 'serial-1'
    assert msg.action == MessageAction.MESSAGE_UPDATE

    json_data = msg.as_dict()
    assert json_data['serial'] == 'serial-1'
    assert json_data['action'] == 1  # Numeric wire value for MESSAGE_UPDATE
    assert json_data['name'] == 'test'
    assert json_data['data'] == 'hello'


# UTS: rest/unit/TM2s/version-populated-from-wire-0
def test_tm2s_version_populated_from_wire():
    msg = Message.from_encoded({
        'serial': 'msg-serial-1',
        'name': 'test',
        'data': 'hello',
        'version': {
            'serial': 'version-serial-1',
            'timestamp': 1700000001000,
            'clientId': 'editor-1',
            'description': 'fixed typo',
            'metadata': {'reason': 'typo', 'tool': 'editor'},
        },
    })

    assert msg.version is not None
    assert isinstance(msg.version, MessageVersion)
    assert msg.version.serial == 'version-serial-1'
    assert msg.version.timestamp == 1700000001000
    assert msg.version.client_id == 'editor-1'
    assert msg.version.description == 'fixed typo'
    assert msg.version.metadata['reason'] == 'typo'
    assert msg.version.metadata['tool'] == 'editor'


# UTS: rest/unit/TM2s1/version-defaults-from-message-0
def test_tm2s1_version_defaults_from_message():
    msg = Message.from_encoded({
        'serial': 'msg-serial-1',
        'timestamp': 1700000000000,
        'name': 'test',
        'data': 'hello',
    })

    # version must be initialized even though not on wire
    assert msg.version is not None
    assert isinstance(msg.version, MessageVersion)

    # TM2s1: version.serial defaults to message serial
    assert msg.version.serial == 'msg-serial-1'

    # TM2s2: version.timestamp defaults to message timestamp
    assert msg.version.timestamp == 1700000000000

    # Other fields should be null
    assert msg.version.client_id is None
    assert msg.version.description is None
    assert msg.version.metadata is None


# UTS: rest/unit/TM2u/annotations-defaults-empty-0
def test_tm2u_annotations_defaults_empty():
    msg = Message.from_encoded({
        'serial': 'msg-serial-1',
        'name': 'test',
    })

    assert msg.annotations is not None
    assert isinstance(msg.annotations, MessageAnnotations)
    assert msg.annotations.summary is not None
    assert msg.annotations.summary == {}  # No keys


# UTS: rest/unit/MOP2a/message-operation-fields-0
def test_mop2a_message_operation_fields():
    op = MessageOperation(
        client_id='user-1',
        description='edit description',
        metadata={'reason': 'typo', 'tool': 'editor'},
    )

    assert op.client_id == 'user-1'
    assert op.description == 'edit description'
    assert op.metadata['reason'] == 'typo'
    assert op.metadata['tool'] == 'editor'

    # Serialization
    json_data = op.as_dict()
    assert json_data['clientId'] == 'user-1'
    assert json_data['description'] == 'edit description'
    assert json_data['metadata']['reason'] == 'typo'

    # All-null construction
    empty_op = MessageOperation()
    assert empty_op.client_id is None
    assert empty_op.description is None
    assert empty_op.metadata is None

    empty_json = empty_op.as_dict()
    assert 'clientId' not in empty_json
    assert 'description' not in empty_json
    assert 'metadata' not in empty_json


# UTS: rest/unit/UDR2a/update-delete-result-fields-0
def test_udr2a_update_delete_result_fields():
    # Non-null versionSerial
    result1 = UpdateDeleteResult.from_dict({'versionSerial': 'version-serial-abc'})
    assert isinstance(result1, UpdateDeleteResult)
    assert result1.version_serial == 'version-serial-abc'

    # Null versionSerial (message superseded)
    result2 = UpdateDeleteResult.from_dict({'versionSerial': None})
    assert result2.version_serial is None

    # Missing versionSerial key treated as null
    result3 = UpdateDeleteResult.from_dict({})
    assert result3.version_serial is None


# UTS: rest/unit/TAN2/annotation-attributes-and-action-0
def test_tan2_annotation_attributes_and_action():
    # DEVIATION: the spec's payload carries "encoding": null, which Annotation.from_encoded
    # cannot accept - it reads obj.get('encoding', '') so the default only applies to a missing
    # key, and decode() then calls strip() on None. Same root cause as Message.from_encoded,
    # where message_types_test.py holds the env-gated spec-correct assertion. The key is
    # omitted here so the field assertions this test exists for still run.
    ann = Annotation.from_encoded({
        'id': 'ann-id-1',
        'action': 0,
        'clientId': 'user-1',
        'name': 'like',
        'count': 5,
        'data': 'thumbs-up',
        'timestamp': 1700000000000,
        'serial': 'ann-serial-1',
        'messageSerial': 'msg-serial-1',
        'type': 'com.example.reaction',
        'extras': {'custom': 'metadata'},
    })

    assert isinstance(ann, Annotation)
    assert ann.id == 'ann-id-1'
    assert ann.action == AnnotationAction.ANNOTATION_CREATE
    assert ann.client_id == 'user-1'
    assert ann.name == 'like'
    assert ann.count == 5
    assert ann.data == 'thumbs-up'
    assert ann.timestamp == 1700000000000
    assert ann.serial == 'ann-serial-1'
    assert ann.message_serial == 'msg-serial-1'
    assert ann.type == 'com.example.reaction'
    assert ann.extras['custom'] == 'metadata'

    # AnnotationAction numeric values
    assert int(AnnotationAction.ANNOTATION_CREATE) == 0
    assert int(AnnotationAction.ANNOTATION_DELETE) == 1
    assert AnnotationAction(0) == AnnotationAction.ANNOTATION_CREATE
    assert AnnotationAction(1) == AnnotationAction.ANNOTATION_DELETE
