"""Derived from uts/realtime/unit/channels/channel_state_events.md in ably/specification.

Spec points: RTL2, RTL2a, RTL2b, RTL2d, RTL2g, RTL2i, RTL4c, RTL24, TH1, TH2, TH3, TH5, TH6
"""

import asyncio

import pytest

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelstate import ChannelState, ChannelStateChange
from ably.types.flags import Flag
from ably.util.exceptions import AblyException
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import MockWebSocket, attached_message, connected_message

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')

# How long an operation which the specification expects to settle is given
# before a test calls it hung
OPERATION_TIMEOUT = 1.0


def channel_error_message(channel, code, message, status_code=None):
    """An ERROR protocol message scoped to `channel`."""
    error = {'code': code, 'message': message}
    if status_code is not None:
        error['statusCode'] = status_code
    return {'action': int(ProtocolMessageAction.ERROR), 'channel': channel, 'error': error}


def echo_attached(mock_ws, **attached_fields):
    """A handler confirming each ATTACH with an ATTACHED for the same channel."""
    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(msg.get('channel'), **attached_fields))
    return on_message_from_client


def capture_last(channel, event):
    """Keeps the most recent state change `channel` emits for `event`.

    `ChannelStateChange` carries no `event` attribute, so the event a change was
    emitted for is the key it is registered against. A single-element list
    stands in for the specification's nullable `captured_change`.
    """
    captured = []

    def record(change):
        captured.append(change)

    channel.on(event, record)
    return captured


async def connected_client(mock_ws, **kwargs):
    """A client connected through `mock_ws`."""
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


# UTS: realtime/unit/RTL2b/channel-state-attribute-0
async def test_rtl2b_channel_state_attribute():
    channel_name = 'test-RTL2b'

    client = realtime_client()
    channel = client.channels.get(channel_name)

    assert isinstance(channel.state, ChannelState)
    assert channel.state == ChannelState.INITIALIZED


# UTS: realtime/unit/RTL2b/initial-state-initialized-1
async def test_rtl2b_initial_state_initialized():
    channel_name = 'test-RTL2b-init'

    client = realtime_client()

    channel = client.channels.get(channel_name)

    assert channel.state == ChannelState.INITIALIZED


# UTS: realtime/unit/RTL2a/state-change-events-emitted-0
async def test_rtl2a_state_change_events_emitted():
    channel_name = 'test-RTL2a'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    state_changes = []

    def record(change):
        state_changes.append(change)

    channel.on(record)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    mock_ws.on_message_from_client = echo_attached(mock_ws)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert len(state_changes) >= 2
    assert state_changes[0].current == ChannelState.ATTACHING
    assert state_changes[0].previous == ChannelState.INITIALIZED
    assert state_changes[1].current == ChannelState.ATTACHED
    assert state_changes[1].previous == ChannelState.ATTACHING


# UTS: realtime/unit/RTL2d/state-change-object-structure-0
async def test_rtl2d_state_change_object_structure():
    channel_name = 'test-RTL2d'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attached(mock_ws)
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    # TH5 has the change carry the event that generated it; ably-python's
    # ChannelStateChange is (previous, current, resumed, reason), so the event is
    # read from the key the listener is registered against. See
    # deviations.md
    captured = capture_last(channel, ChannelState.ATTACHING)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert captured
    captured_change = captured[0]
    assert isinstance(captured_change, ChannelStateChange)
    assert captured_change.current == ChannelState.ATTACHING
    assert captured_change.previous == ChannelState.INITIALIZED


# UTS: realtime/unit/RTL2d/state-change-error-reason-1
async def test_rtl2d_state_change_error_reason():
    channel_name = 'test-RTL2d-error'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(
                channel_error_message(msg.get('channel'), 40160, 'Channel denied', 401))

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    captured = capture_last(channel, ChannelState.FAILED)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    with pytest.raises(AblyException):
        await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert captured
    captured_change = captured[0]
    assert captured_change.current == ChannelState.FAILED
    assert captured_change.reason is not None
    assert captured_change.reason.code == 40160
    assert captured_change.reason.message == 'Channel denied'


# UTS: realtime/unit/RTL2/filtered-event-subscription-0
async def test_rtl2_filtered_event_subscription():
    channel_name = 'test-RTL2-filtered'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attached(mock_ws)
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    attached_events = []

    def record(change):
        attached_events.append(change)

    channel.on(ChannelState.ATTACHED, record)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert len(attached_events) == 1
    assert attached_events[0].current == ChannelState.ATTACHED
    # The event which produced the change is the key the listener is registered
    # against, ATTACHED here


# UTS: realtime/unit/RTL2g/update-event-condition-change-0
async def test_rtl2g_update_event_condition_change():
    channel_name = 'test-RTL2g'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attached(mock_ws)
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    update_events = []

    def record(change):
        update_events.append(change)

    channel.on('update', record)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    # A further ATTACHED without the RESUMED flag stands for a loss of message
    # continuity, which RTL12 reports as an UPDATE rather than a state change
    mock_ws.send_to_client(attached_message(channel_name))
    await settle()

    assert channel.state == ChannelState.ATTACHED
    assert len(update_events) == 1
    assert update_events[0].current == ChannelState.ATTACHED
    assert update_events[0].previous == ChannelState.ATTACHED
    assert update_events[0].resumed is False


# UTS: realtime/unit/RTL2g/no-duplicate-state-events-1
async def test_rtl2g_no_duplicate_state_events():
    channel_name = 'test-RTL2g-nodup'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attached(mock_ws)
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    all_events = []

    def record_all(change):
        all_events.append(change)

    # The specification filters `all_events` on `event == attached` to separate
    # the ATTACHED state event from the RTL12 UPDATE. Without an `event`
    # attribute the two are told apart by the key they arrive on
    attached_state_events = []

    def record_attached(change):
        attached_state_events.append(change)

    channel.on(record_all)
    channel.on(ChannelState.ATTACHED, record_attached)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    initial_count = len(all_events)
    assert initial_count >= 2

    mock_ws.send_to_client(attached_message(channel_name))
    await settle()

    assert len(attached_state_events) == 1


# UTS: realtime/unit/RTL2i/has-backlog-flag-true-0
@deviation
async def test_rtl2i_has_backlog_flag_true():
    channel_name = 'test-RTL2i'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attached(mock_ws, flags=int(Flag.HAS_BACKLOG))
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    captured = capture_last(channel, ChannelState.ATTACHED)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert captured
    assert captured[0].has_backlog is True


# UTS: realtime/unit/RTL2i/has-backlog-flag-false-1
async def test_rtl2i_has_backlog_flag_false():
    channel_name = 'test-RTL2i-false'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attached(mock_ws)
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    captured = capture_last(channel, ChannelState.ATTACHED)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert captured
    # RTL2i makes `hasBacklog` optional, and the specification accepts false or
    # null. ably-python's ChannelStateChange carries no such attribute
    has_backlog = getattr(captured[0], 'has_backlog', None)
    assert has_backlog is False or has_backlog is None


# UTS: realtime/unit/RTL2d/resumed-flag-propagated-2
async def test_rtl2d_resumed_flag_propagated():
    channel_name = 'test-RTL2d-resumed'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = echo_attached(mock_ws, flags=int(Flag.RESUMED))
    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    captured = capture_last(channel, ChannelState.ATTACHED)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert captured
    assert captured[0].resumed is True


# UTS: realtime/unit/RTL24/error-reason-populated-0
async def test_rtl24_error_reason_populated():
    channel_name = 'test-errorReason'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(
                channel_error_message(msg.get('channel'), 40160, 'Not authorized', 401))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    with pytest.raises(AblyException):
        await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert channel.state == ChannelState.FAILED
    assert channel.error_reason is not None
    assert channel.error_reason.code == 40160
    assert channel.error_reason.message == 'Not authorized'


# UTS: realtime/unit/RTL4c/error-reason-cleared-attach-0
async def test_rtl4c_error_reason_cleared_attach():
    channel_name = 'test-errorReason-clear'
    attach_count = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_count.append(msg)
            if len(attach_count) == 1:
                mock_ws.send_to_client(channel_error_message(msg.get('channel'), 40160, 'Denied'))
            else:
                mock_ws.send_to_client(attached_message(msg.get('channel')))

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
