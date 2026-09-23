"""Derived from uts/realtime/unit/channels/channel_connection_state.md in ably/specification.

Spec points: RTL3, RTL3a, RTL3b, RTL3c, RTL3d, RTL3e, RTL4c1
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
from test.uts.helpers.clock import FakeClock, advance_to_connection_state, settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import (
    CONNECTED_MESSAGE_NO_IDLE,
    MockWebSocket,
    attached_message,
    connected_message,
    contains_in_order,
    detached_message,
)

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')

# How long an operation which the specification expects to settle is given
# before a test calls it hung
OPERATION_TIMEOUT = 1.0

# A fatal connection-level ERROR, which takes the connection to FAILED
ACCOUNT_DISABLED = {
    'action': int(ProtocolMessageAction.ERROR),
    'error': {'code': 40198, 'statusCode': 403, 'message': 'Account disabled'},
}


def echo_attach_and_detach(mock_ws, attach_messages=None, **attached_fields):
    """A handler confirming each ATTACH with an ATTACHED and each DETACH with a DETACHED."""
    def on_message_from_client(msg):
        action = msg.get('action')
        if action == ProtocolMessageAction.ATTACH:
            if attach_messages is not None:
                attach_messages.append(msg)
            mock_ws.send_to_client(attached_message(msg.get('channel'), **attached_fields))
        elif action == ProtocolMessageAction.DETACH:
            mock_ws.send_to_client(detached_message(msg.get('channel')))
    return on_message_from_client


def swallow_attach(mock_ws, attach_messages=None):
    """A handler which records ATTACH messages and never answers them."""
    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH and attach_messages is not None:
            attach_messages.append(msg)
    return on_message_from_client


def record_channel_states(channel):
    """Collects the ChannelStateChange objects `channel` emits from now on."""
    changes = []

    def record(change):
        changes.append(change)

    channel.on(record)
    return changes


async def connected_client(mock_ws, **kwargs):
    """A client connected through `mock_ws`."""
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


async def drop_transport(client, mock_ws):
    """Ends the transport and leaves the reconnection attempt unanswered.

    RTN15a reconnects immediately after a drop from CONNECTED, so DISCONNECTED
    is passed through rather than settled in; the connection then waits in
    CONNECTING on an attempt nothing answers. The specification's `AWAIT_STATE
    disconnected` becomes an assertion on the recorded sequence.
    """
    connection_states = []

    def record(change):
        connection_states.append(change.current)

    client.connection.on(record)
    mock_ws.on_connection_attempt = lambda conn: None
    mock_ws.simulate_disconnect()
    await poll_until(
        lambda: ConnectionState.DISCONNECTED in connection_states,
        OPERATION_TIMEOUT,
        'the connection to reach DISCONNECTED',
    )
    await settle()


async def reconnect_transport(client, mock_ws):
    """Ends the transport and waits for the connection to be re-established."""
    reconnections = []

    def record(change):
        reconnections.append(change)

    client.connection.on(ConnectionState.CONNECTED, record)
    mock_ws.simulate_disconnect()
    await poll_until(lambda: reconnections, OPERATION_TIMEOUT, 'the connection to be re-established')


# UTS: realtime/unit/RTL3e/disconnected-attached-noop-0
async def test_rtl3e_disconnected_attached_noop():
    channel_name = 'test-RTL3e-attached'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attach_and_detach(mock_ws)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    channel_state_changes = record_channel_states(channel)

    await drop_transport(client, mock_ws)

    assert channel.state == ChannelState.ATTACHED
    assert len(channel_state_changes) == 0


# UTS: realtime/unit/RTL3e/disconnected-attaching-noop-1
async def test_rtl3e_disconnected_attaching_noop():
    channel_name = 'test-RTL3e-attaching'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = swallow_attach(mock_ws)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    attach_future = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    channel_state_changes = record_channel_states(channel)

    await drop_transport(client, mock_ws)

    assert channel.state == ChannelState.ATTACHING
    assert len(channel_state_changes) == 0
    attach_future.cancel()


# UTS: realtime/unit/RTL3a/failed-attached-to-failed-0
@deviation
async def test_rtl3a_failed_attached_to_failed():
    channel_name = 'test-RTL3a-attached'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attach_and_detach(mock_ws)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    channel_state_changes = record_channel_states(channel)

    mock_ws.send_to_client_and_close(ACCOUNT_DISABLED)
    await await_connection_state(client, ConnectionState.FAILED)
    await settle()

    assert channel.state == ChannelState.FAILED
    assert channel.error_reason is not None
    assert channel.error_reason.code == 40198

    assert len(channel_state_changes) >= 1
    failed_change = next(
        (c for c in channel_state_changes if c.current == ChannelState.FAILED), None)
    assert failed_change is not None
    assert failed_change.previous == ChannelState.ATTACHED
    assert failed_change.reason is not None
    assert failed_change.reason.code == 40198


# UTS: realtime/unit/RTL3a/failed-attaching-to-failed-1
@deviation
async def test_rtl3a_failed_attaching_to_failed():
    channel_name = 'test-RTL3a-attaching'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = swallow_attach(mock_ws)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    attach_future = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    channel_state_changes = record_channel_states(channel)

    mock_ws.send_to_client_and_close(ACCOUNT_DISABLED)
    await await_connection_state(client, ConnectionState.FAILED)
    await settle()

    # Asserted ahead of the pending attach, which the specification has fail:
    # the attach only ends once the channel state does change
    assert channel.state == ChannelState.FAILED
    assert channel.error_reason is not None

    with pytest.raises(AblyException):
        await asyncio.wait_for(attach_future, OPERATION_TIMEOUT)

    failed_change = next(
        (c for c in channel_state_changes if c.current == ChannelState.FAILED), None)
    assert failed_change is not None
    assert failed_change.previous == ChannelState.ATTACHING


# UTS: realtime/unit/RTL3a/other-states-unaffected-2
async def test_rtl3a_other_states_unaffected():
    initialized_channel_name = 'test-RTL3a-init'
    detached_channel_name = 'test-RTL3a-detached'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attach_and_detach(mock_ws)
    client = await connected_client(mock_ws)
    initialized_channel = client.channels.get(initialized_channel_name)
    detached_channel = client.channels.get(detached_channel_name)

    assert initialized_channel.state == ChannelState.INITIALIZED

    await asyncio.wait_for(detached_channel.attach(), OPERATION_TIMEOUT)
    await asyncio.wait_for(detached_channel.detach(), OPERATION_TIMEOUT)
    assert detached_channel.state == ChannelState.DETACHED

    init_changes = record_channel_states(initialized_channel)
    detached_changes = record_channel_states(detached_channel)

    mock_ws.send_to_client_and_close(ACCOUNT_DISABLED)
    await await_connection_state(client, ConnectionState.FAILED)
    await settle()

    assert initialized_channel.state == ChannelState.INITIALIZED
    assert detached_channel.state == ChannelState.DETACHED
    assert len(init_changes) == 0
    assert len(detached_changes) == 0


# UTS: realtime/unit/RTL3b/closed-attached-to-detached-0
async def test_rtl3b_closed_attached_to_detached():
    channel_name = 'test-RTL3b'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attach_and_detach(mock_ws)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    channel_state_changes = record_channel_states(channel)

    await asyncio.wait_for(client.close(), OPERATION_TIMEOUT)
    assert client.connection.state == ConnectionState.CLOSED

    assert channel.state == ChannelState.DETACHED

    detached_change = next(
        (c for c in channel_state_changes if c.current == ChannelState.DETACHED), None)
    assert detached_change is not None
    assert detached_change.previous == ChannelState.ATTACHED


# UTS: realtime/unit/RTL3b/closed-attaching-to-detached-1
async def test_rtl3b_closed_attaching_to_detached():
    channel_name = 'test-RTL3b-attaching'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = swallow_attach(mock_ws)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    attach_future = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    channel_state_changes = record_channel_states(channel)

    await asyncio.wait_for(client.close(), OPERATION_TIMEOUT)
    assert client.connection.state == ConnectionState.CLOSED

    # The specification has the pending attach fail. ably-python's `attach()`
    # raises only for SUSPENDED and FAILED, so the DETACHED which RTL3b brings
    # about resolves it instead. See deviations-channels-state.md
    assert await asyncio.wait_for(attach_future, OPERATION_TIMEOUT) is None

    assert channel.state == ChannelState.DETACHED

    detached_change = next(
        (c for c in channel_state_changes if c.current == ChannelState.DETACHED), None)
    assert detached_change is not None
    assert detached_change.previous == ChannelState.ATTACHING


# UTS: realtime/unit/RTL3c/suspended-attached-to-suspended-0
async def test_rtl3c_suspended_attached_to_suspended():
    channel_name = 'test-RTL3c'
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )
    mock_ws.on_message_from_client = echo_attach_and_detach(mock_ws)
    # A refused attempt is only given up on when the connecting transition timer
    # expires, so a short request timeout keeps each retry cycle short
    client = realtime_client(
        mock_ws, clock=clock, disconnected_retry_timeout=1000, realtime_request_timeout=300)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED

    channel_state_changes = record_channel_states(channel)

    mock_ws.on_connection_attempt = lambda conn: conn.respond_with_refused()
    mock_ws.simulate_disconnect()
    await settle()

    await advance_to_connection_state(client, clock, ConnectionState.SUSPENDED, step=5000, limit=30)

    assert channel.state == ChannelState.SUSPENDED

    suspended_change = next(
        (c for c in channel_state_changes if c.current == ChannelState.SUSPENDED), None)
    assert suspended_change is not None
    assert suspended_change.previous == ChannelState.ATTACHED


# UTS: realtime/unit/RTL3c/suspended-attaching-to-suspended-1
async def test_rtl3c_suspended_attaching_to_suspended():
    channel_name = 'test-RTL3c-attaching'
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )
    mock_ws.on_message_from_client = swallow_attach(mock_ws)
    # The channel's attach timeout and the connection's transition timeout are
    # the same option, so it is set beyond the connection state TTL: otherwise
    # RTL4f suspends the channel on its own before the connection gets there,
    # and the transition RTL3c is about never happens
    client = realtime_client(
        mock_ws, clock=clock, disconnected_retry_timeout=1000, realtime_request_timeout=300000)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    attach_future = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)

    channel_state_changes = record_channel_states(channel)

    mock_ws.on_connection_attempt = lambda conn: conn.respond_with_refused()
    mock_ws.simulate_disconnect()
    await settle()

    await advance_to_connection_state(client, clock, ConnectionState.SUSPENDED, step=5000, limit=30)

    assert channel.state == ChannelState.SUSPENDED

    suspended_change = next(
        (c for c in channel_state_changes if c.current == ChannelState.SUSPENDED), None)
    assert suspended_change is not None
    assert suspended_change.previous == ChannelState.ATTACHING

    with pytest.raises(AblyException):
        await asyncio.wait_for(attach_future, OPERATION_TIMEOUT)


# UTS: realtime/unit/RTL3d/reattach-attached-with-serial-0
async def test_rtl3d_reattach_attached_with_serial():
    channel_name = 'test-RTL3d-attached'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attach_and_detach(
        mock_ws, attach_messages, channelSerial='serial-001')
    client = await connected_client(mock_ws, disconnected_retry_timeout=100)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 1

    channel_state_changes = record_channel_states(channel)

    await reconnect_transport(client, mock_ws)
    # The channel is ATTACHED throughout the re-attach's opening moments, so the
    # second ATTACH is what marks the re-attach having started
    await poll_until(lambda: len(attach_messages) == 2, OPERATION_TIMEOUT, 'a second ATTACH')
    await await_channel_state(channel, ChannelState.ATTACHED, OPERATION_TIMEOUT)

    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 2

    assert attach_messages[1].get('channelSerial') == 'serial-001'

    observed = [c.current for c in channel_state_changes]
    assert contains_in_order(observed, [ChannelState.ATTACHING, ChannelState.ATTACHED])


# UTS: realtime/unit/RTL3d/reattach-suspended-channels-1
async def test_rtl3d_reattach_suspended_channels():
    channel_name = 'test-RTL3d-suspended'
    attach_messages = []
    clock = FakeClock()

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )
    mock_ws.on_message_from_client = echo_attach_and_detach(mock_ws, attach_messages)
    client = realtime_client(
        mock_ws, clock=clock, disconnected_retry_timeout=1000, suspended_retry_timeout=2000,
        realtime_request_timeout=300)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) == 1

    mock_ws.on_connection_attempt = lambda conn: conn.respond_with_refused()
    mock_ws.simulate_disconnect()
    await settle()

    await advance_to_connection_state(client, clock, ConnectionState.SUSPENDED, step=5000, limit=30)
    assert channel.state == ChannelState.SUSPENDED

    channel_state_changes = record_channel_states(channel)

    mock_ws.on_connection_attempt = lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE)

    await advance_to_connection_state(client, clock, ConnectionState.CONNECTED, step=2500, limit=10)
    await await_channel_state(channel, ChannelState.ATTACHED, OPERATION_TIMEOUT)

    assert channel.state == ChannelState.ATTACHED
    assert len(attach_messages) >= 2

    observed = [c.current for c in channel_state_changes]
    assert contains_in_order(observed, [ChannelState.ATTACHING, ChannelState.ATTACHED])


# UTS: realtime/unit/RTL3d/init-detached-not-reattached-2
async def test_rtl3d_init_detached_not_reattached():
    initialized_channel_name = 'test-RTL3d-init'
    detached_channel_name = 'test-RTL3d-detached'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attach_and_detach(mock_ws, attach_messages)
    client = await connected_client(mock_ws, disconnected_retry_timeout=100)
    initialized_channel = client.channels.get(initialized_channel_name)
    detached_channel = client.channels.get(detached_channel_name)

    assert initialized_channel.state == ChannelState.INITIALIZED

    await asyncio.wait_for(detached_channel.attach(), OPERATION_TIMEOUT)
    await asyncio.wait_for(detached_channel.detach(), OPERATION_TIMEOUT)
    assert detached_channel.state == ChannelState.DETACHED

    attach_count_before = len(attach_messages)

    init_changes = record_channel_states(initialized_channel)
    detached_changes = record_channel_states(detached_channel)

    await reconnect_transport(client, mock_ws)
    await settle()

    assert initialized_channel.state == ChannelState.INITIALIZED
    assert detached_channel.state == ChannelState.DETACHED
    assert len(init_changes) == 0
    assert len(detached_changes) == 0

    new_attach_channels = [m.get('channel') for m in attach_messages[attach_count_before:]]
    assert initialized_channel_name not in new_attach_channels
    assert detached_channel_name not in new_attach_channels


# UTS: realtime/unit/RTL3d/multiple-channels-reattached-3
async def test_rtl3d_multiple_channels_reattached():
    channel1_name = 'test-RTL3d-multi1'
    channel2_name = 'test-RTL3d-multi2'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attach_and_detach(mock_ws, attach_messages)
    client = await connected_client(mock_ws, disconnected_retry_timeout=100)
    channel1 = client.channels.get(channel1_name)
    channel2 = client.channels.get(channel2_name)

    await asyncio.wait_for(channel1.attach(), OPERATION_TIMEOUT)
    await asyncio.wait_for(channel2.attach(), OPERATION_TIMEOUT)
    assert channel1.state == ChannelState.ATTACHED
    assert channel2.state == ChannelState.ATTACHED

    attach_count_before = len(attach_messages)

    await reconnect_transport(client, mock_ws)
    await poll_until(
        lambda: len(attach_messages) == attach_count_before + 2,
        OPERATION_TIMEOUT,
        'both channels to re-attach',
    )
    await await_channel_state(channel1, ChannelState.ATTACHED, OPERATION_TIMEOUT)
    await await_channel_state(channel2, ChannelState.ATTACHED, OPERATION_TIMEOUT)

    assert channel1.state == ChannelState.ATTACHED
    assert channel2.state == ChannelState.ATTACHED

    new_attach_channels = [m.get('channel') for m in attach_messages[attach_count_before:]]
    assert channel1_name in new_attach_channels
    assert channel2_name in new_attach_channels
