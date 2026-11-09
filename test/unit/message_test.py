import pytest

import ably.pubsub.types.message
from ably.pubsub.types.message import Message, message_size, validate_message_size
from ably.pubsub.util.exceptions import AblyException


# TM2a, TM2c, TM2f
def test_update_inner_message_fields_tm2():
    proto_msg: dict = {
        'id': 'abcdefg',
        'connectionId': 'custom_connection_id',
        'timestamp': 23134,
        'messages': [
            {
                'event': 'test',
                'data': 'hello there'''
            }
        ]
    }
    ably.pubsub.types.message.Message.update_inner_message_fields(proto_msg)
    messages: list[dict] = proto_msg.get('messages')
    msg_index = 0
    for msg in messages:
        assert msg.get('id') == f"abcdefg:{msg_index}"
        assert msg.get('connectionId') == 'custom_connection_id'
        assert msg.get('timestamp') == 23134
        msg_index = msg_index + 1


# TM2a, TM2c, TM2f
def test_update_inner_message_fields_for_presence_msg_tm2():
    proto_msg: dict = {
        'id': 'abcdefg',
        'connectionId': 'custom_connection_id',
        'timestamp': 23134,
        'presence': [
            {
                'event': 'test',
                'data': 'hello there'
            }
        ]
    }
    ably.pubsub.types.message.Message.update_inner_message_fields(proto_msg)
    presence_messages: list[dict] = proto_msg.get('presence')
    msg_index = 0
    for presence_msg in presence_messages:
        assert presence_msg.get('id') == f"abcdefg:{msg_index}"
        assert presence_msg.get('connectionId') == 'custom_connection_id'
        assert presence_msg.get('timestamp') == 23134
        msg_index = msg_index + 1


# RSL6b
def test_invalid_base64_data_is_delivered_with_remaining_encoding():
    message = ably.pubsub.types.message.Message.from_encoded({
        'name': 'event',
        'data': 'encrypted-data-here',
        'encoding': 'custom-encryption/base64',
    })

    assert message.data == 'encrypted-data-here'
    assert message.encoding == 'custom-encryption/base64'


# TM6a, TM6e
def test_message_size_sums_name_data_client_id_and_extras():
    assert message_size(Message()) == 0
    assert message_size(Message(name='event', data='hello', client_id='me')) == 12
    # TM6d: extras count as their JSON
    assert message_size(Message(extras={'push': {'a': 1}})) == len('{"push":{"a":1}}')
    # An id is not counted
    assert message_size(Message(id='abc:0', data='x')) == 1


# TM6b, TM6c, TM6f
def test_message_size_of_each_kind_of_data():
    # TM6f: a string is its length, and a non-ASCII one is not counted as its JSON escape
    assert message_size(Message(data='h\u00e9llo')) == 5
    # TM6c: binary is its byte length, not the length of its base64
    assert message_size(Message(data=b'\x00' * 10)) == 10
    assert message_size(Message(data=bytearray(10))) == 10
    # TM6b: an object or array is the length of its JSON
    assert message_size(Message(data={'k': 'v'})) == len('{"k":"v"}')
    assert message_size(Message(data=[1, '\u00e9'])) == len('[1,"\u00e9"]')


# RSL1i, TO3l8f: the limit applies to the messages published together
def test_validate_message_size_raises_40009_above_the_limit():
    messages = [Message(name='a', data='x' * 4), Message(name='b', data='x' * 4)]

    validate_message_size(messages, 10)
    with pytest.raises(AblyException) as excinfo:
        validate_message_size(messages, 9)

    assert excinfo.value.code == 40009
    assert excinfo.value.status_code == 400
