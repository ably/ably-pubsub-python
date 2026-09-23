"""Tests for the `mock_websocket` helper, driven through the realtime client it
serves.

Where a test proves something about the mock's own contract rather than about
the client's behaviour, it drives `as_connect()` directly, standing in for
`WebSocketTransport` and using only the surface the transport uses.
"""

import asyncio
import json

import msgpack
import pytest

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import FakeClock
from test.uts.helpers.mock_http import MockHttpClient
from test.uts.helpers.mock_websocket import (
    CLOSED_MESSAGE,
    CONNECTED_MESSAGE,
    DISCONNECTED_MESSAGE,
    ERROR_MESSAGE,
    HEARTBEAT_MESSAGE,
    JSON_PROTOCOL,
    MSGPACK_PROTOCOL,
    PING_MESSAGE,
    MockEventType,
    MockWebSocket,
    connected_message,
)

CONNECTED = int(ProtocolMessageAction.CONNECTED)
CLOSE = int(ProtocolMessageAction.CLOSE)

# Short enough that a test which waits out a connect timeout stays quick, and
# long enough that it never pre-empts a response the test means to give.
SHORT_REQUEST_TIMEOUT = 300

# Long enough that no test reconnects behind its own assertions.
NO_RETRY = 60000


def succeeding(message=CONNECTED_MESSAGE):
    """A connection handler which accepts every attempt and sends `message`."""
    return lambda connection: connection.respond_with_success(message)


async def wait_for(predicate, timeout=3.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        assert loop.time() < deadline, 'Timed out waiting for the client'
        await asyncio.sleep(0.005)


async def connected(mock, **kwargs):
    """A client which has reached CONNECTED through `mock`."""
    kwargs.setdefault('disconnected_retry_timeout', NO_RETRY)
    client = realtime_client(mock, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


def event_types(mock):
    return [event.type for event in mock.events]


# Connection outcomes

async def test_respond_with_success_connects_the_client():
    mock = MockWebSocket(on_connection_attempt=succeeding())

    client = await connected(mock)

    assert client.connection.connection_manager.connection_id == 'test-connection-id'
    assert client.connection.connection_details.connection_key == 'test-connection-key'


async def test_respond_with_success_alone_leaves_the_client_connecting():
    # A connection that opens and then says nothing is a silent server, which
    # the client waits out rather than treating as a failure
    mock = MockWebSocket(on_connection_attempt=lambda connection: connection.respond_with_success())
    client = realtime_client(mock, realtime_request_timeout=NO_RETRY)

    client.connect()
    await wait_for(lambda: len(mock.connections) == 1)

    assert client.connection.state == ConnectionState.CONNECTING


async def test_an_unanswered_attempt_succeeds_with_no_messages():
    mock = MockWebSocket()
    client = realtime_client(mock, realtime_request_timeout=NO_RETRY)

    client.connect()
    await wait_for(lambda: len(mock.connections) == 1)

    assert event_types(mock) == [MockEventType.CONNECTION_ATTEMPT, MockEventType.CONNECTION_SUCCESS]
    assert client.connection.state == ConnectionState.CONNECTING


async def test_respond_with_refused_is_indistinguishable_from_a_silent_server():
    # `ws_connect` catches only WebSocketException and socket.gaierror, so the
    # ConnectionRefusedError a refused TCP connection raises never reaches the
    # transport's failure path; the connect timeout is what ends the attempt
    mock = MockWebSocket(on_connection_attempt=lambda connection: connection.respond_with_refused())
    client = realtime_client(mock, realtime_request_timeout=SHORT_REQUEST_TIMEOUT,
                             disconnected_retry_timeout=NO_RETRY)

    client.connect()
    await await_connection_state(client, ConnectionState.DISCONNECTED)

    assert event_types(mock) == [MockEventType.CONNECTION_ATTEMPT, MockEventType.CONNECTION_FAILURE]
    assert client.connection.error_reason.code == 50003
    assert client.connection.error_reason.status_code == 504


async def test_respond_with_timeout_reaches_the_same_generic_timeout():
    mock = MockWebSocket(on_connection_attempt=lambda connection: connection.respond_with_timeout())
    client = realtime_client(mock, realtime_request_timeout=SHORT_REQUEST_TIMEOUT,
                             disconnected_retry_timeout=NO_RETRY)

    client.connect()
    await await_connection_state(client, ConnectionState.DISCONNECTED)

    assert client.connection.error_reason.code == 50003


async def test_respond_with_dns_error_fails_the_attempt_with_its_cause():
    mock = MockWebSocket(on_connection_attempt=lambda connection: connection.respond_with_dns_error())
    client = realtime_client(mock, realtime_request_timeout=NO_RETRY,
                             disconnected_retry_timeout=NO_RETRY)

    client.connect()
    await await_connection_state(client, ConnectionState.DISCONNECTED)

    reason = client.connection.error_reason
    assert reason.code == 40000
    assert reason.status_code == 400
    assert 'Name resolution failed for main.realtime.ably.net' in str(reason)


async def test_respond_with_error_fails_the_connection():
    mock = MockWebSocket(on_connection_attempt=lambda connection: connection.respond_with_error(
        ERROR_MESSAGE(40000, 'Bad request')))
    client = realtime_client(mock, realtime_request_timeout=NO_RETRY)

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED)

    assert client.connection.error_reason.code == 40000
    assert MockEventType.SERVER_DISCONNECT in event_types(mock)


async def test_respond_with_error_can_leave_the_connection_open():
    mock = MockWebSocket(on_connection_attempt=lambda connection: connection.respond_with_error(
        ERROR_MESSAGE(40000, 'Bad request'), then_close=False))
    client = realtime_client(mock, realtime_request_timeout=NO_RETRY)

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED)

    assert MockEventType.SERVER_DISCONNECT not in event_types(mock)


# The connection attempt as the test sees it

async def test_a_pending_connection_carries_the_url_the_client_built():
    mock = MockWebSocket(on_connection_attempt=succeeding())

    await connected(mock)

    attempt = mock.connection_attempts[0]
    assert attempt.url.scheme == 'wss'
    assert attempt.url.host == 'main.realtime.ably.net'
    assert attempt.url.port == 443
    assert attempt.url.query_params['key'] == 'app.key:secret'
    assert attempt.url.query_params['format'] == 'msgpack'
    assert attempt.timestamp > 0


async def test_a_pending_connection_carries_the_headers_the_client_sent():
    mock = MockWebSocket(on_connection_attempt=succeeding())

    await connected(mock)

    headers = mock.connection_attempts[0].headers
    assert 'ably-agent' in headers
    assert 'ably-python' in headers['Ably-Agent']


async def test_the_protocol_follows_use_binary_protocol():
    binary = MockWebSocket(on_connection_attempt=succeeding())
    text = MockWebSocket(on_connection_attempt=succeeding())

    await connected(binary)
    await connected(text, use_binary_protocol=False)

    assert binary.connection_attempts[0].protocol == MSGPACK_PROTOCOL
    assert text.connection_attempts[0].protocol == JSON_PROTOCOL
    assert 'format' not in text.connection_attempts[0].url.query_params


# The events timeline

async def test_the_timeline_records_a_connection_and_a_client_close_in_order():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock)

    await client.close()

    assert event_types(mock) == [
        MockEventType.CONNECTION_ATTEMPT,
        MockEventType.CONNECTION_SUCCESS,
        MockEventType.MESSAGE_TO_CLIENT,
        MockEventType.MESSAGE_FROM_CLIENT,
        MockEventType.CLIENT_CLOSE,
    ]
    assert mock.events[0].data is mock.connection_attempts[0]
    assert mock.events[2].data == CONNECTED_MESSAGE
    assert mock.events[3].data == {'action': CLOSE}
    assert mock.events[4].data.code == 1000


async def test_the_timeline_orders_a_full_disconnect_and_reconnect():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock)
    states = []
    client.connection.on(lambda change: states.append(change.current))

    mock.send_to_client_and_close(DISCONNECTED_MESSAGE)
    await wait_for(lambda: len(mock.connections) == 2)
    await await_connection_state(client, ConnectionState.CONNECTED)

    # RTN15a retries immediately after a drop from CONNECTED, so no time passes
    assert states == [
        ConnectionState.DISCONNECTED,
        ConnectionState.CONNECTING,
        ConnectionState.CONNECTED,
    ]
    assert event_types(mock)[2:] == [
        MockEventType.MESSAGE_TO_CLIENT,
        MockEventType.MESSAGE_TO_CLIENT,
        MockEventType.SERVER_DISCONNECT,
        MockEventType.CONNECTION_ATTEMPT,
        MockEventType.CONNECTION_SUCCESS,
        MockEventType.MESSAGE_TO_CLIENT,
    ]
    assert mock.connection_attempts[1].url.query_params['resume'] == 'test-connection-key'


async def test_messages_from_client_collects_what_the_client_sent():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock)

    await client.close()

    assert mock.messages_from_client == [{'action': CLOSE}]


async def test_events_of_type_filters_the_timeline():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock)

    await client.close()

    assert len(mock.events_of_type(MockEventType.CLIENT_CLOSE)) == 1
    assert mock.events_of_type(MockEventType.PING_FRAME) == []


# Server-initiated closes

async def test_simulate_disconnect_drops_the_transport():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock, disconnected_retry_timeout=NO_RETRY)
    states = []
    client.connection.on(lambda change: states.append(change.current))

    mock.simulate_disconnect()
    await wait_for(lambda: len(mock.connections) == 2)

    # RTN15a retries immediately from CONNECTED, so DISCONNECTED is transient
    # and has to be read off the recorded sequence
    assert MockEventType.SERVER_DISCONNECT in event_types(mock)
    assert states[0] == ConnectionState.DISCONNECTED


async def test_simulate_disconnect_carries_its_error_to_the_state_change():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock)
    reasons = []
    client.connection.on(lambda change: reasons.append(change.reason))

    mock.simulate_disconnect('the server went away')
    await wait_for(lambda: reasons and reasons[0] is not None)

    assert 'the server went away' in str(reasons[0])


async def test_send_to_client_and_close_delivers_the_message_before_the_close():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock, disconnected_retry_timeout=NO_RETRY)

    mock.send_to_client_and_close(ERROR_MESSAGE(40000, 'Bad request'))
    await await_connection_state(client, ConnectionState.FAILED)

    assert event_types(mock)[-2:] == [
        MockEventType.MESSAGE_TO_CLIENT,
        MockEventType.SERVER_DISCONNECT,
    ]
    assert client.connection.error_reason.code == 40000


async def test_a_server_sent_closed_message_leaves_the_connection_state_alone():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock, disconnected_retry_timeout=NO_RETRY)

    mock.send_to_client_and_close(CLOSED_MESSAGE)
    await wait_for(lambda: mock.connections[0].closed)
    await asyncio.sleep(0.05)

    # `on_closed` disposes the transport without notifying a state, so CLOSED
    # is only ever reached through the client's own close path
    assert client.connection.state == ConnectionState.CONNECTED


async def test_a_closed_connection_ignores_a_second_server_close():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock, disconnected_retry_timeout=NO_RETRY)
    connection = mock.active_connection

    states = []
    client.connection.on(lambda change: states.append(change.current))

    connection.simulate_disconnect()
    connection.simulate_disconnect()
    await wait_for(lambda: len(mock.connections) == 2)

    assert len(mock.events_of_type(MockEventType.SERVER_DISCONNECT)) == 1
    assert states[0] == ConnectionState.DISCONNECTED


# Client-initiated close

async def test_await_client_close_returns_the_close_the_library_asked_for():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock)

    waiting = mock.await_client_close(timeout=2)
    await client.close()
    close_event = await waiting

    assert close_event.code == 1000
    assert close_event.reason is None
    assert client.connection.state == ConnectionState.CLOSED


async def test_a_client_close_clears_the_active_connection():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock)

    await client.close()

    assert mock.active_connection is None
    assert len(mock.connections) == 1


# The await-based API

async def test_await_connection_attempt_hands_the_attempt_to_the_test():
    mock = MockWebSocket()
    client = realtime_client(mock, realtime_request_timeout=NO_RETRY)

    waiting = mock.await_connection_attempt(timeout=2)
    client.connect()
    attempt = await waiting
    attempt.respond_with_success(CONNECTED_MESSAGE)
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert attempt.protocol == MSGPACK_PROTOCOL


async def test_a_waiting_test_takes_precedence_over_the_connection_handler():
    handled = []
    mock = MockWebSocket(on_connection_attempt=handled.append)
    client = realtime_client(mock, realtime_request_timeout=NO_RETRY)

    waiting = mock.await_connection_attempt(timeout=2)
    client.connect()
    attempt = await waiting
    attempt.respond_with_success(CONNECTED_MESSAGE)
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert handled == []


async def test_a_second_attempt_is_caught_by_awaiting_before_responding():
    mock = MockWebSocket()
    client = realtime_client(mock, realtime_request_timeout=NO_RETRY,
                             disconnected_retry_timeout=50)

    first_attempt = mock.await_connection_attempt(timeout=2)
    client.connect()
    first = await first_attempt
    # The retry follows the response immediately, so its waiter is registered
    # before the response rather than after it
    second_attempt = mock.await_connection_attempt(timeout=2)
    first.respond_with_dns_error()
    second = await second_attempt
    second.respond_with_success(CONNECTED_MESSAGE)
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert len(mock.connection_attempts) == 2


async def test_await_next_message_from_client_returns_the_decoded_message():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock)

    waiting = mock.await_next_message_from_client(timeout=2)
    close = asyncio.ensure_future(client.close())
    message = await waiting

    assert message == {'action': CLOSE}
    await close


async def test_an_await_that_is_never_answered_fails_the_test():
    mock = MockWebSocket()

    with pytest.raises(AssertionError, match='^Timeout waiting for connection attempt$'):
        await mock.await_connection_attempt(timeout=0.05)


async def test_an_await_reports_a_handler_that_raised():
    def broken(connection):
        raise TypeError('a handler bug')

    mock = MockWebSocket(on_connection_attempt=broken)
    client = realtime_client(mock, realtime_request_timeout=NO_RETRY,
                             disconnected_retry_timeout=NO_RETRY)

    client.connect()
    await await_connection_state(client, ConnectionState.DISCONNECTED)

    # A TypeError escaping into `ws_connect` would silently make it retry with
    # different keyword arguments, so the mock keeps it and fails the attempt
    assert len(mock.connection_attempts) == 1
    assert isinstance(mock.handler_errors[0], TypeError)
    with pytest.raises(AssertionError, match='a handler bug'):
        await mock.await_next_message_from_client(timeout=0.05)


# The handler-based API

async def test_the_connection_handler_can_branch_on_the_attempt_count():
    attempts = []

    def connect(connection):
        attempts.append(connection)
        if len(attempts) == 1:
            connection.respond_with_dns_error()
        else:
            connection.respond_with_success(CONNECTED_MESSAGE)

    mock = MockWebSocket(on_connection_attempt=connect)
    client = realtime_client(mock, realtime_request_timeout=NO_RETRY,
                             disconnected_retry_timeout=50)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert len(attempts) == 2


async def test_the_message_handler_receives_every_message_from_the_client():
    captured = []
    mock = MockWebSocket(on_connection_attempt=succeeding(), on_message_from_client=captured.append)
    client = await connected(mock)

    await client.close()

    assert captured == [{'action': CLOSE}]


async def test_the_handlers_can_be_assigned_after_construction():
    mock = MockWebSocket()
    client = realtime_client(mock, realtime_request_timeout=NO_RETRY)

    mock.on_connection_attempt = succeeding()
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert len(mock.connections) == 1


# Raw data frame hooks

async def test_the_binary_frame_hook_runs_alongside_the_decoded_handler():
    frames = []
    decoded = []
    mock = MockWebSocket(on_connection_attempt=succeeding(),
                         on_message_from_client=decoded.append,
                         on_binary_data_frame=frames.append)
    client = await connected(mock)

    await client.close()

    assert decoded == [{'action': CLOSE}]
    assert len(frames) == 1
    assert isinstance(frames[0], bytes)
    assert msgpack.unpackb(frames[0], raw=False) == {'action': CLOSE}


async def test_the_text_frame_hook_runs_alongside_the_decoded_handler():
    frames = []
    decoded = []
    mock = MockWebSocket(on_connection_attempt=succeeding(),
                         on_message_from_client=decoded.append,
                         on_text_data_frame=frames.append)
    client = await connected(mock, use_binary_protocol=False)

    await client.close()

    assert decoded == [{'action': CLOSE}]
    assert len(frames) == 1
    assert isinstance(frames[0], str)
    assert json.loads(frames[0]) == {'action': CLOSE}


async def test_the_text_hook_is_silent_under_the_binary_protocol():
    text = []
    binary = []
    mock = MockWebSocket(on_connection_attempt=succeeding(),
                         on_text_data_frame=text.append,
                         on_binary_data_frame=binary.append)
    client = await connected(mock)

    await client.close()

    assert text == []
    assert len(binary) == 1


# Encoding

async def test_a_message_given_as_a_dict_is_encoded_for_the_clients_protocol():
    binary = MockWebSocket(on_connection_attempt=succeeding())
    text = MockWebSocket(on_connection_attempt=succeeding())

    await connected(binary)
    await connected(text, use_binary_protocol=False)

    assert binary.connections[0].protocol == MSGPACK_PROTOCOL
    assert text.connections[0].protocol == JSON_PROTOCOL


async def test_a_message_given_already_encoded_is_passed_through():
    packed = msgpack.packb(CONNECTED_MESSAGE, use_bin_type=True)
    mock = MockWebSocket(on_connection_attempt=lambda connection: connection.respond_with_success(packed))

    client = await connected(mock)

    assert client.connection.connection_manager.connection_id == 'test-connection-id'


async def test_a_json_string_reaches_a_client_on_the_text_protocol():
    encoded = json.dumps(CONNECTED_MESSAGE)
    mock = MockWebSocket(on_connection_attempt=lambda connection: connection.respond_with_success(encoded))

    client = await connected(mock, use_binary_protocol=False)

    assert client.connection.connection_manager.connection_id == 'test-connection-id'


async def test_sending_a_template_leaves_it_untouched():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    before = json.dumps(CONNECTED_MESSAGE, sort_keys=True)

    await connected(mock)

    assert json.dumps(CONNECTED_MESSAGE, sort_keys=True) == before


async def test_connected_message_overrides_the_templates_connection_details():
    message = connected_message('other-id', maxIdleInterval=1000)
    mock = MockWebSocket(on_connection_attempt=succeeding(message))

    client = await connected(mock)

    assert client.connection.connection_manager.connection_id == 'other-id'
    assert client.connection.connection_details.max_idle_interval == 1000
    assert CONNECTED_MESSAGE['connectionDetails']['maxIdleInterval'] == 15000


# Protocol message templates

async def test_a_heartbeat_message_answers_the_clients_ping():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock)

    waiting = mock.await_next_message_from_client(timeout=2)
    ping = asyncio.ensure_future(client.connection.ping())
    heartbeat = await waiting
    mock.send_to_client({**HEARTBEAT_MESSAGE, 'id': heartbeat['id']})

    assert heartbeat['action'] == int(ProtocolMessageAction.HEARTBEAT)
    assert await ping >= 0


async def test_error_message_derives_its_status_code_from_its_code():
    assert ERROR_MESSAGE(40142, 'Token expired')['error'] == {
        'code': 40142, 'statusCode': 401, 'message': 'Token expired'}


async def test_a_ping_message_is_recorded_but_draws_no_pong():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock)

    mock.send_to_client(PING_MESSAGE('ping-id'))
    await asyncio.sleep(0.05)

    # RTN23c1 is unimplemented: action 22 matches no branch of
    # `on_protocol_message`, so no PONG goes back
    assert mock.messages_from_client == []
    assert client.connection.state == ConnectionState.CONNECTED


# Ping frames

async def test_a_ping_frame_is_recorded_but_reaches_no_library_hook():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock)
    transport = client.connection.connection_manager.transport
    before = transport.last_activity

    mock.send_ping_frame()
    await asyncio.sleep(0.05)

    # `WebSocketTransport` has no ping hook, so a ping frame is not activity
    assert len(mock.events_of_type(MockEventType.PING_FRAME)) == 1
    assert transport.last_activity == before
    assert client.connection.state == ConnectionState.CONNECTED


async def test_the_client_asks_for_no_heartbeat_mode():
    mock = MockWebSocket(on_connection_attempt=succeeding())

    await connected(mock)

    # RTN23b: omitting `heartbeats` leaves the server free to use ping frames
    assert 'heartbeats' not in mock.connection_attempts[0].url.query_params


# Ordering requirements

async def test_respond_with_success_establishes_the_connection_before_the_message():
    mock = MockWebSocket()
    connect = mock.as_connect()
    seen = []

    async def transport():
        async with connect('wss://host?format=json') as websocket:
            seen.append('established')
            async for frame in websocket:
                seen.append(json.loads(frame)['action'])
                return

    reading = asyncio.ensure_future(transport())
    attempt = await mock.await_connection_attempt(timeout=2)
    attempt.respond_with_success(CONNECTED_MESSAGE)
    await reading

    assert seen == ['established', CONNECTED]


async def test_close_delivers_its_notification_asynchronously():
    mock = MockWebSocket(on_connection_attempt=lambda connection: connection.respond_with_success())
    connect = mock.as_connect()
    ended = []

    async def transport():
        async with connect('wss://host?format=json') as websocket:
            async for _ in websocket:
                pass
            ended.append('read loop over')

    reading = asyncio.ensure_future(transport())
    await wait_for(lambda: mock.active_connection is not None)

    await mock.connections[0].close()

    # The close reaches the read loop from the stream, never inline
    assert ended == []
    await reading
    assert ended == ['read loop over']


async def test_a_server_close_reaches_the_client_on_a_later_turn():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock, disconnected_retry_timeout=NO_RETRY)
    states = []
    client.connection.on(lambda change: states.append(change.current))

    mock.simulate_disconnect()

    # Nothing has reached the client's read loop yet
    assert client.connection.state == ConnectionState.CONNECTED
    assert states == []
    await wait_for(lambda: states and states[0] == ConnectionState.DISCONNECTED)


# Test management

async def test_reset_clears_the_timeline_and_the_connections():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    await connected(mock)

    mock.reset()

    assert mock.events == []
    assert mock.connections == []
    assert mock.active_connection is None


async def test_reset_drops_a_waiting_test():
    mock = MockWebSocket()
    waiting = asyncio.ensure_future(mock.await_connection_attempt(timeout=0.1))
    await asyncio.sleep(0)

    mock.reset()

    with pytest.raises(AssertionError, match='^Timeout waiting for connection attempt$'):
        await waiting


async def test_reset_leaves_the_handlers_in_place():
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = await connected(mock)
    await client.close()

    mock.reset()
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert len(mock.connections) == 1


# Composition with the other helpers

async def test_a_realtime_client_can_take_the_http_mock_as_well():
    mock_ws = MockWebSocket(on_connection_attempt=succeeding())
    mock_http = MockHttpClient(on_request=lambda request: request.respond_with(200, [4321]))
    client = realtime_client(mock_ws, mock_http=mock_http)

    assert await client.time() == 4321


async def test_a_realtime_client_can_take_the_fake_clock():
    clock = FakeClock()
    mock = MockWebSocket(on_connection_attempt=succeeding())
    client = realtime_client(mock, clock=clock)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    # The idle timer the CONNECTED message starts is scheduled on the fake clock
    assert clock.pending


async def test_a_client_which_never_connected_records_nothing():
    mock = MockWebSocket(on_connection_attempt=succeeding())

    client = realtime_client(mock)

    assert client.connection.state == ConnectionState.INITIALIZED
    assert mock.events == []


async def test_auto_connect_can_be_asked_for_explicitly():
    mock = MockWebSocket(on_connection_attempt=succeeding())

    client = realtime_client(mock, auto_connect=True)
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert len(mock.connection_attempts) == 1


async def test_send_to_client_without_a_connection_fails_the_test():
    mock = MockWebSocket()

    with pytest.raises(AssertionError, match='^No connection has been established$'):
        mock.send_to_client(HEARTBEAT_MESSAGE)
