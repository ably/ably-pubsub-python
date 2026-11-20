"""Derived from uts/realtime/unit/channels/channel_patch_message.md in ably/specification.

Spec points: RTL32, RTL32b, RTL32b1, RTL32d, RTL32f, MPD3, MPD4, MPD4a, TM2v, TM9

A patch is a MESSAGE protocol message and so requires an ACK; the mock answers each one, as the
specification's own handlers do, with the ACK's `res` wrapped in an array, one entry per
ProtocolMessage. The two publishing tests deliberately do not attach the channel, and their mock does
not answer ATTACH: like a publish, a patch is sent on an INITIALIZED channel.

The specification's `extras: { "headers": [...] }` is `MessagePatchExtras(headers=[...])`, and
`Message.applyPatch(message, patch)` is the instance method `Message.apply_patch`, called through the class.
"""

import json
import uuid

from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.transport.websockettransport import ProtocolMessageAction
from ably.pubsub.types.channelstate import ChannelState
from ably.pubsub.types.message import Message, MessageAction
from ably.pubsub.types.messagepatch import (
    MessagePatchDataOperation,
    MessagePatches,
    MessagePatchExtras,
    MessagePatchHeaderOperation,
)
from ably.pubsub.types.operations import UpdateDeleteResult
from test.uts.helpers.client import await_connection_state, poll_until, realtime_client
from test.uts.helpers.mock_websocket import (
    MockWebSocket,
    ack,
    attached_message,
    connected_message,
    message_protocol_message,
)

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')


def random_id():
    return uuid.uuid4().hex[:8]


def acking_mock(captured_messages):
    """A mock which connects and ACKs each MESSAGE, and does not answer ATTACH."""
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        captured_messages.append(msg)
        if msg.get('action') == ProtocolMessageAction.MESSAGE:
            mock_ws.send_to_client(ack(msg, serials=['version-serial-1']))

    mock_ws.on_message_from_client = on_message_from_client
    return mock_ws


def attaching_mock(channel_name):
    """A mock which connects and attaches `channel_name`."""
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    return mock_ws


def last_message_pm(captured_messages):
    message_pm = None
    for pm in captured_messages:
        if pm.get('action') == ProtocolMessageAction.MESSAGE:
            message_pm = pm
    return message_pm


# UTS: realtime/unit/RTL32b1/patch-message-action-0
async def test_rtl32b1_patch_message_action():
    channel_name = f'test-RTL32-patch-{random_id()}'
    captured_messages = []
    mock_ws = acking_mock(captured_messages)
    client = realtime_client(mock_ws, use_binary_protocol=False)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    result = await channel.patch_message(
        Message(
            serial='msg-serial-1',
            patches=MessagePatches(
                data=[MessagePatchDataOperation(op='append', path='/text', data='lo')],
                extras=MessagePatchExtras(headers=[
                    MessagePatchHeaderOperation(op='set', key='status', value='complete'),
                ]),
            ),
        ),
    )

    message_pm = last_message_pm(captured_messages)
    assert message_pm is not None

    assert message_pm['channel'] == channel_name
    assert len(message_pm['messages']) == 1

    msg = message_pm['messages'][0]
    assert msg['action'] == 6  # MESSAGE_PATCH numeric value
    assert msg['serial'] == 'msg-serial-1'
    assert msg['patches']['data'] == [{'op': 'append', 'path': '/text', 'data': 'lo'}]
    assert msg['patches']['extras']['headers'] == [{'op': 'set', 'key': 'status', 'value': 'complete'}]

    assert isinstance(result, UpdateDeleteResult)
    assert result.version_serial == 'version-serial-1'

    # The patch was sent without attaching the channel
    assert not any(pm.get('action') == ProtocolMessageAction.ATTACH for pm in captured_messages)
    assert channel.state == ChannelState.INITIALIZED


# UTS: realtime/unit/RTL32f/patch-values-encoded-0
async def test_rtl32f_patch_values_encoded():
    channel_name = f'test-RTL32f-{random_id()}'
    captured_messages = []
    mock_ws = acking_mock(captured_messages)
    client = realtime_client(mock_ws, use_binary_protocol=False)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await channel.patch_message(
        Message(
            serial='s1',
            patches=MessagePatches(data=[
                MessagePatchDataOperation(op='set', path='/obj', data={'b': 1}),
                MessagePatchDataOperation(op='set', path='/bin', data=bytes([0x01, 0x02])),
                MessagePatchDataOperation(op='set', path='/done', data=True),
            ]),
        ),
    )

    message_pm = last_message_pm(captured_messages)

    ops = message_pm['messages'][0]['patches']['data']
    assert json.loads(ops[0]['data']) == {'b': 1}
    assert ops[0]['encoding'] == 'json'
    assert ops[1]['data'] == 'AQI='
    assert ops[1]['encoding'] == 'base64'
    assert ops[2]['data'] == 'true'
    assert ops[2]['encoding'] == 'json'


# UTS: realtime/unit/MPD4/patch-received-decoded-0
async def test_mpd4_patch_received_decoded():
    channel_name = f'test-MPD4-{random_id()}'
    mock_ws = attaching_mock(channel_name)
    client = realtime_client(mock_ws, use_binary_protocol=False)
    channel = client.channels.get(channel_name)
    received = []

    def on_message(msg):
        received.append(msg)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await channel.subscribe(on_message)

    mock_ws.send_to_client(message_protocol_message(
        channel_name,
        [{
            'action': 6,
            'serial': 'msg-serial-1',
            'version': {'serial': 'version-serial-2', 'timestamp': 1700000002000},
            'patches': {
                'data': [
                    {'op': 'set', 'path': '/a', 'data': '{"b":1}', 'encoding': 'json'},
                    {'op': 'set', 'path': '/c', 'data': 'AQI=', 'encoding': 'base64'},
                    {'op': 'append', 'path': '/d', 'data': 'text'},
                ],
                'extras': {'headers': [{'op': 'set', 'key': 'status', 'value': 'complete'}]},
            },
        }],
        id='conn:0',
        timestamp=1700000002000,
    ))
    await poll_until(lambda: len(received) == 1, description='the patch is delivered')

    msg = received[0]
    assert msg.action == MessageAction.MESSAGE_PATCH
    assert msg.serial == 'msg-serial-1'
    assert msg.version.serial == 'version-serial-2'

    ops = msg.patches.data
    assert len(ops) == 3

    # MPD4a — JSON value stays as JSON text
    assert ops[0].op == 'set'
    assert ops[0].path == '/a'
    assert ops[0].data == '{"b":1}'
    assert ops[0].encoding == 'json'

    # MPD4 — Base64 is decoded to binary, leaving no encoding
    assert ops[1].data == bytes([0x01, 0x02])
    assert ops[1].encoding is None or ops[1].encoding == ''

    assert ops[2].data == 'text'
    assert ops[2].encoding is None or ops[2].encoding == ''

    assert msg.patches.extras.headers[0].op == 'set'
    assert msg.patches.extras.headers[0].key == 'status'
    assert msg.patches.extras.headers[0].value == 'complete'


# UTS: realtime/unit/TM9/subscriber-applies-patch-0
async def test_tm9_subscriber_applies_patch():
    channel_name = f'test-TM9-subscriber-{random_id()}'
    mock_ws = attaching_mock(channel_name)
    client = realtime_client(mock_ws, use_binary_protocol=False)
    channel = client.channels.get(channel_name)

    patched_message = None
    patches_applied = 0

    def on_message(msg):
        nonlocal patched_message, patches_applied
        if msg.action == MessageAction.MESSAGE_CREATE:
            patched_message = msg
        elif msg.action == MessageAction.MESSAGE_PATCH:
            patched_message = Message.apply_patch(patched_message, msg)
            patches_applied += 1

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await channel.subscribe(on_message)

    def send_message(msg_serial, wire_message):
        mock_ws.send_to_client(message_protocol_message(
            channel_name,
            [wire_message],
            id='conn:' + msg_serial,
            timestamp=1700000000000,
        ))

    send_message('0', {
        'action': 0,
        'serial': 'msg-serial-1',
        'clientId': 'author',
        'name': 'reply',
        'data': '{"text":"Hel","toolCalls":[]}',
        'encoding': 'json',
    })
    send_message('1', {
        'action': 6,
        'serial': 'msg-serial-1',
        'clientId': 'patcher',
        'version': {'serial': 'version-serial-2', 'timestamp': 1700000001000},
        'patches': {'data': [{'op': 'append', 'path': '/text', 'data': 'lo'}]},
    })
    send_message('2', {
        'action': 6,
        'serial': 'msg-serial-1',
        'version': {'serial': 'version-serial-3', 'timestamp': 1700000002000},
        'patches': {
            'data': [{'op': 'set', 'path': '/toolCalls/-', 'data': '{"name":"search"}', 'encoding': 'json'}],
            'extras': {'headers': [{'op': 'set', 'key': 'status', 'value': 'complete'}]},
        },
    })
    await poll_until(lambda: patches_applied == 2, description='both patches are applied')

    assert patched_message.action == MessageAction.MESSAGE_UPDATE
    assert patched_message.serial == 'msg-serial-1'
    assert patched_message.version.serial == 'version-serial-3'
    assert patched_message.data == {'text': 'Hello', 'toolCalls': [{'name': 'search'}]}
    assert patched_message.extras['headers'] == {'status': 'complete'}

    # Kept from the MESSAGE_CREATE, not taken from the patches
    assert patched_message.client_id == 'author'
    assert patched_message.name == 'reply'
