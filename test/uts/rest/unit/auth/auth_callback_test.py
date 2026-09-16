"""Derived from uts/rest/unit/auth/auth_callback.md in ably/specification.

Spec points: RSA8c, RSA8d
"""

import base64
import re
import time

import pytest

from ably import api_version
from ably.types.tokendetails import TokenDetails
from ably.types.tokenrequest import TokenRequest
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.mock_http import MockHttpClient

CHANNEL_BODY = {'channelId': 'test'}

JWT = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-jwt-payload'

REQUEST_TOKEN_PATH = re.compile(r'^/keys/.*/requestToken$')

AUTH_HOST = 'auth.example.com'


def now():
    return int(time.time() * 1000)


def bearer(token):
    """The Bearer credential ably-python sends for `token`.

    NOTE: the specification asserts the raw token string. RSA3b makes the
    Base64 encoding optional ("the token string is optionally Base64-encoded
    and used in the `Authorization: Bearer` header"), and ably-python encodes,
    so the specification's literal is one permitted rendering of two.
    """
    return 'Bearer ' + base64.b64encode(token.encode('utf-8')).decode('ascii')


def capture_and_respond(captured_requests, body=None):
    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, body if body is not None else CHANNEL_BODY)

    return on_request


# UTS: rest/unit/RSA8d/callback-invoked-for-auth-0
async def test_rsa8d_callback_invoked_for_auth():
    callback_invoked = False
    callback_params = None
    captured_requests = []

    async def auth_callback(params):
        nonlocal callback_invoked, callback_params
        callback_invoked = True
        callback_params = params
        return TokenDetails(token='callback-token', expires=now() + 3600000)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    await client.request('GET', '/channels/test', version=api_version)

    assert callback_invoked is True
    assert callback_params is not None

    assert len(captured_requests) == 1
    assert captured_requests[0].headers['Authorization'] == bearer('callback-token')


# UTS: rest/unit/RSA8d/callback-returns-jwt-1
async def test_rsa8d_callback_returns_jwt():
    captured_requests = []

    async def auth_callback(params):
        return JWT

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    await client.request('GET', '/channels/test', version=api_version)

    assert captured_requests[0].headers['Authorization'] == bearer(JWT)


# UTS: rest/unit/RSA8d/callback-returns-token-request-2
async def test_rsa8d_callback_returns_token_request():
    captured_requests = []

    async def auth_callback(params):
        return TokenRequest(
            key_name='app.key',
            ttl=3600000,
            timestamp=now(),
            nonce='unique-nonce',
            mac='computed-mac',
        )

    def on_request(request):
        captured_requests.append(request)
        if REQUEST_TOKEN_PATH.match(request.path):
            request.respond_with(200, {'token': 'exchanged-token', 'expires': now() + 3600000})
        else:
            request.respond_with(200, CHANNEL_BODY)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    await client.request('GET', '/channels/test', version=api_version)

    assert len(captured_requests) == 2

    first_request = captured_requests[0]
    assert first_request.method == 'POST'
    assert REQUEST_TOKEN_PATH.match(first_request.path)

    second_request = captured_requests[1]
    assert second_request.headers['Authorization'] == bearer('exchanged-token')


# UTS: rest/unit/RSA8d/callback-receives-token-params-3
async def test_rsa8d_callback_receives_token_params():
    received_params = None

    async def auth_callback(params):
        nonlocal received_params
        received_params = params
        return TokenDetails(token='test-token', expires=now() + 3600000)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, CHANNEL_BODY),
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    await client.auth.authorize(token_params={
        'client_id': 'requested-client-id',
        'ttl': 7200000,
        'capability': {'channel1': ['publish']},
    })

    assert received_params['client_id'] == 'requested-client-id'
    assert received_params['ttl'] == 7200000
    assert received_params['capability'] == {'channel1': ['publish']}


def auth_url_mock(captured_requests, token_body=None, token_headers=None):
    """A mock that answers the auth_url with a token and everything else with a channel."""
    body = token_body if token_body is not None else {
        'token': 'authurl-token',
        'expires': now() + 3600000,
    }

    def on_request(request):
        captured_requests.append(request)
        if request.url.host == AUTH_HOST:
            request.respond_with(200, body, token_headers)
        else:
            request.respond_with(200, CHANNEL_BODY)

    return MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )


# UTS: rest/unit/RSA8c/authurl-invoked-for-auth-0
async def test_rsa8c_authurl_invoked_for_auth():
    captured_requests = []
    client = rest_client(auth_url_mock(captured_requests),
                         auth_url=f'https://{AUTH_HOST}/token')

    await client.request('GET', '/channels/test', version=api_version)

    auth_request = captured_requests[0]
    assert auth_request.url.host == AUTH_HOST
    assert auth_request.url.path == '/token'
    assert auth_request.method == 'GET'

    api_request = captured_requests[1]
    assert api_request.headers['Authorization'] == bearer('authurl-token')


# UTS: rest/unit/RSA8c/authurl-post-method-1
async def test_rsa8c_authurl_post_method():
    captured_requests = []
    client = rest_client(auth_url_mock(captured_requests),
                         auth_url=f'https://{AUTH_HOST}/token',
                         auth_method='POST')

    await client.request('GET', '/channels/test', version=api_version)

    auth_request = captured_requests[0]
    assert auth_request.method == 'POST'


# UTS: rest/unit/RSA8c/authurl-custom-headers-2
async def test_rsa8c_authurl_custom_headers():
    captured_requests = []
    client = rest_client(auth_url_mock(captured_requests),
                         auth_url=f'https://{AUTH_HOST}/token',
                         auth_headers={
                             'X-Custom-Header': 'custom-value',
                             'X-API-Key': 'my-api-key',
                         })

    await client.request('GET', '/channels/test', version=api_version)

    auth_request = captured_requests[0]
    assert auth_request.headers['X-Custom-Header'] == 'custom-value'
    assert auth_request.headers['X-API-Key'] == 'my-api-key'


# UTS: rest/unit/RSA8c/authurl-query-params-3
async def test_rsa8c_authurl_query_params():
    captured_requests = []
    client = rest_client(auth_url_mock(captured_requests),
                         auth_url=f'https://{AUTH_HOST}/token',
                         auth_params={
                             'client_id': 'my-client',
                             'scope': 'publish:*',
                         })

    await client.request('GET', '/channels/test', version=api_version)

    auth_request = captured_requests[0]
    assert auth_request.url.query_params['client_id'] == 'my-client'
    assert auth_request.url.query_params['scope'] == 'publish:*'


# UTS: rest/unit/RSA8c/authurl-returns-jwt-4
async def test_rsa8c_authurl_returns_jwt():
    captured_requests = []
    jwt = 'eyJhbGciOiJIUzI1NiJ9.jwt-body.signature'
    client = rest_client(
        auth_url_mock(captured_requests, token_body=jwt,
                      token_headers={'Content-Type': 'text/plain'}),
        auth_url=f'https://{AUTH_HOST}/jwt')

    await client.request('GET', '/channels/test', version=api_version)

    api_request = captured_requests[1]
    assert api_request.headers['Authorization'] == bearer(jwt)


# UTS: rest/unit/RSA8d/callback-error-propagated-4
async def test_rsa8d_callback_error_propagated():
    captured_requests = []

    async def auth_callback(params):
        raise Exception('Authentication server unavailable')

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=capture_and_respond(captured_requests),
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    with pytest.raises(AblyException) as excinfo:
        await client.request('GET', '/channels/test', version=api_version)

    # NOTE: the spec asserts the error message contains the callback's own text. ably-python
    # wraps the callback failure in an AblyException whose `message` names the callback and
    # whose `cause` is the original exception; the rendered error carries both.
    assert excinfo.value.code == 40170
    assert 'auth_callback raised an exception' in excinfo.value.message
    assert 'Authentication server unavailable' in str(excinfo.value.cause)
    assert 'Authentication server unavailable' in str(excinfo.value)

    assert len(captured_requests) == 0


# UTS: rest/unit/RSA8c/authurl-error-propagated-5
async def test_rsa8c_authurl_error_propagated():
    captured_requests = []

    def on_request(request):
        captured_requests.append(request)
        if request.url.host == AUTH_HOST:
            request.respond_with(500, {'error': 'Internal server error'})
        else:
            request.respond_with(200, CHANNEL_BODY)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, auth_url=f'https://{AUTH_HOST}/token')

    with pytest.raises(AblyException) as excinfo:
        await client.request('GET', '/channels/test', version=api_version)

    assert excinfo.value.status_code == 500

    assert len(captured_requests) == 1
    assert captured_requests[0].url.host == AUTH_HOST
