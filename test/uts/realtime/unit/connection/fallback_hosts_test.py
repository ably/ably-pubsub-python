"""Derived from uts/realtime/unit/connection/fallback_hosts_test.md in ably/specification.

Spec points: RTN17, RTN17e, RTN17f, RTN17f1, RTN17g, RTN17h, RTN17i, RTN17j

Two adaptations run through the whole file, both recorded in
deviations.md.

`ConnectionManager.check_connection` issues the RTN17j connectivity check with a
synchronous module-level `httpx.get`, which neither the client's HTTP layer nor
any other seam reaches. Every test here that leaves the client a fallback set
therefore replaces that function for the duration of the test, so nothing in the
batch touches the network.

The specifications fail the primary host with `respond_with_refused()` or
`respond_with_timeout()`. `WebSocketTransport.ws_connect` catches only
`WebSocketException` and `socket.gaierror`, so neither produces the transport
failure that starts the fallback loop; an unresolvable host does, and is what
every test below fails the primary with.
"""

import asyncio
import re
from types import SimpleNamespace

import httpx

from ably.realtime import connectionmanager
from ably.realtime.connection import ConnectionState
from ably.transport.defaults import Defaults
from test.uts.helpers.client import await_connection_state, poll_until, realtime_client
from test.uts.helpers.mock_http import MockHttpClient
from test.uts.helpers.mock_websocket import MockWebSocket, connected_message

# REC1: the default endpoint gives the primary domain and the fallback set
PRIMARY_HOST = Defaults.get_hostname(Defaults.endpoint)
FALLBACK_PATTERN = re.compile(r'\.[abcde]\.fallback\.ably-realtime\.com$')

CONNECTIVITY_CHECK = 'internet-up'

DISCONNECTED_503 = {
    'action': 6,
    'error': {'code': 50003, 'statusCode': 503, 'message': 'Service temporarily unavailable'},
}


def serve_connectivity_check(monkeypatch, body='yes'):
    """Answers RTN17j's connectivity check in process, and records the calls.

    `check_connection` calls `httpx.get` directly, so the function itself is what
    a test has to replace: a client-scoped seam cannot reach it, and left alone
    it makes a real, blocking request on every failed connection.
    """
    requests = []

    def get(url, *args, **kwargs):
        requests.append(SimpleNamespace(url=str(url), method='GET'))
        return httpx.Response(200, text=body, request=httpx.Request('GET', url))

    monkeypatch.setattr(connectionmanager.httpx, 'get', get)
    return requests


def connected(connection_id='connection-id', connection_key='connection-key'):
    """The CONNECTED message the specifications answer a fallback attempt with."""
    return connected_message(
        connection_id, connectionKey=connection_key,
        maxIdleInterval=15000, connectionStateTtl=120000)


def fallback_client(mock_websocket, **kwargs):
    """A client left with the fallback set REC2 gives its endpoint.

    `realtime_client` defaults the set to empty, which every other derived test
    wants and these tests are precisely about not having.
    """
    kwargs.setdefault('fallback_hosts', None)
    return realtime_client(mock_websocket, **kwargs)


# UTS: realtime/unit/RTN17i/prefer-primary-domain-0
async def test_rtn17i_prefer_primary_domain(monkeypatch):
    serve_connectivity_check(monkeypatch)
    hosts = []

    def on_connection_attempt(conn):
        hosts.append(conn.url.host)
        if len(hosts) == 1:
            conn.respond_with_dns_error()
        else:
            conn.respond_with_success(connected())

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = fallback_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=10.0)

    assert hosts[0] == PRIMARY_HOST
    assert FALLBACK_PATTERN.search(hosts[1])

    hosts.clear()
    reconnected = []

    def on_connected(change):
        reconnected.append(change)

    def on_reconnection_attempt(conn):
        hosts.append(conn.url.host)
        conn.respond_with_success(connected('connection-id-2', 'connection-key-2'))

    mock_ws.on_connection_attempt = on_reconnection_attempt
    client.connection.on(ConnectionState.CONNECTED, on_connected)

    # The specification waits out DISCONNECTED between the drop and the
    # reconnection; RTN15a retries a drop from CONNECTED with no delay, so the
    # state is gone before it can be waited on and the reconnection is what the
    # test waits for
    mock_ws.simulate_disconnect()
    await poll_until(lambda: len(reconnected) > 0, timeout=10.0,
                     description='the connection to be re-established')

    assert len(hosts) >= 1
    # The primary domain is tried first even though it failed the last time
    assert hosts[0] == PRIMARY_HOST


# UTS: realtime/unit/RTN17f/fallback-on-error-0
async def test_rtn17f_fallback_on_error(monkeypatch):
    serve_connectivity_check(monkeypatch)
    hosts = []

    def on_connection_attempt(conn):
        hosts.append(conn.url.host)
        if len(hosts) == 1:
            # The specification writes "Host unresolvable" as the primary's
            # failure; an unresolvable host is RSC15l's first condition
            conn.respond_with_dns_error()
        else:
            conn.respond_with_success(connected())

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = fallback_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=10.0)

    assert len(hosts) >= 2
    assert 'realtime.ably' in hosts[0]
    assert 'fallback' in hosts[1]


# UTS: realtime/unit/RTN17f1/disconnected-5xx-fallback-0
async def test_rtn17f1_disconnected_5xx_fallback(monkeypatch):
    serve_connectivity_check(monkeypatch)
    hosts = []

    def on_connection_attempt(conn):
        hosts.append(conn.url.host)
        if len(hosts) == 1:
            conn.respond_with_success()
            conn.send_to_client_and_close(DISCONNECTED_503)
        else:
            conn.respond_with_success(connected())

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = fallback_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=10.0)

    assert len(hosts) >= 2
    assert 'realtime.ably' in hosts[0]
    assert 'fallback' in hosts[1]


# UTS: realtime/unit/RTN17j/connectivity-check-before-fallback-0
async def test_rtn17j_connectivity_check_before_fallback(monkeypatch):
    http_requests = serve_connectivity_check(monkeypatch)
    hosts = []

    def on_connection_attempt(conn):
        hosts.append(conn.url.host)
        if len(hosts) == 1:
            conn.respond_with_dns_error()
        else:
            conn.respond_with_success(connected())

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = fallback_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=15.0)

    connectivity_checks = [request for request in http_requests
                           if CONNECTIVITY_CHECK in request.url]
    assert len(connectivity_checks) >= 1
    assert connectivity_checks[0].method == 'GET'
    assert len(hosts) >= 2


# UTS: realtime/unit/RTN17g/empty-fallback-set-error-0
async def test_rtn17g_empty_fallback_set_error(monkeypatch):
    connectivity_checks = serve_connectivity_check(monkeypatch)
    hosts = []

    def on_connection_attempt(conn):
        hosts.append(conn.url.host)
        conn.respond_with_refused()

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    # REC2c2: a custom domain has no fallback set of its own
    client = fallback_client(
        mock_ws, realtime_host='custom.example.com', realtime_request_timeout=300,
        disconnected_retry_timeout=60000)

    client.connect()
    await await_connection_state(client, ConnectionState.DISCONNECTED, timeout=5.0)

    # Long enough for a fallback attempt to show up, were one going to be made
    await asyncio.sleep(0.5)

    assert len(hosts) == 1
    assert hosts[0] == 'custom.example.com'
    # An empty fallback set is answered immediately, with no connectivity check
    assert connectivity_checks == []


# UTS: realtime/unit/RTN17h/fallback-domains-from-rec2-0
async def test_rtn17h_fallback_domains_from_rec2(monkeypatch):
    serve_connectivity_check(monkeypatch)
    hosts = []

    def on_connection_attempt(conn):
        hosts.append(conn.url.host)
        if len(hosts) == 1:
            conn.respond_with_dns_error()
        else:
            conn.respond_with_success(connected())

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    client = fallback_client(mock_ws)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=10.0)

    assert len(hosts) >= 2
    fallback_host = hosts[1]
    assert 'fallback.ably-realtime.com' in fallback_host
    assert FALLBACK_PATTERN.search(fallback_host)


# UTS: realtime/unit/RTN17j/fallback-random-order-1
async def test_rtn17j_fallback_random_order(monkeypatch):
    serve_connectivity_check(monkeypatch)
    fallback_orders = []

    for _ in range(5):
        hosts = []

        def on_connection_attempt(conn, hosts=hosts):
            hosts.append(conn.url.host)
            if len(hosts) <= 3:
                conn.respond_with_dns_error()
            else:
                conn.respond_with_success(connected())

        mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
        client = fallback_client(mock_ws)

        client.connect()
        await await_connection_state(client, ConnectionState.CONNECTED, timeout=15.0)

        fallback_orders.append(tuple(hosts[1:]))
        await client.close()

    assert len(set(fallback_orders)) >= 2


# UTS: realtime/unit/RTN17e/http-uses-same-fallback-0
async def test_rtn17e_http_uses_same_fallback(monkeypatch):
    serve_connectivity_check(monkeypatch)
    channel_name = 'test-RTN17e'
    hosts = []
    http_requests = []

    def on_connection_attempt(conn):
        hosts.append(conn.url.host)
        if len(hosts) == 1:
            conn.respond_with_dns_error()
        else:
            conn.respond_with_success(connected())

    def on_request(request):
        http_requests.append(request)
        request.respond_with(200, [])

    mock_ws = MockWebSocket(on_connection_attempt=on_connection_attempt)
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request)
    client = fallback_client(mock_ws, mock_http=mock_http)

    client.connect()
    await await_connection_state(client, ConnectionState.CONNECTED, timeout=10.0)

    connected_fallback_host = hosts[1]

    channel = client.channels.get(channel_name)
    await channel.history()

    history_requests = [request for request in http_requests
                        if 'messages' in request.url.path]
    assert len(history_requests) >= 1
    assert history_requests[0].url.host == connected_fallback_host
