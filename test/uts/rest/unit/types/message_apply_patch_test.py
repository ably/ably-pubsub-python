"""Derived from uts/rest/unit/types/message_apply_patch.md in ably/specification.

Spec points: TM9, TM9a, TM9b, TM9c, TM9d, TM9d1-TM9d4, TM9e, TM9f, TM9f1-TM9f5, TM9g, TM9g1-TM9g4

`Message.applyPatch(message, patch)` is the instance method `Message.apply_patch`, called here through
the class so that it reads as the specification's static function. `fromEncoded` is spelled
`from_encoded`, and `toJson` is spelled `as_dict`. Binary data decodes to a `bytearray`, which
compares equal to the `bytes` the specification writes.
"""

import base64
import json

import pytest

from ably.pubsub.types.message import Message, MessageAction
from ably.pubsub.util.exceptions import AblyException


def decode(**values):
    return Message.from_encoded({'serial': 's1', 'timestamp': 1, **values})


def decode_patch(patches, **values):
    return decode(**{
        'action': 6,  # MESSAGE_PATCH
        'version': {'serial': 'v2', 'timestamp': 2},
        'patches': patches,
        **values,
    })


def assert_apply_fails(message, patch, description=''):
    """`Message.applyPatch(message, patch) FAILS WITH error`, with the 40000/400 every failure carries."""
    with pytest.raises(AblyException) as excinfo:
        Message.apply_patch(message, patch)
    assert excinfo.value.code == 40000, description
    assert excinfo.value.status_code == 400, description


# UTS: rest/unit/TM9f3/apply-to-decoded-data-0
def test_tm9f3_apply_to_decoded_data():
    message = decode(
        name='reply',
        data='{"content":[{"type":"text","text":"Hel"}],"meta":{"kept":true}}',
        encoding='json',
        extras={'headers': {'status': 'streaming', 'model': 'm1'}},
    )
    patch = decode_patch({
        'data': [
            {'op': 'append', 'path': '/content/0/text', 'data': 'lo'},
            {'op': 'set', 'path': '/content/-', 'data': '{"type":"tool"}', 'encoding': 'json'},
            {'op': 'set', 'path': '/done', 'data': 'true', 'encoding': 'json'},
        ],
        'extras': {
            'headers': [
                {'op': 'set', 'key': 'status', 'value': 'complete'},
                {'op': 'remove', 'key': 'model'},
            ],
        },
    })

    patched = Message.apply_patch(message, patch)

    assert patched.action == MessageAction.MESSAGE_UPDATE
    assert patched.serial == 's1'
    assert patched.name == 'reply'
    assert patched.version.serial == 'v2'
    assert patched.data == {
        'content': [{'type': 'text', 'text': 'Hello'}, {'type': 'tool'}],
        'meta': {'kept': True},
        'done': True,
    }
    assert patched.encoding is None or patched.encoding == ''
    assert patched.extras == {'headers': {'status': 'complete'}}
    assert patched.patches is None
    assert isinstance(patched, Message)


# UTS: rest/unit/TM9d/keeps-message-fields-0
def test_tm9d_keeps_message_fields():
    message = decode(clientId='author', connectionId='c1', data='Hel')
    patch = decode_patch(
        {'data': [{'op': 'append', 'data': 'lo'}]},
        clientId='patcher', connectionId='c2', timestamp=2,
    )

    patched = Message.apply_patch(message, patch)

    assert patched.client_id == 'author'
    assert patched.connection_id == 'c1'
    assert patched.timestamp == 1
    assert patched.version.serial == 'v2'
    assert patched.data == 'Hello'


# UTS: rest/unit/TM9c/message-not-mutated-0
def test_tm9c_message_not_mutated():
    message = decode(
        action=0,  # MESSAGE_CREATE
        data='{"a":{"text":"x"},"b":{"unchanged":true},"list":[1]}',
        encoding='json',
        extras={'headers': {'h': 'v'}},
    )
    before = message.as_dict()
    patch = decode_patch({
        'data': [
            {'op': 'append', 'path': '/a/text', 'data': 'y'},
            {'op': 'set', 'path': '/list/-', 'data': '2', 'encoding': 'json'},
        ],
        'extras': {'headers': [{'op': 'set', 'key': 'h', 'value': 'w'}]},
    })

    patched = Message.apply_patch(message, patch)

    assert message.as_dict() == before
    assert message.action == MessageAction.MESSAGE_CREATE
    assert message.data == {'a': {'text': 'x'}, 'b': {'unchanged': True}, 'list': [1]}
    assert message.extras == {'headers': {'h': 'v'}}

    assert patched.data == {'a': {'text': 'xy'}, 'b': {'unchanged': True}, 'list': [1, 2]}
    assert patched.extras == {'headers': {'h': 'w'}}


# UTS: rest/unit/TM9f5/splice-into-json-text-0
def test_tm9f5_splice_into_json_text():
    text = '{ "content" : [ {"text":"Hel"} ], "n": 1.0 }'
    message = decode(data=text)
    patch = decode_patch({
        'data': [
            {'op': 'append', 'path': '/content/0/text', 'data': 'lo "world"'},
            {'op': 'set', 'path': '/obj', 'data': '{ "spaced" : 1 }', 'encoding': 'json'},
            {'op': 'set', 'path': '/content/-', 'data': 'end'},
        ],
    })

    patched = Message.apply_patch(message, patch)

    assert isinstance(patched.data, str)
    assert patched.data == (
        '{ "content" : [ {"text":"Hello \\"world\\""},"end" ], "n": 1.0,"obj":{ "spaced" : 1 } }'
    )
    assert patched.encoding is None or patched.encoding == ''


# UTS: rest/unit/TM9f5/splice-into-binary-json-1
def test_tm9f5_splice_into_binary_json():
    text = '{ "content" : [ {"text":"Hel"} ] }'
    message = decode(data=base64.b64encode(text.encode('utf-8')).decode('ascii'), encoding='base64')
    patch = decode_patch({
        'data': [{'op': 'append', 'path': '/content/0/text', 'data': 'lo'}],
    })

    patched = Message.apply_patch(message, patch)

    assert isinstance(patched.data, (bytes, bytearray))
    assert bytes(patched.data).decode('utf-8') == '{ "content" : [ {"text":"Hello"} ] }'


# UTS: rest/unit/TM9f5f/remove-from-json-text-0
def test_tm9f5f_remove_from_json_text():
    patch = decode_patch({
        'data': [
            {'op': 'remove', 'path': '/a/1'},
            {'op': 'remove', 'path': '/b'},
            {'op': 'remove', 'path': '/c'},
            {'op': 'remove', 'path': '/d/only'},
        ],
    })
    message = Message(serial='s1', data='{"a":[1,2,3],"b":2,"c":3,"d":{"only":true}}')

    patched = Message.apply_patch(message, patch)

    # /a/1: element 2 is followed by 3, so deleted up to it (TM9f5f)
    # /b and then /c: each is followed by another member, so deleted up to it (TM9f5f)
    # /d/only: the only member of "d", so its text is deleted (TM9f5h)
    assert patched.data == '{"a":[1,3],"d":{}}'

    # Last of several
    message2 = Message(serial='s1', data='{"a":1, "b":2}')
    patch2 = decode_patch({'data': [{'op': 'remove', 'path': '/b'}]})

    patched2 = Message.apply_patch(message2, patch2)

    # TM9f5g: deleted from the end of 1, the previous value
    assert patched2.data == '{"a":1}'


# UTS: rest/unit/TM9f5i/escaped-member-name-0
def test_tm9f5i_escaped_member_name():
    message = decode(data='{"a\\u0062":"x","c/d":"y"}')
    patch = decode_patch({
        'data': [
            {'op': 'append', 'path': '/ab', 'data': '1'},
            {'op': 'append', 'path': '/c~1d', 'data': '2'},
        ],
    })

    patched = Message.apply_patch(message, patch)

    assert patched.data == '{"a\\u0062":"x1","c/d":"y2"}'


# UTS: rest/unit/TM9f5e/json-string-escaping-0
def test_tm9f5e_json_string_escaping():
    appended = 'q"b\\n\nt\tc\u0001é<>&'
    message = decode(data='{"t":""}')
    patch = decode_patch({
        'data': [
            {'op': 'append', 'path': '/t', 'data': appended},
            {'op': 'set', 'path': '/new\nkey', 'data': 'v'},
        ],
    })

    patched = Message.apply_patch(message, patch)

    assert isinstance(patched.data, str)
    assert json.loads(patched.data) == {'t': appended, 'new\nkey': 'v'}
    assert patched.data.startswith('{"t":"q')
    assert patched.data.endswith('"}')


# UTS: rest/unit/TM9f2/apply-to-whole-data-0
def test_tm9f2_apply_to_whole_data():
    append = decode_patch({'data': [{'op': 'append', 'data': ' world'}]})

    # TM9f2c — string
    assert Message.apply_patch(decode(data='hello'), append).data == 'hello world'

    # TM9f2b — absent data
    appended = Message.apply_patch(decode(), append)
    assert appended.data == ' world'
    assert appended.encoding is None or appended.encoding == ''

    # TM9f2c — binary
    append_binary = decode_patch({'data': [{'op': 'append', 'data': 'Aw==', 'encoding': 'base64'}]})
    binary = decode(data='AQI=', encoding='base64')
    assert Message.apply_patch(binary, append_binary).data == bytes([0x01, 0x02, 0x03])

    # TM9f2a — set to a JSON value
    set_json = decode_patch({'data': [{'op': 'set', 'data': '{"a":1}', 'encoding': 'json'}]})
    patched = Message.apply_patch(decode(data='hello'), set_json)
    assert patched.data == {'a': 1}
    assert patched.encoding is None or patched.encoding == ''

    # TM9f2a — set to a string
    set_string = decode_patch({'data': [{'op': 'set', 'data': 'replaced'}]})
    assert Message.apply_patch(decode(data='{"a":1}', encoding='json'), set_string).data == 'replaced'


# UTS: rest/unit/TM9f2d/append-whole-non-string-0
def test_tm9f2d_append_whole_non_string():
    message = decode(data='{"a":1}', encoding='json')

    append = decode_patch({'data': [{'op': 'append', 'data': 'x'}]})
    assert_apply_fails(message, append)

    remove = decode_patch({'data': [{'op': 'remove'}]})
    assert_apply_fails(message, remove)

    # TM9f2b, TM9f2c — the operation's encoding must be empty
    append_json = decode_patch({'data': [{'op': 'append', 'data': '"x"', 'encoding': 'json'}]})
    for target in [decode(), decode(data='text')]:
        assert_apply_fails(target, append_json, f'append_json to {target.data!r}')

    # TM9f2a — a JSON scalar cannot replace the whole of data
    for value in ['null', '1', 'true', '"s"']:
        set_scalar = decode_patch({'data': [{'op': 'set', 'data': value, 'encoding': 'json'}]})
        assert_apply_fails(decode(data='hello'), set_scalar, f'set {value}')


# UTS: rest/unit/TM9e/atomic-rejection-0
def test_tm9e_atomic_rejection():
    message = decode(data='{"a":"x"}', encoding='json', extras={'headers': {'h': 'v'}})
    patch = decode_patch({
        'data': [
            {'op': 'append', 'path': '/a', 'data': 'y'},
            {'op': 'append', 'path': '/missing', 'data': 'y'},
        ],
        'extras': {'headers': [{'op': 'set', 'key': 'h', 'value': 'w'}]},
    })

    assert_apply_fails(message, patch)

    assert message.data == {'a': 'x'}
    assert message.extras == {'headers': {'h': 'v'}}


# UTS: rest/unit/TM9f3/invalid-operations-rejected-0
def test_tm9f3_invalid_operations_rejected():
    cases = [
        # [data, operation]
        [{'a': 1}, {'op': 'append', 'path': '/a', 'data': 'x'}],    # TM9f3f: not a string
        [{'a': []}, {'op': 'append', 'path': '/a/-', 'data': 'x'}],  # TM9f3f: "-"
        # TM9f3f: encoding not empty
        [{'a': 'x'}, {'op': 'append', 'path': '/a', 'data': '"y"', 'encoding': 'json'}],
        [{'a': []}, {'op': 'remove', 'path': '/a/-'}],               # TM9f3g: "-"
        [{'a': []}, {'op': 'set', 'path': '/a/0', 'data': 'x'}],     # TM9f3e: no element 0
        [{'a': [1]}, {'op': 'set', 'path': '/a/01', 'data': 'x'}],   # TM9f3e: leading zero is not an index
        [{'a': 1}, {'op': 'set', 'path': '/a/b', 'data': 'x'}],      # TM9f3c: parent is a number
        [{'a': 1}, {'op': 'set', 'path': '/x/y', 'data': 'x'}],      # TM9f3b: /x does not exist
        [{'a': 1}, {'op': 'set', 'path': 'a', 'data': 'x'}],         # TM9f3a: no leading "/"
        [{'a': 1}, {'op': 'set', 'path': '/~2', 'data': 'x'}],       # TM9f3a: invalid "~" escape
        [{'a': 1}, {'op': 'remove', 'path': '/b'}],                  # TM9f3g: /b does not exist
        [{'a': 1}, {'op': 'move', 'path': '/a'}],                    # TM9f1: unknown op
    ]

    for data, op in cases:
        for form, message in [
            ('decoded JSON', decode(data=json.dumps(data), encoding='json')),
            ('JSON text', decode(data=json.dumps(data))),
        ]:
            patch = decode_patch({'data': [op]})
            assert_apply_fails(message, patch, f'{op} on {form} {data}')

    # TM9f3 — a path operation on data that is not a JSON object or array
    not_container = decode(data='plain text')
    patch = decode_patch({'data': [{'op': 'set', 'path': '/a', 'data': 'x'}]})
    with pytest.raises(AblyException) as excinfo:
        Message.apply_patch(not_container, patch)
    assert excinfo.value.code == 40000


# UTS: rest/unit/TM9g1/remove-missing-header-0
def test_tm9g1_remove_missing_header():
    message = decode(data='x')
    patch = decode_patch({'extras': {'headers': [{'op': 'remove', 'key': 'h'}]}})

    assert_apply_fails(message, patch)


# UTS: rest/unit/TM9g1/set-header-adds-extras-1
def test_tm9g1_set_header_adds_extras():
    message = decode(data='x')
    patch = decode_patch({'extras': {'headers': [{'op': 'set', 'key': 'status', 'value': 'done'}]}})

    assert Message.apply_patch(message, patch).extras == {'headers': {'status': 'done'}}


# UTS: rest/unit/TM9g2/user-claim-operations-0
def test_tm9g2_user_claim_operations():
    message = decode(data='x', extras={'headers': {'h': 'v'}, 'userClaim': 'moderator'})

    set_claim = decode_patch(
        {'data': [{'op': 'append', 'data': 'y'}], 'extras': {'userClaim': {'op': 'set', 'value': 'guest'}}},
        extras={'push': {'notification': {'title': 't'}}, 'userClaim': 'guest'},
    )
    patched = Message.apply_patch(message, set_claim)
    assert patched.extras == {'headers': {'h': 'v'}, 'userClaim': 'guest'}
    assert patched.version.serial == 'v2'

    remove = decode_patch({
        'data': [{'op': 'append', 'data': 'y'}],
        'extras': {'userClaim': {'op': 'remove'}},
    })
    assert Message.apply_patch(message, remove).extras == {'headers': {'h': 'v'}}

    # Removing a missing claim succeeds, and leaves no extras (TM9g4)
    unclaimed = decode(data='x')
    assert Message.apply_patch(unclaimed, remove).extras is None


# UTS: rest/unit/TM9g3/privileged-remove-0
def test_tm9g3_privileged_remove():
    message = decode(data='x', extras={'headers': {'h': 'v'}, 'privileged': {'skipRule': '*'}})
    patch = decode_patch({
        'extras': {
            'headers': [{'op': 'set', 'key': 'h', 'value': 'w'}],
            'privileged': {'op': 'remove'},
        },
    })

    assert Message.apply_patch(message, patch).extras == {'headers': {'h': 'w'}}


# UTS: rest/unit/TM9a/reject-non-patch-or-serial-0
def test_tm9a_reject_non_patch_or_serial():
    message = decode(data='x')

    # TM9b
    other = decode_patch({'data': [{'op': 'append', 'data': 'y'}]}, serial='s2')
    assert_apply_fails(message, other)

    # TM9a
    assert_apply_fails(message, message)


# UTS: rest/unit/TM9f4/reserved-member-name-0
def test_tm9f4_reserved_member_name():
    message = decode(data='{}', encoding='json')
    patch = decode_patch({
        'data': [{'op': 'set', 'path': '/__proto__', 'data': '{"polluted":true}', 'encoding': 'json'}],
    })

    patched = Message.apply_patch(message, patch)

    assert list(patched.data.keys()) == ['__proto__']
    assert patched.data['__proto__'] == {'polluted': True}
