"""Derived from uts/realtime/unit/channels/channel_properties.md in ably/specification.

Spec points: RTL15, RTL15b, RTL15b2, RTL15c

RTL15's `RealtimeChannel#properties` object is absent from ably-python; the two
serials it holds are kept as private fields on the channel. These tests read
them through the accessors below, so that what RTL15b and RTL15c require of the
serials is exercised even though the object that should carry them is missing.
"""

import asyncio

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.channelstate import ChannelState
from ably.types.flags import Flag
from test.uts.helpers.client import (
    await_channel_state,
    await_connection_state,
    poll_until,
    realtime_client,
)
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import (
    CONNECTED_MESSAGE,
    CONNECTED_MESSAGE_NO_IDLE,
    MockWebSocket,
    attached_message,
    detached_message,
    server_detached_message,
)

# How long an operation which the specification expects to settle is given
# before a test calls it hung
OPERATION_TIMEOUT = 1.0


def attach_serial(channel):
    """The channel's `attachSerial`, which the library keeps privately."""
    return channel._RealtimeChannel__attach_serial


def channel_serial(channel):
    """The channel's `channelSerial`, which the library keeps privately."""
    return channel._RealtimeChannel__channel_serial


def message_message(channel, channel_serial=None, messages=None):
    """A MESSAGE protocol message carrying one message for `channel`."""
    msg = {
        'action': int(ProtocolMessageAction.MESSAGE),
        'channel': channel,
        'messages': messages if messages is not None else [{'name': 'event', 'data': 'data'}],
    }
    if channel_serial is not None:
        msg['channelSerial'] = channel_serial
    return msg


def presence_message(channel, channel_serial):
    """A PRESENCE protocol message with no members, sent for its serial alone."""
    return {
        'action': int(ProtocolMessageAction.PRESENCE),
        'channel': channel,
        'channelSerial': channel_serial,
        'presence': [],
    }


def channel_error_message(channel, code, message, status_code):
    """An ERROR message scoped to a channel, which RTN15i routes to that channel."""
    return {
        'action': int(ProtocolMessageAction.ERROR),
        'channel': channel,
        'error': {'code': code, 'statusCode': status_code, 'message': message},
    }


def attach_responder(mock_ws, serial_for_attach):
    """Answers each ATTACH with an ATTACHED whose serial `serial_for_attach` decides."""
    attach_count = 0

    def on_message_from_client(msg):
        nonlocal attach_count
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_count += 1
            serial = serial_for_attach(attach_count)
            if serial is not None:
                mock_ws.send_to_client(attached_message(msg.get('channel'), channelSerial=serial))
        elif msg.get('action') == ProtocolMessageAction.DETACH:
            mock_ws.send_to_client(detached_message(msg.get('channel')))

    return on_message_from_client


async def connected_client(mock_ws, **kwargs):
    """A client connected through `mock_ws`, which the channel tests open with."""
    client = realtime_client(mock_ws, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


# UTS: realtime/unit/RTL15c/attach-serial-from-attached-0
async def test_rtl15c_attach_serial_from_attached():
    channel_name = 'test-RTL15c'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = attach_responder(
        mock_ws, lambda count: f'attach-serial-{count}')

    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    assert attach_serial(channel) is None

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert attach_serial(channel) == 'attach-serial-1'

    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)
    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert attach_serial(channel) == 'attach-serial-2'


# UTS: realtime/unit/RTL15c/attach-serial-server-reattach-1
async def test_rtl15c_attach_serial_server_reattach():
    channel_name = 'test-RTL15c-update'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = attach_responder(mock_ws, lambda count: 'initial-serial')

    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert attach_serial(channel) == 'initial-serial'

    # An unsolicited ATTACHED with no RESUMED flag, which RTL12 treats as an update
    mock_ws.send_to_client(attached_message(channel_name, channelSerial='updated-serial'))
    await poll_until(
        lambda: attach_serial(channel) == 'updated-serial',
        OPERATION_TIMEOUT, "attachSerial is updated")

    assert attach_serial(channel) == 'updated-serial'


# UTS: realtime/unit/RTL15c/attach-serial-not-updated-resumed-2
@deviation
async def test_rtl15c_attach_serial_not_updated_resumed():
    # DEVIATION: RTL15c updates attachSerial only from an ATTACHED whose `resumed` is false.
    # `_on_message` (`ably/realtime/channel.py:708`) assigns `__attach_serial` from every
    # ATTACHED, before it has looked at the flags, so a resumed ATTACHED overwrites it.
    channel_name = 'test-RTL15c-resumed'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = attach_responder(mock_ws, lambda count: 'initial-serial')

    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert attach_serial(channel) == 'initial-serial'

    mock_ws.send_to_client(attached_message(
        channel_name, channelSerial='resumed-serial', flags=int(Flag.RESUMED)))

    # channelSerial is updated per RTL15b whatever the RESUMED flag says, which
    # shows that the message has been processed
    await poll_until(
        lambda: channel_serial(channel) == 'resumed-serial',
        OPERATION_TIMEOUT, "channelSerial is updated")

    assert attach_serial(channel) == 'initial-serial'


# UTS: realtime/unit/RTL15b/channel-serial-from-attached-0
async def test_rtl15b_channel_serial_from_attached():
    channel_name = 'test-RTL15b-attached'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = attach_responder(mock_ws, lambda count: 'serial-001')

    client = realtime_client(mock_ws)
    channel = client.channels.get(channel_name)

    assert channel_serial(channel) is None

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)

    assert channel_serial(channel) == 'serial-001'


# UTS: realtime/unit/RTL15b/channel-serial-from-messages-1
@deviation
async def test_rtl15b_channel_serial_from_messages():
    # DEVIATION: RTL15b updates channelSerial for a PRESENCE action as it does for MESSAGE.
    # The PRESENCE branch of `_on_message` (`ably/realtime/channel.py:751`) hands the members
    # to the presence map and never touches `__channel_serial`, so it keeps the serial of the
    # last MESSAGE. The MESSAGE half of this test passes.
    channel_name = 'test-RTL15b-messages'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = attach_responder(mock_ws, lambda count: 'serial-001')

    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel_serial(channel) == 'serial-001'

    mock_ws.send_to_client(message_message(channel_name, channel_serial='serial-002'))
    await poll_until(
        lambda: channel_serial(channel) == 'serial-002',
        OPERATION_TIMEOUT, "channelSerial follows the MESSAGE")

    mock_ws.send_to_client(presence_message(channel_name, 'serial-003'))
    await settle()

    assert channel_serial(channel) == 'serial-003'


# UTS: realtime/unit/RTL15b/serial-not-updated-empty-2
@deviation
async def test_rtl15b_serial_not_updated_empty():
    # DEVIATION: RTL15b sets channelSerial from a protocol message only where the field is
    # populated. `_on_message` (`ably/realtime/channel.py:743`) assigns it unconditionally
    # for a MESSAGE, so a MESSAGE with no channelSerial sets the channel's serial to null.
    channel_name = 'test-RTL15b-noupdate'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = attach_responder(mock_ws, lambda count: 'serial-001')

    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel_serial(channel) == 'serial-001'

    mock_ws.send_to_client(message_message(channel_name))
    await settle()

    assert channel_serial(channel) == 'serial-001'


# UTS: realtime/unit/RTL15b/serial-not-updated-irrelevant-3
async def test_rtl15b_serial_not_updated_irrelevant():
    channel_name = 'test-RTL15b-irrelevant'
    attach_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )

    def on_message_from_client(msg):
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_messages.append(msg)
            mock_ws.send_to_client(attached_message(msg.get('channel'), channelSerial='serial-001'))

    mock_ws.on_message_from_client = on_message_from_client
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel_serial(channel) == 'serial-001'

    detached = server_detached_message(channel_name, 90198, 'Detached', status_code=500)
    detached['channelSerial'] = 'serial-should-not-apply'
    mock_ws.send_to_client(detached)

    # RTL13a reattaches; waiting for the second ATTACH keeps the wait off the
    # ATTACHED state the channel still holds at this point
    await poll_until(lambda: len(attach_messages) == 2, OPERATION_TIMEOUT, "a second ATTACH")
    await await_channel_state(channel, ChannelState.ATTACHED, OPERATION_TIMEOUT)

    assert len(attach_messages) == 2
    assert channel_serial(channel) == 'serial-001'


# UTS: realtime/unit/RTL15b2/serial-cleared-detached-0
async def test_rtl15b2_serial_cleared_detached():
    channel_name = 'test-RTL15b1-detached'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = attach_responder(mock_ws, lambda count: 'serial-001')

    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel_serial(channel) == 'serial-001'

    await asyncio.wait_for(channel.detach(), OPERATION_TIMEOUT)

    assert channel.state == ChannelState.DETACHED
    assert channel_serial(channel) is None


# UTS: realtime/unit/RTL15b2/serial-retained-suspended-1
@deviation
async def test_rtl15b2_serial_retained_suspended():
    # DEVIATION: RTL15b2 clears channelSerial only for DETACHED and FAILED, keeping it
    # through SUSPENDED so that the next ATTACH can carry it (RTL4c1). `_notify_state`
    # (`ably/realtime/channel.py:812`) clears it for SUSPENDED too, under a comment naming
    # the superseded RTP5a1.
    channel_name = 'test-RTL15b2-suspended'
    clock = FakeClock()
    attach_count = 0

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE_NO_IDLE),
    )

    def on_message_from_client(msg):
        nonlocal attach_count
        if msg.get('action') == ProtocolMessageAction.ATTACH:
            attach_count += 1
            if attach_count == 1:
                mock_ws.send_to_client(attached_message(msg.get('channel'), channelSerial='serial-001'))
            # A second ATTACH goes unanswered, so it times out into SUSPENDED

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(mock_ws, clock=clock, realtime_request_timeout=100)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel_serial(channel) == 'serial-001'

    mock_ws.send_to_client(
        server_detached_message(channel_name, 90198, 'Detached', status_code=500))
    await await_channel_state(channel, ChannelState.ATTACHING, OPERATION_TIMEOUT)
    await settle()

    await clock.advance(150)
    await await_channel_state(channel, ChannelState.SUSPENDED, OPERATION_TIMEOUT)

    assert channel.state == ChannelState.SUSPENDED
    assert channel_serial(channel) == 'serial-001'


# UTS: realtime/unit/RTL15b2/serial-cleared-failed-2
async def test_rtl15b2_serial_cleared_failed():
    channel_name = 'test-RTL15b2-failed'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    mock_ws.on_message_from_client = attach_responder(mock_ws, lambda count: 'serial-001')

    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await asyncio.wait_for(channel.attach(), OPERATION_TIMEOUT)
    assert channel_serial(channel) == 'serial-001'

    mock_ws.send_to_client(channel_error_message(channel_name, 40160, 'Not permitted', 401))
    await await_channel_state(channel, ChannelState.FAILED, OPERATION_TIMEOUT)

    assert channel.state == ChannelState.FAILED
    assert channel_serial(channel) is None
