import ably.types.message


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
    ably.types.message.Message.update_inner_message_fields(proto_msg)
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
    ably.types.message.Message.update_inner_message_fields(proto_msg)
    presence_messages: list[dict] = proto_msg.get('presence')
    msg_index = 0
    for presence_msg in presence_messages:
        assert presence_msg.get('id') == f"abcdefg:{msg_index}"
        assert presence_msg.get('connectionId') == 'custom_connection_id'
        assert presence_msg.get('timestamp') == 23134
        msg_index = msg_index + 1


# RSL6b
def test_invalid_base64_data_is_delivered_with_remaining_encoding():
    message = ably.types.message.Message.from_encoded({
        'name': 'event',
        'data': 'encrypted-data-here',
        'encoding': 'custom-encryption/base64',
    })

    assert message.data == 'encrypted-data-here'
    assert message.encoding == 'custom-encryption/base64'
