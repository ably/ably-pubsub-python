"""Derived from uts/realtime/unit/channels/channel_update_delete_message.md in ably/specification.

Spec points: RTL32, RTL32a, RTL32b, RTL32b1, RTL32b2, RTL32c, RTL32d, RTL32e

An update, delete or append is a MESSAGE protocol message and so requires an ACK; the
mock answers each one, as the specification's own handlers do. The specification writes
the ACK's `res` as a single object, while the protocol carries one entry per
ProtocolMessage, so the ACKs below wrap it in an array.
"""

import uuid

import pytest

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.message import Message, MessageAction
from ably.types.operations import MessageOperation, UpdateDeleteResult
from ably.util.exceptions import AblyException
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.mock_websocket import MockWebSocket, attached_message, connected_message

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')

ACK_ACTION = 1
NACK_ACTION = 2


def random_id():
    return uuid.uuid4().hex[:8]


def ack(msg, serials=('version-serial-1',)):
    return {
        'action': ACK_ACTION,
        'msgSerial': msg['msgSerial'],
        'count': 1,
        'res': [{'serials': list(serials)}],
    }


def nack(msg, code, message):
    return {
        'action': NACK_ACTION,
        'msgSerial': msg['msgSerial'],
        'count': 1,
        'error': {'code': code, 'statusCode': code // 100, 'message': message},
    }


def updating_mock(channel_name, captured_messages=None, answer=ack, serials=('version-serial-1',)):
    """A mock which connects, attaches `channel_name` and answers each MESSAGE.

    `answer` builds the ACK or NACK the mock replies with, so that a test can pin
    the version serial the ACK carries or reject the operation outright.
    """
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if captured_messages is not None:
            captured_messages.append(msg)
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg.get('action') == ProtocolMessageAction.MESSAGE:
            mock_ws.send_to_client(answer(msg))

    mock_ws.on_message_from_client = on_message_from_client
    return mock_ws


async def attached_channel(mock_ws, channel_name, **kwargs):
    """A channel attached over `mock_ws`, which every test here starts from."""
    client = realtime_client(mock_ws, **kwargs)
    channel = client.channels.get(channel_name)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await channel.attach()
    return channel


def sent_messages(captured_messages):
    """The MESSAGE protocol messages among those the client sent."""
    return [msg for msg in captured_messages if msg.get('action') == ProtocolMessageAction.MESSAGE]


# UTS: realtime/unit/RTL32b/update-message-action-0
async def test_rtl32b_update_message_action():
    channel_name = f'test-RTL32-update-{random_id()}'
    captured_messages = []

    mock_ws = updating_mock(channel_name, captured_messages)
    channel = await attached_channel(mock_ws, channel_name)

    await channel.update_message(Message(serial='msg-serial-1', name='updated', data='new-data'))

    message_pms = sent_messages(captured_messages)
    assert len(message_pms) == 1

    message_pm = message_pms[0]
    assert message_pm['channel'] == channel_name
    assert len(message_pm['messages']) == 1

    msg = message_pm['messages'][0]
    assert msg['action'] == MessageAction.MESSAGE_UPDATE
    assert msg['serial'] == 'msg-serial-1'
    assert msg['name'] == 'updated'
    assert msg['data'] == 'new-data'


# UTS: realtime/unit/RTL32b/delete-message-action-1
async def test_rtl32b_delete_message_action():
    channel_name = f'test-RTL32-delete-{random_id()}'
    captured_messages = []

    mock_ws = updating_mock(channel_name, captured_messages)
    channel = await attached_channel(mock_ws, channel_name)

    await channel.delete_message(Message(serial='msg-serial-1'))

    msg = sent_messages(captured_messages)[0]['messages'][0]
    assert msg['action'] == MessageAction.MESSAGE_DELETE
    assert msg['serial'] == 'msg-serial-1'


# UTS: realtime/unit/RTL32b/append-message-action-2
async def test_rtl32b_append_message_action():
    channel_name = f'test-RTL32-append-{random_id()}'
    captured_messages = []

    mock_ws = updating_mock(channel_name, captured_messages)
    channel = await attached_channel(mock_ws, channel_name)

    await channel.append_message(
        Message(serial='msg-serial-1', data='appended-data'),
        operation=MessageOperation(description='appended content'),
    )

    msg = sent_messages(captured_messages)[0]['messages'][0]
    assert msg['action'] == MessageAction.MESSAGE_APPEND
    assert msg['serial'] == 'msg-serial-1'
    assert msg['data'] == 'appended-data'


# UTS: realtime/unit/RTL32b2/version-from-operation-0
async def test_rtl32b2_version_from_operation():
    channel_name = f'test-RTL32b2-{random_id()}'
    captured_messages = []

    mock_ws = updating_mock(channel_name, captured_messages)
    channel = await attached_channel(mock_ws, channel_name)

    await channel.update_message(
        Message(serial='msg-serial-1', data='v2'),
        operation=MessageOperation(description='edited content', metadata={'reason': 'typo'}),
    )
    await channel.update_message(Message(serial='msg-serial-2', data='v2'))

    message_pms = sent_messages(captured_messages)
    assert len(message_pms) == 2

    msg_with_op = message_pms[0]['messages'][0]
    assert msg_with_op['version']['description'] == 'edited content'
    assert msg_with_op['version']['metadata']['reason'] == 'typo'

    msg_without_op = message_pms[1]['messages'][0]
    assert 'version' not in msg_without_op


# UTS: realtime/unit/RTL32c/no-message-mutation-0
async def test_rtl32c_no_message_mutation():
    channel_name = f'test-RTL32c-{random_id()}'

    mock_ws = updating_mock(channel_name)
    channel = await attached_channel(mock_ws, channel_name)

    original_message = Message(serial='msg-serial-1', name='original', data='original-data')
    await channel.update_message(original_message)

    assert original_message.name == 'original'
    assert original_message.data == 'original-data'
    assert original_message.serial == 'msg-serial-1'
    assert original_message.action is None


# UTS: realtime/unit/RTL32d/ack-returns-result-0
async def test_rtl32d_ack_returns_result():
    channel_name = f'test-RTL32d-{random_id()}'
    version_serial = '01770000000000-000@abcdef:000'

    mock_ws = updating_mock(channel_name, answer=lambda msg: ack(msg, serials=(version_serial,)))
    channel = await attached_channel(mock_ws, channel_name)

    result = await channel.update_message(Message(serial='msg-serial-1', data='updated'))

    assert isinstance(result, UpdateDeleteResult)
    assert result.version_serial == version_serial


# UTS: realtime/unit/RTL32d/nack-returns-error-1
async def test_rtl32d_nack_returns_error():
    channel_name = f'test-RTL32d-nack-{random_id()}'

    mock_ws = updating_mock(
        channel_name, answer=lambda msg: nack(msg, 40160, 'Not permitted'))
    channel = await attached_channel(mock_ws, channel_name)

    with pytest.raises(AblyException) as excinfo:
        await channel.update_message(Message(serial='msg-serial-1', data='updated'))

    assert excinfo.value.code == 40160


# UTS: realtime/unit/RTL32e/params-in-protocol-message-0
async def test_rtl32e_params_in_protocol_message():
    channel_name = f'test-RTL32e-{random_id()}'
    captured_messages = []

    mock_ws = updating_mock(channel_name, captured_messages)
    channel = await attached_channel(mock_ws, channel_name)

    await channel.update_message(
        Message(serial='msg-serial-1', data='v2'),
        params={'key1': 'value1', 'key2': 'value2'},
    )

    message_pm = sent_messages(captured_messages)[0]
    assert message_pm['params']['key1'] == 'value1'
    assert message_pm['params']['key2'] == 'value2'


# UTS: realtime/unit/RTL32a/serial-validation-required-0
async def test_rtl32a_serial_validation_required():
    channel_name = f'test-RTL32a-{random_id()}'

    mock_ws = updating_mock(channel_name)
    channel = await attached_channel(mock_ws, channel_name)

    with pytest.raises(AblyException) as empty_serial:
        await channel.update_message(Message(serial='', data='v2'))
    assert empty_serial.value.code == 40003

    with pytest.raises(AblyException) as missing_serial:
        await channel.delete_message(Message(data='v2'))
    assert missing_serial.value.code == 40003
