"""Construction and teardown for the clients that derived tests drive."""

import asyncio
import logging

from ably import AblyRealtime, AblyRest
from ably.types.testoptions import TestOptions

log = logging.getLogger(__name__)

DEFAULT_KEY = 'app.key:secret'

CREDENTIAL_OPTIONS = ('key', 'token', 'token_details', 'auth_callback', 'auth_url', 'key_name')

# How long teardown gives a client to reach CLOSED, so that one left in a state
# it cannot leave fails its own test rather than hanging the suite.
CLOSE_TIMEOUT = 5.0

# The wait the specifications quote for a connection state change.
STATE_TIMEOUT = 5.0

__open_clients = []


def rest_client(mock_http, **kwargs):
    """A REST client whose HTTP calls `mock_http` serves.

    Stands in for the specifications' `install_mock(mock_http)` followed by
    `Rest(options: ...)`. Credentials default to a key where a specification
    does not name any. The client is closed when the test ends.
    """
    if not any(option in kwargs for option in CREDENTIAL_OPTIONS):
        kwargs['key'] = DEFAULT_KEY
    client = AblyRest(test_options=TestOptions(http_transport=mock_http.as_transport()), **kwargs)
    __open_clients.append(client)
    return client


def realtime_client(mock_websocket=None, mock_http=None, clock=None, **kwargs):
    """A realtime client whose I/O the mocks passed to it serve.

    Stands in for the specifications' `install_mock(mock_ws)` followed by
    `Realtime(options: ...)`. `mock_websocket` serves its websocket
    connections, `mock_http` its HTTP calls and `clock` its delayed callbacks;
    each is left to the real implementation when omitted.

    Credentials default to a key where a specification does not name any,
    `auto_connect` to false, and the fallback hosts to none. See
    [deviations.md](../deviations.md) for those last two. The client is closed
    when the test ends.
    """
    if not any(option in kwargs for option in CREDENTIAL_OPTIONS):
        kwargs['key'] = DEFAULT_KEY
    kwargs.setdefault('auto_connect', False)
    kwargs.setdefault('fallback_hosts', [])
    client = AblyRealtime(test_options=TestOptions(
        http_transport=mock_http.as_transport() if mock_http is not None else None,
        websocket_connect=mock_websocket.as_connect() if mock_websocket is not None else None,
        timer=clock.timer if clock is not None else None,
    ), **kwargs)
    __open_clients.append(client)
    return client


async def await_connection_state(client, state, timeout=STATE_TIMEOUT):
    """Waits for `client`'s connection to reach `state`.

    This is the specifications' `AWAIT_STATE`. The listener is registered
    before the wait begins, so a state reached in the meantime is not missed.

    Only a state the client reaches on its own can be waited for this way:
    with a `FakeClock` installed, nothing moves time but `advance()`, so a
    state that a timer produces has to be recorded with `connection.on(...)`
    and asserted afterwards, or waited for from a task started first.
    """
    connection = client.connection
    if connection.state == state:
        return
    reached = asyncio.get_running_loop().create_future()

    def on_state(change):
        if not reached.done():
            reached.set_result(change)

    connection.once(state, on_state)
    try:
        await asyncio.wait_for(reached, timeout)
    except asyncio.TimeoutError:
        raise AssertionError(
            f'Timed out waiting for connection state {state}; it was {connection.state}') from None


async def next_connection_state(client, state, timeout=STATE_TIMEOUT):
    """Waits for `client`'s connection to enter `state` afresh.

    Where `await_connection_state` is satisfied by the state the connection is
    already in, this one always waits for the next entry into it, which is what
    a specification means by reconnecting to a state it has held before.
    """
    connection = client.connection
    reached = asyncio.get_running_loop().create_future()

    def on_state(change):
        if not reached.done():
            reached.set_result(change)

    connection.once(state, on_state)
    try:
        return await asyncio.wait_for(reached, timeout)
    except asyncio.TimeoutError:
        raise AssertionError(
            f'Timed out waiting for the next {state}; it was {connection.state}') from None


async def close_open_clients():
    """Closes the clients a test built, whatever state they are in.

    A realtime client which never connected, or whose connect failed, reaches
    CLOSED by the same path as a connected one. Teardown carries on through a
    client that cannot get there, closing its HTTP layer directly so the rest
    of the suite is not left holding it.
    """
    while __open_clients:
        client = __open_clients.pop()
        try:
            await asyncio.wait_for(client.close(), CLOSE_TIMEOUT)
        except Exception as error:
            log.warning(f'close_open_clients(): {type(client).__name__} did not close: {error!r}')
            try:
                await client.http.close()
            except Exception:
                pass
