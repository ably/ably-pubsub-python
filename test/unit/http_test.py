import httpx
import pytest

from ably import AblyRest
from ably.types.testoptions import TestOptions
from ably.util.exceptions import AblyException


def test_http_get_rest_hosts_works_when_fallback_realtime_host_is_set():
    ably = AblyRest(token="foo")
    ably.options.fallback_host = ably.options.get_hosts()[0]
    # Should not raise TypeError
    hosts = ably.http.get_hosts()
    assert isinstance(hosts, list)
    assert all(isinstance(host, str) for host in hosts)


def test_http_get_rest_hosts_works_when_fallback_realtime_host_is_not_set():
    ably = AblyRest(token="foo")
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
    ably = AblyRest(token="foo", test_options=TestOptions(http_transport=transport))

    server_time = await ably.time()

    assert server_time == 1500000000000
    assert len(transport.requests) == 1
    assert transport.requests[0].method == 'GET'
    assert transport.requests[0].url.path == '/time'
    await ably.close()


async def test_http_surfaces_transport_connection_errors():
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    transport = RecordingTransport(refuse)
    ably = AblyRest(token="foo", test_options=TestOptions(http_transport=transport))

    with pytest.raises(AblyException):
        await ably.time()

    # Every host is tried before the error is surfaced (RSC15l)
    assert len(transport.requests) == len(ably.http.get_hosts())
    await ably.close()


def test_http_uses_a_network_transport_without_test_options():
    ably = AblyRest(token="foo")
    assert isinstance(ably.http._Http__client._transport, httpx.AsyncHTTPTransport)
