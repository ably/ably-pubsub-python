"""Derived from uts/realtime/unit/channels/channel_publish.md in ably/specification.

Spec points: RTN7d, RTN7e, RTN19a, RTN19a2, RTN19b

The RTL6 sections of the same specification are derived in `channel_publish_test.py`,
which these tests share their setup helpers with. The two files split one specification
between publishing itself and the fate of a message still awaiting its ACK.

`RealtimeChannel.publish()` resolves on the ACK (RTL6b), so a publish these
specifications deliberately leave unacknowledged is driven as a task and awaited once the
state change under test has happened.
"""

import asyncio

import pytest

from ably.realtime.channel import ChannelState
from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.operations import PublishResult
from ably.util.exceptions import AblyException
from test.uts.helpers.client import (
    STATE_TIMEOUT,
    await_channel_state,
    await_connection_state,
    next_connection_state,
    poll_until,
)
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message
from test.uts.realtime.unit.channels.channel_publish_test import (
    CONNECTED_MESSAGE,
    ack_message,
    advance_until_suspended,
    attached_message,
    connected_client,
    published,
    random_id,
)


def attach_only_server(mock_ws):
    """Answers an ATTACH with ATTACHED and leaves every MESSAGE unacknowledged."""
    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(msg['channel']))

    return on_message_from_client


async def await_published(mock_ws, count=1):
    """Waits until `count` MESSAGE ProtocolMessages have left the client.

    A publish awaiting its ACK is in flight rather than in any state, so it is
    the message on the wire that says the premise holds.
    """
    await poll_until(lambda: len(published(mock_ws)) >= count,
                     description=f'{count} MESSAGE(s) sent')


# UTS: realtime/unit/RTN7e/pending-fail-suspended-0
async def test_rtn7e_pending_fail_suspended():
    channel_name = f'test-RTN7e-suspended-{random_id()}'
    clock = FakeClock()
    attempt_count = 0

    def on_connection_attempt(conn):
        nonlocal attempt_count
        attempt_count += 1
        # The specification installs a second mock which refuses every attempt;
        # the mock is installed once here and refuses from the second attempt on
        if attempt_count == 1:
            conn.respond_with_success(CONNECTED_MESSAGE)
        else:
            conn.respond_with_refused()

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    mock_ws.on_message_from_client = attach_only_server(mock_ws)
    client = await connected_client(mock_ws, clock=clock, disconnected_retry_timeout=1000)
    channel = client.channels.get(channel_name)

    await channel.attach()

    publish_task = asyncio.ensure_future(channel.publish('pending', 'data'))
    await await_published(mock_ws)

    mock_ws.simulate_disconnect()
    await settle()

    await advance_until_suspended(client, clock)
    assert client.connection.state == ConnectionState.SUSPENDED

    with pytest.raises(AblyException) as error:
        await asyncio.wait_for(publish_task, STATE_TIMEOUT)

    assert error.value.code is not None


# UTS: realtime/unit/RTN7e/pending-fail-closed-1
async def test_rtn7e_pending_fail_closed():
    channel_name = f'test-RTN7e-closed-{random_id()}'
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE))
    mock_ws.on_message_from_client = attach_only_server(mock_ws)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    publish_task = asyncio.ensure_future(channel.publish('pending', 'data'))
    await await_published(mock_ws)

    await client.close()
    assert client.connection.state == ConnectionState.CLOSED

    with pytest.raises(AblyException) as error:
        await asyncio.wait_for(publish_task, STATE_TIMEOUT)

    assert error.value.code is not None


# UTS: realtime/unit/RTN7e/pending-fail-failed-2
# DEVIATION RTN7e: a connection-level ERROR reaches FAILED through
# `ConnectionManager.on_error` -> `enact_state_change`
# (`ably/realtime/connectionmanager.py:477`), which never calls
# `fail_queued_messages`. The message stays pending and the publish never resolves.
# See deviations-channels-publish.md.
@deviation
async def test_rtn7e_pending_fail_failed():
    channel_name = f'test-RTN7e-failed-{random_id()}'
    attempt_count = 0

    def on_connection_attempt(conn):
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count == 1:
            conn.respond_with_success(CONNECTED_MESSAGE)
        else:
            conn.respond_with_success()

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.MESSAGE:
            # The message is left unacknowledged and a fatal error forces FAILED
            mock_ws.send_to_client_and_close({
                'action': int(ProtocolMessageAction.ERROR),
                'error': {'code': 80000, 'statusCode': 400, 'message': 'Fatal error'},
            })

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt,
                            on_message_from_client=on_message_from_client)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    publish_task = asyncio.ensure_future(channel.publish('pending', 'data'))

    await await_connection_state(client, ConnectionState.FAILED)

    with pytest.raises(AblyException) as error:
        await asyncio.wait_for(publish_task, STATE_TIMEOUT)

    assert error.value.code is not None


# UTS: realtime/unit/RTN7e/multiple-pending-fail-3
async def test_rtn7e_multiple_pending_fail():
    channel_name = f'test-RTN7e-multi-{random_id()}'
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE))
    mock_ws.on_message_from_client = attach_only_server(mock_ws)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    publishes = [
        asyncio.ensure_future(channel.publish('msg1', 'data1')),
        asyncio.ensure_future(channel.publish('msg2', 'data2')),
        asyncio.ensure_future(channel.publish('msg3', 'data3')),
    ]
    await await_published(mock_ws, 3)

    await client.close()

    for publish_task in publishes:
        with pytest.raises(AblyException) as error:
            await asyncio.wait_for(publish_task, STATE_TIMEOUT)
        assert error.value.code is not None


# UTS: realtime/unit/RTN7e/error-represents-reason-4
# DEVIATION RTN7e: as for `pending-fail-failed-2`, nothing fails the pending message when
# a connection-level ERROR drives the connection to FAILED, so no error reaches the
# publish at all — let alone the one that caused the state change. The connection's own
# `error_reason` does carry it. See deviations-channels-publish.md.
@deviation
async def test_rtn7e_error_represents_reason():
    channel_name = f'test-RTN7e-error-reason-{random_id()}'

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.MESSAGE:
            mock_ws.send_to_client_and_close({
                'action': int(ProtocolMessageAction.ERROR),
                'error': {'code': 80019, 'statusCode': 400,
                          'message': 'Connection closed due to admin action'},
            })

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
        on_message_from_client=on_message_from_client)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    publish_task = asyncio.ensure_future(channel.publish('pending', 'data'))

    await await_connection_state(client, ConnectionState.FAILED)

    with pytest.raises(AblyException) as error:
        await asyncio.wait_for(publish_task, STATE_TIMEOUT)

    assert error.value.code == 80019
    assert error.value.status_code == 400
    assert error.value.message == 'Connection closed due to admin action'

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 80019


# UTS: realtime/unit/RTN7d/fail-disconnected-no-queue-0
async def test_rtn7d_fail_disconnected_no_queue():
    channel_name = f'test-RTN7d-{random_id()}'
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE))
    mock_ws.on_message_from_client = attach_only_server(mock_ws)
    client = await connected_client(mock_ws, queue_messages=False)
    channel = client.channels.get(channel_name)

    await channel.attach()

    publish_task = asyncio.ensure_future(channel.publish('pending', 'data'))
    await await_published(mock_ws)

    state_changes = []

    def record(change):
        state_changes.append(change.current)

    client.connection.on(record)

    mock_ws.simulate_disconnect()

    with pytest.raises(AblyException) as error:
        await asyncio.wait_for(publish_task, STATE_TIMEOUT)

    assert error.value.code is not None
    assert ConnectionState.DISCONNECTED in state_changes


# UTS: realtime/unit/RTN7d/survive-disconnected-queue-1
async def test_rtn7d_survive_disconnected_queue():
    channel_name = f'test-RTN7d-default-{random_id()}'
    captured_messages = []
    connection_count = 0

    def on_connection_attempt(conn):
        nonlocal connection_count
        connection_count += 1
        conn.respond_with_success(CONNECTED_MESSAGE)

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.MESSAGE:
            captured_messages.append((connection_count, msg))
            # The first connection leaves the message pending
            if connection_count >= 2:
                mock_ws.send_to_client(ack_message(msg, ['serial-ack']))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt,
                            on_message_from_client=on_message_from_client)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    publish_task = asyncio.ensure_future(channel.publish('pending', 'data'))
    await await_published(mock_ws)

    # RTN15a retries a drop from CONNECTED immediately, so the reconnection
    # needs no time to pass where the specification advances the clock
    reconnected = asyncio.ensure_future(next_connection_state(client, ConnectionState.CONNECTED))
    mock_ws.simulate_disconnect()
    await reconnected

    result = await asyncio.wait_for(publish_task, STATE_TIMEOUT)

    assert isinstance(result, PublishResult)
    assert result.serials[0] == 'serial-ack'


# UTS: realtime/unit/RTN19a/resent-on-new-transport-0
async def test_rtn19a_resent_on_new_transport():
    channel_name = f'test-RTN19a-{random_id()}'
    captured_messages = []
    connection_count = 0

    def on_connection_attempt(conn):
        nonlocal connection_count
        connection_count += 1
        conn.respond_with_success(CONNECTED_MESSAGE)

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.MESSAGE:
            captured_messages.append({'msg': msg, 'connection': connection_count})
            if connection_count >= 2:
                mock_ws.send_to_client(ack_message(msg, ['serial-resent']))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt,
                            on_message_from_client=on_message_from_client)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    publish_task = asyncio.ensure_future(channel.publish('resend-me', 'data'))
    await await_published(mock_ws)

    first_transport_messages = [m for m in captured_messages if m['connection'] == 1]
    assert len(first_transport_messages) == 1

    reconnected = asyncio.ensure_future(next_connection_state(client, ConnectionState.CONNECTED))
    mock_ws.simulate_disconnect()
    await reconnected

    result = await asyncio.wait_for(publish_task, STATE_TIMEOUT)

    second_transport_messages = [m for m in captured_messages if m['connection'] == 2]
    assert len(second_transport_messages) >= 1
    assert second_transport_messages[0]['msg']['messages'][0]['name'] == 'resend-me'

    assert isinstance(result, PublishResult)
    assert result.serials[0] == 'serial-resent'


# UTS: realtime/unit/RTN19a2/same-serial-on-resume-0
async def test_rtn19a2_same_serial_on_resume():
    channel_name = f'test-RTN19a2-resume-{random_id()}'
    captured_messages = []
    original_connection_id = 'connection-abc'
    connection_count = 0

    def on_connection_attempt(conn):
        nonlocal connection_count
        connection_count += 1
        # RTN15c6: the same connectionId on both makes the second a valid resume.
        # The specification puts connectionKey at the top level of the CONNECTED;
        # protocol.md carries it in connectionDetails, which is where it is read from.
        conn.respond_with_success(connected_message(
            original_connection_id, connectionKey=f'key-{connection_count}'))

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.MESSAGE:
            captured_messages.append({'msg': msg, 'connection': connection_count})
            if connection_count >= 2:
                mock_ws.send_to_client(ack_message(msg, ['serial-resumed']))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt,
                            on_message_from_client=on_message_from_client)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    publishes = [
        asyncio.ensure_future(channel.publish('msg1', 'data1')),
        asyncio.ensure_future(channel.publish('msg2', 'data2')),
    ]
    await await_published(mock_ws, 2)

    first_transport_messages = [m for m in captured_messages if m['connection'] == 1]
    original_serial_1 = first_transport_messages[0]['msg']['msgSerial']
    original_serial_2 = first_transport_messages[1]['msg']['msgSerial']

    reconnected = asyncio.ensure_future(next_connection_state(client, ConnectionState.CONNECTED))
    mock_ws.simulate_disconnect()
    await reconnected

    await asyncio.wait_for(asyncio.gather(*publishes), STATE_TIMEOUT)

    second_transport_messages = [m for m in captured_messages if m['connection'] == 2]
    assert len(second_transport_messages) == 2
    assert second_transport_messages[0]['msg']['msgSerial'] == original_serial_1
    assert second_transport_messages[1]['msg']['msgSerial'] == original_serial_2


# UTS: realtime/unit/RTN19a2/new-serial-failed-resume-1
async def test_rtn19a2_new_serial_failed_resume():
    channel_name = f'test-RTN19a2-failed-resume-{random_id()}'
    captured_messages = []
    connection_count = 0

    def on_connection_attempt(conn):
        nonlocal connection_count
        connection_count += 1
        if connection_count == 1:
            conn.respond_with_success(connected_message('connection-first', connectionKey='key-first'))
        else:
            # RTN15c7: a new connectionId with an error is a failed resume
            failed_resume = connected_message('connection-new', connectionKey='key-new')
            failed_resume['error'] = {
                'code': 80018, 'statusCode': 400, 'message': 'Connection not resumable'}
            conn.respond_with_success(failed_resume)

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(channel_name))
        elif msg['action'] == ProtocolMessageAction.MESSAGE:
            captured_messages.append({'msg': msg, 'connection': connection_count})
            if connection_count >= 2:
                mock_ws.send_to_client(ack_message(msg, ['serial-new']))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt,
                            on_message_from_client=on_message_from_client)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    publishes = [
        asyncio.ensure_future(channel.publish('msg1', 'data1')),
        asyncio.ensure_future(channel.publish('msg2', 'data2')),
    ]
    await await_published(mock_ws, 2)

    first_transport_messages = [m for m in captured_messages if m['connection'] == 1]
    assert first_transport_messages[0]['msg']['msgSerial'] == 0
    assert first_transport_messages[1]['msg']['msgSerial'] == 1

    reconnected = asyncio.ensure_future(next_connection_state(client, ConnectionState.CONNECTED))
    mock_ws.simulate_disconnect()
    await reconnected

    await asyncio.wait_for(asyncio.gather(*publishes), STATE_TIMEOUT)

    # NOTE: the specification's assertion cannot distinguish the two behaviours it is
    # written to separate — the original serials are already 0 and 1, so a resend that
    # kept them and a resend that drew fresh ones from a reset counter look identical.
    # See deviations-channels-publish.md; what ably-python actually does is resend the
    # message dictionary unchanged, serial included.
    second_transport_messages = [m for m in captured_messages if m['connection'] == 2]
    assert len(second_transport_messages) == 2
    assert second_transport_messages[0]['msg']['msgSerial'] == 0
    assert second_transport_messages[1]['msg']['msgSerial'] == 1


# UTS: realtime/unit/RTN19b/attach-resent-on-reconnect-0
async def test_rtn19b_attach_resent_on_reconnect():
    channel_name = f'test-RTN19b-attach-{random_id()}'
    captured_attach_messages = []
    connection_count = 0

    def on_connection_attempt(conn):
        nonlocal connection_count
        connection_count += 1
        conn.respond_with_success(CONNECTED_MESSAGE)

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            captured_attach_messages.append({'msg': msg, 'connection': connection_count})
            # The first connection leaves the channel ATTACHING
            if connection_count >= 2:
                mock_ws.send_to_client(attached_message(msg['channel']))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt,
                            on_message_from_client=on_message_from_client)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    attach_task = asyncio.ensure_future(channel.attach())
    await await_channel_state(channel, ChannelState.ATTACHING)

    first_transport_attaches = [m for m in captured_attach_messages if m['connection'] == 1]
    assert len(first_transport_attaches) == 1
    assert first_transport_attaches[0]['msg']['channel'] == channel_name

    reconnected = asyncio.ensure_future(next_connection_state(client, ConnectionState.CONNECTED))
    mock_ws.simulate_disconnect()
    await reconnected

    await asyncio.wait_for(attach_task, STATE_TIMEOUT)

    assert channel.state == ChannelState.ATTACHED

    second_transport_attaches = [m for m in captured_attach_messages if m['connection'] == 2]
    assert len(second_transport_attaches) >= 1
    assert second_transport_attaches[0]['msg']['channel'] == channel_name


# UTS: realtime/unit/RTN19b/detach-resent-on-reconnect-1
async def test_rtn19b_detach_resent_on_reconnect():
    channel_name = f'test-RTN19b-detach-{random_id()}'
    captured_detach_messages = []
    connection_count = 0

    def on_connection_attempt(conn):
        nonlocal connection_count
        connection_count += 1
        conn.respond_with_success(CONNECTED_MESSAGE)

    def on_message_from_client(msg):
        if msg['action'] == ProtocolMessageAction.ATTACH:
            mock_ws.send_to_client(attached_message(msg['channel']))
        elif msg['action'] == ProtocolMessageAction.DETACH:
            captured_detach_messages.append({'msg': msg, 'connection': connection_count})
            # The first connection leaves the channel DETACHING
            if connection_count >= 2:
                mock_ws.send_to_client({'action': int(ProtocolMessageAction.DETACHED),
                                        'channel': msg['channel']})

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt,
                            on_message_from_client=on_message_from_client)
    client = await connected_client(mock_ws)
    channel = client.channels.get(channel_name)

    await channel.attach()

    detach_task = asyncio.ensure_future(channel.detach())
    await await_channel_state(channel, ChannelState.DETACHING)

    first_transport_detaches = [m for m in captured_detach_messages if m['connection'] == 1]
    assert len(first_transport_detaches) == 1

    reconnected = asyncio.ensure_future(next_connection_state(client, ConnectionState.CONNECTED))
    mock_ws.simulate_disconnect()
    await reconnected

    await asyncio.wait_for(detach_task, STATE_TIMEOUT)

    assert channel.state == ChannelState.DETACHED

    second_transport_detaches = [m for m in captured_detach_messages if m['connection'] == 2]
    assert len(second_transport_detaches) >= 1
    assert second_transport_detaches[0]['msg']['channel'] == channel_name
