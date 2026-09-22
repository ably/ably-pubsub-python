"""Derived from uts/rest/unit/types/presence_message_types.md in ably/specification.

Spec points: TP1, TP2, TP3, TP3a, TP3b, TP3c, TP3d, TP3e, TP3f, TP3g, TP3h, TP3i, TP4, TP5
"""

from datetime import datetime, timedelta

from ably.types.presence import PresenceAction, PresenceMessage
from test.uts.helpers.deviations import deviation, spec_error


def datetime_from_ms(ms):
    """The datetime ably-python decodes a wire timestamp into."""
    return datetime.utcfromtimestamp(0) + timedelta(milliseconds=ms)


def decode_protocol_message_presence(protocol_message):
    """The `presence` array of a ProtocolMessage, decoded the way the client decodes one.

    ably-python has no ProtocolMessage type; `RealtimeChannel._on_message` hands the raw
    `presence` array of an incoming PRESENCE or SYNC message to `from_encoded_array`.
    """
    return PresenceMessage.from_encoded_array(protocol_message['presence'])


# UTS: rest/unit/TP2/presence-action-enum-values-0
def test_tp2_presence_action_enum_values():
    assert PresenceAction.ABSENT == 0
    assert PresenceAction.PRESENT == 1
    assert PresenceAction.ENTER == 2
    assert PresenceAction.LEAVE == 3
    assert PresenceAction.UPDATE == 4


# UTS: rest/unit/TP3a/presence-message-attributes-0
def test_tp3a_presence_message_attributes():
    # TP3a - id attribute
    msg = PresenceMessage(id='presence-123')
    assert msg.id == 'presence-123'

    # TP3b - action attribute
    msg = PresenceMessage(action=PresenceAction.ENTER)
    assert msg.action == PresenceAction.ENTER

    # TP3c - clientId attribute
    msg = PresenceMessage(client_id='user-1')
    assert msg.client_id == 'user-1'

    # TP3d - connectionId attribute
    msg = PresenceMessage(connection_id='conn-1')
    assert msg.connection_id == 'conn-1'

    # TP3e - data attribute (string)
    msg = PresenceMessage(data='hello')
    assert msg.data == 'hello'

    # TP3e - data attribute (object)
    msg = PresenceMessage(data={'status': 'online'})
    assert msg.data == {'status': 'online'}

    # TP3f - encoding attribute
    msg = PresenceMessage(encoding='json')
    assert msg.encoding == 'json'

    # TP3g - timestamp attribute
    msg = PresenceMessage(timestamp=1234567890000)
    assert msg.timestamp == 1234567890000

    # TP3i - extras attribute
    msg = PresenceMessage(extras={'headers': {'x-custom': 'value'}})
    assert msg.extras['headers']['x-custom'] == 'value'


# UTS: rest/unit/TP3h/member-key-combines-ids-0
def test_tp3h_member_key_combines_ids():
    msg = PresenceMessage(connection_id='conn-1', client_id='user-1')
    assert msg.member_key == 'conn-1:user-1'

    msg2 = PresenceMessage(connection_id='conn-2', client_id='user-1')
    assert msg2.member_key == 'conn-2:user-1'

    # Same clientId, different connectionId - different memberKey
    assert msg.member_key != msg2.member_key


# UTS: rest/unit/TP3d/connectionid-from-protocol-message-0
@deviation
def test_tp3d_connectionid_from_protocol_message():
    protocol_msg = {
        'action': 14,  # PRESENCE
        'connectionId': 'proto-conn-1',
        # UTS SPEC ERROR: TP3d - protocol.md encodes the presence action as the enum
        # ordinal, not the string "enter".
        'presence': [
            {'action': PresenceAction.ENTER, 'clientId': 'user-1'},
        ],
    }

    presence_msg = decode_protocol_message_presence(protocol_msg)[0]
    assert presence_msg.connection_id == 'proto-conn-1'


# UTS: rest/unit/TP3a/id-from-protocol-message-1
@deviation
def test_tp3a_id_from_protocol_message():
    protocol_msg = {
        'action': 14,  # PRESENCE
        'id': 'proto-msg-42',
        # UTS SPEC ERROR: TP3a - protocol.md encodes the presence action as the enum
        # ordinal, not the string "enter".
        'presence': [
            {'action': PresenceAction.ENTER, 'clientId': 'alice'},
            {'action': PresenceAction.ENTER, 'clientId': 'bob'},
        ],
    }

    presence = decode_protocol_message_presence(protocol_msg)
    assert presence[0].id == 'proto-msg-42:0'
    assert presence[1].id == 'proto-msg-42:1'


# UTS: rest/unit/TP3g/timestamp-from-protocol-message-0
@deviation
def test_tp3g_timestamp_from_protocol_message():
    protocol_msg = {
        'action': 14,  # PRESENCE
        'timestamp': 9999999,
        # UTS SPEC ERROR: TP3g - protocol.md encodes the presence action as the enum
        # ordinal, not the string "enter".
        'presence': [
            {'action': PresenceAction.ENTER, 'clientId': 'user-1'},
        ],
    }

    presence_msg = decode_protocol_message_presence(protocol_msg)[0]
    assert presence_msg.timestamp == 9999999


# UTS: rest/unit/TP3/presence-from-json-0
def test_tp3_presence_from_json():
    json_data = {
        'id': 'pm-123',
        # UTS SPEC ERROR: TP3 - protocol.md encodes the presence action as the enum
        # ordinal, not the string "enter".
        'action': PresenceAction.ENTER,
        'clientId': 'user-1',
        'connectionId': 'conn-1',
        'data': 'hello',
        'encoding': None,
        'timestamp': 1234567890000,
        'extras': {'headers': {'x-key': 'x-value'}},
    }

    msg = PresenceMessage.from_encoded(json_data)

    assert msg.id == 'pm-123'
    assert msg.action == PresenceAction.ENTER
    assert msg.client_id == 'user-1'
    assert msg.connection_id == 'conn-1'
    assert msg.data == 'hello'
    # NOTE: features.md types TP3g as `Time`, so a datetime is the idiomatic rendering.
    assert msg.timestamp == datetime_from_ms(1234567890000)
    assert msg.extras['headers']['x-key'] == 'x-value'


# UTS: rest/unit/TP3/presence-encoded-data-from-json-1
def test_tp3_presence_encoded_data_from_json():
    test_cases = [
        (None, 'plain text', 'plain text'),
        ('json', '{"status":"online"}', {'status': 'online'}),
        ('base64', 'SGVsbG8=', b'Hello'),
    ]

    for encoding, wire_data, expected_data in test_cases:
        json_data = {
            # UTS SPEC ERROR: TP3 - protocol.md encodes the presence action as the enum
            # ordinal, not the string "enter".
            'action': PresenceAction.ENTER,
            'clientId': 'user-1',
            'data': wire_data,
            'encoding': encoding,
        }

        msg = PresenceMessage.from_encoded(json_data)

        assert msg.data == expected_data
        # Encoding consumed. ably-python spells "no encoding" as the empty string.
        assert msg.encoding == ''


# UTS: rest/unit/TP3/presence-to-json-2
# An outgoing action is asserted as the string "enter", where protocol.md encodes it as the
# enum ordinal; see deviations.md.
@spec_error
def test_tp3_presence_to_json():
    msg = PresenceMessage(
        action=PresenceAction.ENTER,
        client_id='user-1',
        data='hello',
        extras={'headers': {'x-key': 'x-value'}},
    )

    json_data = msg.to_encoded()

    assert json_data['action'] == 'enter'
    assert json_data['clientId'] == 'user-1'
    assert json_data['data'] == 'hello'
    assert json_data['extras']['headers']['x-key'] == 'x-value'


# UTS: rest/unit/TP3/null-attributes-omitted-3
# The same outgoing string action as presence-to-json-2; see deviations.md.
@spec_error
def test_tp3_null_attributes_omitted():
    msg = PresenceMessage(action=PresenceAction.ENTER, client_id='user-1')

    json_data = msg.to_encoded()

    assert json_data['action'] == 'enter'
    assert json_data['clientId'] == 'user-1'
    assert 'data' not in json_data or json_data['data'] is None
    assert 'encoding' not in json_data or json_data['encoding'] is None
    assert 'extras' not in json_data or json_data['extras'] is None
    assert 'id' not in json_data or json_data['id'] is None


# UTS: rest/unit/TP4/from-encoded-presence-0
def test_tp4_from_encoded_presence():
    # fromEncoded - single message
    raw = {
        # UTS SPEC ERROR: TP4 - protocol.md encodes the presence action as the enum
        # ordinal, not the string "enter".
        'action': PresenceAction.ENTER,
        'clientId': 'user-1',
        'data': '{"status":"online"}',
        'encoding': 'json',
    }

    msg = PresenceMessage.from_encoded(raw)

    assert msg.action == PresenceAction.ENTER
    assert msg.client_id == 'user-1'
    assert msg.data == {'status': 'online'}
    # ably-python spells "no encoding" as the empty string.
    assert msg.encoding == ''

    # fromEncodedArray - array of messages
    raw_array = [
        {'action': PresenceAction.ENTER, 'clientId': 'alice', 'data': 'hello'},
        {'action': PresenceAction.ENTER, 'clientId': 'bob', 'data': 'world'},
    ]

    messages = PresenceMessage.from_encoded_array(raw_array)

    assert len(messages) == 2
    assert messages[0].client_id == 'alice'
    assert messages[0].data == 'hello'
    assert messages[1].client_id == 'bob'
    assert messages[1].data == 'world'


# UTS: rest/unit/TP5/presence-message-size-0
@deviation
def test_tp5_presence_message_size():
    # Size includes clientId + data + extras (same formula as TM6)
    msg = PresenceMessage(
        action=PresenceAction.ENTER,
        client_id='user-1',
        data='hello',
    )

    size = msg.size

    # Size should account for clientId (6 bytes) + data (5 bytes) = 11
    assert size == 11

    # Size with object data (JSON-encoded size)
    msg2 = PresenceMessage(
        action=PresenceAction.ENTER,
        client_id='u',
        data={'key': 'value'},
    )

    # clientId (1) + JSON-encoded data length
    assert msg2.size > 1
