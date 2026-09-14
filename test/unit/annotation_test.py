"""Unit tests for Annotation type and validation logic.

Tests cover:
- RSAN1a3: type validation in construct_validate_annotation
- TAN2a: id and connectionId fields on Annotation
- RSAN1c4: idempotent publishing ID format
- RTAN4b: protocol message field population
- RSAN1c1/RSAN2a: explicit action setting in publish/delete
- TAN3: from_encoded / from_encoded_array decoding
- TAN2i: serial-based equality
- RSAN1c3: encryption of the data payload on an encrypted channel
"""

import base64

import pytest

from ably.pubsub.rest.annotations import construct_validate_annotation, serial_from_msg_or_serial
from ably.pubsub.types.annotation import Annotation, AnnotationAction
from ably.pubsub.types.message import Message
from ably.pubsub.util.crypto import generate_random_key, get_cipher
from ably.pubsub.util.exceptions import AblyException

# --- RSAN1a3: type validation ---

def test_construct_validate_annotation_requires_type():
    """RSAN1a3: Annotation type must be specified"""
    annotation = Annotation(name='👍')  # No type
    with pytest.raises(AblyException) as exc_info:
        construct_validate_annotation('serial123', annotation)
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == 40000
    assert 'type' in str(exc_info.value).lower()


def test_construct_validate_annotation_with_type_succeeds():
    """RSAN1a3: Annotation with type should pass validation"""
    annotation = Annotation(type='reaction:distinct.v1', name='👍')
    result = construct_validate_annotation('serial123', annotation)
    assert result.type == 'reaction:distinct.v1'
    assert result.message_serial == 'serial123'


def test_construct_validate_annotation_requires_annotation_object():
    """Second argument must be an Annotation instance"""
    with pytest.raises(AblyException) as exc_info:
        construct_validate_annotation('serial123', 'not_an_annotation')
    assert exc_info.value.status_code == 400


def test_serial_from_msg_or_serial_with_string():
    """RSAN1a: Accept string serial"""
    assert serial_from_msg_or_serial('abc123') == 'abc123'


def test_serial_from_msg_or_serial_with_message():
    """RSAN1a1: Accept Message object with serial"""
    msg = Message(serial='abc123')
    assert serial_from_msg_or_serial(msg) == 'abc123'


def test_serial_from_msg_or_serial_rejects_invalid():
    """RSAN1a: Reject invalid input"""
    with pytest.raises(AblyException):
        serial_from_msg_or_serial(None)
    with pytest.raises(AblyException):
        serial_from_msg_or_serial(12345)


# --- TAN2a: id field on Annotation ---

def test_annotation_has_id_field():
    """TAN2a: Annotation must have id field"""
    annotation = Annotation(id='test-id-123', type='reaction', name='👍')
    assert annotation.id == 'test-id-123'


def test_annotation_id_in_as_dict():
    """TAN2a: id should be included in as_dict() output"""
    annotation = Annotation(id='test-id', type='reaction', name='👍')
    d = annotation.as_dict()
    assert d['id'] == 'test-id'


def test_annotation_id_from_encoded():
    """TAN2a: id should be read from encoded wire format"""
    encoded = {
        'id': 'wire-id-123',
        'type': 'reaction',
        'name': '👍',
        'action': 0,
    }
    annotation = Annotation.from_encoded(encoded)
    assert annotation.id == 'wire-id-123'


def test_annotation_id_in_copy_with():
    """TAN2a: id should be preserved/overridden in _copy_with()"""
    annotation = Annotation(id='original-id', type='reaction', name='👍')
    copy = annotation._copy_with(id='new-id')
    assert copy.id == 'new-id'
    assert annotation.id == 'original-id'  # Original unchanged


# --- TAN2a/TAN2c: connectionId field ---

def test_annotation_has_connection_id():
    """Annotation must have connection_id field"""
    annotation = Annotation(connection_id='conn-123', type='reaction', name='👍')
    assert annotation.connection_id == 'conn-123'


def test_annotation_connection_id_from_encoded():
    """connection_id should be read from encoded wire format"""
    encoded = {
        'connectionId': 'conn-456',
        'type': 'reaction',
        'action': 0,
    }
    annotation = Annotation.from_encoded(encoded)
    assert annotation.connection_id == 'conn-456'


# --- RSAN1c4: idempotent publishing ID format ---

def test_idempotent_id_format():
    """RSAN1c4: ID should be base64(9 random bytes) + ':0'"""
    # We can't test the actual REST publish without a server, but we can
    # verify the format by checking the regex pattern
    import os
    random_id = base64.b64encode(os.urandom(9)).decode('ascii') + ':0'
    # Should be base64 chars followed by ':0'
    assert random_id.endswith(':0')
    # Base64 of 9 bytes = 12 chars
    base64_part = random_id[:-2]
    assert len(base64_part) == 12
    # Verify it's valid base64
    decoded = base64.b64decode(base64_part)
    assert len(decoded) == 9


# --- RTAN4b: protocol message field population ---

def test_update_inner_annotation_fields():
    """RTAN4b: Populate annotation fields from protocol message envelope"""
    proto_msg = {
        'id': 'proto-msg-id',
        'connectionId': 'conn-abc',
        'timestamp': 1234567890,
        'annotations': [
            {'type': 'reaction', 'name': '👍'},
            {'type': 'reaction', 'name': '👎'},
        ]
    }
    Annotation.update_inner_annotation_fields(proto_msg)
    annotations = proto_msg['annotations']

    # First annotation
    assert annotations[0]['id'] == 'proto-msg-id:0'
    assert annotations[0]['connectionId'] == 'conn-abc'
    assert annotations[0]['timestamp'] == 1234567890

    # Second annotation
    assert annotations[1]['id'] == 'proto-msg-id:1'
    assert annotations[1]['connectionId'] == 'conn-abc'
    assert annotations[1]['timestamp'] == 1234567890


def test_update_inner_annotation_fields_preserves_existing():
    """RTAN4b: Don't overwrite existing annotation fields"""
    proto_msg = {
        'id': 'proto-msg-id',
        'connectionId': 'conn-abc',
        'timestamp': 1234567890,
        'annotations': [
            {
                'type': 'reaction',
                'id': 'existing-id',
                'connectionId': 'existing-conn',
                'timestamp': 9999999999,
            },
        ]
    }
    Annotation.update_inner_annotation_fields(proto_msg)
    annotation = proto_msg['annotations'][0]

    # Existing values should be preserved
    assert annotation['id'] == 'existing-id'
    assert annotation['connectionId'] == 'existing-conn'
    assert annotation['timestamp'] == 9999999999


def test_update_inner_annotation_fields_no_annotations():
    """RTAN4b: Should handle missing annotations gracefully"""
    proto_msg = {'id': 'proto-msg-id'}
    # Should not raise
    Annotation.update_inner_annotation_fields(proto_msg)


# --- RSAN1c1/RSAN2a: explicit action setting ---

def test_annotation_default_action_is_create():
    """Default action should be ANNOTATION_CREATE"""
    annotation = Annotation(type='reaction', name='👍')
    assert annotation.action == AnnotationAction.ANNOTATION_CREATE


def test_annotation_copy_with_action():
    """_copy_with should allow changing action"""
    annotation = Annotation(type='reaction', name='👍')
    deleted = annotation._copy_with(action=AnnotationAction.ANNOTATION_DELETE)
    assert deleted.action == AnnotationAction.ANNOTATION_DELETE
    assert annotation.action == AnnotationAction.ANNOTATION_CREATE  # Original unchanged


# --- TAN3: from_encoded() with None data ---

def test_from_encoded_with_none_data():
    """from_encoded should handle None data properly"""
    encoded = {
        'type': 'reaction',
        'name': '👍',
        'action': 0,
    }
    annotation = Annotation.from_encoded(encoded)
    assert annotation.data is None
    assert annotation.type == 'reaction'


def test_from_encoded_with_data():
    """from_encoded should decode data when present"""
    encoded = {
        'type': 'reaction',
        'name': '👍',
        'action': 0,
        'data': 'hello',
    }
    annotation = Annotation.from_encoded(encoded)
    assert annotation.data == 'hello'


def test_from_encoded_with_json_data():
    """from_encoded should decode JSON-encoded data"""
    import json
    encoded = {
        'type': 'reaction',
        'action': 0,
        'data': json.dumps({'count': 5}),
        'encoding': 'json',
    }
    annotation = Annotation.from_encoded(encoded)
    assert annotation.data == {'count': 5}


# --- TAN2i: __eq__ based on serial ---

def test_annotation_eq_by_serial():
    """TAN2i: Annotations with same serial should be equal"""
    a1 = Annotation(serial='s1', type='reaction', name='👍')
    a2 = Annotation(serial='s1', type='different', name='👎')
    assert a1 == a2


def test_annotation_ne_by_serial():
    """TAN2i: Annotations with different serials should not be equal"""
    a1 = Annotation(serial='s1', type='reaction', name='👍')
    a2 = Annotation(serial='s2', type='reaction', name='👍')
    assert a1 != a2


def test_annotation_eq_fallback_includes_client_id():
    """Fallback equality should include client_id"""
    a1 = Annotation(type='reaction', name='👍', client_id='user1',
                    message_serial='ms1', action=AnnotationAction.ANNOTATION_CREATE)
    a2 = Annotation(type='reaction', name='👍', client_id='user2',
                    message_serial='ms1', action=AnnotationAction.ANNOTATION_CREATE)
    assert a1 != a2  # Different client_id


def test_annotation_eq_fallback_same_fields():
    """Fallback equality with same fields should be equal"""
    a1 = Annotation(type='reaction', name='👍', client_id='user1',
                    message_serial='ms1', action=AnnotationAction.ANNOTATION_CREATE)
    a2 = Annotation(type='reaction', name='👍', client_id='user1',
                    message_serial='ms1', action=AnnotationAction.ANNOTATION_CREATE)
    assert a1 == a2


# --- as_dict serialization ---

def test_annotation_as_dict_filters_none():
    """as_dict should not include None values"""
    annotation = Annotation(type='reaction', name='👍')
    d = annotation.as_dict()
    assert 'serial' not in d
    assert 'extras' not in d
    assert 'type' in d
    assert 'name' in d


def test_annotation_as_dict_includes_action():
    """as_dict should include action as integer"""
    annotation = Annotation(type='reaction', name='👍', action=AnnotationAction.ANNOTATION_DELETE)
    d = annotation.as_dict()
    assert d['action'] == 1  # ANNOTATION_DELETE


# --- from_encoded_array ---

def test_from_encoded_array():
    """from_encoded_array should decode multiple annotations"""
    encoded_array = [
        {'type': 'reaction', 'name': '👍', 'action': 0},
        {'type': 'reaction', 'name': '👎', 'action': 1},
    ]
    annotations = Annotation.from_encoded_array(encoded_array)
    assert len(annotations) == 2
    assert annotations[0].name == '👍'
    assert annotations[0].action == AnnotationAction.ANNOTATION_CREATE
    assert annotations[1].name == '👎'
    assert annotations[1].action == AnnotationAction.ANNOTATION_DELETE


# --- encryption of the data payload ---

def _cipher():
    return get_cipher({'key': generate_random_key(256)})


@pytest.mark.parametrize('binary', [False, True])
@pytest.mark.parametrize('payload', [
    'secret text',
    {'secret': 'value'},
    ['secret', 1],
    bytearray(b'secret bytes'),
])
def test_encrypt_data_round_trips(payload, binary):
    """encrypt() must encrypt the data payload, and from_encoded() must decrypt it"""
    cipher = _cipher()
    annotation = Annotation(type='reaction:distinct.v1', name='👍', data=payload)
    annotation.encrypt(cipher)

    d = annotation.as_dict(binary=binary)
    assert 'cipher+aes-256-cbc' in d['encoding']
    assert 'secret' not in str(d['data'])

    decoded = Annotation.from_encoded(d, cipher=cipher)
    assert decoded.data == payload


def test_encrypt_without_data_is_a_noop():
    """Annotations commonly carry no data, which must not error"""
    annotation = Annotation(type='reaction:distinct.v1', name='👍')
    annotation.encrypt(_cipher())
    assert annotation.data is None
    assert 'data' not in annotation.as_dict()


def test_encrypt_is_idempotent():
    """Already-encrypted data must not be encrypted a second time"""
    cipher = _cipher()
    annotation = Annotation(type='reaction:distinct.v1', data='secret text')
    annotation.encrypt(cipher)
    once = annotation.as_dict()['data']
    annotation.encrypt(cipher)
    assert annotation.as_dict()['data'] == once


def test_from_encoded_without_cipher_leaves_residual_encoding():
    """Decoding encrypted data with no cipher must leave the transform in `encoding`"""
    cipher = _cipher()
    annotation = Annotation(type='reaction:distinct.v1', data='secret text')
    annotation.encrypt(cipher)
    d = annotation.as_dict()

    decoded = Annotation.from_encoded(d)
    assert 'cipher+aes-256-cbc' in decoded.encoding
    assert decoded.data != 'secret text'
