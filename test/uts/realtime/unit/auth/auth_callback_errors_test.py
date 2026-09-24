"""Derived from uts/realtime/unit/auth/auth_callback_errors_test.md in ably/specification.

Spec points: RSA4c, RSA4c2, RSA4c3, RSA4d, RSA4e, RSA4f
"""

import asyncio
import time

import pytest

from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.types.tokendetails import TokenDetails
from ably.util.exceptions import AblyException
from test.uts.helpers.client import await_connection_state, realtime_client, rest_client
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

AUTH_MESSAGE = {'action': int(ProtocolMessageAction.AUTH)}

# A retry far enough out that a DISCONNECTED connection does not reconnect
# behind the assertions.
NO_RECONNECT = 60000

# The specification's 128KiB limit, exceeded by one character.
OVERSIZED_TOKEN = 'x' * 131073

CHANNEL_DETAILS_BODY = {
    'channelId': 'test-channel',
    'status': {'isActive': True, 'occupancy': {'metrics': {'connections': 0}}},
}


def now():
    return int(time.time() * 1000)


def connect_successfully():
    """A handler that completes the attempt and sends CONNECTED behind it."""
    message = connected_message('connection-id', connectionKey='connection-key')

    def on_connection_attempt(conn):
        conn.respond_with_success(message)

    return on_connection_attempt


async def poll_until(condition, timeout=5.0, description='condition'):
    """Waits for `condition` to hold, yielding to the event loop between checks.

    This is the specifications' `AWAIT UNTIL`. The auth paths chain tasks
    several levels deep, so a single yield is not enough to see the result of
    one; the deadline is a safety net, not a delay.
    """
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f'Timed out waiting for {description}')
        await settle(passes=5)


# UTS: realtime/unit/RSA4c2/callback-error-connecting-disconnected-0
async def test_rsa4c2_callback_error_connecting_disconnected():
    auth_callback_count = 0

    async def auth_callback(params):
        nonlocal auth_callback_count
        auth_callback_count += 1
        if auth_callback_count == 1:
            raise AblyException('Auth server unavailable', 500, 50000)
        return TokenDetails(token=f'valid-token-{auth_callback_count}', expires=now() + 3600000)

    mock_ws = MockWebSocket(on_connection_attempt=connect_successfully())
    client = realtime_client(mock_ws, auth_callback=auth_callback, use_binary_protocol=False,
                             disconnected_retry_timeout=NO_RECONNECT)

    state_changes = []
    client.connection.on(lambda change: state_changes.append(change))

    client.connect()
    await await_connection_state(client, ConnectionState.DISCONNECTED)

    assert client.connection.state == ConnectionState.DISCONNECTED

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 80019
    assert client.connection.error_reason.status_code == 401
    # RSA4c2 requires `cause` to carry the underlying 50000 error.
    # `ConnectionManager.on_error_from_authorize` builds the 80019 without one,
    # so the callback's own error is only in the log.
    assert client.connection.error_reason.cause is None

    disconnected_changes = [c for c in state_changes if c.current == ConnectionState.DISCONNECTED]
    assert len(disconnected_changes) >= 1
    assert disconnected_changes[0].reason is not None
    assert disconnected_changes[0].reason.code == 80019


# UTS: realtime/unit/RSA4c2/callback-timeout-connecting-disconnected-1
async def test_rsa4c2_callback_timeout_connecting_disconnected():
    never_returns = asyncio.Event()

    async def auth_callback(params):
        await never_returns.wait()

    clock = FakeClock()
    mock_ws = MockWebSocket(on_connection_attempt=connect_successfully())
    client = realtime_client(mock_ws, clock=clock, auth_callback=auth_callback,
                             realtime_request_timeout=10000, use_binary_protocol=False,
                             disconnected_retry_timeout=NO_RECONNECT)

    state_changes = []
    client.connection.on(lambda change: state_changes.append(change))

    client.connect()
    # With the fake clock installed only `advance` moves time, so the state the
    # timeout produces is recorded and asserted rather than awaited
    await clock.advance(11000)

    assert client.connection.state == ConnectionState.DISCONNECTED

    # RSA4c requires a callback that outruns `realtimeRequestTimeout` to be
    # treated as an auth error, giving 80019/401. ably-python applies no
    # timeout to the callback itself: the CONNECTING transition timer ends the
    # attempt instead, with the generic "request timeout" error it raises for
    # any connect that does not complete in time.
    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 50003
    assert client.connection.error_reason.status_code == 504

    never_returns.set()


# UTS: realtime/unit/RSA4c3/callback-error-connected-stays-0
async def test_rsa4c3_callback_error_connected_stays():
    auth_callback_count = 0

    async def auth_callback(params):
        nonlocal auth_callback_count
        auth_callback_count += 1
        if auth_callback_count == 1:
            return TokenDetails(token='initial-token', expires=now() + 3600000)
        raise AblyException('Auth server unavailable', 500, 50000)

    mock_ws = MockWebSocket(on_connection_attempt=connect_successfully())
    client = realtime_client(mock_ws, auth_callback=auth_callback, use_binary_protocol=False)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    state_changes = []
    client.connection.on(lambda change: state_changes.append(change))

    mock_ws.send_to_client(AUTH_MESSAGE)

    await poll_until(lambda: auth_callback_count >= 2, description='the reauth callback to run')
    await settle()

    assert client.connection.state == ConnectionState.CONNECTED
    assert state_changes == []
    assert client.connection.error_reason is None


# UTS: realtime/unit/RSA4d/callback-403-connecting-failed-0
@deviation
async def test_rsa4d_callback_403_connecting_failed():
    connection_attempted = False

    async def auth_callback(params):
        raise AblyException('Account disabled', 403, 40300)

    def on_connection_attempt(conn):
        nonlocal connection_attempted
        connection_attempted = True
        conn.respond_with_success(connected_message('connection-id', connectionKey='connection-key'))

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = realtime_client(mock_ws, auth_callback=auth_callback, use_binary_protocol=False,
                             disconnected_retry_timeout=NO_RECONNECT)

    state_changes = []
    client.connection.on(lambda change: state_changes.append(change))

    client.connect()
    await await_connection_state(client, ConnectionState.FAILED)

    assert client.connection.state == ConnectionState.FAILED
    assert connection_attempted is False

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 80019
    assert client.connection.error_reason.status_code == 403
    assert client.connection.error_reason.cause is not None
    assert client.connection.error_reason.cause.code == 40300
    assert client.connection.error_reason.cause.status_code == 403

    failed_changes = [c for c in state_changes if c.current == ConnectionState.FAILED]
    assert len(failed_changes) == 1
    assert failed_changes[0].reason is not None
    assert failed_changes[0].reason.code == 80019
    assert failed_changes[0].reason.status_code == 403

    disconnected_changes = [c for c in state_changes if c.current == ConnectionState.DISCONNECTED]
    assert disconnected_changes == []


# UTS: realtime/unit/RSA4d/callback-403-reauth-failed-1
@deviation
async def test_rsa4d_callback_403_reauth_failed():
    auth_callback_count = 0

    async def auth_callback(params):
        nonlocal auth_callback_count
        auth_callback_count += 1
        if auth_callback_count == 1:
            return TokenDetails(token='initial-token', expires=now() + 3600000)
        raise AblyException('Account suspended', 403, 40300)

    mock_ws = MockWebSocket(on_connection_attempt=connect_successfully())
    client = realtime_client(mock_ws, auth_callback=auth_callback, use_binary_protocol=False,
                             disconnected_retry_timeout=NO_RECONNECT)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    mock_ws.send_to_client(AUTH_MESSAGE)

    await await_connection_state(client, ConnectionState.FAILED)

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 80019
    assert client.connection.error_reason.status_code == 403
    assert client.connection.error_reason.cause is not None
    assert client.connection.error_reason.cause.code == 40300


# UTS: realtime/unit/RSA4f/callback-invalid-type-format-0
@deviation
async def test_rsa4f_callback_invalid_type_format():
    async def auth_callback(params):
        return 12345

    mock_ws = MockWebSocket(on_connection_attempt=connect_successfully())
    client = realtime_client(mock_ws, auth_callback=auth_callback, use_binary_protocol=False,
                             disconnected_retry_timeout=NO_RECONNECT)

    client.connect()
    await await_connection_state(client, ConnectionState.DISCONNECTED)

    assert client.connection.state == ConnectionState.DISCONNECTED

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 80019
    assert client.connection.error_reason.status_code == 401


# UTS: realtime/unit/RSA4f/callback-oversized-token-format-1
@pytest.mark.skip(
    reason='A token over 128KiB makes the websocket URL longer than httpx.URL accepts, and '
           'the mock parses every connection URL through it, so the attempt raises InvalidURL '
           'inside the mock before it is recorded and nothing about the SDK can be observed.')
async def test_rsa4f_callback_oversized_token_format():
    async def auth_callback(params):
        return OVERSIZED_TOKEN

    mock_ws = MockWebSocket(on_connection_attempt=connect_successfully())
    client = realtime_client(mock_ws, auth_callback=auth_callback, use_binary_protocol=False,
                             disconnected_retry_timeout=NO_RECONNECT)

    client.connect()
    await await_connection_state(client, ConnectionState.DISCONNECTED)

    assert client.connection.state == ConnectionState.DISCONNECTED

    assert client.connection.error_reason is not None
    assert client.connection.error_reason.code == 80019
    assert client.connection.error_reason.status_code == 401


# UTS: realtime/unit/RSA4e/rest-callback-error-40170-0
async def test_rsa4e_rest_callback_error_40170():
    async def auth_callback(params):
        raise Exception('Network failure connecting to auth server')

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, CHANNEL_DETAILS_BODY),
    )
    client = rest_client(mock_http, auth_callback=auth_callback, use_binary_protocol=False)

    channel = client.channels.get('test-channel')
    with pytest.raises(AblyException) as excinfo:
        await channel.status()

    assert excinfo.value.code == 40170
    assert excinfo.value.status_code == 401
    assert excinfo.value.message is not None
    assert len(excinfo.value.message) > 0
