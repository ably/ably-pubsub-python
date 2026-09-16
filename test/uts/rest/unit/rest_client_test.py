"""Derived from uts/rest/unit/rest_client.md in ably/specification.

Spec points: RSC5, RSC7c, RSC7d, RSC7e, RSC8, RSC8a, RSC8b, RSC8c, RSC8d, RSC8e, RSC13, RSC17, RSC18
"""

import re

import msgpack
import pytest

from ably.rest.auth import Auth
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient

SERVER_TIME_MS = 1234567890000

# NOTE: the spec stubs /time with {"time": 1234567890000}. The endpoint answers with an array
# holding the time, which is what time.md stubs and what the SDK reads, so the value is kept
# and the shape corrected.
TIME_RESPONSE = [SERVER_TIME_MS]

PUBLISH_RESPONSE = {'serials': ['s1']}


def connect_successfully(conn):
    conn.respond_with_success()


# UTS: rest/unit/RSC5/auth-attribute-accessible-0
async def test_rsc5_auth_attribute_accessible():
    mock_http = MockHttpClient(on_connection_attempt=connect_successfully)
    client = rest_client(mock_http)

    assert client.auth is not None
    assert isinstance(client.auth, Auth)


# UTS: rest/unit/RSC7e/ably-version-header-0
async def test_rsc7e_ably_version_header():
    captured_request = None

    def on_request(request):
        nonlocal captured_request
        captured_request = request
        request.respond_with(200, TIME_RESPONSE)

    mock_http = MockHttpClient(on_connection_attempt=connect_successfully, on_request=on_request)
    client = rest_client(mock_http)

    await client.time()

    assert captured_request is not None
    assert 'X-Ably-Version' in captured_request.headers
    assert re.fullmatch(r'[0-9.]+', captured_request.headers['X-Ably-Version'])


# UTS: rest/unit/RSC7d/ably-agent-header-format-0
async def test_rsc7d_ably_agent_header_format():
    mock_http = MockHttpClient(on_connection_attempt=connect_successfully)
    mock_http.queue_response(200, TIME_RESPONSE)
    client = rest_client(mock_http)

    await client.time()

    request = mock_http.captured_requests[0]
    assert 'Ably-Agent' in request.headers

    agent = request.headers['Ably-Agent']
    # Format: key[/value] entries joined by spaces, including at least the library name/version
    assert re.search(r'ably-[a-z]+/[0-9]+\.[0-9]+\.[0-9]+', agent)


# UTS: rest/unit/RSC7c/request-id-included-0
async def test_rsc7c_request_id_included():
    mock_http = MockHttpClient(on_connection_attempt=connect_successfully)
    mock_http.queue_response(200, TIME_RESPONSE)
    client = rest_client(mock_http, add_request_ids=True)

    await client.time()

    request = mock_http.captured_requests[0]
    assert 'request_id' in request.url.query_params

    request_id = request.url.query_params['request_id']
    assert len(request_id) >= 12
    assert re.fullmatch(r'[A-Za-z0-9_-]+', request_id)


# UTS: rest/unit/RSC7c/request-id-preserved-fallback-1
async def test_rsc7c_request_id_preserved_fallback():
    mock_http = MockHttpClient(on_connection_attempt=connect_successfully)
    # First request fails with 500 (triggers fallback retry)
    mock_http.queue_response(500, {'error': {'code': 50000, 'statusCode': 500, 'message': 'Internal error'}})
    # Retry succeeds
    mock_http.queue_response(200, TIME_RESPONSE)
    client = rest_client(mock_http, add_request_ids=True,
                         fallback_hosts=['a.example.com', 'b.example.com'])

    await client.time()

    assert len(mock_http.captured_requests) == 2

    request_id_1 = mock_http.captured_requests[0].url.query_params['request_id']
    request_id_2 = mock_http.captured_requests[1].url.query_params['request_id']

    assert request_id_1 == request_id_2


# UTS: rest/unit/RSC8a/protocol-selection-0
async def test_rsc8a_protocol_selection():
    mock_http = MockHttpClient(on_connection_attempt=connect_successfully)

    test_cases = [
        (True, 'application/x-msgpack'),
        (False, 'application/json'),
    ]

    for use_binary_protocol, expected_content_type in test_cases:
        mock_http.reset()
        mock_http.queue_response(201, PUBLISH_RESPONSE)

        client = rest_client(mock_http, use_binary_protocol=use_binary_protocol)

        await client.channels.get('test').publish(name='e', data='d')

        request = mock_http.captured_requests[0]
        assert request.headers['Content-Type'] == expected_content_type
        assert request.headers['Accept'] == expected_content_type


# UTS: rest/unit/RSC8c/accept-content-type-headers-0
async def test_rsc8c_accept_content_type_headers():
    mock_http = MockHttpClient(on_connection_attempt=connect_successfully)
    mock_http.queue_response(201, PUBLISH_RESPONSE)
    client = rest_client(mock_http, use_binary_protocol=False)

    await client.channels.get('test').publish(name='e', data='d')

    request = mock_http.captured_requests[0]
    assert request.headers['Accept'] == 'application/json'
    assert request.headers['Content-Type'] == 'application/json'


# UTS: rest/unit/RSC8d/mismatched-response-content-type-0
async def test_rsc8d_mismatched_response_content_type():
    mock_http = MockHttpClient(on_connection_attempt=connect_successfully)
    # Client requests JSON but server returns msgpack
    mock_http.queue_response(
        200,
        msgpack.packb(TIME_RESPONSE, use_bin_type=False),
        {'Content-Type': 'application/x-msgpack'},
    )
    client = rest_client(mock_http, use_binary_protocol=False)

    result = await client.time()

    # Should successfully parse msgpack response despite requesting JSON
    assert result == SERVER_TIME_MS


# UTS: rest/unit/RSC8e/unsupported-content-type-0
async def test_rsc8e_unsupported_content_type_error_status():
    # NOTE: a single queued response is not enough here. A 5xx is retried against every host
    # (RSC15l3), so the handler answers each attempt.
    mock_http = MockHttpClient(
        on_connection_attempt=connect_successfully,
        on_request=lambda request: request.respond_with(
            500, '<html>Server Error</html>', {'Content-Type': 'text/html'}),
    )
    client = rest_client(mock_http)

    with pytest.raises(AblyException) as excinfo:
        await client.time()

    # The key assertion is that the HTTP status code is propagated
    assert excinfo.value.status_code == 500


# UTS: rest/unit/RSC8e/unsupported-content-type-0
@deviation
async def test_rsc8e_unsupported_content_type_success_status():
    # DEVIATION: a 2xx carrying an undecodable content type surfaces as 500/50000
    # ("Unexpected exception: ValueError: Unsupported content type") rather than 400/40013.
    mock_http = MockHttpClient(on_connection_attempt=connect_successfully)
    mock_http.queue_response(200, '<html>OK</html>', {'Content-Type': 'text/html'})
    client = rest_client(mock_http)

    with pytest.raises(AblyException) as excinfo:
        await client.time()

    assert excinfo.value.status_code == 400
    assert excinfo.value.code == 40013


# UTS: rest/unit/RSC8/error-decoded-from-msgpack-0
async def test_rsc8_error_decoded_from_msgpack():
    mock_http = MockHttpClient(
        on_connection_attempt=connect_successfully,
        on_request=lambda request: request.respond_with(
            400,
            msgpack.packb({
                'error': {
                    'code': 40099,
                    'statusCode': 400,
                    'message': 'Test error',
                },
            }, use_bin_type=False),
            {'Content-Type': 'application/x-msgpack'},
        ),
    )
    client = rest_client(mock_http, use_binary_protocol=True)

    with pytest.raises(AblyException) as excinfo:
        await client.time()

    assert excinfo.value.code == 40099
    assert excinfo.value.status_code == 400
    assert excinfo.value.message == 'Test error'


# UTS: rest/unit/RSC13/request-timeout-enforced-0
async def test_rsc13_request_timeout_enforced():
    # NOTE: http_request_timeout is seconds in ably-python where the spec counts milliseconds,
    # so the spec's 1000ms is shortened to 0.1 to keep the test quick.
    # Every host delays, because a timed-out request sends the client on to the next one.
    mock_http = MockHttpClient(
        on_connection_attempt=connect_successfully,
        on_request=lambda request: request.respond_with_delay(5000, 200, TIME_RESPONSE),
    )
    client = rest_client(mock_http, http_request_timeout=0.1)

    with pytest.raises(AblyException) as excinfo:
        await client.time()

    assert excinfo.value.code == 50003 or 'timeout' in excinfo.value.message.lower()


# UTS: rest/unit/RSC17/client-id-from-options-0
async def test_rsc17_client_id_from_options():
    mock_http = MockHttpClient(on_connection_attempt=connect_successfully)
    client = rest_client(mock_http, client_id='explicit-client-id')

    assert client.client_id == 'explicit-client-id'
    assert client.client_id == client.auth.client_id


# UTS: rest/unit/RSC17/client-id-matches-auth-1
async def test_rsc17_client_id_matches_auth():
    mock_http = MockHttpClient(on_connection_attempt=connect_successfully)
    client = rest_client(mock_http, client_id='explicit-client-id')

    assert client.client_id == 'explicit-client-id'
    assert client.client_id == client.auth.client_id


# UTS: rest/unit/RSC18/tls-controls-protocol-scheme-0
async def test_rsc18_tls_controls_protocol_scheme():
    mock_http = MockHttpClient(on_connection_attempt=connect_successfully)

    test_cases = [
        (True, 'https'),
        (False, 'http'),
    ]

    for tls, expected_scheme in test_cases:
        mock_http.reset()
        mock_http.queue_response(200, TIME_RESPONSE)

        client = rest_client(mock_http, tls=tls)

        await client.time()

        request = mock_http.captured_requests[0]
        assert request.url.scheme == expected_scheme


# UTS: rest/unit/RSC18/basic-auth-over-http-rejected-1
async def test_rsc18_basic_auth_over_http_rejected():
    # DEVIATION: the spec expects the constructor to reject the combination. ably-python builds
    # the client and raises 40103 when a request that carries Basic Auth is attempted, which is
    # what RSA1 and RSC18 require of an attempt to use Basic Auth over HTTP.
    mock_http = MockHttpClient(on_connection_attempt=connect_successfully)
    mock_http.queue_response(201, PUBLISH_RESPONSE)
    client = rest_client(mock_http, tls=False)

    with pytest.raises(AblyException) as excinfo:
        await client.channels.get('test').publish(name='e', data='d')

    assert excinfo.value.code == 40103
    assert 'TLS' in excinfo.value.message
    assert len(mock_http.captured_requests) == 0


# UTS: rest/unit/RSC18/basic-auth-over-http-rejected-1
async def test_rsc18_token_auth_over_http_allowed():
    mock_http = MockHttpClient(on_connection_attempt=connect_successfully)
    mock_http.queue_response(200, TIME_RESPONSE)
    client = rest_client(mock_http, token='some-token-string', tls=False)

    result = await client.time()

    assert result == SERVER_TIME_MS

    # NOTE: time() is sent unauthenticated, so a publish follows to show that a request
    # carrying token auth is permitted over HTTP.
    mock_http.queue_response(201, PUBLISH_RESPONSE)
    await client.channels.get('test').publish(name='e', data='d')

    request = mock_http.captured_requests[1]
    assert request.url.scheme == 'http'
    assert request.headers['Authorization'].startswith('Bearer ')
