import asyncio

import pytest

from ably.realtime.connection import ConnectionState
from test.uts.helpers.client import close_open_clients, realtime_client
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.mock_websocket import CONNECTED_MESSAGE, MockWebSocket


@pytest.fixture(autouse=True)
async def close_clients():
    yield
    await close_open_clients()


# RTN14c
async def test_an_attempt_the_transition_timer_ends_is_cancelled():
    # The server never answers the handshake, so only the transition timer ends the attempt
    mock_ws = MockWebSocket(on_connection_attempt=lambda conn: None)
    clock = FakeClock()
    client = realtime_client(mock_ws, clock=clock, realtime_request_timeout=1000)

    client.connect()
    await settle()
    attempt = client.connection.connection_manager.connect_base_task
    assert not attempt.done()

    await clock.advance(1100)
    await settle()

    assert client.connection.state == ConnectionState.DISCONNECTED
    assert attempt.done()


# RTN14c
async def test_an_attempt_the_transition_timer_ends_does_not_connect_afterwards():
    authorised = asyncio.Event()
    attempts = []

    async def auth_callback(token_params):
        await authorised.wait()
        return 'a-token'

    def on_connection_attempt(conn):
        attempts.append(conn)
        conn.respond_with_success(CONNECTED_MESSAGE)

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    clock = FakeClock()
    client = realtime_client(mock_ws, clock=clock, auth_callback=auth_callback,
                             realtime_request_timeout=1000)

    client.connect()
    await settle()
    await clock.advance(1100)
    assert client.connection.state == ConnectionState.DISCONNECTED

    # The auth callback answers after the attempt it was serving has been given up on
    authorised.set()
    await settle()

    assert client.connection.state == ConnectionState.DISCONNECTED
    assert attempts == []
