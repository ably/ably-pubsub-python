"""Derived from uts/realtime/unit/connection/when_state_test.md in ably/specification.

Spec points: RTN26, RTN26a, RTN26b
"""

import asyncio

from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import STATE_TIMEOUT, await_connection_state, realtime_client
from test.uts.helpers.clock import settle
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

CONNECTED_MESSAGE = connected_message('connection-id', connectionKey='connection-key')


def when_state(connection, state):
    """The specifications' `connection.whenState(state, listener)`.

    ably-python spells it `Connection._when_state(state)`, which returns an
    awaitable instead of taking a listener: already resolved with `None` when
    the connection is in `state` (RTN26a), and otherwise resolving with the
    `ConnectionStateChange` that enters it (RTN26b). Run as a task it carries
    the same two observables a listener does — whether it has been called, and
    with what. See [deviations.md](../../../deviations.md).

    The deferred branch registers its `once` when the coroutine starts rather
    than when it is created, so a caller yields to the event loop after this
    returns if the state may change in the meantime.
    """
    return asyncio.ensure_future(connection._when_state(state))


def next_connection_state(connection, state):
    """An awaitable of the *next* entry into `state`, registered now.

    `await_connection_state` returns at once for the state the connection is
    already in, which is not what a test asserting a second entry into a state
    wants.
    """
    reached = asyncio.get_running_loop().create_future()

    def on_state(change):
        if not reached.done():
            reached.set_result(change)

    connection.once(state, on_state)
    return asyncio.wait_for(reached, STATE_TIMEOUT)


# UTS: realtime/unit/RTN26a/immediate-callback-current-state-0
async def test_rtn26a_immediate_callback_current_state():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    client = realtime_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    waiter = when_state(client.connection, ConnectionState.CONNECTED)

    # Resolved before the event loop is yielded to, which is the strongest
    # reading of the specification's "invoked synchronously or very quickly"
    assert waiter.done()
    assert await waiter is None


# UTS: realtime/unit/RTN26b/deferred-callback-future-state-0
async def test_rtn26b_deferred_callback_future_state():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    client = realtime_client(mock_ws)

    assert client.connection.state == ConnectionState.INITIALIZED

    waiter = when_state(client.connection, ConnectionState.CONNECTED)
    await settle()

    assert not waiter.done()

    client.connect()
    change = await asyncio.wait_for(waiter, STATE_TIMEOUT)

    assert change is not None
    assert change.previous in (ConnectionState.INITIALIZED, ConnectionState.CONNECTING)
    assert change.current == ConnectionState.CONNECTED


# UTS: realtime/unit/RTN26b/fires-only-once-1
async def test_rtn26b_fires_only_once():
    attempts = []

    def on_connection_attempt(conn):
        attempts.append(conn)
        index = len(attempts)
        conn.respond_with_success(
            connected_message(f'connection-id-{index}', connectionKey=f'connection-key-{index}'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, disconnected_retry_timeout=100)

    invocations = []

    async def record():
        invocations.append(await client.connection._when_state(ConnectionState.CONNECTED))

    listener = asyncio.ensure_future(record())
    await settle()

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await asyncio.wait_for(listener, STATE_TIMEOUT)

    assert len(invocations) == 1

    reconnected = next_connection_state(client.connection, ConnectionState.CONNECTED)
    mock_ws.simulate_disconnect()
    # RTN15a retries immediately after a drop from CONNECTED, so the second
    # connection is established without any time passing
    await reconnected

    assert client.connection.connection_manager.connection_id == 'connection-id-2'
    assert len(invocations) == 1


# UTS: realtime/unit/RTN26a/multiple-whenstate-calls-1
async def test_rtn26a_multiple_whenstate_calls():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    client = realtime_client(mock_ws)

    first = when_state(client.connection, ConnectionState.CONNECTED)
    second = when_state(client.connection, ConnectionState.CONNECTED)
    third = when_state(client.connection, ConnectionState.CONNECTING)
    await settle()

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await asyncio.wait_for(asyncio.gather(first, second, third), STATE_TIMEOUT)

    assert first.done()
    assert second.done()
    assert third.done()


# UTS: realtime/unit/RTN26a/no-fire-for-past-state-2
async def test_rtn26a_no_fire_for_past_state():
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    client = realtime_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    waiter = when_state(client.connection, ConnectionState.CONNECTING)
    await settle()

    # whenState reads the current state, not the states already passed through
    assert not waiter.done()
    waiter.cancel()


# UTS: realtime/unit/RTN26/whenstate-different-states-0
async def test_rtn26_whenstate_different_states():
    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: conn.respond_with_refused())
    # A refused connect reaches DISCONNECTED when the connecting transition
    # timer expires, so a short request timeout keeps that wait small
    client = realtime_client(mock_ws, realtime_request_timeout=300)

    initialized = when_state(client.connection, ConnectionState.INITIALIZED)
    connecting = when_state(client.connection, ConnectionState.CONNECTING)
    disconnected = when_state(client.connection, ConnectionState.DISCONNECTED)
    await settle()

    assert initialized.done()
    assert await initialized is None
    assert not connecting.done()
    assert not disconnected.done()

    client.connect()
    await asyncio.wait_for(disconnected, STATE_TIMEOUT)

    assert initialized.done()
    assert connecting.done()
    assert disconnected.done()
