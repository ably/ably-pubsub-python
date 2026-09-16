"""Derived from uts/rest/unit/auth/token_renewal.md in ably/specification.

Spec points: RSA4a2, RSA4b, RSA4b1, RSC10, RSC10b
"""

import base64
import time

import msgpack
import pytest

from ably.types.tokendetails import TokenDetails
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient

CHANNEL_DETAILS_BODY = {
    'channelId': 'test',
    'status': {
        'isActive': True,
        'occupancy': {
            'metrics': {
                'connections': 0,
            },
        },
    },
}


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


def token_error_body(code, message):
    return {
        'error': {
            'code': code,
            'statusCode': 401,
            'message': message,
        },
    }


# UTS: rest/unit/RSA4b/renewal-on-40142-0
async def test_rsa4b_renewal_on_40142():
    callback_count = 0
    tokens = ['first-token', 'second-token']
    captured_requests = []
    request_count = 0

    async def auth_callback(params):
        nonlocal callback_count
        token = tokens[callback_count]
        callback_count += 1
        return TokenDetails(token=token, expires=now() + 3600000)

    def on_request(request):
        nonlocal request_count
        captured_requests.append(request)
        request_count += 1
        if request_count == 1:
            request.respond_with(401, token_error_body(40142, 'Token expired'))
        else:
            request.respond_with(200, [{'channel': 'test'}])

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    result = await client.channels.get('test').history()

    assert callback_count == 2
    assert request_count == 2

    assert captured_requests[0].headers['Authorization'] == bearer('first-token')
    assert captured_requests[1].headers['Authorization'] == bearer('second-token')

    assert isinstance(result.items, list)


# UTS: rest/unit/RSA4b/renewal-on-40140-1
async def test_rsa4b_renewal_on_40140():
    callback_count = 0
    request_count = 0

    async def auth_callback(params):
        nonlocal callback_count
        callback_count += 1
        return TokenDetails(token=f'token-{callback_count}', expires=now() + 3600000)

    def on_request(request):
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            request.respond_with(401, token_error_body(40140, 'Token error'))
        else:
            request.respond_with(200, [])

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    await client.channels.get('test').history()

    assert callback_count == 2
    assert request_count == 2


# UTS: rest/unit/RSA4b1/preemptive-renewal-0
async def test_rsa4b1_preemptive_renewal():
    callback_count = 0
    captured_requests = []

    async def auth_callback(params):
        nonlocal callback_count
        callback_count += 1
        if callback_count == 1:
            return TokenDetails(token='expired-token', expires=now() - 1000)
        return TokenDetails(token='fresh-token', expires=now() + 3600000)

    def on_request(request):
        captured_requests.append(request)
        request.respond_with(200, [])

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    await client.auth.authorize()
    await client.channels.get('test').history()

    # UTS SPEC ERROR: RSA4b1 - the spec point makes pre-emptive expiry detection optional and
    # conditional on a clock offset persisted from the Ably service (RSA10k), which this setup
    # never establishes, so a compliant library may send the expired token and let the server rule.
    assert callback_count == 1

    requests_to_history = [r for r in captured_requests if r.path == '/channels/test/messages']
    assert len(requests_to_history) == 1
    assert requests_to_history[0].headers['Authorization'] == bearer('expired-token')


# UTS: rest/unit/RSA4a2/no-renewal-without-callback-0
async def test_rsa4a2_no_renewal_without_callback():
    request_count = 0

    def on_request(request):
        nonlocal request_count
        request_count += 1
        request.respond_with(401, token_error_body(40142, 'Token expired'))

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, token='static-token')

    with pytest.raises(AblyException) as excinfo:
        await client.channels.get('test').history()

    assert excinfo.value.code == 40171

    assert request_count == 1


# UTS: rest/unit/RSA4b/renewal-via-authurl-2
# DEVIATION: RSA8c takes a JSON auth_url response to be "a TokenRequest or
# TokenDetails object". ably-python recognises TokenDetails only when the payload
# carries `issued` (ably/rest/auth.py, Auth.request_token), so the specification's
# `{"token": ..., "expires": ...}` is read as a TokenRequest, and TokenRequest.from_json
# rejects it as 40170 on the very first fetch. The auth_url requests themselves now
# reach the mock.
@deviation
async def test_rsa4b_renewal_via_authurl():
    captured_requests = []
    request_count = 0

    def on_request(request):
        nonlocal request_count
        captured_requests.append(request)
        request_count += 1

        if request.url.host == 'example.com':
            if request_count == 1:
                request.respond_with(200, {'token': 'first-token', 'expires': now() + 3600000})
            else:
                request.respond_with(200, {'token': 'second-token', 'expires': now() + 3600000})
        elif request_count == 2:
            request.respond_with(401, token_error_body(40142, 'Token expired'))
        else:
            request.respond_with(200, [])

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, auth_url='https://example.com/auth')

    await client.channels.get('test').history()

    auth_requests = [r for r in captured_requests if r.url.host == 'example.com']
    assert len(auth_requests) == 2

    api_requests = [r for r in captured_requests if r.url.host != 'example.com']
    assert len(api_requests) == 2

    assert api_requests[1].headers['Authorization'] == bearer('second-token')


# UTS: rest/unit/RSA4b/renewal-limit-no-loop-3
async def test_rsa4b_renewal_limit_no_loop():
    callback_count = 0
    request_count = 0

    async def auth_callback(params):
        nonlocal callback_count
        callback_count += 1
        return TokenDetails(token=f'token-{callback_count}', expires=now() + 3600000)

    def on_request(request):
        nonlocal request_count
        request_count += 1
        request.respond_with(401, token_error_body(40142, 'Token expired'))

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    with pytest.raises(AblyException) as excinfo:
        await client.channels.get('test').history()

    assert excinfo.value.code == 40142

    assert callback_count == 2
    assert request_count == 2


# UTS: rest/unit/RSC10/request-retried-after-renewal-0
async def test_rsc10_request_retried_after_renewal():
    callback_count = 0
    captured_requests = []

    async def auth_callback(params):
        nonlocal callback_count
        callback_count += 1
        return TokenDetails(token=f'token-{callback_count}', expires=now() + 3600000)

    def on_request(request):
        captured_requests.append(request)
        if request.headers['Authorization'] == bearer('token-1'):
            request.respond_with(401, token_error_body(40142, 'Token expired'))
        else:
            request.respond_with(200, CHANNEL_DETAILS_BODY)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    result = await client.channels.get('test').status()

    assert result.channel_id == 'test'
    assert result.status.is_active is True

    channel_requests = [r for r in captured_requests if r.path == '/channels/test']
    assert len(channel_requests) == 2

    assert callback_count == 2

    assert channel_requests[0].headers['Authorization'] == bearer('token-1')
    assert channel_requests[1].headers['Authorization'] == bearer('token-2')


# UTS: rest/unit/RSC10b/non-token-401-no-renewal-0
async def test_rsc10b_non_token_401_no_renewal():
    callback_count = 0
    request_count = 0

    async def auth_callback(params):
        nonlocal callback_count
        callback_count += 1
        return TokenDetails(token=f'token-{callback_count}', expires=now() + 3600000)

    def on_request(request):
        nonlocal request_count
        request_count += 1
        request.respond_with(401, token_error_body(40100, 'Unauthorized'))

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    with pytest.raises(AblyException) as excinfo:
        await client.channels.get('test').status()

    assert excinfo.value.code == 40100

    assert request_count == 1
    assert callback_count == 1


# UTS: rest/unit/RSA4b/renewal-msgpack-response-4
async def test_rsa4b_renewal_msgpack_response():
    callback_count = 0
    request_count = 0

    async def auth_callback(params):
        nonlocal callback_count
        callback_count += 1
        return TokenDetails(token=f'token-{callback_count}', expires=now() + 3600000)

    def on_request(request):
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            request.respond_with(
                401,
                msgpack.packb(token_error_body(40142, 'Token expired'), use_bin_type=False),
                {'Content-Type': 'application/x-msgpack'},
            )
        else:
            request.respond_with(
                200,
                msgpack.packb(CHANNEL_DETAILS_BODY, use_bin_type=False),
                {'Content-Type': 'application/x-msgpack'},
            )

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, auth_callback=auth_callback, use_binary_protocol=True)

    # UTS SPEC ERROR: RSA4b - the spec drives this through `client.time()`, but `/time` carries no
    # credentials (its own rest/unit/RSC16/no-auth-required-2 asserts that), so it can never
    # receive a token error or trigger renewal; an authenticated call exercises the stated intent.
    result = await client.channels.get('test').status()

    assert callback_count == 2
    assert request_count == 2

    assert result.channel_id == 'test'
