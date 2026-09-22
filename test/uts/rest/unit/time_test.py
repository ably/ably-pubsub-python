"""Derived from uts/rest/unit/time.md in ably/specification.

Spec points: RSC16
"""

import pytest

from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient

SERVER_TIME_MS = 1704067200000


def capture_and_respond(captured_requests, body=None):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, body if body is not None else [SERVER_TIME_MS])

    return on_request


# UTS: rest/unit/RSC16/returns-server-time-0
async def test_rsc16_time_returns_server_time():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    result = await client.time()

    # NOTE: the spec asserts the result IS DateTime. Its stated requirement allows
    # "a DateTime or timestamp", and time() returns milliseconds since the epoch.
    assert isinstance(result, (int, float))
    assert result == SERVER_TIME_MS

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.method == 'GET'
    assert request.path == '/time'


# UTS: rest/unit/RSC16/request-format-get-time-1
async def test_rsc16_time_request_format():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    await client.time()

    assert len(captured_requests) == 1
    request = captured_requests[0]

    assert request.method == 'GET'
    assert request.path == '/time'

    assert 'X-Ably-Version' in request.headers
    assert 'Ably-Agent' in request.headers


# UTS: rest/unit/RSC16/no-auth-required-2
async def test_rsc16_time_does_not_require_authentication():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http)

    result = await client.time()

    assert isinstance(result, (int, float))

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert 'Authorization' not in request.headers


# UTS: rest/unit/RSC16/works-without-tls-3
async def test_rsc16_time_works_without_tls():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, tls=False, use_token_auth=True)

    result = await client.time()

    assert isinstance(result, (int, float))

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.url.scheme == 'http'
    assert 'Authorization' not in request.headers


# UTS: rest/unit/RSC16/error-propagated-4
async def test_rsc16_time_propagates_errors():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(500, {
            'error': {
                'message': 'Internal server error',
                'code': 50000,
                'statusCode': 500,
            },
        }),
    )
    client = rest_client(mock_http)

    with pytest.raises(AblyException) as excinfo:
        await client.time()

    assert excinfo.value.status_code == 500
    assert excinfo.value.code == 50000
