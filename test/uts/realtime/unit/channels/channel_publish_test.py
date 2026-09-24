"""Derived from uts/realtime/unit/channels/channel_publish.md in ably/specification.

Spec points: RTL6, RTL6a, RTL6c, RTL6c1, RTL6c2, RTL6c4, RTL6c5, RTL6i, RTL6i1, RTL6i2,
RTL6i3, RTL6j

The RTN7d, RTN7e, RTN19a, RTN19a2 and RTN19b sections of the same specification are
derived in `channel_publish_pending_test.py`, which imports the helpers below.

Two translations recur through the file.

`RealtimeChannel.publish()` resolves on the ACK (RTL6b, `ably/realtime/channel.py:442`),
so where a specification's mock records a MESSAGE without answering it, an ACK is added:
the awaited publish would otherwise never return. Where a specification says in as many
words not to acknowledge a message, it is left unacknowledged and the publish is driven
as a task.

`RealtimeChannel.publish()` takes its arguments positionally; the keyword form the
specifications write, which `RestChannel.publish()` does accept, raises `ValueError` here.
"""

import asyncio
import json
import uuid

import msgpack
import pytest

from ably.realtime.channel import ChannelState
from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.message import Message
from ably.types.operations import PublishResult
from ably.util.exceptions import AblyException
from test.uts.helpers.client import (
    await_channel_state,
    await_connection_state,
    next_connection_state,
    poll_until,
    realtime_client,
)
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.deviations import spec_error
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')


def random_id():
    return uuid.uuid4().hex[:8]


def attached_message(channel_name):
    return {'action': int(ProtocolMessageAction.ATTACHED), 'channel': channel_name}


def ack_message(protocol_message, serials=('serial',)):
    """An ACK for one ProtocolMessage, carrying `serials` as its RTL6j result."""
    return {
        'action': int(ProtocolMessageAction.ACK),
        'msgSerial': protocol_message['msgSerial'],
        'count': 1,
        'res': [{'serials': list(serials)}],
    }


def nack_message(protocol_message, error):
    return {
        'action': int(ProtocolMessageAction.NACK),
        'msgSerial': protocol_message['msgSerial'],
        'count': 1,
        'error': error,
    }


def attaching_server(mock_ws, captured_messages=None, serials=('serial',), ack=True):
    """The handler most of these specifications set on the mock.

    An ATTACH is answered with ATTACHED, and each MESSAGE is recorded in
    `captured_messages` and — unless the specification asks for it to be left
    pending — acknowledged.
    """
    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(msg['channel']))
        elif msg['action'] == ProtocolMessageAction.MESSAGE:
            if captured_messages is not None:
                captured_messages.append(msg)
            if ack:
                mock_ws.send_to_client(ack_message(msg, serials))

    return on_message_from_client


def published(mock_ws):
    """Every MESSAGE ProtocolMessage the client has sent."""
    return [msg for msg in mock_ws.messages_from_client
            if msg['action'] == ProtocolMessageAction.MESSAGE]


async def advance_until_suspended(client, clock, step=2000, limit=80):
    """Moves notional time on until the connection enters SUSPENDED.

    The specifications advance 2000ms up to 15 times, which assumes the
    `connectionStateTtl` client option shortens the suspend timer. ably-python
    discards that option (`ably/types/options.py:64`) and the suspend timer reads
    `Defaults.connection_state_ttl` (120000) directly
    (`ably/realtime/connectionmanager.py:745`), so reaching SUSPENDED takes the
    full two minutes of notional time. See
    [deviations.md](../../../deviations.md).
    """
    for _ in range(limit):
        await clock.advance(step)
        if client.connection.state == ConnectionState.SUSPENDED:
            return
    raise AssertionError(
        f'Connection did not reach SUSPENDED; it was {client.connection.state}')


async def connected_client(mock_ws, **kwargs):
    """A client connected through `mock_ws`, as every test here starts."""
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


# UTS: realtime/unit/RTL6i1/publish-name-and-data-0
async def test_rtl6i1_publish_name_and_data():
    channel_name = f'test-RTL6i1-{random_id()}'
    captured_messages = []
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE))
    mock_ws.on_message_from_client = attaching_server(mock_ws, captured_messages)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()
    await channel.publish('greeting', 'hello')

    assert len(captured_messages) == 1
    assert captured_messages[0]['action'] == ProtocolMessageAction.MESSAGE
    assert captured_messages[0]['channel'] == channel_name
    assert len(captured_messages[0]['messages']) == 1
    assert captured_messages[0]['messages'][0]['name'] == 'greeting'
    assert captured_messages[0]['messages'][0]['data'] == 'hello'


# UTS: realtime/unit/RTL6i2/publish-message-array-0
async def test_rtl6i2_publish_message_array():
    channel_name = f'test-RTL6i2-{random_id()}'
    captured_messages = []
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE))
    mock_ws.on_message_from_client = attaching_server(mock_ws, captured_messages)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()
    await channel.publish([
        Message(name='event1', data='data1'),
        Message(name='event2', data='data2'),
        Message(name='event3', data='data3'),
    ])

    # A single ProtocolMessage carries the whole array
    assert len(captured_messages) == 1
    assert len(captured_messages[0]['messages']) == 3
    assert captured_messages[0]['messages'][0]['name'] == 'event1'
    assert captured_messages[0]['messages'][1]['name'] == 'event2'
    assert captured_messages[0]['messages'][2]['name'] == 'event3'


# UTS: realtime/unit/RTL6i3/null-fields-json-0
async def test_rtl6i3_null_fields_json():
    channel_name = f'test-RTL6i3-json-{random_id()}'
    captured_frames = []

    def on_text_data_frame(text):
        decoded = json.loads(text)
        if decoded['action'] == ProtocolMessageAction.MESSAGE:
            captured_frames.append(decoded)

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
        on_text_data_frame=on_text_data_frame)
    mock_ws.on_message_from_client = attaching_server(mock_ws)
    client = await connected_client(mock_ws, use_binary_protocol=False)
    channel = client.channels.get(channel_name)

    await channel.attach()
    await channel.publish('click', None)
    await channel.publish(None, 'payload')
    await channel.publish(None, None)

    assert len(captured_frames) == 3

    first = captured_frames[0]['messages'][0]
    assert first['name'] == 'click'
    assert 'data' not in first

    second = captured_frames[1]['messages'][0]
    assert 'name' not in second
    assert second['data'] == 'payload'

    third = captured_frames[2]['messages'][0]
    assert 'name' not in third
    assert 'data' not in third


# UTS: realtime/unit/RTL6i3/null-fields-msgpack-1
async def test_rtl6i3_null_fields_msgpack():
    channel_name = f'test-RTL6i3-msgpack-{random_id()}'
    captured_frames = []

    def on_binary_data_frame(raw):
        decoded = msgpack.unpackb(raw, raw=False)
        if decoded['action'] == ProtocolMessageAction.MESSAGE:
            captured_frames.append(decoded)

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
        on_binary_data_frame=on_binary_data_frame)
    mock_ws.on_message_from_client = attaching_server(mock_ws)
    client = await connected_client(mock_ws, use_binary_protocol=True)
    channel = client.channels.get(channel_name)

    await channel.attach()
    await channel.publish('click', None)
    await channel.publish(None, 'payload')
    await channel.publish(None, None)

    assert len(captured_frames) == 3

    first = captured_frames[0]['messages'][0]
    assert first['name'] == 'click'
    assert 'data' not in first

    second = captured_frames[1]['messages'][0]
    assert 'name' not in second
    assert second['data'] == 'payload'

    third = captured_frames[2]['messages'][0]
    assert 'name' not in third
    assert 'data' not in third


# UTS: realtime/unit/RTL6c1/publish-when-attached-0
async def test_rtl6c1_publish_when_attached():
    channel_name = f'test-RTL6c1-{random_id()}'
    captured_messages = []
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE))
    mock_ws.on_message_from_client = attaching_server(mock_ws, captured_messages)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    assert client.connection.state == ConnectionState.CONNECTED
    assert channel.state == ChannelState.ATTACHED

    await channel.publish('test', 'immediate')

    assert len(captured_messages) == 1
    assert captured_messages[0]['messages'][0]['name'] == 'test'
    assert captured_messages[0]['messages'][0]['data'] == 'immediate'


# UTS: realtime/unit/RTL6c1/publish-when-attaching-1
async def test_rtl6c1_publish_when_attaching():
    channel_name = f'test-RTL6c1-attaching-{random_id()}'
    captured_messages = []

    def on_message_from_client(msg):
        # An ATTACH goes unanswered, so the channel stays ATTACHING
        if msg['action'] == ProtocolMessageAction.MESSAGE:
            captured_messages.append(msg)
            mock_ws.send_to_client(ack_message(msg))

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
        on_message_from_client=on_message_from_client)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    attach_task = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING)

    await channel.publish('while-attaching', 'data')

    # ATTACHING is neither SUSPENDED nor FAILED, so the message goes out at once
    assert len(captured_messages) == 1
    assert captured_messages[0]['messages'][0]['name'] == 'while-attaching'

    attach_task.cancel()


# UTS: realtime/unit/RTL6c1/publish-when-initialized-2
async def test_rtl6c1_publish_when_initialized():
    channel_name = f'test-RTL6c1-init-{random_id()}'
    captured_messages = []
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE))
    mock_ws.on_message_from_client = attaching_server(mock_ws, captured_messages)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    assert channel.state == ChannelState.INITIALIZED

    await channel.publish('before-attach', 'data')

    assert len(captured_messages) == 1
    assert captured_messages[0]['messages'][0]['name'] == 'before-attach'


# UTS: realtime/unit/RTL6c2/queued-when-connecting-0
async def test_rtl6c2_queued_when_connecting():
    channel_name = f'test-RTL6c2-connecting-{random_id()}'
    captured_messages = []
    attempts = []

    mock_ws = MockWebSocket(
        # The attempt is left unanswered, so the connection stays CONNECTING.
        # The specification recovers it afterwards with
        # `await_connection_attempt()`, which registers its waiter when called
        # and so would wait for a second attempt; the handler keeps this one.
        on_connection_attempt=attempts.append)
    mock_ws.on_message_from_client = attaching_server(mock_ws, captured_messages)
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    client.connect()
    await poll_until(lambda: len(attempts) == 1, description='a connection attempt is in flight')
    assert client.connection.state == ConnectionState.CONNECTING

    publish_task = asyncio.ensure_future(channel.publish('queued', 'waiting'))
    await settle()

    assert captured_messages == []

    attempts[0].respond_with_success(CONNECTED_MESSAGE)
    await await_connection_state(client, ConnectionState.CONNECTED)
    await asyncio.wait_for(publish_task, 5)

    assert len(captured_messages) == 1
    assert captured_messages[0]['messages'][0]['name'] == 'queued'
    assert captured_messages[0]['messages'][0]['data'] == 'waiting'


# UTS: realtime/unit/RTL6c2/queued-when-disconnected-1
async def test_rtl6c2_queued_when_disconnected():
    channel_name = f'test-RTL6c2-disconnected-{random_id()}'
    captured_messages = []
    attempt_count = 0

    def on_connection_attempt(conn):
        nonlocal attempt_count
        attempt_count += 1
        # RTN15a retries a drop from CONNECTED with no time passing, so
        # DISCONNECTED is not a state the connection rests in. Failing that
        # retry holds it there long enough to publish into it.
        if attempt_count == 2:
            conn.respond_with_dns_error()
        else:
            conn.respond_with_success(CONNECTED_MESSAGE)

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    mock_ws.on_message_from_client = attaching_server(mock_ws, captured_messages)
    # A retry timeout longer than the test keeps the connection in DISCONNECTED
    client = await connected_client(mock_ws, disconnected_retry_timeout=60000)
    channel = client.channels.get(channel_name)

    state_changes = []

    def record(change):
        state_changes.append(change.current)

    client.connection.on(record)

    mock_ws.simulate_disconnect()
    await poll_until(
        lambda: client.connection.state == ConnectionState.DISCONNECTED and attempt_count == 2,
        description='the connection has settled in DISCONNECTED')

    assert ConnectionState.DISCONNECTED in state_changes

    publish_task = asyncio.ensure_future(channel.publish('during-disconnect', 'queued'))
    await settle()

    message_count_before = len(captured_messages)
    assert message_count_before == 0

    reconnected = asyncio.ensure_future(next_connection_state(client, ConnectionState.CONNECTED))
    client.connect()
    await reconnected
    await asyncio.wait_for(publish_task, 5)

    assert len(captured_messages) > message_count_before
    queued = [msg for msg in captured_messages
              if msg['messages'][0]['name'] == 'during-disconnect']
    assert len(queued) == 1


# UTS: realtime/unit/RTL6c2/queued-when-initialized-2
async def test_rtl6c2_queued_when_initialized():
    channel_name = f'test-RTL6c2-init-{random_id()}'
    captured_messages = []
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE))
    mock_ws.on_message_from_client = attaching_server(mock_ws, captured_messages)
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    assert client.connection.state == ConnectionState.INITIALIZED

    publish_task = asyncio.ensure_future(channel.publish('pre-connect', 'early'))
    await settle()

    assert captured_messages == []

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await asyncio.wait_for(publish_task, 5)

    assert len(captured_messages) == 1
    assert captured_messages[0]['messages'][0]['name'] == 'pre-connect'


# UTS: realtime/unit/RTL6c4/fails-conn-suspended-0
async def test_rtl6c4_fails_conn_suspended():
    channel_name = f'test-RTL6c4-suspended-{random_id()}'
    clock = FakeClock()
    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: conn.respond_with_refused())
    client = realtime_client(mock_ws, clock=clock, disconnected_retry_timeout=1000)
    channel = client.channels.get(channel_name)

    client.connect()
    await advance_until_suspended(client, clock)

    assert client.connection.state == ConnectionState.SUSPENDED

    with pytest.raises(AblyException) as error:
        await channel.publish('fail', 'should-error')

    assert error.value.code is not None


# UTS: realtime/unit/RTL6c4/fails-conn-closed-1
async def test_rtl6c4_fails_conn_closed():
    channel_name = f'test-RTL6c4-closed-{random_id()}'
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE))
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await client.close()
    assert client.connection.state == ConnectionState.CLOSED

    with pytest.raises(AblyException) as error:
        await channel.publish('fail', 'should-error')

    assert error.value.code is not None


# UTS: realtime/unit/RTL6c4/fails-conn-failed-2
async def test_rtl6c4_fails_conn_failed():
    channel_name = f'test-RTL6c4-failed-{random_id()}'
    fatal_error = {
        'action': int(ProtocolMessageAction.ERROR),
        'error': {'code': 80000, 'statusCode': 400, 'message': 'Fatal error'},
    }
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_error(fatal_error, then_close=True))
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED)

    with pytest.raises(AblyException) as error:
        await channel.publish('fail', 'should-error')

    assert error.value.code is not None


# UTS: realtime/unit/RTL6c4/fails-channel-suspended-3
async def test_rtl6c4_fails_channel_suspended():
    channel_name = f'test-RTL6c4-ch-suspended-{random_id()}'
    captured_messages = []
    clock = FakeClock()

    def on_message_from_client(msg):
        # An ATTACH goes unanswered, so the channel's state timer suspends it
        if msg['action'] == ProtocolMessageAction.MESSAGE:
            captured_messages.append(msg)

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
        on_message_from_client=on_message_from_client)
    client = await connected_client(mock_ws, clock=clock, realtime_request_timeout=100)
    channel = client.channels.get(channel_name)

    attach_task = asyncio.ensure_future(channel.attach())
    await settle()
    await clock.advance(150)

    with pytest.raises(AblyException):
        await attach_task

    assert channel.state == ChannelState.SUSPENDED

    with pytest.raises(AblyException) as error:
        await channel.publish('fail', 'should-error')

    assert error.value.code is not None
    assert captured_messages == []


# UTS: realtime/unit/RTL6c4/fails-channel-failed-4
async def test_rtl6c4_fails_channel_failed():
    channel_name = f'test-RTL6c4-ch-failed-{random_id()}'
    captured_messages = []

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client({
                'action': int(ProtocolMessageAction.ERROR),
                'channel': channel_name,
                'error': {'code': 40160, 'statusCode': 401, 'message': 'Not permitted'},
            })
        elif msg['action'] == ProtocolMessageAction.MESSAGE:
            captured_messages.append(msg)

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
        on_message_from_client=on_message_from_client)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    with pytest.raises(AblyException):
        await channel.attach()

    assert channel.state == ChannelState.FAILED

    with pytest.raises(AblyException) as error:
        await channel.publish('fail', 'should-error')

    assert error.value.code is not None
    assert captured_messages == []


# UTS: realtime/unit/RTL6c2/fails-no-queue-messages-3
async def test_rtl6c2_fails_no_queue_messages():
    channel_name = f'test-RTL6c2-noqueue-{random_id()}'
    attempts = []
    # The attempt is left unanswered, so the connection stays CONNECTING
    mock_ws = MockWebSocket(on_connection_attempt=attempts.append)
    client = realtime_client(mock_ws, queue_messages=False)
    channel = client.channels.get(channel_name)

    client.connect()
    await poll_until(lambda: len(attempts) == 1, description='a connection attempt is in flight')
    assert client.connection.state == ConnectionState.CONNECTING

    with pytest.raises(AblyException) as error:
        await channel.publish('fail', 'should-error')

    assert error.value.code is not None

    # The attempt is answered so that teardown does not wait it out
    attempts[0].respond_with_success(CONNECTED_MESSAGE)


# UTS: realtime/unit/RTL6c5/no-implicit-attach-0
async def test_rtl6c5_no_implicit_attach():
    channel_name = f'test-RTL6c5-{random_id()}'
    captured_messages = []
    attach_messages = []

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.MESSAGE:
            captured_messages.append(msg)
            mock_ws.send_to_client(ack_message(msg))

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
        on_message_from_client=on_message_from_client)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    assert channel.state == ChannelState.INITIALIZED

    await channel.publish('no-attach', 'test')

    # RTL6c1: CONNECTED and a channel that is neither SUSPENDED nor FAILED
    assert len(captured_messages) == 1

    assert channel.state == ChannelState.INITIALIZED
    assert attach_messages == []


# UTS: realtime/unit/RTL6c2/queued-messages-order-4
async def test_rtl6c2_queued_messages_order():
    channel_name = f'test-RTL6c2-order-{random_id()}'
    captured_messages = []
    attempts = []
    # The attempt is left unanswered, so the connection stays CONNECTING
    mock_ws = MockWebSocket(on_connection_attempt=attempts.append)
    mock_ws.on_message_from_client = attaching_server(mock_ws, captured_messages)
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    client.connect()
    await poll_until(lambda: len(attempts) == 1, description='a connection attempt is in flight')
    assert client.connection.state == ConnectionState.CONNECTING

    publishes = [
        asyncio.ensure_future(channel.publish('first', '1')),
        asyncio.ensure_future(channel.publish('second', '2')),
        asyncio.ensure_future(channel.publish('third', '3')),
    ]
    await settle()

    assert captured_messages == []

    attempts[0].respond_with_success(CONNECTED_MESSAGE)
    await await_connection_state(client, ConnectionState.CONNECTED)
    await asyncio.wait_for(asyncio.gather(*publishes), 5)

    assert len(captured_messages) == 3
    assert captured_messages[0]['messages'][0]['name'] == 'first'
    assert captured_messages[1]['messages'][0]['name'] == 'second'
    assert captured_messages[2]['messages'][0]['name'] == 'third'


# UTS: realtime/unit/RTL6i1/publish-message-object-1
# SPEC ERROR RTL6i1: an object payload is asserted to travel unstringified. RSL4c3 and
# RSL4d3, which RTL6a defers to, both require it to be stringified and carry
# `encoding: "json"` — which is what ably-python sends. The same fault is recorded for
# `rest/unit/channel/publish.md:129` in deviations.md. Fix the specification first.
@spec_error
async def test_rtl6i1_publish_message_object():
    channel_name = f'test-RTL6i1-obj-{random_id()}'
    captured_messages = []
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE))
    mock_ws.on_message_from_client = attaching_server(mock_ws, captured_messages)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()
    await channel.publish(Message(name='custom', data={'key': 'value'}))

    assert len(captured_messages) == 1
    assert len(captured_messages[0]['messages']) == 1
    assert captured_messages[0]['messages'][0]['name'] == 'custom'
    assert captured_messages[0]['messages'][0]['data'] == {'key': 'value'}


# UTS: realtime/unit/RTL6j/publish-result-serials-0
async def test_rtl6j_publish_result_serials():
    channel_name = f'test-RTL6j-{random_id()}'
    captured_messages = []
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE))
    mock_ws.on_message_from_client = attaching_server(mock_ws, captured_messages, serials=['abc123'])
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()
    result = await channel.publish('greeting', 'hello')

    # RTN7b: the first message on a connection carries msgSerial 0
    assert len(captured_messages) == 1
    assert captured_messages[0]['msgSerial'] == 0

    assert isinstance(result, PublishResult)
    assert len(result.serials) == 1
    assert result.serials[0] == 'abc123'


# UTS: realtime/unit/RTL6j/batch-publish-serials-1
async def test_rtl6j_batch_publish_serials():
    channel_name = f'test-RTL6j-batch-{random_id()}'
    captured_messages = []
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE))
    mock_ws.on_message_from_client = attaching_server(
        mock_ws, captured_messages, serials=['serial-1', None, 'serial-3'])
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()
    result = await channel.publish([
        Message(name='event1', data='data1'),
        Message(name='event2', data='data2'),
        Message(name='event3', data='data3'),
    ])

    assert len(captured_messages) == 1
    assert len(captured_messages[0]['messages']) == 3

    assert isinstance(result, PublishResult)
    assert len(result.serials) == 3
    assert result.serials[0] == 'serial-1'
    # PBR2a: a conflated message carries no serial
    assert result.serials[1] is None
    assert result.serials[2] == 'serial-3'


# UTS: realtime/unit/RTL6j/incrementing-msg-serial-2
async def test_rtl6j_incrementing_msg_serial():
    channel_name = f'test-RTL6j-serial-{random_id()}'
    captured_messages = []

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.MESSAGE:
            captured_messages.append(msg)
            mock_ws.send_to_client(ack_message(msg, [f'serial-{msg["msgSerial"]}']))

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
        on_message_from_client=on_message_from_client)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()
    first = await channel.publish('first', '1')
    second = await channel.publish('second', '2')
    third = await channel.publish('third', '3')

    assert len(captured_messages) == 3
    assert captured_messages[0]['msgSerial'] == 0
    assert captured_messages[1]['msgSerial'] == 1
    assert captured_messages[2]['msgSerial'] == 2

    assert first.serials[0] == 'serial-0'
    assert second.serials[0] == 'serial-1'
    assert third.serials[0] == 'serial-2'


# UTS: realtime/unit/RTL6j/nack-results-error-3
async def test_rtl6j_nack_results_error():
    channel_name = f'test-RTL6j-nack-{random_id()}'

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.MESSAGE:
            mock_ws.send_to_client(nack_message(
                msg, {'code': 40160, 'statusCode': 401, 'message': 'Publish rejected'}))

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
        on_message_from_client=on_message_from_client)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    with pytest.raises(AblyException) as error:
        await channel.publish('rejected', 'data')

    assert error.value.code == 40160
    assert error.value.message == 'Publish rejected'

