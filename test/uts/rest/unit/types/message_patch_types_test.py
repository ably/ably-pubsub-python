"""Derived from uts/rest/unit/types/message_patch_types.md in ably/specification.

Spec points: TM5, TM2v, MPA1, MPA2, MPA2a, MPA2b, MPA2b1, MPA2b2, MPA2b3, MPD2, MPD2a-MPD2d, MPD4,
MPD4a, MPH2, MPH2a-MPH2c, MPU2, MPU2a, MPU2b, MPP2, MPP2a

`fromJson` and `fromEncoded` are spelled `from_encoded`, `toJson` is spelled `as_dict`, `userClaim` is
`user_claim`, and the specification's `extras: { "headers": [...] }` is `MessagePatchExtras(headers=[...])`.
"""

from ably.pubsub.types.message import Message, MessageAction
from ably.pubsub.types.messagepatch import (
    MessagePatchDataOperation,
    MessagePatches,
    MessagePatchExtras,
    MessagePatchHeaderOperation,
    MessagePatchPrivilegedOperation,
    MessagePatchUserClaimOperation,
)


# UTS: rest/unit/TM5/message-patch-action-value-0
def test_tm5_message_patch_action_value():
    assert int(MessageAction.MESSAGE_PATCH) == 6
    assert MessageAction(6) == MessageAction.MESSAGE_PATCH

    msg = Message.from_encoded({'serial': 's1', 'action': 6})
    assert msg.action == MessageAction.MESSAGE_PATCH


# UTS: rest/unit/TM2v/patches-parsed-from-wire-0
def test_tm2v_patches_parsed_from_wire():
    msg = Message.from_encoded({
        'action': 6,
        'serial': 'msg-serial-1',
        'version': {'serial': 'version-serial-2', 'timestamp': 1700000002000},
        'patches': {
            'data': [
                {'op': 'append', 'path': '/content/0/text', 'data': ' more'},
                {'op': 'set', 'data': 'replaced'},
                {'op': 'remove', 'path': '/old'},
            ],
            'extras': {
                'headers': [
                    {'op': 'set', 'key': 'status', 'value': 'complete'},
                    {'op': 'set', 'key': 'count', 'value': 3},
                    {'op': 'set', 'key': 'final', 'value': True},
                    {'op': 'remove', 'key': 'draft'},
                ],
                'userClaim': {'op': 'set', 'value': 'moderator'},
                'privileged': {'op': 'remove'},
            },
        },
    })

    assert isinstance(msg.patches, MessagePatches)

    data_ops = msg.patches.data
    assert len(data_ops) == 3
    assert isinstance(data_ops[0], MessagePatchDataOperation)
    assert data_ops[0].op == 'append'
    assert data_ops[0].path == '/content/0/text'
    assert data_ops[0].data == ' more'
    assert data_ops[1].op == 'set'
    assert data_ops[1].path is None or data_ops[1].path == ''
    assert data_ops[1].data == 'replaced'
    assert data_ops[2].op == 'remove'
    assert data_ops[2].path == '/old'
    assert data_ops[2].data is None

    headers = msg.patches.extras.headers
    assert len(headers) == 4
    assert isinstance(headers[0], MessagePatchHeaderOperation)
    assert headers[0].op == 'set'
    assert headers[0].key == 'status'
    assert headers[0].value == 'complete'
    assert headers[1].value == 3
    assert headers[2].value is True
    assert headers[3].op == 'remove'
    assert headers[3].key == 'draft'
    assert headers[3].value is None

    assert isinstance(msg.patches.extras.user_claim, MessagePatchUserClaimOperation)
    assert msg.patches.extras.user_claim.op == 'set'
    assert msg.patches.extras.user_claim.value == 'moderator'

    assert isinstance(msg.patches.extras.privileged, MessagePatchPrivilegedOperation)
    assert msg.patches.extras.privileged.op == 'remove'


# UTS: rest/unit/MPD4/patch-values-decoded-0
def test_mpd4_patch_values_decoded():
    msg = Message.from_encoded({
        'action': 6,
        'serial': 's1',
        'patches': {
            'data': [
                {'op': 'set', 'path': '/a', 'data': '{"b":1}', 'encoding': 'json'},
                {'op': 'set', 'path': '/n', 'data': '42', 'encoding': 'json'},
                {'op': 'set', 'path': '/c', 'data': 'AQI=', 'encoding': 'base64'},
                {'op': 'set', 'path': '/u', 'data': 'aGk=', 'encoding': 'utf-8/base64'},
                {'op': 'set', 'path': '/j', 'data': 'eyJ4IjoxfQ==', 'encoding': 'json/utf-8/base64'},
                {'op': 'append', 'path': '/d', 'data': 'text'},
            ],
        },
    })

    ops = msg.patches.data

    # MPD4a — JSON values stay as JSON text, whatever their type
    assert ops[0].data == '{"b":1}'
    assert ops[0].encoding == 'json'
    assert ops[1].data == '42'
    assert ops[1].encoding == 'json'

    # MPD4 — other transforms are inverted, as for a message's data
    assert ops[2].data == bytes([0x01, 0x02])
    assert ops[2].encoding is None or ops[2].encoding == ''
    assert ops[3].data == 'hi'
    assert ops[3].encoding is None or ops[3].encoding == ''

    # MPD4a — the transforms after a leading json are inverted, leaving the JSON text
    assert ops[4].data == '{"x":1}'
    assert ops[4].encoding == 'json'

    assert ops[5].data == 'text'
    assert ops[5].encoding is None or ops[5].encoding == ''


# UTS: rest/unit/MPA2/patches-serialized-to-wire-0
def test_mpa2_patches_serialized_to_wire():
    msg = Message(
        serial='s1',
        action=MessageAction.MESSAGE_PATCH,
        patches=MessagePatches(
            data=[
                MessagePatchDataOperation(op='append', path='/text', data='lo'),
                MessagePatchDataOperation(op='remove', path='/old'),
            ],
            extras=MessagePatchExtras(headers=[
                MessagePatchHeaderOperation(op='set', key='status', value='complete'),
            ]),
        ),
    )
    json_data = msg.as_dict(binary=False)

    assert json_data['action'] == 6
    assert json_data['serial'] == 's1'
    assert json_data['patches']['data'] == [
        {'op': 'append', 'path': '/text', 'data': 'lo'},
        {'op': 'remove', 'path': '/old'},
    ]
    assert json_data['patches']['extras']['headers'] == [
        {'op': 'set', 'key': 'status', 'value': 'complete'},
    ]
