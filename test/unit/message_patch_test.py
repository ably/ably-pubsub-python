"""Message patches (PSRFC-44): building and sending them, decoding received ones, and applying them.

The applier tests are ported from ably-pubsub-js's `test/unit/message_patch.test.js` (by way of
ably-pubsub-kotlin's `MessagePatchingTest`), so that the SDKs give Ably's result. The UTS derivations of
the specification's own tests are under `test/uts`: `rest/unit/channel/patch_message_test.py`,
`rest/unit/types/message_patch_types_test.py`, `rest/unit/types/message_apply_patch_test.py` and
`realtime/unit/channels/channel_patch_message_test.py`.
"""

import base64
import json
import uuid

import msgpack
import pytest

from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.server import (
    MessageAction,
    MessagePatchDataOperation,
    MessagePatches,
    MessagePatchExtras,
    MessagePatchHeaderOperation,
)
from ably.pubsub.transport.websockettransport import ProtocolMessageAction
from ably.pubsub.types.message import Message
from ably.pubsub.types.messagepatch import _quote
from ably.pubsub.types.operations import MessageOperation
from ably.pubsub.util.exceptions import AblyException
from test.uts.helpers.client import await_connection_state, realtime_client, rest_client
from test.uts.helpers.mock_http import MockHttpClient
from test.uts.helpers.mock_websocket import MockWebSocket, attached_message, connected_message


def decode(**fields):
    """A received message, from the fields of its wire form."""
    return Message.from_encoded({'serial': 's1', 'timestamp': 1, **fields})


def decode_patch(patches, **fields):
    return decode(action=6, version={'serial': 'v2', 'timestamp': 2}, patches=patches, **fields)


def assert_rejected(message, error):
    with pytest.raises(AblyException) as e:
        message()
    assert e.value.code == 40000
    assert error in e.value.message


# ---- Decoding and encoding ----

def test_decodes_a_patch_keeping_json_values_as_text():
    patch = decode_patch({
        'data': [
            {'op': 'set', 'path': '/a', 'data': '{"b":1}', 'encoding': 'json'},
            {'op': 'set', 'path': '/c', 'data': 'AQI=', 'encoding': 'base64'},
            {'op': 'append', 'path': '/d', 'data': 'text'},
        ],
        'extras': {'headers': [{'op': 'set', 'key': 'status', 'value': 'complete'}]},
    })

    assert patch.action == MessageAction.MESSAGE_PATCH
    ops = patch.patches.data
    assert (ops[0].op, ops[0].path, ops[0].data, ops[0].encoding) == ('set', '/a', '{"b":1}', 'json')
    assert (ops[1].data, ops[1].encoding) == (bytearray([1, 2]), '')
    assert (ops[2].op, ops[2].data) == ('append', 'text')
    header = patch.patches.extras.headers[0]
    assert (header.op, header.key, header.value) == ('set', 'status', 'complete')


def test_a_data_operations_value_is_decoded_as_message_data_is_except_for_json():
    patch = decode_patch({'data': [
        {'op': 'set', 'path': '/n', 'data': '42', 'encoding': 'json'},
        {'op': 'set', 'path': '/b', 'data': 'false', 'encoding': 'json'},
        {'op': 'set', 'path': '/s', 'data': 'plain'},
        {'op': 'set', 'path': '/m', 'data': {'over': 'msgpack'}},
    ]})

    # MPD4a: a JSON value is left as its text, with the encoding json.
    assert [op.data for op in patch.patches.data] == ['42', 'false', 'plain', {'over': 'msgpack'}]
    assert [op.encoding for op in patch.patches.data] == ['json', 'json', '', '']


@pytest.mark.parametrize('binary', [False, True], ids=['JSON', 'MsgPack'])
def test_encodes_a_patch_for_the_wire(binary):
    patch = MessagePatches(
        data=[
            MessagePatchDataOperation('set', path='/a', data={'b': 1}),
            MessagePatchDataOperation('set', path='/c', data=b'\x01\x02'),
            MessagePatchDataOperation('remove', path='/d'),
            MessagePatchDataOperation('set', path='/e', data='text'),
            MessagePatchDataOperation('set', path='/f', data=True),
            MessagePatchDataOperation('set', data=None),
        ],
        extras=MessagePatchExtras(headers=[
            MessagePatchHeaderOperation('set', 'stage', 'done'),
            MessagePatchHeaderOperation('remove', 'old'),
        ]),
    )

    wire = Message(serial='s1', action=MessageAction.MESSAGE_PATCH, patches=patch).as_dict(binary=binary)

    assert wire['action'] == 6
    assert wire['serial'] == 's1'
    binary_op = {'op': 'set', 'path': '/c', 'data': b'\x01\x02'} if binary \
        else {'op': 'set', 'path': '/c', 'data': 'AQI=', 'encoding': 'base64'}
    assert wire['patches'] == {
        'data': [
            {'op': 'set', 'path': '/a', 'data': '{"b":1}', 'encoding': 'json'},
            binary_op,
            {'op': 'remove', 'path': '/d'},
            {'op': 'set', 'path': '/e', 'data': 'text'},
            {'op': 'set', 'path': '/f', 'data': 'true', 'encoding': 'json'},
            {'op': 'set', 'data': 'null', 'encoding': 'json'},
        ],
        'extras': {'headers': [{'op': 'set', 'key': 'stage', 'value': 'done'}, {'op': 'remove', 'key': 'old'}]},
    }


def test_a_value_json_cannot_hold_fails_before_sending():
    with pytest.raises(AblyException) as e:
        MessagePatches(data=[MessagePatchDataOperation('set', path='/a', data=object())]).as_dict()
    assert e.value.code == 40013


def test_a_received_patch_is_sent_again_as_it_is():
    wire = {
        'data': [
            {'op': 'set', 'path': '/a', 'data': '{"b":1}', 'encoding': 'json'},
            {'op': 'set', 'path': '/c', 'data': 'AQI=', 'encoding': 'base64'},
            {'op': 'remove', 'path': '/d'},
        ],
        'extras': {'headers': [{'op': 'set', 'key': 'h', 'value': 'v'}], 'userClaim': {'op': 'remove'},
                   'privileged': {'op': 'remove'}},
    }

    assert decode_patch(wire).patches.as_dict() == wire


# ---- Applying ----

def test_applies_operations_to_decoded_json_data():
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
        'extras': {'headers': [{'op': 'set', 'key': 'status', 'value': 'complete'},
                               {'op': 'remove', 'key': 'model'}]},
    })

    patched = message.apply_patch(patch)

    assert patched.action == MessageAction.MESSAGE_UPDATE
    assert (patched.serial, patched.name, patched.version.serial) == ('s1', 'reply', 'v2')
    assert patched.data == {'content': [{'type': 'text', 'text': 'Hello'}, {'type': 'tool'}],
                            'meta': {'kept': True}, 'done': True}
    assert patched.extras == {'headers': {'status': 'complete'}}
    assert patched.patches is None


def test_keeps_the_copys_fields_other_than_data_extras_and_version():
    message = decode(clientId='author', connectionId='c1', data='Hel')
    patch = decode_patch({'data': [{'op': 'append', 'data': 'lo'}]}, clientId='patcher', connectionId='c2')

    patched = message.apply_patch(patch)

    assert (patched.client_id, patched.connection_id, patched.timestamp) == ('author', 'c1', 1)
    assert patched.version.serial == 'v2'
    assert patched.data == 'Hello'


def test_does_not_change_the_copy_and_shares_unchanged_parts():
    message = decode(data='{"a":{"text":"x"},"b":{"unchanged":true}}', encoding='json',
                     extras={'headers': {'h': 'v'}})
    before = message.data
    patch = decode_patch({'data': [{'op': 'append', 'path': '/a/text', 'data': 'y'}],
                          'extras': {'headers': [{'op': 'set', 'key': 'h', 'value': 'w'}]}})

    patched = message.apply_patch(patch)

    assert message.data == {'a': {'text': 'x'}, 'b': {'unchanged': True}}
    assert message.data is before
    assert message.extras == {'headers': {'h': 'v'}}
    assert patched.data['a'] == {'text': 'xy'}
    assert patched.data['b'] is before['b']


def test_splices_operations_into_json_text_keeping_its_formatting():
    text = '{ "content" : [ {"text":"Hel"} ], "n": 1.0 }'
    patch = decode_patch({'data': [
        {'op': 'append', 'path': '/content/0/text', 'data': 'lo "world"'},
        {'op': 'set', 'path': '/obj', 'data': '{ "spaced" : 1 }', 'encoding': 'json'},
        {'op': 'set', 'path': '/content/-', 'data': 'end'},
    ]})
    expected = '{ "content" : [ {"text":"Hello \\"world\\""},"end" ], "n": 1.0,"obj":{ "spaced" : 1 } }'

    assert decode(data=text).apply_patch(patch).data == expected
    from_binary = decode(data=base64.b64encode(text.encode()).decode(), encoding='base64').apply_patch(patch)
    assert bytes(from_binary.data).decode() == expected


def test_patches_json_kept_outside_a_message():
    patches = decode_patch({'data': [{'op': 'remove', 'path': '/a/1'}, {'op': 'remove', 'path': '/b'},
                                     {'op': 'remove', 'path': '/c'}]}).patches

    assert patches.apply_to_data('{"a":[1,2,3],"b":2,"c":3}') == '{"a":[1,3]}'
    assert patches.apply_to_data(b'{"a":[1,2,3],"b":2,"c":3}') == b'{"a":[1,3]}'
    assert patches.apply_to_data({'a': [1, 2, 3], 'b': 2, 'c': 3}) == {'a': [1, 3]}


def test_applies_operations_to_the_whole_of_data():
    append = decode_patch({'data': [{'op': 'append', 'data': ' world'}]})
    assert decode(data='hello').apply_patch(append).data == 'hello world'

    append_binary = decode_patch({'data': [{'op': 'append', 'data': 'Aw==', 'encoding': 'base64'}]})
    assert decode(data='AQI=', encoding='base64').apply_patch(append_binary).data == bytearray([1, 2, 3])

    # Appending to no data gives the value.
    assert decode().apply_patch(append).data == ' world'

    replaced = decode(data='hello').apply_patch(decode_patch({'data': [{'op': 'set', 'data': '{"a":1}',
                                                                         'encoding': 'json'}]}))
    assert replaced.data == {'a': 1}
    assert replaced.encoding == ''


def test_rejects_the_whole_patch_if_any_operation_is_rejected():
    message = decode(data='{"a":"x"}', encoding='json', extras={'headers': {'h': 'v'}})
    patch = decode_patch({'data': [{'op': 'append', 'path': '/a', 'data': 'y'},
                                   {'op': 'append', 'path': '/missing', 'data': 'y'}]})

    assert_rejected(lambda: message.apply_patch(patch),
                    'Unable to apply data patch operation 1 (append at "/missing"): '
                    'path "/missing" does not exist')
    assert message.data == {'a': 'x'}


@pytest.mark.parametrize('data,op,error', [
    ('{"a":1}', {'op': 'append', 'path': '/a', 'data': 'x'}, 'the value there is not a string'),
    ('{"a":[]}', {'op': 'append', 'path': '/a/-', 'data': 'x'}, '"-" can only be used to set'),
    ('{"a":[]}', {'op': 'set', 'path': '/a/0', 'data': 'x'}, 'does not exist'),
    ('{"a":1}', {'op': 'set', 'path': '/a/b', 'data': 'x'}, 'its parent is not an object or array'),
    ('{"a":1}', {'op': 'set', 'path': 'a', 'data': 'x'}, 'must be a JSON Pointer'),
    ('{"a":1}', {'op': 'remove', 'path': '/b'}, 'does not exist'),
    ('{"a":1}', {'op': 'remove'}, 'requires a path'),
    ('{"a":1}', {'op': 'move', 'path': '/a'}, 'unknown message patch operation "move"'),
])
@pytest.mark.parametrize('decoded', [True, False], ids=['decoded', 'text'])
def test_rejects_invalid_operations(data, op, error, decoded):
    message = decode(data=data, encoding='json') if decoded else decode(data=data)

    assert_rejected(lambda: message.apply_patch(decode_patch({'data': [op]})), error)


def test_rejects_appending_to_the_whole_of_data_that_is_not_a_string_or_binary():
    message = decode(data='{"a":1}', encoding='json')

    assert_rejected(lambda: message.apply_patch(decode_patch({'data': [{'op': 'append', 'data': 'x'}]})),
                    'both be strings or both be binary')


def test_sets_or_removes_the_claim_takes_the_patchs_version_and_ignores_the_patchs_own_extras():
    message = decode(data='x', extras={'headers': {'h': 'v'}, 'userClaim': 'moderator'})

    patched = message.apply_patch(decode_patch(
        {'data': [{'op': 'append', 'data': 'y'}],
         'extras': {'userClaim': {'op': 'set', 'value': 'guest'}}},
        extras={'push': {'notification': {'title': 't'}}, 'userClaim': 'guest'},
    ))
    assert patched.extras == {'headers': {'h': 'v'}, 'userClaim': 'guest'}
    assert patched.version.serial == 'v2'

    remove = decode_patch({'data': [{'op': 'append', 'data': 'y'}], 'extras': {'userClaim': {'op': 'remove'}}})
    assert message.apply_patch(remove).extras == {'headers': {'h': 'v'}}
    # Removing a claim the message does not have succeeds.
    assert decode(data='x').apply_patch(remove).extras is None


def test_removes_privileged_extras():
    message = decode(data='x', extras={'headers': {'h': 'v'}, 'privileged': {'skipRule': '*'}})
    patch = decode_patch({'extras': {'headers': [{'op': 'set', 'key': 'h', 'value': 'w'}],
                                     'privileged': {'op': 'remove'}}})

    assert message.apply_patch(patch).extras == {'headers': {'h': 'w'}}


def test_rejects_removing_a_header_that_does_not_exist():
    patch = decode_patch({'extras': {'headers': [{'op': 'remove', 'key': 'h'}]}})

    assert_rejected(lambda: decode(data='x').apply_patch(patch), 'the header does not exist')


def test_rejects_a_patch_for_another_message_or_a_message_that_is_not_a_patch():
    message = decode(data='x')
    other = decode_patch({'data': [{'op': 'append', 'data': 'y'}]}, serial='s2')

    assert_rejected(lambda: message.apply_patch(other), 'the patch is for message s2')
    assert_rejected(lambda: message.apply_patch(message), 'only a message.patch can be applied')


def test_key_escapes_and_duplicate_keys_in_json_text():
    # A token matches a key after JSON escapes are decoded, and the first of two equal keys.
    patch = decode_patch({'data': [{'op': 'set', 'path': '/café', 'data': '2', 'encoding': 'json'}]})

    patched = decode(data='{"caf\\u00e9":1,"café":0}').apply_patch(patch)

    assert patched.data == '{"caf\\u00e9":2,"café":0}'


def test_rejects_an_operation_whose_value_cannot_be_decoded():
    patch = decode_patch({'data': [{'op': 'set', 'path': '/a', 'data': 'x', 'encoding': 'cipher+aes-256-cbc'}]})

    assert_rejected(lambda: decode(data='{}', encoding='json').apply_patch(patch), 'this SDK cannot decode')


def test_quotes_strings_as_ably_does():
    assert _quote('a"b\\c\n\x01</>') == '"a\\"b\\\\c\\n\\u0001</>"'
    # A lone surrogate becomes U+FFFD, as Ably does with invalid UTF-8.
    assert _quote('x\ud800y') == '"x�y"'
    assert _quote('😀') == '"😀"'


# ---- Sending ----

def random_id():
    return uuid.uuid4().hex[:8]


async def test_http_patch_message_sends_a_patch():
    channel_name = f'test-patch-{random_id()}'
    captured = []

    def on_request(request):
        captured.append(request)
        request.respond_with(200, {'versionSerial': 'v2'})

    mock_http = MockHttpClient(on_connection_attempt=lambda conn: conn.respond_with_success(),
                               on_request=on_request)
    channel = rest_client(mock_http).channels.get(channel_name)

    patches = MessagePatches(
        data=[MessagePatchDataOperation('append', path='/text', data='lo')],
        extras=MessagePatchExtras(headers=[MessagePatchHeaderOperation('set', 'stage', 'done')]),
    )
    result = await channel.patch_message(
        Message(serial='s1', patches=patches),
        operation=MessageOperation(description='streamed'),
        params={'key': 'value'},
    )

    assert result.version_serial == 'v2'
    request = captured[0]
    assert request.method == 'PATCH'
    assert request.url.path == f'/channels/{channel_name}/messages/s1'
    assert request.url.query_params['key'] == 'value'
    body = msgpack.unpackb(request.body)
    assert body['action'] == 6
    assert body['serial'] == 's1'
    assert body['version'] == {'description': 'streamed'}
    assert body['patches'] == {'data': [{'op': 'append', 'path': '/text', 'data': 'lo'}],
                               'extras': {'headers': [{'op': 'set', 'key': 'stage', 'value': 'done'}]}}
    assert 'data' not in body


async def test_patch_message_without_a_serial_fails_before_any_request():
    captured = []
    mock_http = MockHttpClient(on_connection_attempt=lambda conn: conn.respond_with_success(),
                               on_request=captured.append)
    channel = rest_client(mock_http).channels.get(f'test-patch-{random_id()}')

    with pytest.raises(AblyException) as e:
        await channel.patch_message(Message(serial='', patches=MessagePatches(
            data=[MessagePatchDataOperation('append', path='/text', data='x')])))

    assert e.value.code == 40003
    assert captured == []


async def test_realtime_patch_message_sends_a_message_with_the_patch():
    channel_name = f'test-patch-{random_id()}'
    captured = []
    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: conn.respond_with_success(
        connected_message('connection-id', connectionKey='connection-key')))

    def on_message_from_client(msg):
        captured.append(msg)
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg.get('action') == ProtocolMessageAction.MESSAGE:
            mock_ws.send_to_client({'action': 1, 'msgSerial': msg['msgSerial'], 'count': 1,
                                    'res': [{'serials': ['v2']}]})

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await channel.attach()

    result = await channel.patch_message(Message(serial='s1', patches=MessagePatches(
        data=[MessagePatchDataOperation('set', path='/done', data=True)])))

    assert result.version_serial == 'v2'
    sent = [msg for msg in captured if msg.get('action') == ProtocolMessageAction.MESSAGE][-1]
    message = sent['messages'][0]
    assert (message['action'], message['serial']) == (6, 's1')
    assert message['patches'] == {'data': [{'op': 'set', 'path': '/done', 'data': 'true', 'encoding': 'json'}]}
    await client.close()


def test_a_received_patch_round_trips_through_its_wire_form():
    """What a publisher sends is what a subscriber decodes and applies."""
    wire = Message(serial='s1', action=MessageAction.MESSAGE_PATCH,
                   patches=MessagePatches(data=[MessagePatchDataOperation('append', path='/text', data='lo'),
                                                MessagePatchDataOperation('set', path='/n', data=2)])).as_dict()
    received = Message.from_encoded(json.loads(json.dumps({**wire, 'version': {'serial': 'v2'}})))

    assert isinstance(received.patches, MessagePatches)
    assert decode(data='{"text":"Hel"}', encoding='json').apply_patch(received).data == {'text': 'Hello', 'n': 2}
