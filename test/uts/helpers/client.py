"""Construction and teardown for the clients that derived tests drive."""

import asyncio
import inspect
import logging

from ably import AblyRealtime, AblyRest
from ably.types.testoptions import TestOptions
from test.uts.helpers.clock import settle
from test.uts.helpers.sandbox import SANDBOX_ENDPOINT

log = logging.getLogger(__name__)

DEFAULT_KEY = 'app.key:secret'

CREDENTIAL_OPTIONS = ('key', 'token', 'token_details', 'auth_callback', 'auth_url', 'key_name')

# How long teardown gives a client to reach CLOSED, so that one left in a state
# it cannot leave fails its own test rather than hanging the suite.
CLOSE_TIMEOUT = 5.0

# The wait the specifications quote for a connection state change.
STATE_TIMEOUT = 5.0

# What an integration specification's `poll_until(interval: 500ms, timeout: 10s)`
# is asking for, as wall-clock seconds.
POLL_TIMEOUT = 10.0
POLL_INTERVAL = 0.5

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


def sandbox_rest_client(key=None, **kwargs):
    """A REST client talking to the real sandbox, for the integration tier.

    Stands in for an integration specification's `Rest(options: ClientOptions(
    key: api_key, endpoint: "nonprod:sandbox"))`. Where `rest_client` serves
    every call from a mock, this one reaches the network: it carries no
    `test_options`, because there is no transport to install in front of a
    server the tests are there to talk to.

    `key` is the positional credential most specifications pass; one that
    authenticates some other way passes `token=`, `auth_callback=` or
    `auth_url=` instead and leaves it out. The protocol defaults to JSON, which
    is what a specification without a `## Protocol Variants` section means; a
    specification with one drives it from the `use_binary_protocol` fixture.
    The client is closed when the test ends.
    """
    if key is not None:
        kwargs['key'] = key
    kwargs.setdefault('endpoint', SANDBOX_ENDPOINT)
    kwargs.setdefault('use_binary_protocol', False)
    client = AblyRest(**kwargs)
    __open_clients.append(client)
    return client


def sandbox_realtime_client(key=None, **kwargs):
    """A realtime client talking to the real sandbox, for the integration tier.

    Several REST specifications need presence members or presence history that
    only a realtime connection can produce, and read them back over REST.

    Unlike `realtime_client`, this one leaves `auto_connect` and the fallback
    hosts at their library defaults: connecting is the point, and a real
    fallback host is a real host worth reaching for. The client is closed when
    the test ends.
    """
    if key is not None:
        kwargs['key'] = key
    kwargs.setdefault('endpoint', SANDBOX_ENDPOINT)
    kwargs.setdefault('use_binary_protocol', False)
    client = AblyRealtime(**kwargs)
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


async def await_channel_state(channel, state, timeout=STATE_TIMEOUT):
    """Waits for `channel` to reach `state`, returning at once if it holds it."""
    if channel.state == state:
        return
    reached = asyncio.get_running_loop().create_future()

    def on_state(change):
        if not reached.done():
            reached.set_result(change)

    channel.once(state, on_state)
    try:
        await asyncio.wait_for(reached, timeout)
    except asyncio.TimeoutError:
        raise AssertionError(
            f'Timed out waiting for channel state {state}; it was {channel.state}') from None


async def poll_until(condition, timeout=STATE_TIMEOUT, description='condition'):
    """Yields to the event loop until `condition()` holds.

    This is the specifications' `AWAIT UNTIL`. It suits a premise a state does
    not capture, such as an attempt being in flight: `client.connect()` sets
    CONNECTING before the attempt is scheduled, so waiting on the state is
    satisfied before anything has happened.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        if loop.time() >= deadline:
            raise AssertionError(f'Timed out waiting until {description}')
        await asyncio.sleep(0)


async def wall_clock_poll_until(condition, timeout=POLL_TIMEOUT, description='condition',
                                interval=POLL_INTERVAL):
    """Waits on real time until `condition` gives something truthy, and returns it.

    This is the integration tier's `poll_until`. `poll_until` above yields to
    the event loop between attempts, which is the right thing against a mock,
    where nothing but the loop can move the state being waited for. Against a
    real server it would spin a core on a network wait, so this one sleeps the
    specifications' interval instead.

    `condition` may be a plain callable or a coroutine function, since what a
    specification usually polls for is the result of a request. The value the
    condition gave is returned, so a condition that answers with the page it
    fetched saves fetching it again:

        async def published_message():
            page = await channel.history()
            return page if len(page.items) == 1 else None

        history = await wall_clock_poll_until(
            published_message, description='the published message to reach history')

    A `PaginatedResult` is truthy whether or not it holds anything, so a
    condition that returns one straight from `history()` is satisfied by the
    first empty page. Answer with `None` until the page holds what the test is
    waiting for, as above.

    A timeout raises, naming what was being waited for rather than leaving a
    caller with the bare deadline.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        result = condition()
        if inspect.isawaitable(result):
            result = await result
        if result:
            return result
        if loop.time() >= deadline:
            raise AssertionError(f'Timed out after {timeout}s waiting for {description}')
        await asyncio.sleep(interval)


async def connected_client(mock_websocket, **kwargs):
    """A realtime client already CONNECTED through `mock_websocket`.

    Most channel specifications open this way, since a channel cannot attach
    until the connection carrying it is up.
    """
    from ably.realtime.connection import ConnectionState
    from test.uts.helpers.mock_websocket import CONNECTED_MESSAGE

    if mock_websocket.on_connection_attempt is None:
        mock_websocket.on_connection_attempt = lambda conn: conn.respond_with_success(CONNECTED_MESSAGE)
    client = realtime_client(mock_websocket, **kwargs)
    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    return client


async def drop_transport(client, mock_websocket):
    """Drops the transport under `client` and leaves the connection DISCONNECTED.

    The connection retries a drop from CONNECTED immediately, so the attempt
    handler is stalled first, leaving the connection settled where a
    specification expects to find it rather than reconnecting behind the
    assertions. Returns the connection states recorded along the way.
    """
    from ably.realtime.connection import ConnectionState

    states = []

    def record(change):
        states.append(change.current)

    client.connection.on(record)
    mock_websocket.on_connection_attempt = lambda conn: None
    mock_websocket.simulate_disconnect()
    await poll_until(
        lambda: ConnectionState.DISCONNECTED in states,
        description='the connection to report DISCONNECTED')
    await settle()
    return states


async def reconnect_transport(client, mock_websocket, connected_message=None):
    """Drops the transport and waits for `client` to reach CONNECTED again.

    Waiting on the connection state alone would be satisfied by the CONNECTED
    the client already holds, so this counts a fresh arrival.
    """
    from ably.realtime.connection import ConnectionState
    from test.uts.helpers.mock_websocket import CONNECTED_MESSAGE

    message = CONNECTED_MESSAGE if connected_message is None else connected_message
    reconnected = []

    def record(change):
        reconnected.append(change)

    client.connection.on(ConnectionState.CONNECTED, record)
    mock_websocket.on_connection_attempt = lambda conn: conn.respond_with_success(message)
    mock_websocket.simulate_disconnect()
    await poll_until(lambda: len(reconnected) > 0, description='the connection to be re-established')
    return reconnected[0]
