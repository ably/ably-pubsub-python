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

AUTH_URL_SKIP_REASON = 'auth_url requests bypass the injected HTTP transport; see the note in each test.'


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


# UTS: rest/unit/RSA8c/authurl-invoked-for-auth-0
@pytest.mark.skip(reason=AUTH_URL_SKIP_REASON)
async def test_rsa8c_authurl_invoked_for_auth():
    # `Auth.token_request_from_auth_url` builds its own `httpx.AsyncClient` rather than going
    # through `Http`, so the auth_url call never reaches the mock. Enabling the test would send a
    # real request to auth.example.com, so it is skipped outright rather than gated.
    pass


# UTS: rest/unit/RSA8c/authurl-post-method-1
@pytest.mark.skip(reason=AUTH_URL_SKIP_REASON)
async def test_rsa8c_authurl_post_method():
    # See the note on test_rsa8c_authurl_invoked_for_auth.
    pass


# UTS: rest/unit/RSA8c/authurl-custom-headers-2
@pytest.mark.skip(reason=AUTH_URL_SKIP_REASON)
async def test_rsa8c_authurl_custom_headers():
    # See the note on test_rsa8c_authurl_invoked_for_auth.
    pass


# UTS: rest/unit/RSA8c/authurl-query-params-3
@pytest.mark.skip(reason=AUTH_URL_SKIP_REASON)
async def test_rsa8c_authurl_query_params():
    # See the note on test_rsa8c_authurl_invoked_for_auth.
    pass


# UTS: rest/unit/RSA8c/authurl-returns-jwt-4
@pytest.mark.skip(reason=AUTH_URL_SKIP_REASON)
async def test_rsa8c_authurl_returns_jwt():
    # See the note on test_rsa8c_authurl_invoked_for_auth.
    pass


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
@pytest.mark.skip(reason=AUTH_URL_SKIP_REASON)
async def test_rsa8c_authurl_error_propagated():
    # See the note on test_rsa8c_authurl_invoked_for_auth.
    pass
