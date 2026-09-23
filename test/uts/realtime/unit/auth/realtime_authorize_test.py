"""Derived from uts/realtime/unit/auth/realtime_authorize.md in ably/specification.

Spec points: RTC8, RTC8a, RTC8a1, RTC8a2, RTC8a3, RTC8b, RTC8b1, RTC8c
"""

import asyncio
import time

import pytest

from ably.realtime.channel import ChannelState
from ably.realtime.connection import ConnectionEvent, ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.tokendetails import TokenDetails
from ably.util.exceptions import AblyException
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import settle
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

AUTH_ACTION = int(ProtocolMessageAction.AUTH)
ATTACH_ACTION = int(ProtocolMessageAction.ATTACH)


def now():
    return int(time.time() * 1000)


def numbered_token_callback(counter):
    """The specifications' authCallback: `token-1`, `token-2`, ... in turn.

    `counter` is a single-element list so that the caller can read how many
    times the callback ran.
    """
    async def auth_callback(params):
        counter[0] += 1
        return TokenDetails(token=f'token-{counter[0]}', expires=now() + 3600000)

    return auth_callback


def error_message(code, status_code, message):
    return {
        'action': int(ProtocolMessageAction.ERROR),
        'error': {'code': code, 'statusCode': status_code, 'message': message},
    }


def channel_error_message(channel, code, status_code, message):
    return {
        'action': int(ProtocolMessageAction.ERROR),
        'channel': channel,
        'error': {'code': code, 'statusCode': status_code, 'message': message},
    }


def attached_message(channel):
    return {'action': int(ProtocolMessageAction.ATTACHED), 'channel': channel, 'flags': 0}


async def poll_until(condition, timeout=5.0, description='condition'):
    """Waits for `condition` to hold, yielding to the event loop between checks.

    The connect path chains tasks several levels deep, so a single yield is not
    enough to see the result of one; the deadline is a safety net, not a delay.
    """
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f'Timed out waiting for {description}')
        await settle(passes=5)


async def await_channel_state(channel, state, timeout=5.0):
    """Waits for `channel` to reach `state`.

    This is the specifications' `AWAIT_STATE` for a channel; the connection has
    `await_connection_state` in `test.uts.helpers.client`.
    """
    deadline = time.monotonic() + timeout
    while channel.state != state:
        if time.monotonic() > deadline:
            raise AssertionError(
                f'Timed out waiting for channel state {state}; it was {channel.state}')
        await settle(passes=5)


# UTS: realtime/unit/RTC8a/authorize-connected-sends-auth-0
async def test_rtc8a_authorize_connected_sends_auth():
    auth_callback_count = [0]
    captured_auth_messages = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected_message('connection-id', connectionKey='connection-key')),
    )
    client = realtime_client(mock_ws, auth_callback=numbered_token_callback(auth_callback_count))

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    state_changes = []
    client.connection.on(lambda change: state_changes.append(change))

    def on_message_from_client(message):
        if message['action'] == AUTH_ACTION:
            captured_auth_messages.append(message)
            mock_ws.send_to_client(
                connected_message('connection-id', connectionKey='connection-key-2'))

    mock_ws.on_message_from_client = on_message_from_client

    token_details = await client.auth.authorize()

    assert auth_callback_count[0] == 2

    assert len(captured_auth_messages) == 1
    assert captured_auth_messages[0].get('auth') is not None
    assert captured_auth_messages[0]['auth']['accessToken'] == 'token-2'

    assert token_details.token == 'token-2'

    state_transitions = [c for c in state_changes if c.current != c.previous]
    assert state_transitions == []
    assert client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/unit/RTC8a1/successful-reauth-update-event-0
async def test_rtc8a1_successful_reauth_update_event():
    auth_callback_count = [0]

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected_message('connection-id-1', connectionKey='connection-key-1')),
    )
    client = realtime_client(mock_ws, auth_callback=numbered_token_callback(auth_callback_count))

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    update_events = []
    connected_events = []
    state_changes = []

    client.connection.on(ConnectionEvent.UPDATE, lambda change: update_events.append(change))
    client.connection.on(ConnectionState.CONNECTED, lambda change: connected_events.append(change))
    client.connection.on(lambda change: state_changes.append(change))

    def on_message_from_client(message):
        if message['action'] == AUTH_ACTION:
            mock_ws.send_to_client(connected_message(
                'connection-id-2', connectionKey='connection-key-2',
                maxIdleInterval=20000, connectionStateTtl=180000))

    mock_ws.on_message_from_client = on_message_from_client

    await client.auth.authorize()
    await settle()

    assert len(update_events) == 1
    assert update_events[0].previous == ConnectionState.CONNECTED
    assert update_events[0].current == ConnectionState.CONNECTED

    assert connected_events == []

    state_transitions = [c for c in state_changes if c.current != c.previous]
    assert state_transitions == []

    # RTN21: the reauth CONNECTED overrides the connection details. The
    # specification reads `client.connection.id` and `client.connection.key`;
    # ably-python exposes neither, carrying the id on the connection manager
    # and the key on the connection details.
    assert client.connection.connection_manager.connection_id == 'connection-id-2'
    assert client.connection.connection_details.connection_key == 'connection-key-2'


# UTS: realtime/unit/RTC8a1/capability-downgrade-channel-failed-1
async def test_rtc8a1_capability_downgrade_channel_failed():
    auth_callback_count = [0]
    channel_name = 'private-channel'

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected_message('connection-id', connectionKey='connection-key')),
    )
    client = realtime_client(mock_ws, auth_callback=numbered_token_callback(auth_callback_count))

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    channel = client.channels.get(channel_name)

    def on_message_from_client(message):
        if message['action'] == ATTACH_ACTION and message.get('channel') == channel_name:
            mock_ws.send_to_client(attached_message(channel_name))
        if message['action'] == AUTH_ACTION:
            # The reauth succeeds at the connection level
            mock_ws.send_to_client(
                connected_message('connection-id', connectionKey='connection-key-2'))
            # and is followed by the channel-level ERROR the downgrade produces.
            # The two are queued in order on the same connection, so the ERROR
            # reaches the client behind the CONNECTED.
            mock_ws.send_to_client(channel_error_message(
                channel_name, 40160, 401, 'Channel denied access based on given capability'))

    mock_ws.on_message_from_client = on_message_from_client

    await channel.attach()
    await await_channel_state(channel, ChannelState.ATTACHED)

    channel_state_changes = []
    channel.on(lambda change: channel_state_changes.append(change))

    await client.auth.authorize()
    await await_channel_state(channel, ChannelState.FAILED)

    assert channel.state == ChannelState.FAILED

    failed_changes = [c for c in channel_state_changes if c.current == ChannelState.FAILED]
    assert len(failed_changes) == 1
    assert failed_changes[0].reason is not None
    assert failed_changes[0].reason.code == 40160
    assert failed_changes[0].reason.status_code == 401

    assert client.connection.state == ConnectionState.CONNECTED


# UTS: realtime/unit/RTC8a2/failed-reauth-connection-failed-0
async def test_rtc8a2_failed_reauth_connection_failed():
    auth_callback_count = [0]

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected_message('connection-id', connectionKey='connection-key')),
    )
    client = realtime_client(mock_ws, auth_callback=numbered_token_callback(auth_callback_count))

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    state_changes = []
    client.connection.on(lambda change: state_changes.append(change))

    def on_message_from_client(message):
        if message['action'] == AUTH_ACTION:
            mock_ws.send_to_client_and_close(
                error_message(40012, 400, 'Incompatible clientId'))

    mock_ws.on_message_from_client = on_message_from_client

    with pytest.raises(AblyException) as excinfo:
        await client.auth.authorize()

    assert excinfo.value.code == 40012

    assert client.connection.state == ConnectionState.FAILED

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 40012

    assert ConnectionState.FAILED in [c.current for c in state_changes]


# UTS: realtime/unit/RTC8a3/authorize-completes-after-response-0
async def test_rtc8a3_authorize_completes_after_response():
    auth_callback_count = [0]

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(
            connected_message('connection-id', connectionKey='connection-key')),
    )
    client = realtime_client(mock_ws, auth_callback=numbered_token_callback(auth_callback_count))

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    # The waiter is registered before authorize starts, so the AUTH message is
    # not missed while the task is being scheduled
    next_message = mock_ws.await_next_message_from_client()
    authorize_future = asyncio.create_task(client.auth.authorize())

    auth_msg = await next_message
    assert auth_msg['action'] == AUTH_ACTION

    # The server has not responded, so authorize has not completed
    await settle()
    assert authorize_future.done() is False

    mock_ws.send_to_client(connected_message('connection-id', connectionKey='connection-key-2'))

    token_details = await authorize_future

    assert authorize_future.done() is True
    assert token_details.token == 'token-2'


# UTS: realtime/unit/RTC8b/authorize-connecting-halts-attempt-0
async def test_rtc8b_authorize_connecting_halts_attempt():
    auth_callback_count = [0]
    captured_ws_urls = []
    connection_attempt_count = [0]

    def on_connection_attempt(conn):
        connection_attempt_count[0] += 1
        captured_ws_urls.append(conn.url)
        if connection_attempt_count[0] == 1:
            # The transport opens but no CONNECTED arrives, so the client stays
            # in CONNECTING
            conn.respond_with_success()
        else:
            conn.respond_with_success(
                connected_message('connection-id', connectionKey='connection-key'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, auth_callback=numbered_token_callback(auth_callback_count))

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTING)
    # The attempt has to be in flight for authorize to have one to halt
    await poll_until(lambda: connection_attempt_count[0] == 1,
                     description='the first connection attempt')

    token_details = await client.auth.authorize()

    assert token_details.token == 'token-2'
    assert client.connection.state == ConnectionState.CONNECTED
    assert auth_callback_count[0] == 2
    assert connection_attempt_count[0] == 2
    assert captured_ws_urls[1].query_params['accessToken'] == 'token-2'


# UTS: realtime/unit/RTC8b1/authorize-connecting-fails-on-failed-0
async def test_rtc8b1_authorize_connecting_fails_on_failed():
    auth_callback_count = [0]
    connection_attempt_count = [0]

    def on_connection_attempt(conn):
        connection_attempt_count[0] += 1
        if connection_attempt_count[0] == 1:
            conn.respond_with_success()
        else:
            conn.respond_with_success()
            conn.send_to_client_and_close(error_message(40101, 401, 'Invalid credentials'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, auth_callback=numbered_token_callback(auth_callback_count))

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTING)
    # The attempt has to be in flight for authorize to have one to halt
    await poll_until(lambda: connection_attempt_count[0] == 1,
                     description='the first connection attempt')

    with pytest.raises(AblyException) as excinfo:
        await client.auth.authorize()

    assert excinfo.value.code == 40101
    assert client.connection.state == ConnectionState.FAILED


# UTS: realtime/unit/RTC8c/authorize-disconnected-initiates-connection-0
async def test_rtc8c_authorize_disconnected_initiates_connection():
    auth_callback_count = [0]
    captured_ws_urls = []
    connection_attempt_count = [0]

    def on_connection_attempt(conn):
        connection_attempt_count[0] += 1
        captured_ws_urls.append(conn.url)
        conn.respond_with_success(
            connected_message('connection-id', connectionKey='connection-key'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, auth_callback=numbered_token_callback(auth_callback_count))

    assert client.connection.state == ConnectionState.INITIALIZED

    state_changes = []
    client.connection.on(lambda change: state_changes.append(change.current))

    token_details = await client.auth.authorize()

    assert token_details.token == 'token-1'
    assert client.connection.state == ConnectionState.CONNECTED

    connecting_at = state_changes.index(ConnectionState.CONNECTING)
    connected_at = state_changes.index(ConnectionState.CONNECTED)
    assert connecting_at < connected_at

    assert captured_ws_urls[0].query_params['accessToken'] == 'token-1'


# UTS: realtime/unit/RTC8c/authorize-failed-initiates-connection-1
async def test_rtc8c_authorize_failed_initiates_connection():
    auth_callback_count = [0]
    captured_ws_urls = []
    connection_attempt_count = [0]

    def on_connection_attempt(conn):
        connection_attempt_count[0] += 1
        captured_ws_urls.append(conn.url)
        conn.respond_with_success()
        if connection_attempt_count[0] == 1:
            conn.send_to_client_and_close(error_message(40101, 401, 'Invalid credentials'))
        else:
            conn.send_to_client(
                connected_message('connection-id', connectionKey='connection-key'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, auth_callback=numbered_token_callback(auth_callback_count))

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED)

    state_changes = []
    client.connection.on(lambda change: state_changes.append(change.current))

    token_details = await client.auth.authorize()

    assert token_details.token == 'token-2'
    assert client.connection.state == ConnectionState.CONNECTED

    connecting_at = state_changes.index(ConnectionState.CONNECTING)
    connected_at = state_changes.index(ConnectionState.CONNECTED)
    assert connecting_at < connected_at

    assert captured_ws_urls[1].query_params['accessToken'] == 'token-2'


# UTS: realtime/unit/RTC8c/authorize-closed-initiates-connection-2
async def test_rtc8c_authorize_closed_initiates_connection():
    auth_callback_count = [0]
    connection_attempt_count = [0]

    def on_connection_attempt(conn):
        connection_attempt_count[0] += 1
        conn.respond_with_success(connected_message(
            f'connection-id-{connection_attempt_count[0]}',
            connectionKey=f'connection-key-{connection_attempt_count[0]}'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, auth_callback=numbered_token_callback(auth_callback_count))

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await client.close()
    assert client.connection.state == ConnectionState.CLOSED

    token_details = await client.auth.authorize()

    assert token_details.token == 'token-2'
    assert client.connection.state == ConnectionState.CONNECTED
