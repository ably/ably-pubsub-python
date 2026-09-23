"""Derived from uts/realtime/unit/channels/channel_annotations.md in ably/specification.

Spec points: RTL26, RTAN1, RTAN1a, RTAN1b, RTAN1c, RTAN1d, RTAN2, RTAN2a, RTAN3, RTAN3a,
RTAN4, RTAN4a, RTAN4b, RTAN4c, RTAN4d, RTAN4e, RTAN4e1, RTAN5, RTAN5a

An annotation is an `ack_required` protocol message, so a publish or delete is awaited
until the server answers it; the mocks below ACK each one, as the specification's own
handlers do.

The specification's RTAN3a section carries no Test ID and so gets no test, as the
suite derives one test per Test ID.

`RealtimeChannelOptions(attachOnSubscribe: false)` does not exist in ably-python and
`annotations.subscribe` always attaches, so the tests that use it attach first instead;
see [deviations-channels-messages.md](../../../deviations-channels-messages.md).
"""

import asyncio
import json
import uuid

import pytest

from ably.realtime.annotations import RealtimeAnnotations
from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.annotation import Annotation, AnnotationAction
from ably.types.channelstate import ChannelState
from ably.types.flags import Flag
from ably.util.exceptions import AblyException
from test.uts.helpers.client import await_connection_state, poll_until, realtime_client
from test.uts.helpers.clock import settle
from test.uts.helpers.mock_websocket import MockWebSocket, attached_message, connected_message

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')

ACK_ACTION = 1
NACK_ACTION = 2

PUBLISH_FLAGS = Flag.PUBLISH | Flag.ANNOTATION_PUBLISH
SUBSCRIBE_FLAGS = Flag.PUBLISH | Flag.ANNOTATION_PUBLISH | Flag.ANNOTATION_SUBSCRIBE

# How long a call the specification expects to settle is given before a test calls it hung
OPERATION_TIMEOUT = 1.0


def random_id():
    return uuid.uuid4().hex[:8]


def ack(msg):
    return {'action': ACK_ACTION, 'msgSerial': msg['msgSerial'], 'count': 1}


def nack(msg, code, message):
    return {
        'action': NACK_ACTION,
        'msgSerial': msg['msgSerial'],
        'count': 1,
        'error': {'code': code, 'statusCode': code // 100, 'message': message},
    }


def annotation_protocol_message(channel_name, annotations, **fields):
    """An ANNOTATION protocol message carrying `annotations` on `channel_name`."""
    return {
        'action': int(ProtocolMessageAction.ANNOTATION),
        'channel': channel_name,
        'annotations': annotations,
        **fields,
    }


def annotating_mock(channel_name, flags=PUBLISH_FLAGS, captured_messages=None, answer=ack):
    """A mock which connects, attaches `channel_name` and answers each ANNOTATION.

    `flags` are the channel modes the ATTACHED confirms, and `answer` builds the ACK
    or NACK the mock replies to an annotation with.
    """
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if captured_messages is not None:
            captured_messages.append(msg)
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name, flags=int(flags)))
        elif msg.get('action') == ProtocolMessageAction.ANNOTATION:
            mock_ws.send_to_client(answer(msg))

    mock_ws.on_message_from_client = on_message_from_client
    return mock_ws


async def connected_client(mock_ws, **kwargs):
    """A client connected over `mock_ws`."""
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


async def attached_channel(mock_ws, channel_name, **kwargs):
    """A channel attached over `mock_ws`, which most of these tests start from."""
    client = await connected_client(mock_ws, **kwargs)
    channel = client.channels.get(channel_name)
    await channel.attach()
    return channel


def recorder(received):
    """An annotation listener appending each annotation it is given to `received`."""
    def record(annotation):
        received.append(annotation)
    return record


def sent_annotations(captured_messages):
    """The ANNOTATION protocol messages among those the client sent."""
    return [msg for msg in captured_messages if msg.get('action') == ProtocolMessageAction.ANNOTATION]


# UTS: realtime/unit/RTL26/annotations-attribute-type-0
async def test_rtl26_annotations_attribute_type():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    client = realtime_client(mock_ws)
    channel = client.channels.get('test-RTL26')

    assert isinstance(channel.annotations, RealtimeAnnotations)


# UTS: realtime/unit/RTAN1a/publish-sends-annotation-0
async def test_rtan1a_publish_sends_annotation():
    channel_name = f'test-RTAN1-publish-{random_id()}'
    captured_messages = []

    mock_ws = annotating_mock(channel_name, captured_messages=captured_messages)
    channel = await attached_channel(mock_ws, channel_name)

    await channel.annotations.publish(
        'msg-serial-1', Annotation(type='com.example.reaction', name='like'))

    annotation_pms = sent_annotations(captured_messages)
    assert len(annotation_pms) == 1

    annotation_pm = annotation_pms[0]
    assert annotation_pm['channel'] == channel_name
    assert len(annotation_pm['annotations']) == 1

    ann = annotation_pm['annotations'][0]
    assert ann['action'] == AnnotationAction.ANNOTATION_CREATE
    assert ann['messageSerial'] == 'msg-serial-1'
    assert ann['type'] == 'com.example.reaction'
    assert ann['name'] == 'like'


# UTS: realtime/unit/RTAN1a/validates-type-required-1
async def test_rtan1a_validates_type_required():
    channel_name = f'test-RTAN1a-validate-{random_id()}'

    mock_ws = annotating_mock(channel_name)
    channel = await attached_channel(mock_ws, channel_name)

    # RSAN1a3 does not mandate a code for the missing type
    with pytest.raises(AblyException):
        await channel.annotations.publish('msg-serial-1', Annotation(name='like'))


# UTS: realtime/unit/RTAN1a/encodes-data-json-2
async def test_rtan1a_encodes_data_json():
    channel_name = f'test-RTAN1a-encode-{random_id()}'
    captured_messages = []
    data = {'key': 'value', 'nested': {'a': 1}}

    mock_ws = annotating_mock(channel_name, captured_messages=captured_messages)
    channel = await attached_channel(mock_ws, channel_name)

    await channel.annotations.publish(
        'msg-serial-1', Annotation(type='com.example.data', data=data))

    ann = sent_annotations(captured_messages)[0]['annotations'][0]
    assert isinstance(ann['data'], str)
    assert ann['encoding'] == 'json'
    assert json.loads(ann['data']) == data


# UTS: realtime/unit/RTAN1b/publish-channel-state-0
async def test_rtan1b_publish_channel_state():
    channel_name = f'test-RTAN1b-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client({
                'action': int(ProtocolMessageAction.ERROR),
                'channel': channel_name,
                'error': {'code': 40160, 'statusCode': 401, 'message': 'Not permitted'},
            })

    mock_ws.on_message_from_client = on_message_from_client

    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    with pytest.raises(AblyException):
        await channel.attach()

    assert channel.state == ChannelState.FAILED

    with pytest.raises(AblyException):
        await channel.annotations.publish(
            'msg-serial-1', Annotation(type='com.example.reaction', name='like'))


# UTS: realtime/unit/RTAN1d/publish-ack-nack-0
async def test_rtan1d_publish_ack_nack():
    # ACK case: the publish resolves
    ack_channel_name = f'test-RTAN1d-ack-{random_id()}'
    ack_mock = annotating_mock(ack_channel_name)
    ack_channel = await attached_channel(ack_mock, ack_channel_name)

    await ack_channel.annotations.publish(
        'msg-serial-1', Annotation(type='com.example.reaction', name='like'))

    # NACK case: the publish rejects with the error the NACK carried
    nack_channel_name = f'test-RTAN1d-nack-{random_id()}'
    nack_mock = annotating_mock(
        nack_channel_name, answer=lambda msg: nack(msg, 40160, 'Not permitted'))
    nack_channel = await attached_channel(nack_mock, nack_channel_name)

    with pytest.raises(AblyException) as excinfo:
        await nack_channel.annotations.publish(
            'msg-serial-1', Annotation(type='com.example.reaction', name='like'))

    assert excinfo.value.code == 40160


# UTS: realtime/unit/RTAN2a/delete-sends-annotation-0
async def test_rtan2a_delete_sends_annotation():
    channel_name = f'test-RTAN2-delete-{random_id()}'
    captured_messages = []

    mock_ws = annotating_mock(channel_name, captured_messages=captured_messages)
    channel = await attached_channel(mock_ws, channel_name)

    await channel.annotations.delete(
        'msg-serial-1', Annotation(type='com.example.reaction', name='like'))

    ann = sent_annotations(captured_messages)[0]['annotations'][0]
    assert ann['action'] == AnnotationAction.ANNOTATION_DELETE
    assert ann['messageSerial'] == 'msg-serial-1'
    assert ann['type'] == 'com.example.reaction'
    assert ann['name'] == 'like'


# UTS: realtime/unit/RTAN4a/subscribe-delivers-annotations-0
async def test_rtan4a_subscribe_delivers_annotations():
    channel_name = f'test-RTAN4-subscribe-{random_id()}'
    received_annotations = []

    mock_ws = annotating_mock(channel_name, flags=SUBSCRIBE_FLAGS)
    channel = await attached_channel(mock_ws, channel_name)

    await channel.annotations.subscribe(recorder(received_annotations))

    mock_ws.send_to_client(annotation_protocol_message(channel_name, [
        {
            'id': 'ann-1',
            'action': 0,
            'type': 'com.example.reaction',
            'name': 'like',
            'clientId': 'user-1',
            'serial': 'ann-serial-1',
            'messageSerial': 'msg-serial-1',
            'timestamp': 1700000000000,
        },
        {
            'id': 'ann-2',
            'action': 0,
            'type': 'com.example.reaction',
            'name': 'heart',
            'clientId': 'user-2',
            'serial': 'ann-serial-2',
            'messageSerial': 'msg-serial-1',
            'timestamp': 1700000001000,
        },
    ]))
    await poll_until(lambda: len(received_annotations) == 2,
                     description='both annotations are delivered')

    ann1 = received_annotations[0]
    assert isinstance(ann1, Annotation)
    assert ann1.id == 'ann-1'
    assert ann1.action == AnnotationAction.ANNOTATION_CREATE
    assert ann1.type == 'com.example.reaction'
    assert ann1.name == 'like'
    assert ann1.client_id == 'user-1'
    assert ann1.serial == 'ann-serial-1'
    assert ann1.message_serial == 'msg-serial-1'
    assert ann1.timestamp == 1700000000000

    ann2 = received_annotations[1]
    assert ann2.name == 'heart'
    assert ann2.client_id == 'user-2'


# UTS: realtime/unit/RTAN4c/subscribe-type-filter-0
async def test_rtan4c_subscribe_type_filter():
    channel_name = f'test-RTAN4c-filter-{random_id()}'
    reaction_annotations = []

    mock_ws = annotating_mock(channel_name, flags=SUBSCRIBE_FLAGS)
    channel = await attached_channel(mock_ws, channel_name)

    await channel.annotations.subscribe('com.example.reaction', recorder(reaction_annotations))

    mock_ws.send_to_client(annotation_protocol_message(channel_name, [
        {
            'action': 0,
            'type': 'com.example.reaction',
            'name': 'like',
            'messageSerial': 'msg-serial-1',
            'serial': 'ann-serial-1',
            'timestamp': 1700000000000,
        },
        {
            'action': 0,
            'type': 'com.example.comment',
            'name': 'text',
            'messageSerial': 'msg-serial-1',
            'serial': 'ann-serial-2',
            'timestamp': 1700000001000,
        },
        {
            'action': 0,
            'type': 'com.example.reaction',
            'name': 'heart',
            'messageSerial': 'msg-serial-1',
            'serial': 'ann-serial-3',
            'timestamp': 1700000002000,
        },
    ]))
    await poll_until(lambda: len(reaction_annotations) == 2,
                     description='both reaction annotations are delivered')
    await settle()

    assert len(reaction_annotations) == 2
    assert reaction_annotations[0].name == 'like'
    assert reaction_annotations[1].name == 'heart'


# UTS: realtime/unit/RTAN4d/subscribe-implicit-attach-0
async def test_rtan4d_subscribe_implicit_attach():
    channel_name = f'test-RTAN4d-attach-{random_id()}'

    mock_ws = annotating_mock(channel_name, flags=SUBSCRIBE_FLAGS)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    assert channel.state == ChannelState.INITIALIZED

    await channel.annotations.subscribe(lambda annotation: None)

    assert channel.state == ChannelState.ATTACHED


# UTS: realtime/unit/RTAN4e/subscribe-warns-no-mode-0
async def test_rtan4e_subscribe_warns_no_mode(caplog):
    channel_name = f'test-RTAN4e-warn-{random_id()}'

    # The ATTACHED grants PUBLISH alone, leaving ANNOTATION_SUBSCRIBE out
    mock_ws = annotating_mock(channel_name, flags=Flag.PUBLISH)
    channel = await attached_channel(mock_ws, channel_name)

    with caplog.at_level('WARNING', logger='ably.realtime.annotations'):
        await channel.annotations.subscribe(lambda annotation: None)

    warnings = [record.getMessage() for record in caplog.records if record.levelname == 'WARNING']
    assert any('ANNOTATION_SUBSCRIBE' in message for message in warnings)


# UTS: realtime/unit/RTAN4e1/no-warn-unattached-0
async def test_rtan4e1_no_warn_unattached(caplog):
    # The specification leaves the channel unattached with
    # `RealtimeChannelOptions(attachOnSubscribe: false)`. `annotations.subscribe` always
    # attaches in ably-python, so the subscribe is run as a task against a server which
    # never confirms the attach; the channel stays unattached exactly as the
    # specification requires, and the mode check must not run.
    channel_name = f'test-RTAN4e1-{random_id()}'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    assert channel.state == ChannelState.INITIALIZED

    with caplog.at_level('WARNING', logger='ably.realtime.annotations'):
        subscribing = asyncio.ensure_future(channel.annotations.subscribe(lambda annotation: None))
        await poll_until(lambda: channel.state == ChannelState.ATTACHING,
                         description='the implicit attach is in flight')
        await settle()

    assert channel.state != ChannelState.ATTACHED

    warnings = [record.getMessage() for record in caplog.records if record.levelname == 'WARNING']
    assert not any('ANNOTATION_SUBSCRIBE' in message for message in warnings)

    subscribing.cancel()


# UTS: realtime/unit/RTAN5a/unsubscribe-removes-listeners-0
async def test_rtan5a_unsubscribe_removes_listeners():
    channel_name = f'test-RTAN5-unsub-{random_id()}'
    received_annotations = []

    mock_ws = annotating_mock(channel_name, flags=SUBSCRIBE_FLAGS)
    channel = await attached_channel(mock_ws, channel_name)

    listener = recorder(received_annotations)
    await channel.annotations.subscribe(listener)

    mock_ws.send_to_client(annotation_protocol_message(channel_name, [{
        'action': 0,
        'type': 'com.example.reaction',
        'name': 'like',
        'messageSerial': 'msg-serial-1',
        'serial': 'ann-serial-1',
        'timestamp': 1700000000000,
    }]))
    await poll_until(lambda: len(received_annotations) == 1,
                     description='the first annotation is delivered')

    channel.annotations.unsubscribe(listener)

    mock_ws.send_to_client(annotation_protocol_message(channel_name, [{
        'action': 0,
        'type': 'com.example.reaction',
        'name': 'heart',
        'messageSerial': 'msg-serial-1',
        'serial': 'ann-serial-2',
        'timestamp': 1700000001000,
    }]))
    await settle()

    assert len(received_annotations) == 1
    assert received_annotations[0].name == 'like'


# UTS: realtime/unit/RTAN5a/unsubscribe-type-filter-1
async def test_rtan5a_unsubscribe_type_filter():
    channel_name = f'test-RTAN5a-typed-{random_id()}'
    reaction_received = []
    comment_received = []

    mock_ws = annotating_mock(channel_name, flags=SUBSCRIBE_FLAGS)
    channel = await attached_channel(mock_ws, channel_name)

    reaction_listener = recorder(reaction_received)
    comment_listener = recorder(comment_received)

    await channel.annotations.subscribe('com.example.reaction', reaction_listener)
    await channel.annotations.subscribe('com.example.comment', comment_listener)

    channel.annotations.unsubscribe('com.example.reaction', reaction_listener)

    mock_ws.send_to_client(annotation_protocol_message(channel_name, [
        {
            'action': 0,
            'type': 'com.example.reaction',
            'name': 'like',
            'messageSerial': 'msg-serial-1',
            'serial': 'ann-serial-1',
            'timestamp': 1700000000000,
        },
        {
            'action': 0,
            'type': 'com.example.comment',
            'name': 'text',
            'messageSerial': 'msg-serial-1',
            'serial': 'ann-serial-2',
            'timestamp': 1700000001000,
        },
    ]))
    await poll_until(lambda: len(comment_received) == 1,
                     description='the comment annotation is delivered')
    await settle()

    assert len(reaction_received) == 0
    assert len(comment_received) == 1
    assert comment_received[0].type == 'com.example.comment'
