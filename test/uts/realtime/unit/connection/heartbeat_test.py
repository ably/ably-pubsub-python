"""Derived from uts/realtime/unit/connection/heartbeat_test.md in ably/specification.

Spec points: RTN23, RTN23a, RTN23b, RTN23c, RTN23c1

The idle timer is driven on real time here rather than with a `FakeClock`:
`WebSocketTransport.on_idle_timer_expire` schedules through the timer seam but
measures elapsed time against the real clock, so an advance fires the timer
while no time has passed and it reschedules itself. `maxIdleInterval` arrives in
the CONNECTED message and is honoured, so the intervals the specification quotes
in seconds are scaled down to the hundreds of milliseconds below.
"""

import asyncio

import pytest

from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import (
    await_connection_state,
    next_connection_state,
    realtime_client,
)
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import (
    HEARTBEAT_MESSAGE,
    PING_MESSAGE,
    MockEventType,
    MockWebSocket,
    connected_message,
    contains_in_order,
    message_protocol_message,
)

# The specification's `maxIdleInterval` of 2-5 seconds and `realtimeRequestTimeout`
# of 1-2 seconds, scaled so that the whole batch runs in real time
MAX_IDLE_INTERVAL = 200
REQUEST_TIMEOUT = 200

# What the transport waits from the last activity before it declares the
# connection dropped: `maxIdleInterval + realtimeRequestTimeout`, plus the 100 ms
# of slack `on_activity` adds when it arms the timer
IDLE_TIMEOUT = (MAX_IDLE_INTERVAL + REQUEST_TIMEOUT + 100) / 1000

# A wait short enough to leave the idle timer running, standing in for the
# specification's `ADVANCE_TIME` between one server message and the next
WITHIN_IDLE_TIMEOUT = IDLE_TIMEOUT * 0.4

RECONNECT_CYCLE = ConnectionState.CONNECTING, ConnectionState.CONNECTED

FULL_CYCLE = [
    ConnectionState.CONNECTING,
    ConnectionState.CONNECTED,
    ConnectionState.DISCONNECTED,
    ConnectionState.CONNECTING,
    ConnectionState.CONNECTED,
]

PING_FRAMES_SKIP = (
    'RTN23b applies to platforms whose websocket client surfaces ping frame events. '
    'The `websockets` library answers pings inside the protocol and offers no hook, so '
    '`WebSocketTransport` cannot see one: a frame from `send_ping_frame()` reaches no '
    'library code and cannot reset the idle timer. ably-python is an RTN23a platform, '
    'and the specification says the RTN23b tests do not apply to one. '
    'See deviations-connection-liveness.md.')

HEARTBEATS_BOUNCE_SKIP = (
    'RTN23c applies to a client whose own code may be suspended while the transport '
    'stays alive and keeps answering transport-level liveness checks, which the '
    'specification scopes to browser builds. ably-python has no such build, so there is '
    'no configuration of it under which `heartbeats=bounce` is the value to send. That '
    'it sends no `heartbeats` parameter at all is recorded against RTN23a. '
    'See deviations-connection-liveness.md.')


def liveness_client(mock_websocket, **kwargs):
    """A client whose connection drops `IDLE_TIMEOUT` after the last message."""
    kwargs.setdefault('realtime_request_timeout', REQUEST_TIMEOUT)
    kwargs.setdefault('disconnected_retry_timeout', 500)
    return realtime_client(mock_websocket, **kwargs)


def numbered_connections(attempts, max_idle_interval=MAX_IDLE_INTERVAL):
    """An attempt handler answering the nth attempt with connection details n.

    Every test in the specification numbers its connections this way, so that a
    reconnection can be told from the connection it replaced.
    """
    def on_connection_attempt(conn):
        attempts.append(conn)
        conn.respond_with_success(connected_message(
            f'connection-id-{len(attempts)}',
            connectionKey=f'connection-key-{len(attempts)}',
            maxIdleInterval=max_idle_interval,
            connectionStateTtl=120000))
    return on_connection_attempt


def record_states(client):
    """The state changes the connection reports from now on."""
    states = []

    def record(change):
        states.append(change.current)

    client.connection.on(record)
    return states


# UTS: realtime/unit/RTN23a/heartbeats-true-query-param-0
@deviation
async def test_rtn23a_heartbeats_true_query_param():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=numbered_connections(attempts, 15000))
    client = liveness_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    # ably-python cannot observe ping frames, so RTN23b has it ask the server for
    # HEARTBEAT protocol messages instead. It sends no `heartbeats` parameter at all
    assert attempts[0].url.query_params.get('heartbeats') == 'true'


# UTS: realtime/unit/RTN23a/idle-timeout-reconnect-1
async def test_rtn23a_idle_timeout_reconnect():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=numbered_connections(attempts))
    client = liveness_client(mock_ws)
    states = record_states(client)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert len(attempts) == 1

    # The server sends nothing more, so the idle timer runs out and the client
    # reconnects at once, per RTN15a
    await next_connection_state(client, ConnectionState.CONNECTED)

    assert contains_in_order(states, FULL_CYCLE)
    assert len(attempts) == 2
    # The specification reads `client.connection.id`, which ably-python carries
    # on the connection manager
    assert client.connection.connection_manager.connection_id == 'connection-id-2'
    assert len(mock_ws.events_of_type(MockEventType.CLIENT_CLOSE)) == 1


# UTS: realtime/unit/RTN23a/heartbeat-resets-timer-2
async def test_rtn23a_heartbeat_resets_timer():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=numbered_connections(attempts))
    client = liveness_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert len(attempts) == 1

    await asyncio.sleep(WITHIN_IDLE_TIMEOUT)
    mock_ws.send_to_client(HEARTBEAT_MESSAGE)
    await asyncio.sleep(WITHIN_IDLE_TIMEOUT)

    # Longer than the idle timeout has passed since CONNECTED, but not since the
    # HEARTBEAT, so the connection is still up
    assert client.connection.state == ConnectionState.CONNECTED
    assert len(attempts) == 1

    await next_connection_state(client, ConnectionState.CONNECTED)

    assert len(attempts) == 2
    assert len(mock_ws.events_of_type(MockEventType.CLIENT_CLOSE)) == 1


# UTS: realtime/unit/RTN23a/any-message-resets-timer-3
async def test_rtn23a_any_message_resets_timer():
    channel_name = 'test-RTN23a-message'
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=numbered_connections(attempts))
    client = liveness_client(mock_ws)
    states = record_states(client)
    # The channel is created so that the MESSAGE below routes to a channel the
    # collection holds; `Channels._on_channel_message` raises on one it does not
    client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await asyncio.sleep(WITHIN_IDLE_TIMEOUT)
    mock_ws.send_to_client({'action': 1, 'msgSerial': 0, 'count': 1})
    await asyncio.sleep(WITHIN_IDLE_TIMEOUT)

    assert client.connection.state == ConnectionState.CONNECTED

    mock_ws.send_to_client(message_protocol_message(
        channel_name, [{'name': 'event', 'data': 'data'}]))
    await asyncio.sleep(WITHIN_IDLE_TIMEOUT)

    assert len(attempts) == 1

    await next_connection_state(client, ConnectionState.CONNECTED)

    assert contains_in_order(states, FULL_CYCLE)
    assert len(attempts) == 2
    assert len(mock_ws.events_of_type(MockEventType.CLIENT_CLOSE)) == 1


# UTS: realtime/unit/RTN23a/timeout-triggers-reconnect-4
async def test_rtn23a_timeout_triggers_reconnect():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=numbered_connections(attempts))
    client = liveness_client(mock_ws)
    states = record_states(client)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert len(attempts) == 1

    await next_connection_state(client, ConnectionState.CONNECTED)

    assert contains_in_order(states, FULL_CYCLE)
    assert len(attempts) == 2
    assert client.connection.state == ConnectionState.CONNECTED
    assert client.connection.connection_manager.connection_id == 'connection-id-2'
    assert len(mock_ws.events_of_type(MockEventType.CLIENT_CLOSE)) == 1


# UTS: realtime/unit/RTN23a/reconnect-uses-resume-5
async def test_rtn23a_reconnect_uses_resume():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=numbered_connections(attempts))
    client = liveness_client(mock_ws)
    states = record_states(client)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await next_connection_state(client, ConnectionState.CONNECTED)

    assert contains_in_order(states, FULL_CYCLE)
    assert len(attempts) == 2
    assert 'resume' not in attempts[0].url.query_params
    assert attempts[1].url.query_params['resume'] == 'connection-key-1'


# UTS: realtime/unit/RTN23a/ping-resets-timer-6
async def test_rtn23a_ping_resets_timer():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=numbered_connections(attempts))
    client = liveness_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert len(attempts) == 1

    await asyncio.sleep(WITHIN_IDLE_TIMEOUT)
    # A PING is activity like any other message, which is what a client sending
    # `heartbeats=bounce` relies on. ably-python resets the idle timer for every
    # protocol message before it looks at the action, so it counts here too
    mock_ws.send_to_client(PING_MESSAGE('ping-1'))
    await asyncio.sleep(WITHIN_IDLE_TIMEOUT)

    assert client.connection.state == ConnectionState.CONNECTED
    assert len(attempts) == 1

    await next_connection_state(client, ConnectionState.CONNECTED)

    assert len(attempts) == 2
    assert len(mock_ws.events_of_type(MockEventType.CLIENT_CLOSE)) == 1


# UTS: realtime/unit/RTN23b/heartbeats-false-query-param-0
async def test_rtn23b_heartbeats_false_query_param():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=numbered_connections(attempts, 15000))
    client = liveness_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    # The parameter is absent, which is what RTN23b permits a client that can see
    # ping frames to send. ably-python cannot see them, so the value RTN23a asks
    # of it is `true`; that it sends neither is recorded against RTN23a above
    heartbeats = attempts[0].url.query_params.get('heartbeats')
    assert heartbeats == 'false' or heartbeats is None


# UTS: realtime/unit/RTN23b/idle-timeout-reconnect-1
async def test_rtn23b_idle_timeout_reconnect():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=numbered_connections(attempts))
    client = liveness_client(mock_ws)
    states = record_states(client)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert len(attempts) == 1

    # No messages and no ping frames reach the client, so the idle timer runs out
    await next_connection_state(client, ConnectionState.CONNECTED)

    assert contains_in_order(states, FULL_CYCLE)
    assert len(attempts) == 2
    assert client.connection.connection_manager.connection_id == 'connection-id-2'
    assert len(mock_ws.events_of_type(MockEventType.CLIENT_CLOSE)) == 1


# UTS: realtime/unit/RTN23b/ping-frame-resets-timer-2
@pytest.mark.skip(reason=PING_FRAMES_SKIP)
async def test_rtn23b_ping_frame_resets_timer():
    pass


# UTS: realtime/unit/RTN23b/any-message-resets-timer-3
@pytest.mark.skip(reason=PING_FRAMES_SKIP)
async def test_rtn23b_any_message_resets_timer():
    pass


# UTS: realtime/unit/RTN23b/timeout-triggers-reconnect-4
async def test_rtn23b_timeout_triggers_reconnect():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=numbered_connections(attempts))
    client = liveness_client(mock_ws)
    states = record_states(client)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert len(attempts) == 1

    await next_connection_state(client, ConnectionState.CONNECTED)

    assert contains_in_order(states, FULL_CYCLE)
    assert len(attempts) == 2
    assert client.connection.state == ConnectionState.CONNECTED
    assert client.connection.connection_manager.connection_id == 'connection-id-2'
    assert len(mock_ws.events_of_type(MockEventType.CLIENT_CLOSE)) == 1


# UTS: realtime/unit/RTN23b/reconnect-uses-resume-5
async def test_rtn23b_reconnect_uses_resume():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=numbered_connections(attempts))
    client = liveness_client(mock_ws)
    states = record_states(client)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await next_connection_state(client, ConnectionState.CONNECTED)

    assert contains_in_order(states, FULL_CYCLE)
    assert len(attempts) == 2
    assert 'resume' not in attempts[0].url.query_params
    assert attempts[1].url.query_params['resume'] == 'connection-key-1'


# UTS: realtime/unit/RTN23b/multiple-pings-keep-alive-6
@pytest.mark.skip(reason=PING_FRAMES_SKIP)
async def test_rtn23b_multiple_pings_keep_alive():
    pass


# UTS: realtime/unit/RTN23c/heartbeats-bounce-query-param-0
@pytest.mark.skip(reason=HEARTBEATS_BOUNCE_SKIP)
async def test_rtn23c_heartbeats_bounce_query_param():
    pass


# UTS: realtime/unit/RTN23c1/ping-pong-echo-id-0
@deviation
async def test_rtn23c1_ping_pong_echo_id():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=numbered_connections(attempts, 15000))
    client = liveness_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    # RTN23c1 binds every client, whatever `heartbeats` value it sent. ably-python
    # handles no PING: action 22 matches no branch of `on_protocol_message`, so
    # nothing leaves the client and this wait runs out
    mock_ws.send_to_client(PING_MESSAGE('ping-1'))
    pong_with_id = await mock_ws.await_next_message_from_client(timeout=1.0)

    mock_ws.send_to_client({'action': 22})
    pong_without_id = await mock_ws.await_next_message_from_client(timeout=1.0)

    assert pong_with_id['action'] == 23
    assert pong_with_id['id'] == 'ping-1'
    assert pong_with_id.get('msgSerial') is None

    assert pong_without_id['action'] == 23
    assert pong_without_id.get('id') is None
    assert pong_without_id.get('msgSerial') is None

    for pong in (pong_with_id, pong_without_id):
        assert pong.get('channel') is None
        assert pong.get('messages') is None
        assert pong.get('presence') is None

    assert len(mock_ws.messages_from_client) == 2


# UTS: realtime/unit/RTN23c1/pong-regardless-of-heartbeats-param-1
@deviation
async def test_rtn23c1_pong_regardless_of_heartbeats_param():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=numbered_connections(attempts, 15000))
    client = liveness_client(mock_ws, transport_params={'heartbeats': 'false'})

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    assert attempts[0].url.query_params['heartbeats'] == 'false'

    mock_ws.send_to_client(PING_MESSAGE('ping-1'))
    pong = await mock_ws.await_next_message_from_client(timeout=1.0)

    assert pong['action'] == 23
    assert pong['id'] == 'ping-1'
