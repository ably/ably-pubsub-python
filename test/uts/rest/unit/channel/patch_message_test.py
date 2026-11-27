"""Derived from uts/rest/unit/channel/patch_message.md in ably/specification.

Spec points: RSL15, RSL15a, RSL15b, RSL15b1, RSL15c, RSL15e, RSL15g, MPD3, MPD3a, MPD3b, MPD3c, MPD3d

The specification's `extras: { "headers": [...] }` is `MessagePatchExtras(headers=[...])`.
"""

import json
import uuid

import msgpack
import pytest

from ably.pubsub.types.message import Message, MessageAction
from ably.pubsub.types.messagepatch import (
    MessagePatchDataOperation,
    MessagePatches,
    MessagePatchExtras,
    MessagePatchHeaderOperation,
)
from ably.pubsub.types.operations import UpdateDeleteResult
from ably.pubsub.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient


def random_id():
    return uuid.uuid4().hex[:8]


def capture_and_respond(captured_requests):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, {'versionSerial': 'vs1'})

    return on_request


def patching_channel(channel_name, captured_requests, **kwargs):
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, **kwargs)
    return client.channels.get(channel_name)


# UTS: rest/unit/RSL15b1/patch-sends-patch-action-0
async def test_rsl15b1_patch_sends_patch_action():
    channel_name = f'test-RSL15-patch-{random_id()}'
    captured_requests = []
    channel = patching_channel(channel_name, captured_requests, use_binary_protocol=False)

    result = await channel.patch_message(
        Message(
            serial='msg-serial-1',
            patches=MessagePatches(
                data=[
                    MessagePatchDataOperation(op='append', path='/content/0/text', data=' more text'),
                ],
                extras=MessagePatchExtras(headers=[
                    MessagePatchHeaderOperation(op='set', key='status', value='complete'),
                    MessagePatchHeaderOperation(op='remove', key='draft'),
                ]),
            ),
        ),
    )

    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request.method == 'PATCH'
    assert request.url.path == f'/channels/{channel_name}/messages/msg-serial-1'

    body = json.loads(request.body)
    assert body['action'] == 6  # MESSAGE_PATCH numeric value
    assert body['serial'] == 'msg-serial-1'
    assert body['patches']['data'] == [
        {'op': 'append', 'path': '/content/0/text', 'data': ' more text'},
    ]
    assert body['patches']['extras']['headers'] == [
        {'op': 'set', 'key': 'status', 'value': 'complete'},
        {'op': 'remove', 'key': 'draft'},
    ]

    assert isinstance(result, UpdateDeleteResult)
    assert result.version_serial == 'vs1'


# UTS: rest/unit/RSL15g/patch-values-encoded-json-0
async def test_rsl15g_patch_values_encoded_json():
    channel_name = f'test-RSL15g-json-{random_id()}'
    captured_requests = []
    channel = patching_channel(channel_name, captured_requests, use_binary_protocol=False)

    await channel.patch_message(
        Message(
            serial='s1',
            patches=MessagePatches(data=[
                MessagePatchDataOperation(op='append', path='/text', data='lo'),
                MessagePatchDataOperation(op='set', path='/bin', data=bytes([0x01, 0x02])),
                MessagePatchDataOperation(op='set', path='/obj', data={'b': 1}),
                MessagePatchDataOperation(op='set', path='/list/-', data=[1, 2]),
                MessagePatchDataOperation(op='set', path='/count', data=42),
                MessagePatchDataOperation(op='set', path='/done', data=True),
                MessagePatchDataOperation(op='set', path='/cleared', data=None),
                MessagePatchDataOperation(op='remove', path='/old'),
            ]),
        ),
    )

    ops = json.loads(captured_requests[0].body)['patches']['data']
    assert len(ops) == 8

    # MPD3a — string unchanged
    assert ops[0] == {'op': 'append', 'path': '/text', 'data': 'lo'}

    # MPD3b — binary as Base64
    assert ops[1]['data'] == 'AQI='
    assert ops[1]['encoding'] == 'base64'

    # MPD3c — every other JSON value as JSON text
    assert isinstance(ops[2]['data'], str)
    assert json.loads(ops[2]['data']) == {'b': 1}
    assert ops[2]['encoding'] == 'json'
    assert json.loads(ops[3]['data']) == [1, 2]
    assert ops[3]['encoding'] == 'json'
    assert ops[4]['data'] == '42'
    assert ops[4]['encoding'] == 'json'
    assert ops[5]['data'] == 'true'
    assert ops[5]['encoding'] == 'json'
    assert ops[6]['data'] == 'null'
    assert ops[6]['encoding'] == 'json'

    # MPD3d — no data, no encoding
    assert ops[7] == {'op': 'remove', 'path': '/old'}


# UTS: rest/unit/RSL15g/patch-values-encoded-msgpack-1
async def test_rsl15g_patch_values_encoded_msgpack():
    channel_name = f'test-RSL15g-msgpack-{random_id()}'
    captured_requests = []
    channel = patching_channel(channel_name, captured_requests, use_binary_protocol=True)

    await channel.patch_message(
        Message(
            serial='s1',
            patches=MessagePatches(data=[
                MessagePatchDataOperation(op='append', path='/text', data='lo'),
                MessagePatchDataOperation(op='set', path='/bin', data=bytes([0x01, 0x02])),
                MessagePatchDataOperation(op='set', path='/count', data=42),
            ]),
        ),
    )

    body = msgpack.unpackb(captured_requests[0].body)
    assert body['action'] == 6
    ops = body['patches']['data']

    assert ops[0]['data'] == 'lo'
    assert 'encoding' not in ops[0] or ops[0]['encoding'] is None

    # Binary transmitted directly, no Base64
    assert ops[1]['data'] == bytes([0x01, 0x02])
    assert 'encoding' not in ops[1] or ops[1]['encoding'] is None

    # JSON value as a MessagePack string
    assert isinstance(ops[2]['data'], str)
    assert ops[2]['data'] == '42'
    assert ops[2]['encoding'] == 'json'


# UTS: rest/unit/RSL15c/patch-no-mutate-message-0
async def test_rsl15c_patch_no_mutate_message():
    channel_name = f'test-RSL15c-patch-{random_id()}'
    channel = patching_channel(channel_name, [], use_binary_protocol=False)

    object_op = MessagePatchDataOperation(op='set', path='/obj', data={'b': 1})
    binary_op = MessagePatchDataOperation(op='set', path='/bin', data=bytes([0x01, 0x02]))
    message = Message(
        serial='s1',
        patches=MessagePatches(data=[object_op, binary_op]),
    )

    await channel.patch_message(message)

    assert message.action is None or message.action == MessageAction.MESSAGE_CREATE
    assert len(message.patches.data) == 2
    assert message.patches.data[0].data == {'b': 1}
    assert message.patches.data[0].encoding is None or message.patches.data[0].encoding == ''
    assert message.patches.data[1].data == bytes([0x01, 0x02])
    assert message.patches.data[1].encoding is None or message.patches.data[1].encoding == ''


# UTS: rest/unit/RSL15a/patch-serial-required-0
async def test_rsl15a_patch_serial_required():
    captured_requests = []
    channel = patching_channel(f'test-RSL15a-patch-{random_id()}', captured_requests)

    with pytest.raises(AblyException) as excinfo:
        await channel.patch_message(Message(
            patches=MessagePatches(data=[MessagePatchDataOperation(op='append', path='/text', data='x')]),
        ))
    assert excinfo.value.code == 40003

    assert len(captured_requests) == 0
