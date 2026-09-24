"""Derived from uts/realtime/unit/connection/connection_ping_test.md in ably/specification.

Spec points: RTN13, RTN13a, RTN13b, RTN13c, RTN13d, RTN13e

`ping()`'s own timeout does not run on the timer seam — `ConnectionManager.ping`
awaits `asyncio.wait_for(..., realtime_request_timeout / 1000)` on the loop
clock — so the tests that wait one out use a short real `realtime_request_timeout`
rather than a `FakeClock`. The fake clock is still installed where a
specification advances past `connectionStateTtl` to reach SUSPENDED, which no
client option reaches.
"""

import asyncio

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from test.uts.helpers.client import (
    await_connection_state,
    poll_until,
    realtime_client,
)
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_websocket import (
    ERROR_MESSAGE,
    MockWebSocket,
    connected_message,
)

HEARTBEAT = int(ProtocolMessageAction.HEARTBEAT)

# Long enough that a ping which is meant to resolve is never cut short, short
# enough that a ping which is meant to time out does so quickly
REQUEST_TIMEOUT = 2000
SHORT_REQUEST_TIMEOUT = 300

# `Defaults.connection_state_ttl` is 120 s and is read directly by the suspend
# timer, which is the one interval no client option reaches
CONNECTION_STATE_TTL = 120000


def connected(connection_id='conn-id-1', connection_key='conn-key-1', max_idle_interval=15000):
    """The CONNECTED message the specifications answer their attempts with."""
    return connected_message(
        connection_id, connectionKey=connection_key,
        maxIdleInterval=max_idle_interval, connectionStateTtl=CONNECTION_STATE_TTL)


def echo_heartbeats(mock_websocket):
    """A message handler answering each HEARTBEAT with one carrying the same id.

    This is the server side of RTN13a. The handler runs inside `transport.send`,
    so the echo is always back before the ping's timeout can run.
    """
    def on_message_from_client(message):
        if message.get('action') == HEARTBEAT:
            mock_websocket.send_to_client({'action': HEARTBEAT, 'id': message.get('id')})
    return on_message_from_client


def heartbeats_sent(mock_websocket):
    """Every HEARTBEAT the client has sent."""
    return [message for message in mock_websocket.messages_from_client
            if message.get('action') == HEARTBEAT]


async def ping_outcome(ping_task):
    """What a ping produced, as a `(duration, error)` pair.

    The task is always awaited, so an assertion that fails afterwards cannot
    leave its exception unretrieved.
    """
    try:
        return await ping_task, None
    except Exception as error:
        return None, error


# UTS: realtime/unit/RTN13a/ping-heartbeat-roundtrip-0
async def test_rtn13a_ping_heartbeat_roundtrip():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(connected()))
    mock_ws.on_message_from_client = echo_heartbeats(mock_ws)
    client = realtime_client(mock_ws, realtime_request_timeout=REQUEST_TIMEOUT)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    duration = await client.connection.ping()

    assert duration is not None
    assert duration >= 0
    assert len(heartbeats_sent(mock_ws)) == 1


# UTS: realtime/unit/RTN13e/heartbeat-random-id-0
async def test_rtn13e_heartbeat_random_id():
    captured_ids = []

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(connected()))

    def on_message_from_client(message):
        if message.get('action') == HEARTBEAT:
            captured_ids.append(message.get('id'))
            # A heartbeat carrying another ping's id is no answer to this one
            mock_ws.send_to_client({'action': HEARTBEAT, 'id': 'wrong-id'})
            mock_ws.send_to_client({'action': HEARTBEAT, 'id': message.get('id')})

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(mock_ws, realtime_request_timeout=REQUEST_TIMEOUT)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    duration = await client.connection.ping()

    assert duration is not None
    assert duration >= 0
    assert captured_ids[0] is not None
    assert len(captured_ids[0]) > 0


# UTS: realtime/unit/RTN13e/no-id-heartbeat-ignored-1
async def test_rtn13e_no_id_heartbeat_ignored():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(connected()))

    def on_message_from_client(message):
        if message.get('action') == HEARTBEAT:
            # A server-initiated heartbeat carries no id and answers no ping
            mock_ws.send_to_client({'action': HEARTBEAT})
            mock_ws.send_to_client({'action': HEARTBEAT, 'id': message.get('id')})

    mock_ws.on_message_from_client = on_message_from_client
    client = realtime_client(mock_ws, realtime_request_timeout=REQUEST_TIMEOUT)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    duration = await client.connection.ping()

    assert duration is not None
    assert duration >= 0


# UTS: realtime/unit/RTN13e/concurrent-pings-unique-ids-2
async def test_rtn13e_concurrent_pings_unique_ids():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(connected()))
    mock_ws.on_message_from_client = echo_heartbeats(mock_ws)
    client = realtime_client(mock_ws, realtime_request_timeout=REQUEST_TIMEOUT)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    first = asyncio.ensure_future(client.connection.ping())
    second = asyncio.ensure_future(client.connection.ping())

    duration1 = await first
    duration2 = await second

    assert duration1 is not None
    assert duration2 is not None

    sent = heartbeats_sent(mock_ws)
    assert len(sent) == 2
    assert sent[0]['id'] != sent[1]['id']


# UTS: realtime/unit/RTN13c/ping-timeout-0
async def test_rtn13c_ping_timeout():
    # The server answers no HEARTBEAT, so the ping runs out its
    # `realtime_request_timeout`, which is real time here rather than advanced
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(connected()))
    client = realtime_client(mock_ws, realtime_request_timeout=SHORT_REQUEST_TIMEOUT)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    duration, error = await ping_outcome(asyncio.ensure_future(client.connection.ping()))

    assert error is not None
    assert 'timeout' in str(error).lower()


# UTS: realtime/unit/RTN13b/ping-error-initialized-0
async def test_rtn13b_ping_error_initialized():
    client = realtime_client(MockWebSocket())

    assert client.connection.state == ConnectionState.INITIALIZED

    duration, error = await ping_outcome(asyncio.ensure_future(client.connection.ping()))

    assert error is not None


# UTS: realtime/unit/RTN13b/ping-error-suspended-1
async def test_rtn13b_ping_error_suspended():
    clock = FakeClock()
    # The specification fails the attempt with a refused connection; ably-python
    # catches only a websocket error or a name resolution failure, so a refused
    # one produces no state change until the transition timer ends it. See
    # deviations-connection-liveness.md
    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: conn.respond_with_dns_error())
    # A retry timeout past `connectionStateTtl` leaves the suspend timer as the
    # only thing the advance below fires
    client = realtime_client(
        mock_ws, clock=clock, disconnected_retry_timeout=CONNECTION_STATE_TTL * 2,
        suspended_retry_timeout=CONNECTION_STATE_TTL * 2)

    client.connect()
    await await_connection_state(client, ConnectionState.DISCONNECTED)

    await clock.advance(CONNECTION_STATE_TTL + 1000)

    assert client.connection.state == ConnectionState.SUSPENDED

    duration, error = await ping_outcome(asyncio.ensure_future(client.connection.ping()))

    assert error is not None


# UTS: realtime/unit/RTN13b/ping-error-closed-2
async def test_rtn13b_ping_error_closed():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(connected()))
    client = realtime_client(mock_ws, realtime_request_timeout=REQUEST_TIMEOUT)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    await client.close()
    assert client.connection.state == ConnectionState.CLOSED

    duration, error = await ping_outcome(asyncio.ensure_future(client.connection.ping()))

    assert error is not None


# UTS: realtime/unit/RTN13b/ping-error-failed-3
async def test_rtn13b_ping_error_failed():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_error(
            ERROR_MESSAGE(80000, 'Fatal error', status_code=400)))
    client = realtime_client(mock_ws, realtime_request_timeout=REQUEST_TIMEOUT)

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED)

    duration, error = await ping_outcome(asyncio.ensure_future(client.connection.ping()))

    assert error is not None


# UTS: realtime/unit/RTN13d/ping-deferred-connecting-0
async def test_rtn13d_ping_deferred_connecting():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=attempts.append)
    mock_ws.on_message_from_client = echo_heartbeats(mock_ws)
    client = realtime_client(mock_ws, realtime_request_timeout=REQUEST_TIMEOUT)

    client.connect()
    # `connect()` sets CONNECTING before the attempt is scheduled, so the attempt
    # itself is what says the connection is under way
    await poll_until(lambda: len(attempts) == 1, description='a connection attempt')
    assert client.connection.state == ConnectionState.CONNECTING

    ping_task = asyncio.ensure_future(client.connection.ping())
    await settle()

    assert len(heartbeats_sent(mock_ws)) == 0

    attempts[0].respond_with_success(connected())
    await await_connection_state(client, ConnectionState.CONNECTED)

    duration, error = await ping_outcome(ping_task)

    assert error is None
    assert duration is not None
    assert duration >= 0
    assert len(heartbeats_sent(mock_ws)) == 1


# UTS: realtime/unit/RTN13d/ping-deferred-disconnected-1
@deviation
async def test_rtn13d_ping_deferred_disconnected():
    clock = FakeClock()
    attempts = []

    def on_connection_attempt(conn):
        attempts.append(conn)
        # The specification drops an established connection to reach DISCONNECTED.
        # RTN15a retries such a drop with no delay, so the state cannot be held
        # long enough to ping from; a failed first attempt settles there instead
        if len(attempts) == 1:
            conn.respond_with_dns_error()
        else:
            conn.respond_with_success(connected('conn-id-2', 'conn-key-2', max_idle_interval=0))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    mock_ws.on_message_from_client = echo_heartbeats(mock_ws)
    client = realtime_client(mock_ws, clock=clock, disconnected_retry_timeout=500,
                             realtime_request_timeout=REQUEST_TIMEOUT)

    client.connect()
    await await_connection_state(client, ConnectionState.DISCONNECTED)

    ping_task = asyncio.ensure_future(client.connection.ping())
    await settle()

    # RTN13d: a ping requested while DISCONNECTED waits for the connection.
    # ably-python admits only CONNECTED and CONNECTING and errors at once
    deferred = not ping_task.done()

    await clock.advance(600)
    await await_connection_state(client, ConnectionState.CONNECTED)

    duration, error = await ping_outcome(ping_task)

    assert deferred, 'RTN13d: the ping errored instead of waiting for the connection'
    assert error is None
    assert duration is not None
    assert duration >= 0
    assert len(heartbeats_sent(mock_ws)) == 1


# UTS: realtime/unit/RTN13b/deferred-ping-error-failed-4
async def test_rtn13b_deferred_ping_error_failed():
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=attempts.append)
    client = realtime_client(mock_ws, realtime_request_timeout=REQUEST_TIMEOUT)

    client.connect()
    await poll_until(lambda: len(attempts) == 1, description='a connection attempt')
    assert client.connection.state == ConnectionState.CONNECTING

    ping_task = asyncio.ensure_future(client.connection.ping())
    await settle()

    attempts[0].respond_with_error(ERROR_MESSAGE(80000, 'Fatal error', status_code=400))
    await await_connection_state(client, ConnectionState.FAILED)

    duration, error = await ping_outcome(ping_task)

    assert error is not None


# UTS: realtime/unit/RTN13b/deferred-ping-error-suspended-5
@deviation
async def test_rtn13b_deferred_ping_error_suspended():
    clock = FakeClock()
    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: conn.respond_with_dns_error())
    client = realtime_client(
        mock_ws, clock=clock, disconnected_retry_timeout=CONNECTION_STATE_TTL * 2,
        suspended_retry_timeout=CONNECTION_STATE_TTL * 2)

    client.connect()
    await await_connection_state(client, ConnectionState.DISCONNECTED)

    ping_task = asyncio.ensure_future(client.connection.ping())
    await settle()

    # RTN13d: the ping waits for the connection rather than failing where the
    # specification expects it to be deferred
    deferred = not ping_task.done()

    await clock.advance(CONNECTION_STATE_TTL + 1000)
    assert client.connection.state == ConnectionState.SUSPENDED

    duration, error = await ping_outcome(ping_task)

    assert deferred, 'RTN13d: the ping errored instead of waiting for the connection'
    assert error is not None


# UTS: realtime/unit/RTN13c/deferred-ping-timeout-1
@deviation
async def test_rtn13c_deferred_ping_timeout():
    clock = FakeClock()
    attempts = []
    mock_ws = MockWebSocket(on_connection_attempt=attempts.append)
    # The clock holds the CONNECTING transition timer, leaving the real interval
    # below as the only thing the connection waits on
    client = realtime_client(mock_ws, clock=clock, realtime_request_timeout=400)
    timeout_in_secs = 0.4

    client.connect()
    await poll_until(lambda: len(attempts) == 1, description='a connection attempt')
    assert client.connection.state == ConnectionState.CONNECTING

    ping_task = asyncio.ensure_future(client.connection.ping())

    # The connection takes most of the ping's timeout to establish itself
    await asyncio.sleep(timeout_in_secs * 0.75)
    attempts[0].respond_with_success(connected(max_idle_interval=0))
    await await_connection_state(client, ConnectionState.CONNECTED)
    connected_at = asyncio.get_running_loop().time()

    duration, error = await ping_outcome(ping_task)
    failed_after = asyncio.get_running_loop().time() - connected_at

    assert error is not None
    assert 'timeout' in str(error).lower()
    # RTN13c with RTN13d: a deferred ping's timeout runs from the HEARTBEAT going
    # out, not from the call. ably-python starts `wait_for` when `ping()` is
    # called, so the ping expires while the connection is still establishing
    assert failed_after >= timeout_in_secs * 0.9
