"""Derived from uts/realtime/unit/channels/channel_attach.md in ably/specification.

Spec points: RTL4, RTL4a, RTL4b, RTL4c, RTL4c1, RTL4f, RTL4g, RTL4h, RTL4i, RTL4j, RTL4k,
RTL4l, RTL4m
"""

import asyncio

import pytest

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelmode import ChannelMode
from ably.types.channeloptions import ChannelOptions
from ably.types.channelstate import ChannelState
from ably.types.flags import Flag
from ably.util.exceptions import AblyException
from test.uts.helpers.client import (
    await_channel_state,
    await_connection_state,
    poll_until,
    realtime_client,
)
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')

# The same connection with the idle timer switched off, so that a test driving a
# `FakeClock` sees only the timers it is interested in
CONNECTED_MESSAGE_NO_IDLE = connected_message(
    'connection-id', connectionKey='connection-key', maxIdleInterval=0)

# How long an operation which the specification expects to settle is given
# before a test calls it hung
OPERATION_TIMEOUT = 1.0


def attached_message(channel_name, **fields):
    """An ATTACHED for `channel_name`, as the server confirms an attach."""
    return {'action': ProtocolMessageAction.ATTACHED, 'channel': channel_name, **fields}


async def advance_to_connection_state(client, clock, state, step=5000, limit=40):
    """Moves `clock` forward in steps until the connection reaches `state`."""
    for _ in range(limit):
        if client.connection.state == state:
            return
        await clock.advance(step)
    raise AssertionError(
        f'Connection did not reach {state} within {step * limit}ms; it is {client.connection.state}')


async def connected_client(mock_ws, **kwargs):
    """A client connected through `mock_ws`, which the channel tests open with."""
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


# UTS: realtime/unit/RTL4a/already-attached-noop-0
async def test_rtl4a_already_attached_noop():
    channel_name = 'test-RTL4a'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()
    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 1

    await channel.attach()

    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 1


# UTS: realtime/unit/RTL4h/attach-while-attaching-0
async def test_rtl4h_attach_while_attaching():
    channel_name = 'test-RTL4h'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    first = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    second = asyncio.ensure_future(channel.attach())
    await settle()

    mock_ws.send_to_client(attached_message(channel_name))

    await asyncio.wait_for(first, OPERATION_TIMEOUT)
    await asyncio.wait_for(second, OPERATION_TIMEOUT)

    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 1


# UTS: realtime/unit/RTL4h/attach-while-detaching-1
async def test_rtl4h_attach_while_detaching():
    channel_name = 'test-RTL4h-detaching'
    messages_from_client = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        messages_from_client.append(msg)
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()
    assert channel.state == ChannelState.ATTACHED

    detach_future = asyncio.ensure_future(channel.detach())
    await await_channel_state(channel, ChannelState.DETACHING, OPERATION_TIMEOUT)

    attach_future = asyncio.ensure_future(channel.attach())
    await settle()

    # RTL4h has the attach wait for the pending detach to complete, so that the
    # DETACHED below ends the detach and only then is a second ATTACH sent.
    # ably-python's attach requests ATTACHING straight away, which pre-empts the
    # detach and makes the pending detach fail with 90000
    with pytest.raises(AblyException) as detach_error:
        await asyncio.wait_for(detach_future, OPERATION_TIMEOUT)
    # The 90000 the library passes lands in `status_code` and the 409 in `code`,
    # the two being the other way round in `AblyException(message, status_code, code)`
    assert detach_error.value.status_code == 90000

    await asyncio.wait_for(attach_future, OPERATION_TIMEOUT)

    assert channel.state == ChannelState.ATTACHED
    attach_messages = [m for m in messages_from_client if m.get('action') == ProtocolMessageAction.ATTACH]
    assert len(attach_messages) == 2


# UTS: realtime/unit/RTL4g/attach-from-failed-0
async def test_rtl4g_attach_from_failed():
    channel_name = 'test-RTL4g'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            if len(attach_messages) == 1:
                mock_ws.send_to_client({
                    'action': ProtocolMessageAction.ERROR,
                    'channel': channel_name,
                    'error': {'code': 40160, 'statusCode': 401, 'message': 'Denied'},
                })
            else:
                mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    with pytest.raises(AblyException):
        await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.FAILED
    assert channel.error_reason is not None

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert channel.state == ChannelState.ATTACHED
    assert channel.error_reason is None


# UTS: realtime/unit/RTL4c/clears-error-reason-0
async def test_rtl4c_clears_error_reason():
    channel_name = 'test-RTL4c-error-clear'
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(msg.get('channel')))

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(
        mock_ws, clock=clock, realtime_request_timeout=300, suspended_retry_timeout=2000)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    mock_ws.on_connection_attempt = lambda conn: conn.respond_with_refused()
    mock_ws.simulate_disconnect()
    await settle()

    await advance_to_connection_state(client, clock, ConnectionState.SUSPENDED)
    assert channel.state == ChannelState.SUSPENDED
    assert channel.error_reason is not None

    mock_ws.on_connection_attempt = lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE)
    await advance_to_connection_state(client, clock, ConnectionState.CONNECTED, step=2500, limit=10)
    await await_channel_state(channel, ChannelState.ATTACHED, OPERATION_TIMEOUT)

    assert channel.state == ChannelState.ATTACHED
    assert channel.error_reason is None


# UTS: realtime/unit/RTL4b/fails-connection-closed-0
async def test_rtl4b_fails_connection_closed():
    channel_name = 'test-RTL4b-closed'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await client.close()
    assert client.connection.state == ConnectionState.CLOSED

    with pytest.raises(AblyException) as error:
        await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert error.value.code is not None
    assert channel.state != ChannelState.ATTACHED


# UTS: realtime/unit/RTL4b/fails-connection-failed-1
async def test_rtl4b_fails_connection_failed():
    channel_name = 'test-RTL4b-failed'

    def on_connection_attempt(conn):
        conn.respond_with_success(CONNECTED_MESSAGE)
        conn.send_to_client_and_close({
            'action': ProtocolMessageAction.ERROR,
            'error': {'code': 80000, 'statusCode': 500, 'message': 'Fatal error'},
        })

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED)

    with pytest.raises(AblyException) as error:
        await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert error.value is not None
    assert channel.state != ChannelState.ATTACHED


# UTS: realtime/unit/RTL4b/fails-connection-suspended-2
async def test_rtl4b_fails_connection_suspended():
    channel_name = 'test-RTL4b-suspended'
    clock = FakeClock()

    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: conn.respond_with_refused())
    client = realtime_client(mock_ws, clock=clock, realtime_request_timeout=300, channel_retry_timeout=100)
    channel = client.channels.get(channel_name)

    client.connect()
    await advance_to_connection_state(client, clock, ConnectionState.SUSPENDED)

    with pytest.raises(AblyException) as error:
        await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert error.value is not None
    assert channel.state != ChannelState.ATTACHED


# UTS: realtime/unit/RTL4i/queued-while-connecting-0
async def test_rtl4i_queued_while_connecting():
    channel_name = 'test-RTL4i'
    attach_messages = []

    # A handler which does not answer the attempt holds the connection in
    # CONNECTING, which is the specification's "delay connection response"
    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: None)

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTING)

    attach_future = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    assert channel.state == ChannelState.ATTACHING
    assert attach_messages == []
    attach_future.cancel()


# UTS: realtime/unit/RTL4i/completes-on-connected-1
async def test_rtl4i_completes_on_connected():
    channel_name = 'test-RTL4i-connected'
    attach_messages = []

    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: None)

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTING)

    attach_future = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)
    assert attach_messages == []

    await poll_until(lambda: mock_ws.connection_attempts, OPERATION_TIMEOUT, 'a connection attempt')
    mock_ws.connection_attempts[0].respond_with_success(CONNECTED_MESSAGE)

    await asyncio.wait_for(attach_future, OPERATION_TIMEOUT)

    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 1


# UTS: realtime/unit/RTL4c/sends-attach-message-1
async def test_rtl4c_sends_attach_message():
    channel_name = 'test-RTL4c'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    states_during_attach = []

    def on_attaching(change):
        states_during_attach.append(channel.state)

    channel.on(ChannelState.ATTACHING, on_attaching)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert states_during_attach == [ChannelState.ATTACHING]
    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 1
    assert attach_messages[0]['action'] == ProtocolMessageAction.ATTACH
    assert attach_messages[0]['channel'] == channel_name


# UTS: realtime/unit/RTL4c1/includes-channel-serial-0
async def test_rtl4c1_includes_channel_serial():
    channel_name = 'test-RTL4c1'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            mock_ws.send_to_client(attached_message(channel_name, channelSerial='serial-from-server-1'))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    set_options = asyncio.ensure_future(
        channel.set_options(ChannelOptions(modes=[ChannelMode.SUBSCRIBE])))
    await settle()

    assert len(attach_messages) == 2
    assert attach_messages[0].get('channelSerial') is None
    assert attach_messages[1].get('channelSerial') == 'serial-from-server-1'
    set_options.cancel()


# UTS: realtime/unit/RTL4f/timeout-to-suspended-0
async def test_rtl4f_timeout_to_suspended():
    channel_name = 'test-RTL4f'
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )
    client = realtime_client(mock_ws, clock=clock, realtime_request_timeout=100)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    attach_future = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    await clock.advance(150)

    with pytest.raises(AblyException) as error:
        await asyncio.wait_for(attach_future, OPERATION_TIMEOUT)

    assert channel.state == ChannelState.SUSPENDED
    assert error.value is not None


# UTS: realtime/unit/RTL4k/includes-channel-params-0
async def test_rtl4k_includes_channel_params():
    channel_name = 'test-RTL4k'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(
        channel_name, ChannelOptions(params={'rewind': '1', 'delta': 'vcdiff'}))

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert len(attach_messages) == 1
    assert attach_messages[0]['params'] is not None
    assert attach_messages[0]['params']['rewind'] == '1'
    assert attach_messages[0]['params']['delta'] == 'vcdiff'


# UTS: realtime/unit/RTL4l/modes-encoded-as-flags-0
async def test_rtl4l_modes_encoded_as_flags():
    channel_name = 'test-RTL4l'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(
        channel_name, ChannelOptions(modes=[ChannelMode.PUBLISH, ChannelMode.SUBSCRIBE]))

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert len(attach_messages) == 1
    assert attach_messages[0].get('flags') is not None
    assert attach_messages[0]['flags'] & Flag.PUBLISH
    assert attach_messages[0]['flags'] & Flag.SUBSCRIBE


# UTS: realtime/unit/RTL4m/modes-from-attached-0
async def test_rtl4m_modes_from_attached():
    channel_name = 'test-RTL4m'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(
                attached_message(channel_name, flags=Flag.PUBLISH | Flag.SUBSCRIBE))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert channel.modes is not None
    assert ChannelMode.PUBLISH in channel.modes
    assert ChannelMode.SUBSCRIBE in channel.modes


# UTS: realtime/unit/RTL4j/attach-resume-flag-not-set-0
@deviation
async def test_rtl4j_attach_resume_flag_not_set():
    channel_name = 'test-RTL4j'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            mock_ws.send_to_client(attached_message(channel_name))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    set_options = asyncio.ensure_future(channel.set_options(ChannelOptions(params={'rewind': '1'})))
    await settle()

    assert len(attach_messages) == 2
    assert not attach_messages[0].get('flags', 0) & Flag.ATTACH_RESUME
    assert not attach_messages[1].get('flags', 0) & Flag.ATTACH_RESUME
    set_options.cancel()
