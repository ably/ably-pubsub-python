from ably.pubsub.server import MessageAction, MessageOperation, MessageVersion, UpdateDeleteResult
from ably.pubsub.types.message import Message


def test_message_version_none_values_filtered():
    """Test that None values are filtered out in MessageVersion.as_dict()"""
    version = MessageVersion(
        serial='abc123',
        timestamp=None,
        client_id=None
    )

    version_dict = version.as_dict()
    assert 'serial' in version_dict
    assert 'timestamp' not in version_dict
    assert 'clientId' not in version_dict

def test_message_operation_none_values_filtered():
    """Test that None values are filtered out in MessageOperation.as_dict()"""
    operation = MessageOperation(
        client_id='client123',
        description='Test',
        metadata=None
    )

    op_dict = operation.as_dict()
    assert 'clientId' in op_dict
    assert 'description' in op_dict
    assert 'metadata' not in op_dict

def test_message_with_action_and_serial():
    """Test Message can store action and serial"""
    message = Message(
        name='test',
        data='data',
        serial='abc123',
        action=MessageAction.MESSAGE_UPDATE
    )

    assert message.serial == 'abc123'
    assert message.action == MessageAction.MESSAGE_UPDATE

    # Test as_dict includes action and serial
    msg_dict = message.as_dict()
    assert msg_dict['serial'] == 'abc123'
    assert msg_dict['action'] == 1  # MESSAGE_UPDATE value

def test_update_delete_result_from_dict():
    """Test UpdateDeleteResult can be created from dict"""
    result_dict = {'versionSerial': 'abc123:v2'}
    result = UpdateDeleteResult.from_dict(result_dict)

    assert result.version_serial == 'abc123:v2'

def test_update_delete_result_empty():
    """Test UpdateDeleteResult handles None/empty correctly"""
    result = UpdateDeleteResult.from_dict(None)
    assert result.version_serial is None

    result2 = UpdateDeleteResult()
    assert result2.version_serial is None


def test_message_action_enum_values():
    """Test MessageAction enum has correct values"""
    assert MessageAction.MESSAGE_CREATE == 0
    assert MessageAction.MESSAGE_UPDATE == 1
    assert MessageAction.MESSAGE_DELETE == 2
    assert MessageAction.META == 3
    assert MessageAction.MESSAGE_SUMMARY == 4
    assert MessageAction.MESSAGE_APPEND == 5

def test_message_version_serialization():
    """Test MessageVersion can be serialized and deserialized"""
    version = MessageVersion(
        serial='abc123:v2',
        timestamp=1234567890,
        client_id='user1',
        description='Test update',
        metadata={'key': 'value'}
    )

    # Test as_dict
    version_dict = version.as_dict()
    assert version_dict['serial'] == 'abc123:v2'
    assert version_dict['timestamp'] == 1234567890
    assert version_dict['clientId'] == 'user1'
    assert version_dict['description'] == 'Test update'
    assert version_dict['metadata'] == {'key': 'value'}

    # Test from_dict
    reconstructed = MessageVersion.from_dict(version_dict)
    assert reconstructed.serial == version.serial
    assert reconstructed.timestamp == version.timestamp
    assert reconstructed.client_id == version.client_id
    assert reconstructed.description == version.description
    assert reconstructed.metadata == version.metadata

# RSL15b, RTL32b, TM2i
def test_message_extras_preserved_in_as_dict():
    """Test that extras are included when a Message with extras is serialized.

    Regression test: _send_update() in both HttpChannel and RealtimeChannel
    constructed a new Message without copying extras or annotations from the
    user-supplied message, violating RSL15b/RTL32b which require "whatever
    fields were in the user-supplied Message" to be sent.
    See commits 1723f5d (REST) and 0b93c10 (Realtime).
    """
    extras = {'headers': {'status': 'complete'}}
    message = Message(
        name='test',
        data='updated data',
        serial='abc123',
        action=MessageAction.MESSAGE_UPDATE,
        extras=extras,
    )

    msg_dict = message.as_dict()
    assert msg_dict['extras'] == extras
    assert msg_dict['extras']['headers']['status'] == 'complete'


# RSL15b, RTL32b, TM2i
def test_message_extras_none_excluded_from_as_dict():
    """Test that extras=None does not appear in as_dict output."""
    message = Message(
        name='test',
        data='data',
        serial='abc123',
        action=MessageAction.MESSAGE_UPDATE,
    )

    msg_dict = message.as_dict()
    assert 'extras' not in msg_dict


# RSL15b, RTL32b, TM2u
def test_message_annotations_preserved_in_as_dict():
    """Test that annotations are included when a Message with annotations is serialized."""
    from ably.pubsub.types.message import MessageAnnotations
    annotations = MessageAnnotations(summary={'reaction:distinct.v1': {'thumbsup': 5}})
    message = Message(
        name='test',
        data='data',
        serial='abc123',
        action=MessageAction.MESSAGE_UPDATE,
        annotations=annotations,
    )

    msg_dict = message.as_dict()
    assert msg_dict['annotations'] is not None
    assert msg_dict['annotations']['summary']['reaction:distinct.v1'] == {'thumbsup': 5}


def test_message_operation_serialization():
    """Test MessageOperation can be serialized and deserialized"""
    operation = MessageOperation(
        client_id='user1',
        description='Test operation',
        metadata={'key': 'value'}
    )

    # Test as_dict
    op_dict = operation.as_dict()
    assert op_dict['clientId'] == 'user1'
    assert op_dict['description'] == 'Test operation'
    assert op_dict['metadata'] == {'key': 'value'}

    # Test from_dict
    reconstructed = MessageOperation.from_dict(op_dict)
    assert reconstructed.client_id == operation.client_id
    assert reconstructed.description == operation.description
    assert reconstructed.metadata == operation.metadata
