"""Derived from uts/rest/unit/types/message_types.md in ably/specification.

Spec points: TM1, TM2, TM3, TM4, TM2a, TM2b, TM2c, TM2d, TM2e, TM2f, TM2g, TM2h, TM2i
"""

import pytest

from ably.types.message import Message

# `fromEncoded` is spelled `from_encoded` here, and "no encoding" is rendered as the empty
# string rather than null, since EncodeDataMixin joins an empty list of transforms.

ENCODING_CASES = [
    pytest.param(None, 'plain text', 'plain text', id='null'),
    pytest.param('json', '{"key":"value"}', {'key': 'value'}, id='json'),
    pytest.param('base64', 'SGVsbG8=', b'Hello', id='base64'),
    pytest.param('json/base64', 'eyJrIjoidiJ9', {'k': 'v'}, id='json-base64'),
]


# UTS: rest/unit/TM2a/message-attributes-0
def test_tm2a_message_attributes():
    # TM2a - id attribute
    message = Message(id='unique-id')
    assert message.id == 'unique-id'

    # TM2b - name attribute
    message = Message(name='event-name')
    assert message.name == 'event-name'

    # TM2c - data attribute
    message = Message(data='string-data')
    assert message.data == 'string-data'

    message = Message(data={'key': 'value'})
    assert message.data == {'key': 'value'}

    message = Message(data=bytes([0x01, 0x02]))
    assert message.data == bytes([0x01, 0x02])

    # TM2d - clientId attribute
    message = Message(client_id='message-client')
    assert message.client_id == 'message-client'

    # TM2e - connectionId attribute
    message = Message(connection_id='conn-id')
    assert message.connection_id == 'conn-id'

    # TM2f - timestamp attribute
    message = Message(timestamp=1234567890000)
    assert message.timestamp == 1234567890000

    # TM2g - encoding attribute
    message = Message(encoding='json/base64')
    assert message.encoding == 'json/base64'

    # TM2h - extras attribute
    message = Message(extras={
        'push': {'notification': {'title': 'Hello'}},
    })
    assert message.extras['push']['notification']['title'] == 'Hello'

    # TM2i - serial attribute (server-assigned)
    # Serial is typically read-only from server responses


# UTS: rest/unit/TM3/from-encoded-deserialization-0
def test_tm3_from_encoded_deserialization():
    json_data = {
        'id': 'msg-123',
        'name': 'test-event',
        'data': 'hello world',
        'encoding': None,
        'clientId': 'sender-client',
        'connectionId': 'conn-456',
        'timestamp': 1234567890000,
        'extras': {'headers': {'x-custom': 'value'}},
    }

    message = Message.from_encoded(json_data)

    assert message.id == 'msg-123'
    assert message.name == 'test-event'
    assert message.data == 'hello world'
    assert message.client_id == 'sender-client'
    assert message.connection_id == 'conn-456'
    assert message.timestamp == 1234567890000
    assert message.extras['headers']['x-custom'] == 'value'


# UTS: rest/unit/TM3/from-encoded-decodes-encoding-1
@pytest.mark.parametrize('encoding, wire_data, expected_data', ENCODING_CASES)
def test_tm3_from_encoded_decodes_encoding(encoding, wire_data, expected_data):
    json_data = {
        'id': 'msg',
        'name': 'event',
        'data': wire_data,
        'encoding': encoding,
    }

    message = Message.from_encoded(json_data)

    assert message.data == expected_data
    # The spec asserts the encoding is null once consumed; the empty string is how a Message
    # with no remaining transforms renders its encoding here.
    assert message.encoding == ''


# UTS: rest/unit/TM4/message-constructors-0
def test_tm4_message_constructors():
    # constructor(name, data)
    message = Message(name='event-name', data='payload')
    assert message.name == 'event-name'
    assert message.data == 'payload'
    assert message.client_id is None

    # constructor(name, data, clientId)
    message = Message(name='event-name', data='payload', client_id='client-1')
    assert message.name == 'event-name'
    assert message.data == 'payload'
    assert message.client_id == 'client-1'

    # Both name and data are nullable
    message = Message(name=None, data=None)
    assert message.name is None
    assert message.data is None


# UTS: rest/unit/TM/null-missing-attributes-0
def test_tm_null_missing_attributes():
    # Minimal message
    message = Message()

    # All optional attributes should be null/undefined
    assert message.id is None
    assert message.name is None
    assert message.data is None
    assert message.client_id is None
    assert message.timestamp is None


# UTS: rest/unit/TM/message-with-extras-1
def test_tm_message_with_extras():
    # Push notification extras
    message = Message(
        name='push-event',
        data='payload',
        extras={
            'push': {
                'notification': {
                    'title': 'New Message',
                    'body': 'You have a new notification',
                },
                'data': {
                    'customKey': 'customValue',
                },
            },
        },
    )

    assert message.extras['push']['notification']['title'] == 'New Message'
    assert message.extras['push']['data']['customKey'] == 'customValue'
