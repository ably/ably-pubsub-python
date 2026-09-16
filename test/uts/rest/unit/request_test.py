"""Derived from uts/rest/unit/request.md in ably/specification.

Spec points: RSC19, RSC19b, RSC19c, RSC19d, RSC19e, RSC19f, RSC19f1,
HP1, HP3, HP4, HP5, HP6, HP7, HP8
"""

import base64
import json

import httpx
import msgpack
import pytest

from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient

SPEC_KEY = 'appId.keyId:keySecret'

# The number of hosts a single request is tried against: the primary domain plus
# fallbacks, capped at Defaults.http_max_retry_count
HOST_ATTEMPTS = 3


def succeed(conn):
    conn.respond_with_success()


def capture_and_respond(captured_requests, status=200, body=None, headers=None):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(status, body if body is not None else [], headers)

    return on_request


# UTS: rest/unit/RSC19f/supports-http-methods-0
@pytest.mark.parametrize('method', ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
async def test_rsc19f_request_supports_http_methods(method):
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=succeed,
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, key=SPEC_KEY)

    # NOTE: request() takes version as a string in ably-python; the spec writes `version: 3`
    await client.request(method, '/test', version='3')

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.method == method
    assert request.url.path == '/test'


# UTS: rest/unit/RSC19f/query-params-passed-1
async def test_rsc19f_request_query_params_passed():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=succeed,
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, key=SPEC_KEY)

    await client.request('GET', '/channels/test/messages', version='3',
                         params={'limit': '10', 'direction': 'backwards'})

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.url.query_params['limit'] == '10'
    assert request.url.query_params['direction'] == 'backwards'


# UTS: rest/unit/RSC19f/custom-headers-passed-2
async def test_rsc19f_request_custom_headers_passed():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=succeed,
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, key=SPEC_KEY)

    await client.request('GET', '/test', version='3',
                         headers={'X-Custom-Header': 'custom-value', 'X-Another': 'another-value'})

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.headers['X-Custom-Header'] == 'custom-value'
    assert request.headers['X-Another'] == 'another-value'


# UTS: rest/unit/RSC19f/request-body-sent-3
async def test_rsc19f_request_body_sent():
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=succeed,
        on_request=capture_and_respond(captured_requests, status=201, body={'id': '123'}),
    )
    # JSON for easier inspection
    client = rest_client(mock_http, key=SPEC_KEY, use_binary_protocol=False)

    await client.request('POST', '/channels/test/messages', version='3',
                         body={'name': 'event', 'data': 'payload'})

    assert len(captured_requests) == 1
    request = captured_requests[0]
    body = json.loads(request.body)
    assert body['name'] == 'event'
    assert body['data'] == 'payload'


# UTS: rest/unit/RSC19f1/version-param-sets-header-0
@pytest.mark.parametrize('version, expected_header', [('2', '2'), ('3', '3')])
async def test_rsc19f1_version_param_sets_header(version, expected_header):
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_response(200, [])

    client = rest_client(mock_http, key=SPEC_KEY)

    await client.request('GET', '/test', version=version)

    request = mock_http.captured_requests[0]
    assert request.headers['X-Ably-Version'] == expected_header


# UTS: rest/unit/RSC19b/uses-configured-auth-0
async def test_rsc19b_uses_configured_auth():
    # Test Case 1: Basic authentication (API key)
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=succeed,
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, key=SPEC_KEY)

    await client.request('GET', '/test', version='3')

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert 'Authorization' in request.headers
    assert request.headers['Authorization'].startswith('Basic ')

    credentials = base64.b64decode(request.headers['Authorization'][len('Basic '):]).decode('utf-8')
    assert credentials == SPEC_KEY

    # Test Case 2: Token authentication
    captured_requests = []
    mock_http = MockHttpClient(
        on_connection_attempt=succeed,
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, token='my-token-string')

    await client.request('GET', '/test', version='3')

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert 'Authorization' in request.headers
    assert request.headers['Authorization'].startswith('Bearer ')


# UTS: rest/unit/RSC19c/protocol-headers-json-0
async def test_rsc19c_protocol_headers_json():
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_response(200, [])

    client = rest_client(mock_http, key=SPEC_KEY, use_binary_protocol=False)

    await client.request('POST', '/test', version='3', body={'data': 'test'})

    request = mock_http.captured_requests[0]
    assert request.headers['Accept'] == 'application/json'
    assert request.headers['Content-Type'] == 'application/json'


# UTS: rest/unit/RSC19c/protocol-headers-msgpack-1
async def test_rsc19c_protocol_headers_msgpack():
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_response(200, msgpack.packb([], use_bin_type=False),
                             {'Content-Type': 'application/x-msgpack'})

    client = rest_client(mock_http, key=SPEC_KEY, use_binary_protocol=True)

    await client.request('POST', '/test', version='3', body={'data': 'test'})

    request = mock_http.captured_requests[0]
    assert request.headers['Accept'] == 'application/x-msgpack'
    assert request.headers['Content-Type'] == 'application/x-msgpack'


# UTS: rest/unit/RSC19c/body-encoded-per-protocol-2
async def test_rsc19c_body_encoded_per_protocol():
    # Test Case 1: JSON encoding
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_response(200, [])

    client = rest_client(mock_http, key=SPEC_KEY, use_binary_protocol=False)

    await client.request('POST', '/test', version='3',
                         body={'name': 'event', 'data': {'nested': 'value'}})

    request = mock_http.captured_requests[0]
    body = json.loads(request.body)
    assert body['name'] == 'event'
    assert body['data']['nested'] == 'value'

    # Test Case 2: MsgPack encoding
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_response(200, msgpack.packb([], use_bin_type=False),
                             {'Content-Type': 'application/x-msgpack'})

    client = rest_client(mock_http, key=SPEC_KEY, use_binary_protocol=True)

    await client.request('POST', '/test', version='3',
                         body={'name': 'event', 'data': 'value'})

    request = mock_http.captured_requests[0]
    body = msgpack.unpackb(request.body)
    assert body['name'] == 'event'
    assert body['data'] == 'value'


# UTS: rest/unit/RSC19c/response-decoded-by-content-type-3
async def test_rsc19c_response_decoded_by_content_type():
    # Test Case 1: JSON response
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_response(
        200,
        json.dumps([{'id': '1', 'name': 'item1'}, {'id': '2', 'name': 'item2'}]),
        {'Content-Type': 'application/json'},
    )

    client = rest_client(mock_http, key=SPEC_KEY)

    response = await client.request('GET', '/test', version='3')
    items = response.items

    assert len(items) == 2
    assert items[0]['id'] == '1'
    assert items[1]['name'] == 'item2'

    # Test Case 2: MsgPack response
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_response(200, msgpack.packb([{'id': '1'}], use_bin_type=False),
                             {'Content-Type': 'application/x-msgpack'})

    client = rest_client(mock_http, key=SPEC_KEY)

    response = await client.request('GET', '/test', version='3')
    items = response.items

    assert len(items) == 1
    assert items[0]['id'] == '1'


# UTS: rest/unit/RSC19d/response-status-code-0
@pytest.mark.parametrize('status_code', [200, 201, 400, 404, 500])
async def test_rsc19d_response_status_code(status_code):
    mock_http = MockHttpClient(on_connection_attempt=succeed)

    if status_code >= 400:
        body = {'error': {'code': status_code * 100, 'message': 'Error'}}
        # RSC15l3: a 5xx is retried against every host, so every host needs an answer
        count = HOST_ATTEMPTS if 500 <= status_code <= 504 else 1
        mock_http.queue_responses(count, status_code, body)
    else:
        mock_http.queue_response(status_code, [])

    client = rest_client(mock_http, key=SPEC_KEY)
    response = await client.request('GET', '/test', version='3')

    assert response.status_code == status_code


# UTS: rest/unit/RSC19d/response-success-indicator-1
@pytest.mark.parametrize('status_code, expected_success', [
    (200, True),
    (201, True),
    (204, True),
    (299, True),
    (300, False),
    (400, False),
    (500, False),
])
async def test_rsc19d_response_success_indicator(status_code, expected_success):
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    client = rest_client(mock_http, key=SPEC_KEY)

    if status_code >= 400:
        body = {'error': {'code': status_code * 100, 'message': 'Error'}}
        # RSC15l3: a 5xx is retried against every host, so every host needs an answer
        count = HOST_ATTEMPTS if 500 <= status_code <= 504 else 1
        mock_http.queue_responses(count, status_code, body)
    else:
        mock_http.queue_response(status_code, [])

    response = await client.request('GET', '/test', version='3')

    assert response.success == expected_success


# UTS: rest/unit/RSC19d/response-error-code-header-2
async def test_rsc19d_response_error_code_header():
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_response(
        401,
        {'error': {'code': 40101, 'message': 'Unauthorized'}},
        {'X-Ably-Errorcode': '40101'},
    )

    client = rest_client(mock_http, key=SPEC_KEY)

    response = await client.request('GET', '/test', version='3')

    # DEVIATION: the spec asserts errorCode == 40101, and HP6 types it as a number.
    # error_code returns the raw X-Ably-Errorcode header value, so it is a string.
    assert response.error_code == '40101'


# UTS: rest/unit/RSC19d/response-error-message-header-3
async def test_rsc19d_response_error_message_header():
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_response(
        401,
        {'error': {'code': 40101, 'message': 'Unauthorized'}},
        {'X-Ably-Errorcode': '40101', 'X-Ably-Errormessage': 'Token expired'},
    )

    client = rest_client(mock_http, key=SPEC_KEY)

    response = await client.request('GET', '/test', version='3')

    assert response.error_message == 'Token expired'


# UTS: rest/unit/RSC19d/response-headers-accessible-4
async def test_rsc19d_response_headers_accessible():
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_response(
        200,
        [],
        {
            'Content-Type': 'application/json',
            'X-Request-Id': 'req-123',
            'X-Custom-Header': 'custom-value',
        },
    )

    client = rest_client(mock_http, key=SPEC_KEY)

    response = await client.request('GET', '/test', version='3')

    # DEVIATION: the spec (and HP8) expects a map keyed by header name. `headers` is a
    # list of (name, value) pairs, with the names lower-cased by httpx.
    headers = dict(response.headers)
    assert headers['content-type'] == 'application/json'
    assert headers['x-request-id'] == 'req-123'
    assert headers['x-custom-header'] == 'custom-value'


# UTS: rest/unit/RSC19d/response-items-decoded-5
async def test_rsc19d_response_items_decoded():
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_response(200, [
        {'id': 'msg1', 'name': 'event1', 'data': 'data1'},
        {'id': 'msg2', 'name': 'event2', 'data': 'data2'},
    ])

    client = rest_client(mock_http, key=SPEC_KEY)

    response = await client.request('GET', '/channels/test/messages', version='3')
    items = response.items

    assert len(items) == 2
    assert items[0]['id'] == 'msg1'
    assert items[1]['id'] == 'msg2'


# UTS: rest/unit/RSC19d/pagination-with-link-headers-6
async def test_rsc19d_pagination_with_link_headers():
    mock_http = MockHttpClient(on_connection_attempt=succeed)

    # First page
    mock_http.queue_response(200, [{'id': '1'}, {'id': '2'}],
                             {'Link': '</channels/test/messages?page=2>; rel="next"'})

    # Second page, with no "next" link - last page
    mock_http.queue_response(200, [{'id': '3'}], {})

    client = rest_client(mock_http, key=SPEC_KEY)

    response = await client.request('GET', '/channels/test/messages', version='3')

    # First page
    items1 = response.items
    assert len(items1) == 2
    assert response.has_next() is True

    # Navigate to second page
    response = await response.next()
    items2 = response.items
    assert len(items2) == 1
    assert items2[0]['id'] == '3'
    assert response.has_next() is False


# UTS: rest/unit/RSC19d/non-array-response-handling-7
async def test_rsc19d_non_array_response_handling():
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_response(200, {'time': 1234567890000})

    client = rest_client(mock_http, key=SPEC_KEY)

    response = await client.request('GET', '/time', version='3')
    items = response.items

    # The spec allows either wrapping in an array or returning the object directly;
    # ably-python wraps a non-array response as a single item
    assert len(items) == 1
    assert items[0]['time'] == 1234567890000


# UTS: rest/unit/RSC19e/network-error-propagated-0
async def test_rsc19e_network_error_propagated():
    mock_http = MockHttpClient(on_connection_attempt=lambda conn: conn.respond_with_refused())

    client = rest_client(mock_http, key=SPEC_KEY, fallback_hosts=[])

    # DEVIATION: the spec expects an error carrying code 80000, or a message naming the
    # network/connection failure. request() is not wrapped by @catch_all (unlike time()
    # and stats()), so the transport exception reaches the caller unwrapped. Its message
    # does name the connection failure, which is what RSC19e asks be indicated.
    with pytest.raises(httpx.ConnectError) as excinfo:
        await client.request('GET', '/test', version='3')

    assert 'Connection refused' in str(excinfo.value)


# UTS: rest/unit/RSC19e/timeout-error-handling-1
async def test_rsc19e_timeout_error_handling():
    # NOTE: the spec drives this with a 5s delayed response against a 1s
    # http_request_timeout (which it gives in milliseconds; ably-python takes seconds).
    # An injected transport is responsible for enforcing httpx timeouts, and the mock
    # does not implement them, so a delayed response would simply be waited out.
    # queue_timeout() raises the read timeout the client would otherwise have seen.
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_timeout()

    client = rest_client(mock_http, key=SPEC_KEY, http_request_timeout=1, fallback_hosts=[])

    # DEVIATION: the spec expects an error carrying code 50003, or a message naming the
    # timeout. request() is not wrapped by @catch_all, so the transport exception reaches
    # the caller unwrapped; its message does name the timeout.
    with pytest.raises(httpx.ReadTimeout) as excinfo:
        await client.request('GET', '/test', version='3')

    assert 'timed out' in str(excinfo.value)


# UTS: rest/unit/RSC19e/http-error-no-fallback-2
async def test_rsc19e_http_error_no_fallback():
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_response(
        400,
        {'error': {'code': 40000, 'message': 'Bad request'}},
        {'X-Ably-Errorcode': '40000'},
    )

    client = rest_client(mock_http, key=SPEC_KEY,
                         fallback_hosts=['a.ably-realtime.com', 'b.ably-realtime.com'])

    response = await client.request('GET', '/test', version='3')

    # Should return the error response, not retry to fallback
    assert response.status_code == 400
    assert response.success is False
    # DEVIATION: the spec asserts errorCode == 40000; error_code returns the raw header
    assert response.error_code == '40000'

    # Only one request should have been made (no fallback)
    assert len(mock_http.captured_requests) == 1


# UTS: rest/unit/RSC19e/fallback-on-server-error-3
async def test_rsc19e_fallback_on_server_error():
    mock_http = MockHttpClient(on_connection_attempt=succeed)

    # Primary host fails with non-Ably 500 error
    mock_http.queue_response(500, 'Internal Server Error', {'Content-Type': 'text/plain'})

    # Fallback succeeds
    mock_http.queue_response(200, [{'id': '1'}])

    client = rest_client(mock_http, key=SPEC_KEY, fallback_hosts=['fallback.ably-realtime.com'])

    response = await client.request('GET', '/test', version='3')

    assert response.status_code == 200
    assert response.success is True

    # Two requests: primary failed, fallback succeeded
    assert len(mock_http.captured_requests) == 2
    assert mock_http.captured_requests[1].url.host == 'fallback.ably-realtime.com'


# UTS: rest/unit/RSC19b/cannot-override-auth-1
@deviation
async def test_rsc19b_cannot_override_auth():
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_response(200, [])

    client = rest_client(mock_http, key=SPEC_KEY)

    # Attempt to override auth with custom header
    await client.request('GET', '/test', version='3',
                         headers={'Authorization': 'Bearer malicious-token'})

    request = mock_http.captured_requests[0]

    # The configured Basic auth should be used, not the custom header
    assert request.headers['Authorization'].startswith('Basic ')
    # Should NOT contain the attempted override
    assert request.headers['Authorization'] != 'Bearer malicious-token'


# UTS: rest/unit/RSC19f/path-leading-slash-handling-4
@pytest.mark.parametrize('path, expected_path', [
    ('/channels/test', '/channels/test'),
    ('channels/test', '/channels/test'),
])
async def test_rsc19f_path_leading_slash_handling(path, expected_path):
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    client = rest_client(mock_http, key=SPEC_KEY)

    mock_http.queue_response(200, [])

    await client.request('GET', path, version='3')

    request = mock_http.captured_requests[0]
    assert request.url.path == expected_path


# UTS: rest/unit/RSC19d/empty-response-handling-8
@deviation
async def test_rsc19d_empty_response_handling():
    mock_http = MockHttpClient(on_connection_attempt=succeed)
    mock_http.queue_response(204, None, {})

    client = rest_client(mock_http, key=SPEC_KEY)

    response = await client.request('DELETE', '/channels/test/messages/123', version='3')

    assert response.status_code == 204
    assert response.success is True
    items = response.items
    assert items is None or len(items) == 0
