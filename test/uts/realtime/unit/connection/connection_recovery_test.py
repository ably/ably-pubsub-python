"""Derived from uts/realtime/unit/connection/connection_recovery_test.md in ably/specification.

Spec points: RTN16d, RTN16f, RTN16f1, RTN16g, RTN16g1, RTN16g2, RTN16g3, RTN16i,
RTN16j, RTN16k, RTN16l

RTN16 connection recovery is absent from ably-python: `recover` is a client
option with a property and a setter but is read nowhere in the library, there is
no `recover` connect parameter and no recovery key to create or decode. Every
test here but the malformed-key one is therefore gated; see
deviations-connection-liveness.md.
"""

import asyncio
import json

from ably.realtime.channel import ChannelState
from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from test.uts.helpers.client import await_channel_state, await_connection_state, realtime_client
from test.uts.helpers.clock import FakeClock
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import (
    ERROR_MESSAGE,
    MockWebSocket,
    ack,
    attached_message,
    await_published,
    connected_message,
)

ATTACH = int(ProtocolMessageAction.ATTACH)

CONNECTION_STATE_TTL = 120000


def connected(connection_id, connection_key, max_idle_interval=15000, connection_state_ttl=CONNECTION_STATE_TTL):
    """The CONNECTED message the specifications answer their attempts with."""
    return connected_message(
        connection_id, connectionKey=connection_key,
        maxIdleInterval=max_idle_interval, connectionStateTtl=connection_state_ttl)


def channel_serial(channel):
    """The channel's `channelSerial`, which the library keeps privately.

    The specification reads it from an RTL15 `properties` object, which
    ably-python does not expose.
    """
    return channel._RealtimeChannel__channel_serial


def attach_with_serials(mock_websocket, serials):
    """A message handler attaching each channel with the serial named for it."""
    def on_message_from_client(message):
        if message.get('action') == ATTACH:
            channel = message.get('channel')
            mock_websocket.send_to_client(
                attached_message(channel, channelSerial=serials[channel]))
    return on_message_from_client


# UTS: realtime/unit/RTN16g/recovery-key-structure-0
@deviation
async def test_rtn16g_recovery_key_structure():
    serials = {'channel-alpha': 'serial-a-001', 'channel-éàü-世界': 'serial-b-002'}
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected('connection-1', 'key-abc-123')))
    mock_ws.on_message_from_client = attach_with_serials(mock_ws, serials)
    client = realtime_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    channel_a = client.channels.get('channel-alpha')
    channel_b = client.channels.get('channel-éàü-世界')

    await channel_a.attach()
    await await_channel_state(channel_a, ChannelState.ATTACHED)
    await channel_b.attach()
    await await_channel_state(channel_b, ChannelState.ATTACHED)

    # RTN16g: `Connection#createRecoveryKey`. ably-python has no such method
    recovery_key_string = client.connection.create_recovery_key()

    assert recovery_key_string is not None

    recovery_key = json.loads(recovery_key_string)

    assert recovery_key['connectionKey'] == 'key-abc-123'
    assert recovery_key['msgSerial'] == 0
    assert recovery_key['channelSerials'] is not None
    assert recovery_key['channelSerials']['channel-alpha'] == 'serial-a-001'
    # RTN16g1: the serialisation carries any unicode channel name
    assert recovery_key['channelSerials']['channel-éàü-世界'] == 'serial-b-002'

    re_parsed = json.loads(json.dumps(recovery_key))
    assert re_parsed['channelSerials']['channel-éàü-世界'] == 'serial-b-002'


# UTS: realtime/unit/RTN16g3/recovery-key-null-inactive-0
@deviation
async def test_rtn16g3_recovery_key_null_inactive():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected('connection-1', 'key-1')))
    client = realtime_client(mock_ws)

    # Before connecting there is no connection key to recover with
    assert client.connection.create_recovery_key() is None

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    assert client.connection.create_recovery_key() is not None

    close_task = asyncio.ensure_future(client.close())
    # `close()` requests CLOSING before it waits, so one turn of the loop is
    # enough to observe the state the specification asserts in
    await asyncio.sleep(0)
    assert client.connection.state == ConnectionState.CLOSING
    assert client.connection.create_recovery_key() is None

    await close_task
    assert client.connection.state == ConnectionState.CLOSED
    assert client.connection.create_recovery_key() is None

    # A connection which failed is not recoverable either
    failed_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected('conn-f', 'key-f')))
    client_failed = realtime_client(failed_ws)
    client_failed.connect()
    await await_connection_state(client_failed, ConnectionState.CONNECTED)

    failed_ws.send_to_client_and_close(ERROR_MESSAGE(50000, 'Fatal error', status_code=500))
    await await_connection_state(client_failed, ConnectionState.FAILED)
    assert client_failed.connection.create_recovery_key() is None

    # RTN16g3 with RTN8d/RTN9d: the connection key is kept through SUSPENDED, so
    # a suspended connection is still recoverable
    clock = FakeClock()
    suspended_attempts = []

    def on_connection_attempt(conn):
        suspended_attempts.append(conn)
        if len(suspended_attempts) == 1:
            conn.respond_with_success(connected('conn-s', 'key-s', max_idle_interval=0))
        else:
            conn.respond_with_dns_error()

    suspended_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client_suspended = realtime_client(
        suspended_ws, clock=clock, disconnected_retry_timeout=500,
        suspended_retry_timeout=CONNECTION_STATE_TTL * 2)

    client_suspended.connect()
    await await_connection_state(client_suspended, ConnectionState.CONNECTED)

    suspended_ws.simulate_disconnect()
    for _ in range(10):
        if client_suspended.connection.state == ConnectionState.SUSPENDED:
            break
        await clock.advance(15000)

    assert client_suspended.connection.state == ConnectionState.SUSPENDED
    assert client_suspended.connection.create_recovery_key() is not None


# UTS: realtime/unit/RTN16k/recover-query-param-0
@deviation
async def test_rtn16k_recover_query_param():
    recovery_key = json.dumps({
        'connectionKey': 'recovered-key-xyz',
        'msgSerial': 5,
        'channelSerials': {},
    })
    attempts = []

    def on_connection_attempt(conn):
        attempts.append(conn)
        if len(attempts) == 1:
            conn.respond_with_success(connected('recovered-conn-id', 'new-key-after-recovery'))
        else:
            conn.respond_with_success(connected('recovered-conn-id', 'resumed-key'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, recover=recovery_key)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    reconnected = []

    def on_connected(change):
        reconnected.append(change)

    client.connection.on(ConnectionState.CONNECTED, on_connected)
    mock_ws.simulate_disconnect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    # RTN16k: the first attempt carries the recovery key's connection key
    assert attempts[0].url.query_params.get('recover') == 'recovered-key-xyz'
    assert 'resume' not in attempts[0].url.query_params

    # Once connected the client resumes rather than recovers
    assert attempts[1].url.query_params.get('resume') == 'new-key-after-recovery'
    assert 'recover' not in attempts[1].url.query_params


# UTS: realtime/unit/RTN16f/recover-initializes-msgserial-0
@deviation
async def test_rtn16f_recover_initializes_msgserial():
    recovery_key = json.dumps({
        'connectionKey': 'old-key',
        'msgSerial': 42,
        'channelSerials': {'test-channel': 'ch-serial-1'},
    })

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected('recovered-conn', 'new-key')))
    mock_ws.on_message_from_client = attach_with_serials(
        mock_ws, {'test-channel': 'ch-serial-updated'})
    client = realtime_client(mock_ws, recover=recovery_key)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    channel = client.channels.get('test-channel')
    await channel.attach()
    await await_channel_state(channel, ChannelState.ATTACHED)

    publish = asyncio.ensure_future(channel.publish('event', 'data'))
    sent = await await_published(mock_ws)
    mock_ws.send_to_client(ack(sent[0]))
    await publish

    # RTN16f: the counter starts from the recovery key's msgSerial
    assert sent[0]['msgSerial'] == 42


# UTS: realtime/unit/RTN16f1/malformed-recovery-key-0
async def test_rtn16f1_malformed_recovery_key():
    attempts = []

    def on_connection_attempt(conn):
        attempts.append(conn)
        conn.respond_with_success(connected('fresh-conn', 'fresh-key'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, recover='this-is-not-valid-json!!!')

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert client.connection.state == ConnectionState.CONNECTED
    # The specification reads `client.connection.id` and `client.connection.key`,
    # which ably-python carries on the connection manager and the connection details
    assert client.connection.connection_manager.connection_id == 'fresh-conn'
    assert client.connection.connection_details.connection_key == 'fresh-key'

    # The malformed key reaches the connection parameters no more than a valid
    # one would: `recover` is stored and never read
    assert 'recover' not in attempts[0].url.query_params
    assert 'resume' not in attempts[0].url.query_params
    assert len(attempts) == 1


# UTS: realtime/unit/RTN16j/recover-channel-serials-0
@deviation
async def test_rtn16j_recover_channel_serials():
    recovery_key = json.dumps({
        'connectionKey': 'old-key-abc',
        'msgSerial': 10,
        'channelSerials': {
            'channel-one': 'serial-1-abc',
            'channel-two': 'serial-2-def',
            'channel-üñîçöðé': 'serial-3-unicode',
        },
    })

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected('recovered-conn', 'new-key')))
    mock_ws.on_message_from_client = attach_with_serials(
        mock_ws, {'channel-one': 'serial-1-abc-updated'})
    client = realtime_client(mock_ws, recover=recovery_key)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    # RTN16j: the recovery key's channels are instantiated with their serials
    channel_one = client.channels.get('channel-one')
    channel_two = client.channels.get('channel-two')
    channel_unicode = client.channels.get('channel-üñîçöðé')

    assert channel_serial(channel_one) == 'serial-1-abc'
    assert channel_serial(channel_two) == 'serial-2-def'
    assert channel_serial(channel_unicode) == 'serial-3-unicode'

    # RTN16i: they are instantiated, not attached
    assert channel_one.state == ChannelState.INITIALIZED
    assert channel_two.state == ChannelState.INITIALIZED
    assert channel_unicode.state == ChannelState.INITIALIZED

    await channel_one.attach()

    attaches = [message for message in mock_ws.messages_from_client
                if message.get('action') == ATTACH and message.get('channel') == 'channel-one']
    assert len(attaches) == 1
    assert attaches[0]['channelSerial'] == 'serial-1-abc'

    await await_channel_state(channel_one, ChannelState.ATTACHED)
