import httpx
import pytest

from ably.pubsub.realtime.connection import ConnectionState
from ably.pubsub.server import create_http_client
from ably.pubsub.types.testoptions import TestOptions
from ably.pubsub.util.exceptions import AblyException
from test.uts.helpers.client import await_connection_state, close_open_clients, realtime_client
from test.uts.helpers.mock_http import MockHttpClient
from test.uts.helpers.mock_websocket import MockWebSocket


def test_http_get_rest_hosts_works_when_fallback_realtime_host_is_set():
    ably = create_http_client(token="foo")
    ably.options.fallback_host = ably.options.get_hosts()[0]
    # Should not raise TypeError
    hosts = ably.http.get_hosts()
    assert isinstance(hosts, list)
    assert all(isinstance(host, str) for host in hosts)


def test_http_get_rest_hosts_works_when_fallback_realtime_host_is_not_set():
    ably = create_http_client(token="foo")
    ably.options.fallback_host = None
    # Should not raise TypeError
    hosts = ably.http.get_hosts()
    assert isinstance(hosts, list)
    assert all(isinstance(host, str) for host in hosts)


class RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self, response_factory):
        self.requests = []
        self.__response_factory = response_factory

    async def handle_async_request(self, request):
        self.requests.append(request)
        return self.__response_factory(request)


async def test_http_sends_requests_through_an_injected_transport():
    transport = RecordingTransport(lambda request: httpx.Response(200, json=[1500000000000]))
    ably = create_http_client(token="foo", _test_options=TestOptions(http_transport=transport))

    server_time = await ably.time()

    assert server_time == 1500000000000
    assert len(transport.requests) == 1
    assert transport.requests[0].method == 'GET'
    assert transport.requests[0].url.path == '/time'
    await ably.close()


async def test_http_bounds_every_phase_of_a_request():
    transport = RecordingTransport(lambda request: httpx.Response(200, json=[1500000000000]))
    ably = create_http_client(token="foo", http_open_timeout_seconds=2, http_request_timeout_seconds=7,
                              _test_options=TestOptions(http_transport=transport))

    await ably.time()

    # TO3l3 bounds the connect, and TO3l4 the read, the write and the wait for a pooled connection
    assert transport.requests[0].extensions['timeout'] == {'connect': 2, 'read': 7, 'write': 7, 'pool': 7}
    await ably.close()


async def test_http_surfaces_transport_connection_errors():
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    transport = RecordingTransport(refuse)
    ably = create_http_client(token="foo", _test_options=TestOptions(http_transport=transport))

    with pytest.raises(AblyException) as excinfo:
        await ably.time()

    # RSC19e: the httpx error is wrapped, and kept as the cause
    assert excinfo.value.code == 80000
    assert excinfo.value.status_code == 500
    assert isinstance(excinfo.value.cause, httpx.ConnectError)
    assert excinfo.value.__cause__ is excinfo.value.cause
    # Every host is tried before the error is surfaced (RSC15l)
    assert len(transport.requests) == len(ably.http.get_hosts())
    await ably.close()


async def test_http_surfaces_transport_timeouts_as_50003():
    def time_out(request):
        raise httpx.ReadTimeout("timed out", request=request)

    transport = RecordingTransport(time_out)
    ably = create_http_client(key="appId.keyId:keySecret", _test_options=TestOptions(http_transport=transport))

    with pytest.raises(AblyException) as excinfo:
        await ably.channels.get('test').publish('event', 'data')

    assert excinfo.value.code == 50003
    assert excinfo.value.status_code == 504
    assert isinstance(excinfo.value.cause, httpx.TimeoutException)
    await ably.close()


async def test_http_tries_the_primary_and_up_to_max_retry_count_fallbacks():
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    # TO3l5: http_max_retry_count counts the fallback hosts, after the primary
    for retry_count, attempts in [(0, 1), (2, 3), (3, 4), (10, 6)]:
        transport = RecordingTransport(refuse)
        ably = create_http_client(token="foo", http_max_retry_count=retry_count,
                                  _test_options=TestOptions(http_transport=transport))

        with pytest.raises(AblyException):
            await ably.time()

        assert len(transport.requests) == attempts, retry_count
        assert transport.requests[0].url.host == ably.options.get_host()
        await ably.close()


def test_http_uses_a_network_transport_without_test_options():
    ably = create_http_client(token="foo")
    assert isinstance(ably.http._Http__client._transport, httpx.AsyncHTTPTransport)


async def test_auth_url_requests_go_through_the_client_http_layer():
    def respond(request):
        if request.url.host == 'auth.example.com':
            return httpx.Response(200, text='a-token', headers={'content-type': 'text/plain'})
        return httpx.Response(200, json=[1500000000000])

    transport = RecordingTransport(respond)
    ably = create_http_client(auth_url='https://auth.example.com/token',
                              _test_options=TestOptions(http_transport=transport))

    await ably.auth.authorize()

    auth_requests = [r for r in transport.requests if r.url.host == 'auth.example.com']
    assert len(auth_requests) == 1
    assert auth_requests[0].url.path == '/token'
    # An auth_url addresses a server outside Ably, so none of the Ably headers apply
    assert 'Authorization' not in auth_requests[0].headers
    assert 'X-Ably-Version' not in auth_requests[0].headers
    await ably.close()


async def test_auth_url_network_errors_are_40170():
    def respond(request):
        if request.url.host == 'auth.example.com':
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json=[1500000000000])

    transport = RecordingTransport(respond)
    ably = create_http_client(auth_url='https://auth.example.com/token',
                              _test_options=TestOptions(http_transport=transport))

    # RSA4e: a network error reaching the auth_url is a 40170, with the httpx error as the cause
    with pytest.raises(AblyException) as excinfo:
        await ably.auth.authorize()

    assert excinfo.value.code == 40170
    assert excinfo.value.status_code == 401
    assert isinstance(excinfo.value.cause, httpx.ConnectError)
    await ably.close()


async def test_realtime_token_request_network_errors_reach_the_connection_wrapped():
    mock_http = MockHttpClient(on_connection_attempt=lambda conn: conn.respond_with_refused())
    mock_ws = MockWebSocket()
    client = realtime_client(mock_ws, mock_http, key="appId.keyId:keySecret", use_token_auth=True,
                             disconnected_retry_timeout_seconds=600)
    try:
        client.connect()
        await await_connection_state(client, ConnectionState.DISCONNECTED)

        # RSA4c: a failed TokenRequest exchange is an auth error, so the connection is not
        # left holding the httpx exception
        assert isinstance(client.connection.error_reason, AblyException)
        assert client.connection.error_reason.code == 80019
        assert mock_ws.connection_attempts == []
    finally:
        await close_open_clients()


async def test_auth_callback_ably_exceptions_are_passed_through():
    error = AblyException('Account disabled', 403, 40300)

    async def auth_callback(params):
        raise error

    ably = create_http_client(auth_callback=auth_callback)

    # RSA4e: only an error that is not already an AblyException becomes a 40170
    with pytest.raises(AblyException) as excinfo:
        await ably.auth.authorize()

    assert excinfo.value is error
    await ably.close()
