"""Derived from uts/rest/unit/request_endpoint.md in ably/specification.

Spec points: RSC25
"""

from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient

DEFAULT_REST_HOST = 'main.realtime.ably.net'

SERVER_TIME_MS = 1234567890000


def succeed(conn):
    conn.respond_with_success()


def respond_with_time(request):
    # NOTE: the spec's mock answers /time with {"time": ...}. The Ably REST /time
    # endpoint returns an array, which is what time() reads, so the body is given in
    # that shape here; this test asserts on the request, not on the response.
    request.respond_with(200, [SERVER_TIME_MS])


# UTS: rest/unit/RSC25/default-primary-domain-0
async def test_rsc25_default_primary_domain():
    mock_http = MockHttpClient(on_connection_attempt=succeed, on_request=respond_with_time)

    client = rest_client(mock_http)

    await client.time()

    assert len(mock_http.captured_requests) == 1
    assert mock_http.captured_requests[0].url.host == DEFAULT_REST_HOST


# UTS: rest/unit/RSC25/custom-endpoint-domain-1
async def test_rsc25_custom_endpoint_domain():
    mock_http = MockHttpClient(on_connection_attempt=succeed, on_request=respond_with_time)

    client = rest_client(mock_http, endpoint='test')

    await client.time()

    assert len(mock_http.captured_requests) == 1
    assert mock_http.captured_requests[0].url.host == 'test.realtime.ably.net'


# UTS: rest/unit/RSC25/multiple-requests-primary-domain-2
async def test_rsc25_multiple_requests_primary_domain():
    mock_http = MockHttpClient(on_connection_attempt=succeed, on_request=respond_with_time)

    client = rest_client(mock_http)

    await client.time()
    await client.time()
    await client.time()

    assert len(mock_http.captured_requests) == 3
    for request in mock_http.captured_requests:
        assert request.url.host == DEFAULT_REST_HOST


# UTS: rest/unit/RSC25/primary-tried-before-fallback-3
async def test_rsc25_primary_tried_before_fallback():
    request_count = 0

    def on_request(request):
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            request.respond_with(500, {'error': {'code': 50000}})
        else:
            request.respond_with(200, [SERVER_TIME_MS])

    mock_http = MockHttpClient(on_connection_attempt=succeed, on_request=on_request)

    client = rest_client(mock_http)

    await client.time()

    assert len(mock_http.captured_requests) == 2
    # First request was to primary domain
    assert mock_http.captured_requests[0].url.host == DEFAULT_REST_HOST
    # Second request was to a fallback domain (not primary)
    assert mock_http.captured_requests[1].url.host != DEFAULT_REST_HOST


# UTS: rest/unit/RSC25/request-path-preserved-4
async def test_rsc25_request_path_preserved():
    mock_http = MockHttpClient(
        on_connection_attempt=succeed,
        on_request=lambda request: request.respond_with(200, []),
    )

    client = rest_client(mock_http)

    await client.channels.get('test-channel').history()

    assert len(mock_http.captured_requests) == 1
    request = mock_http.captured_requests[0]
    assert request.url.host == DEFAULT_REST_HOST
    assert request.url.path == '/channels/test-channel/messages'
    assert request.method == 'GET'
