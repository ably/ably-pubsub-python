"""Derived from uts/realtime/unit/client/realtime_timeouts.md in ably/specification.

Spec points: RTC7
"""

import asyncio

import pytest

from ably.realtime.channel import ChannelState
from ably.realtime.connection import ConnectionState
from ably.transport.websockettransport import ProtocolMessageAction
from ably.util.exceptions import AblyException
from ably.util.helper import get_random_id
from test.uts.helpers.client import await_connection_state, realtime_client
from test.uts.helpers.clock import FakeClock, settle
from test.uts.helpers.mock_http import MockHttpClient
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

SPEC_KEY = 'appId.keyId:keySecret'

CONNECTED_MESSAGE = connected_message(
    'connection-id', connectionKey='connection-key', maxIdleInterval=15000, connectionStateTtl=120000)

# The CONNECTED message the reconnection test uses. `maxIdleInterval` of zero leaves
# the transport's idle timer unscheduled, which keeps the only timers on the fake
# clock the ones this test is about.
IDLE_FREE_CONNECTED_MESSAGE = connected_message(
    'connection-id', connectionKey='connection-key', maxIdleInterval=0, connectionStateTtl=120000)

CUSTOM_REQUEST_TIMEOUT = 500


def attached_message(channel_name):
    return {
        'action': int(ProtocolMessageAction.ATTACHED),
        'channel': channel_name,
        'flags': 0,
    }


# UTS: realtime/unit/RTC7/attach-request-timeout-0
async def test_rtc7_attach_request_timeout():
    channel_name = f'test-RTC7-attach-{get_random_id()}'

    # An ATTACH draws no response, so the channel's state timer is what ends the attach
    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
    )
    clock = FakeClock()
    client = realtime_client(mock_ws, clock=clock, key=SPEC_KEY, auto_connect=False,
                             realtime_request_timeout=CUSTOM_REQUEST_TIMEOUT)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)

    # The attach runs as a task so that the clock can be advanced underneath it
    attaching = asyncio.create_task(channel.attach())
    await settle()

    assert channel.state == ChannelState.ATTACHING

    await clock.advance(600)

    with pytest.raises(AblyException) as excinfo:
        await attaching

    assert excinfo.value is not None
    # RTL4f: an attach timeout leaves the channel SUSPENDED
    assert channel.state == ChannelState.SUSPENDED


# UTS: realtime/unit/RTC7/detach-request-timeout-1
async def test_rtc7_detach_request_timeout():
    channel_name = f'test-RTC7-detach-{get_random_id()}'
    ignore_detach = False

    def on_message_from_client(message):
        if message['action'] == int(ProtocolMessageAction.ATTACH):
            mock_ws.send_to_client(attached_message(channel_name))
        if message['action'] == int(ProtocolMessageAction.DETACH) and ignore_detach:
            # No response, so the channel's state timer is what ends the detach
            pass

    mock_ws = MockWebSocket(
        on_connection_attempt=lambda conn: conn.respond_with_success(CONNECTED_MESSAGE),
        on_message_from_client=on_message_from_client,
    )
    clock = FakeClock()
    client = realtime_client(mock_ws, clock=clock, key=SPEC_KEY, auto_connect=False,
                             realtime_request_timeout=CUSTOM_REQUEST_TIMEOUT)
    channel = client.channels.get(channel_name)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    await channel.attach()

    ignore_detach = True

    detaching = asyncio.create_task(channel.detach())
    await settle()

    assert channel.state == ChannelState.DETACHING

    await clock.advance(600)

    with pytest.raises(AblyException) as excinfo:
        await detaching

    assert excinfo.value is not None
    # RTL5f: a detach timeout returns the channel to ATTACHED
    assert channel.state == ChannelState.ATTACHED


# UTS: realtime/unit/RTC7/disconnected-retry-timeout-2
async def test_rtc7_disconnected_retry_timeout():
    connection_attempt_count = 0

    def on_connection_attempt(conn):
        nonlocal connection_attempt_count
        connection_attempt_count += 1
        if connection_attempt_count == 1:
            conn.respond_with_success(IDLE_FREE_CONNECTED_MESSAGE)
        else:
            # The spec refuses the attempt. `ws_connect` catches only WebSocketException
            # and socket.gaierror, so a refused connection is left to the transition
            # timer and takes `realtime_request_timeout` to surface; a DNS failure
            # fails fast and reaches the retry logic the same way. See
            # deviations-client.md.
            conn.respond_with_dns_error()

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    # RTN17j's connectivity check is what the mock HTTP client keeps off the network
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, 'yes', {'Content-Type': 'text/plain'}),
    )
    clock = FakeClock()
    client = realtime_client(mock_ws, mock_http=mock_http, clock=clock, key=SPEC_KEY,
                             auto_connect=False, disconnected_retry_timeout=2000, fallback_hosts=[])

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED)
    assert connection_attempt_count == 1

    states = []
    client.connection.on(lambda change: states.append(change.current))

    # RTN15a makes the first retry after a drop from CONNECTED immediate, so the
    # timer-driven retry this test is about is the one after that
    mock_ws.simulate_disconnect()
    await settle()

    assert ConnectionState.DISCONNECTED in states
    count_after_immediate = connection_attempt_count
    assert count_after_immediate > 1

    await clock.advance(1500)
    assert connection_attempt_count == count_after_immediate

    await clock.advance(1500)

    assert connection_attempt_count > count_after_immediate


# UTS: realtime/unit/RTC7/default-timeouts-applied-3
async def test_rtc7_default_timeouts_applied():
    client = realtime_client(key=SPEC_KEY, auto_connect=False)

    assert client.options.realtime_request_timeout == 10000
    assert client.options.disconnected_retry_timeout == 15000
    assert client.options.suspended_retry_timeout == 30000

    # DEVIATION: the spec asserts httpOpenTimeout == 4000 and httpRequestTimeout ==
    # 10000 on the options. ably-python leaves both unset on the options and holds the
    # defaults on the HTTP layer, in seconds rather than milliseconds. See
    # deviations-client.md.
    assert client.options.http_open_timeout is None
    assert client.options.http_request_timeout is None
    assert client.http.http_open_timeout == 4
    assert client.http.http_request_timeout == 10
