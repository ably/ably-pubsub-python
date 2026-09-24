"""Derived from uts/realtime/unit/channels/channel_subscribe.md in ably/specification.

Spec points: RTL7, RTL7a, RTL7b, RTL7f, RTL7g, RTL7h, RTL8, RTL8a, RTL8b, RTL8c, RTL17,
RTL22, RTL22a, RTL22b, RTL22c, RTL22d, MFI1, MFI2, MFI2a, MFI2b, MFI2c, MFI2d, MFI2e
"""

import asyncio

import pytest

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelstate import ChannelState
from ably.util.exceptions import AblyException
from test.uts.helpers.client import (
    await_channel_state,
    await_connection_state,
    poll_until,
    realtime_client,
)
from test.uts.helpers.clock import settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import (
    MockWebSocket,
    attached_message,
    connected_message,
    detached_message,
)

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')

# How long an operation which the specification expects to settle is given
# before a test calls it hung
OPERATION_TIMEOUT = 1.0


def message_protocol_message(channel_name, messages, **fields):
    """A MESSAGE protocol message carrying `messages` on `channel_name`."""
    return {
        'action': int(ProtocolMessageAction.MESSAGE),
        'channel': channel_name,
        'messages': messages,
        **fields,
    }


def message_filter(**criteria):
    """The specification's `MessageFilter` (MFI1), built from `criteria`."""
    from ably.types.messagefilter import MessageFilter

    return MessageFilter(**criteria)


def attaching_mock(channel_name, attach_messages=None, detach_messages=None):
    """A mock which connects and confirms attaches and detaches for `channel_name`.

    Each ATTACH and DETACH is recorded in the list given for it, so that a test
    can count the protocol messages the channel sent.
    """
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            if attach_messages is not None:
                attach_messages.append(msg)
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg.get('action') == ProtocolMessageAction.DETACH:
            if detach_messages is not None:
                detach_messages.append(msg)
            mock_ws.send_to_client(detached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    return mock_ws


async def connected_client(mock_ws, **kwargs):
    """A client connected through `mock_ws`, which the channel tests open with."""
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


def recorder(received):
    """A subscribe listener appending each message it is given to `received`."""
    def record(message):
        received.append(message)
    return record


# UTS: realtime/unit/RTL7a/subscribe-all-messages-0
async def test_rtl7a_subscribe_all_messages():
    # The specification withholds the implicit attach with
    # `RealtimeChannelOptions(attachOnSubscribe: false)`; the channel is attached
    # first instead, which makes the attach `subscribe` awaits a no-op.
    channel_name = 'test-RTL7a'
    received = []

    mock_ws = attaching_mock(channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)
    await channel.attach()

    await channel.subscribe(recorder(received))

    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'event1', 'data': 'data1'}]))
    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'event2', 'data': 'data2'}]))
    await poll_until(lambda: len(received) == 2, description='both messages are delivered')

    assert received[0].name == 'event1'
    assert received[0].data == 'data1'
    assert received[1].name == 'event2'
    assert received[1].data == 'data2'


# UTS: realtime/unit/RTL7a/multiple-messages-per-protocol-1
async def test_rtl7a_multiple_messages_per_protocol():
    channel_name = 'test-RTL7a-multi'
    received = []

    mock_ws = attaching_mock(channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)
    await channel.attach()

    await channel.subscribe(recorder(received))

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'name': 'batch1', 'data': 'first'},
        {'name': 'batch2', 'data': 'second'},
        {'name': 'batch3', 'data': 'third'},
    ]))
    await poll_until(lambda: len(received) == 3, description='all three messages are delivered')

    assert received[0].name == 'batch1'
    assert received[1].name == 'batch2'
    assert received[2].name == 'batch3'


# UTS: realtime/unit/RTL7b/name-filtered-subscribe-0
async def test_rtl7b_name_filtered_subscribe():
    channel_name = 'test-RTL7b'
    received = []

    mock_ws = attaching_mock(channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)
    await channel.attach()

    await channel.subscribe('target', recorder(received))

    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'other', 'data': 'should-not-receive'}]))
    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'target', 'data': 'should-receive'}]))
    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': None, 'data': 'no-name-should-not-receive'}]))
    await poll_until(lambda: len(received) == 1, description='the matching message is delivered')
    await settle()

    assert len(received) == 1
    assert received[0].name == 'target'
    assert received[0].data == 'should-receive'


# UTS: realtime/unit/RTL7b/multiple-name-subscriptions-1
async def test_rtl7b_multiple_name_subscriptions():
    channel_name = 'test-RTL7b-multi'
    alpha_messages = []
    beta_messages = []

    mock_ws = attaching_mock(channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)
    await channel.attach()

    await channel.subscribe('alpha', recorder(alpha_messages))
    await channel.subscribe('beta', recorder(beta_messages))

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'name': 'alpha', 'data': 'a1'},
        {'name': 'beta', 'data': 'b1'},
        {'name': 'alpha', 'data': 'a2'},
        {'name': 'gamma', 'data': 'g1'},
    ]))
    await poll_until(lambda: len(alpha_messages) == 2, description='both alpha messages are delivered')
    await settle()

    assert len(alpha_messages) == 2
    assert alpha_messages[0].data == 'a1'
    assert alpha_messages[1].data == 'a2'

    assert len(beta_messages) == 1
    assert beta_messages[0].data == 'b1'


# UTS: realtime/unit/RTL7g/implicit-attach-initialized-0
async def test_rtl7g_implicit_attach_initialized():
    channel_name = 'test-RTL7g'
    attach_messages = []
    received = []

    mock_ws = attaching_mock(channel_name, attach_messages)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    assert channel.state == ChannelState.INITIALIZED

    await channel.subscribe(recorder(received))

    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 1

    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'test', 'data': 'hello'}]))
    await poll_until(lambda: len(received) == 1, description='the message reaches the listener')


# UTS: realtime/unit/RTL7g/implicit-attach-detached-1
async def test_rtl7g_implicit_attach_detached():
    channel_name = 'test-RTL7g-detached'
    attach_messages = []

    mock_ws = attaching_mock(channel_name, attach_messages)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()
    await channel.detach()
    assert channel.state == ChannelState.DETACHED
    assert len(attach_messages) == 1

    await channel.subscribe(lambda message: None)

    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 2


# UTS: realtime/unit/RTL7g/listener-registered-attach-fails-2
async def test_rtl7g_listener_registered_attach_fails():
    channel_name = 'test-RTL7g-fail'
    received = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def reject_attach(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client({
                'action': int(ProtocolMessageAction.ERROR),
                'channel': channel_name,
                'error': {'code': 40160, 'statusCode': 401, 'message': 'Not permitted'},
            })

    mock_ws.on_message_from_client = reject_attach
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    # The implicit attach is awaited by `subscribe`, so its rejection surfaces
    # as the exception the specification leaves to the attach result
    with pytest.raises(AblyException):
        await channel.subscribe(recorder(received))

    assert channel.state == ChannelState.FAILED

    def accept_attach(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = accept_attach
    await channel.attach()

    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'test', 'data': 'after-reattach'}]))
    await poll_until(lambda: len(received) == 1, description='the registered listener is called')

    assert received[0].data == 'after-reattach'


# UTS: realtime/unit/RTL7h/no-attach-on-subscribe-0
@deviation
async def test_rtl7h_no_attach_on_subscribe():
    from ably.types.channeloptions import ChannelOptions

    channel_name = 'test-RTL7h'
    attach_messages = []

    mock_ws = attaching_mock(channel_name, attach_messages)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name, ChannelOptions(attach_on_subscribe=False))

    assert channel.state == ChannelState.INITIALIZED

    await channel.subscribe(lambda message: None)

    assert channel.state == ChannelState.INITIALIZED
    assert len(attach_messages) == 0


# UTS: realtime/unit/RTL7g/no-attach-when-attached-3
async def test_rtl7g_no_attach_when_attached():
    channel_name = 'test-RTL7g-already'
    attach_messages = []

    mock_ws = attaching_mock(channel_name, attach_messages)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()
    assert len(attach_messages) == 1

    await channel.subscribe(lambda message: None)

    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 1


# UTS: realtime/unit/RTL7g/no-attach-when-attaching-4
async def test_rtl7g_no_attach_when_attaching():
    channel_name = 'test-RTL7g-attaching'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def record_attach(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)

    mock_ws.on_message_from_client = record_attach
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    attach_task = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)
    assert len(attach_messages) == 1

    # `subscribe` awaits the attach already in flight, so it is driven as a task
    subscribe_task = asyncio.ensure_future(channel.subscribe(lambda message: None))
    await settle()

    assert channel.state == ChannelState.ATTACHING
    assert len(attach_messages) == 1

    attach_task.cancel()
    subscribe_task.cancel()


# UTS: realtime/unit/RTL17/no-delivery-when-not-attached-0
@deviation
async def test_rtl17_no_delivery_when_not_attached():
    channel_name = 'test-RTL17'
    received = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
        on_message_from_client=lambda msg: None,
    )
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    # The listener is registered before `subscribe` awaits the attach the mock
    # never confirms, so the channel stays ATTACHING with a subscriber on it
    subscribe_task = asyncio.ensure_future(channel.subscribe(recorder(received)))
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'premature', 'data': 'should-not-deliver'}]))
    await settle()

    assert len(received) == 0

    subscribe_task.cancel()


# UTS: realtime/unit/RTL7f/no-echo-messages-0
@deviation
async def test_rtl7f_no_echo_messages():
    channel_name = 'test-RTL7f'
    connection_id = 'conn-self-123'
    received = []

    mock_ws = attaching_mock(channel_name)
    mock_ws.on_connection_attempt = lambda conn: conn.respond_with_success(
        connected_message(connection_id, connectionKey='key-456'))
    client = await connected_client(mock_ws, echo_messages=False)
    channel = client.channels.get(channel_name)
    await channel.attach()

    await channel.subscribe(recorder(received))

    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'echo', 'data': 'from-self'}], connectionId=connection_id))
    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'remote', 'data': 'from-other'}], connectionId='conn-other-789'))
    await poll_until(lambda: len(received) == 1, description='the remote message is delivered')
    await settle()

    assert len(received) == 1
    assert received[0].name == 'remote'
    assert received[0].data == 'from-other'


# UTS: realtime/unit/RTL8a/unsubscribe-specific-listener-0
async def test_rtl8a_unsubscribe_specific_listener():
    channel_name = 'test-RTL8a'
    messages_a = []
    messages_b = []

    mock_ws = attaching_mock(channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)
    await channel.attach()

    listener_a = recorder(messages_a)
    listener_b = recorder(messages_b)

    await channel.subscribe(listener_a)
    await channel.subscribe(listener_b)

    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'msg1', 'data': 'first'}]))
    await poll_until(lambda: len(messages_a) == 1 and len(messages_b) == 1,
                     description='both listeners see the first message')

    channel.unsubscribe(listener_a)

    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'msg2', 'data': 'second'}]))
    await poll_until(lambda: len(messages_b) == 2, description='the second message is delivered')
    await settle()

    assert len(messages_a) == 1
    assert len(messages_b) == 2
    assert messages_b[1].name == 'msg2'


# UTS: realtime/unit/RTL8b/unsubscribe-named-listener-0
@deviation
async def test_rtl8b_unsubscribe_named_listener():
    channel_name = 'test-RTL8b'
    received = []

    mock_ws = attaching_mock(channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)
    await channel.attach()

    listener = recorder(received)

    await channel.subscribe('alpha', listener)
    await channel.subscribe('beta', listener)

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'name': 'alpha', 'data': 'a1'},
        {'name': 'beta', 'data': 'b1'},
    ]))
    await poll_until(lambda: len(received) == 2, description='both subscriptions are live')

    channel.unsubscribe('alpha', listener)

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'name': 'alpha', 'data': 'a2'},
        {'name': 'beta', 'data': 'b2'},
    ]))
    await poll_until(lambda: len(received) == 3, description='the beta message is delivered')
    await settle()

    assert len(received) == 3
    assert received[2].name == 'beta'
    assert received[2].data == 'b2'


# UTS: realtime/unit/RTL8c/unsubscribe-all-listeners-0
async def test_rtl8c_unsubscribe_all_listeners():
    channel_name = 'test-RTL8c'
    messages_all = []
    messages_named = []

    mock_ws = attaching_mock(channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)
    await channel.attach()

    await channel.subscribe(recorder(messages_all))
    await channel.subscribe('specific', recorder(messages_named))

    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'specific', 'data': 'first'}]))
    await poll_until(lambda: len(messages_all) == 1 and len(messages_named) == 1,
                     description='both listeners see the first message')

    channel.unsubscribe()

    mock_ws.send_to_client(message_protocol_message(channel_name, [
        {'name': 'specific', 'data': 'second'},
        {'name': 'other', 'data': 'third'},
    ]))
    await settle()

    assert len(messages_all) == 1
    assert len(messages_named) == 1


# UTS: realtime/unit/RTL8a/unsubscribe-noop-not-subscribed-1
async def test_rtl8a_unsubscribe_noop_not_subscribed():
    channel_name = 'test-RTL8a-noop'
    received = []

    mock_ws = attaching_mock(channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)
    await channel.attach()

    active_listener = recorder(received)

    def unused_listener(message):
        pass

    await channel.subscribe(active_listener)

    channel.unsubscribe(unused_listener)

    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'test', 'data': 'still-works'}]))
    await poll_until(lambda: len(received) == 1, description='the surviving listener is called')

    assert received[0].data == 'still-works'


# UTS: realtime/unit/RTL22a/filter-matching-name-0
@deviation
async def test_rtl22a_filter_matching_name():
    channel_name = 'test-RTL22a-name'
    filtered = []

    mock_ws = attaching_mock(channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)
    await channel.attach()

    await channel.subscribe(message_filter(name='target-event'), recorder(filtered))

    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'target-event', 'data': 'match-1'}]))
    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'other-event', 'data': 'no-match'}]))
    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'target-event', 'data': 'match-2'}]))
    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': None, 'data': 'no-name'}]))
    await poll_until(lambda: len(filtered) == 2, description='both matching messages are delivered')
    await settle()

    assert len(filtered) == 2
    assert filtered[0].name == 'target-event'
    assert filtered[0].data == 'match-1'
    assert filtered[1].name == 'target-event'
    assert filtered[1].data == 'match-2'


# UTS: realtime/unit/RTL22a/filter-matching-ref-timeserial-1
@deviation
async def test_rtl22a_filter_matching_ref_timeserial():
    channel_name = 'test-RTL22a-ref-timeserial'
    filtered = []

    mock_ws = attaching_mock(channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)
    await channel.attach()

    await channel.subscribe(
        message_filter(ref_timeserial='abc123@1700000000000-0'), recorder(filtered))

    mock_ws.send_to_client(message_protocol_message(channel_name, [{
        'name': 'reply', 'data': 'match',
        'extras': {'ref': {'timeserial': 'abc123@1700000000000-0', 'type': 'com.ably.reply'}},
    }]))
    mock_ws.send_to_client(message_protocol_message(channel_name, [{
        'name': 'reply', 'data': 'no-match',
        'extras': {'ref': {'timeserial': 'xyz789@1700000000000-0', 'type': 'com.ably.reply'}},
    }]))
    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'plain', 'data': 'no-ref'}]))
    mock_ws.send_to_client(message_protocol_message(channel_name, [{
        'name': 'reaction', 'data': 'match-2',
        'extras': {'ref': {'timeserial': 'abc123@1700000000000-0', 'type': 'com.ably.reaction'}},
    }]))
    await poll_until(lambda: len(filtered) == 2, description='both matching messages are delivered')
    await settle()

    assert len(filtered) == 2
    assert filtered[0].data == 'match'
    assert filtered[1].data == 'match-2'


# UTS: realtime/unit/RTL22b/filter-isref-false-0
@deviation
async def test_rtl22b_filter_isref_false():
    channel_name = 'test-RTL22b-isref-false'
    filtered = []

    mock_ws = attaching_mock(channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)
    await channel.attach()

    await channel.subscribe(message_filter(is_ref=False), recorder(filtered))

    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'plain', 'data': 'no-extras'}]))
    mock_ws.send_to_client(message_protocol_message(channel_name, [{
        'name': 'reply', 'data': 'has-ref',
        'extras': {'ref': {'timeserial': 'abc123@1700000000000-0', 'type': 'com.ably.reply'}},
    }]))
    mock_ws.send_to_client(message_protocol_message(channel_name, [{
        'name': 'annotated', 'data': 'extras-no-ref',
        'extras': {'headers': {'custom-key': 'custom-value'}},
    }]))
    mock_ws.send_to_client(message_protocol_message(channel_name, [{
        'name': 'reaction', 'data': 'also-has-ref',
        'extras': {'ref': {'timeserial': 'xyz789@1700000000000-0', 'type': 'com.ably.reaction'}},
    }]))
    await poll_until(lambda: len(filtered) == 2, description='both ref-less messages are delivered')
    await settle()

    assert len(filtered) == 2
    assert filtered[0].name == 'plain'
    assert filtered[0].data == 'no-extras'
    assert filtered[1].name == 'annotated'
    assert filtered[1].data == 'extras-no-ref'


# UTS: realtime/unit/RTL22c/filter-multiple-criteria-0
@deviation
async def test_rtl22c_filter_multiple_criteria():
    channel_name = 'test-RTL22c-multi'
    filtered = []

    mock_ws = attaching_mock(channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)
    await channel.attach()

    await channel.subscribe(
        message_filter(name='comment', ref_type='com.ably.reply'), recorder(filtered))

    mock_ws.send_to_client(message_protocol_message(channel_name, [{
        'name': 'comment', 'data': 'both-match',
        'extras': {'ref': {'timeserial': 'abc@1700000000000-0', 'type': 'com.ably.reply'}},
    }]))
    mock_ws.send_to_client(message_protocol_message(channel_name, [{
        'name': 'comment', 'data': 'name-only',
        'extras': {'ref': {'timeserial': 'def@1700000000000-0', 'type': 'com.ably.reaction'}},
    }]))
    mock_ws.send_to_client(message_protocol_message(channel_name, [{
        'name': 'update', 'data': 'type-only',
        'extras': {'ref': {'timeserial': 'ghi@1700000000000-0', 'type': 'com.ably.reply'}},
    }]))
    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'update', 'data': 'neither'}]))
    mock_ws.send_to_client(message_protocol_message(channel_name, [{
        'name': 'comment', 'data': 'both-match-2',
        'extras': {'ref': {'timeserial': 'jkl@1700000000000-0', 'type': 'com.ably.reply'}},
    }]))
    await poll_until(lambda: len(filtered) == 2, description='both fully matching messages are delivered')
    await settle()

    assert len(filtered) == 2
    assert filtered[0].data == 'both-match'
    assert filtered[1].data == 'both-match-2'


# UTS: realtime/unit/RTL22a/filter-matching-clientid-2
@deviation
async def test_rtl22a_filter_matching_clientid():
    channel_name = 'test-RTL22a-clientid'
    filtered = []

    mock_ws = attaching_mock(channel_name)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)
    await channel.attach()

    await channel.subscribe(message_filter(client_id='user-42'), recorder(filtered))

    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'chat', 'data': 'hello', 'clientId': 'user-42'}]))
    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'chat', 'data': 'hi', 'clientId': 'user-99'}]))
    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'system', 'data': 'broadcast'}]))
    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'chat', 'data': 'world', 'clientId': 'user-42'}]))
    await poll_until(lambda: len(filtered) == 2, description='both messages from user-42 are delivered')
    await settle()

    assert len(filtered) == 2
    assert filtered[0].data == 'hello'
    assert filtered[0].client_id == 'user-42'
    assert filtered[1].data == 'world'
    assert filtered[1].client_id == 'user-42'
