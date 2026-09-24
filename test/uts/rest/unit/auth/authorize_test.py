"""Derived from uts/rest/unit/auth/authorize.md in ably/specification.

Spec points: RSA10, RSA10a, RSA10b, RSA10e, RSA10g, RSA10h, RSA10i, RSA10j, RSA10k, RSA10l
"""

import base64
import re
import time

import pytest

from ably.types.authoptions import AuthOptions
from ably.types.tokendetails import TokenDetails
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation, spec_error
from test.uts.helpers.mock_http import MockHttpClient

KEY = 'appId.keyId:keySecret'

# `channels.get(name).status()` walks status.occupancy.metrics unguarded, so the
# specification's shorter `{"channelId": ..., "status": {"isActive": true}}` body
# cannot be decoded. The extra nesting carries no meaning for these assertions.
CHANNEL_DETAILS_BODY = {
    'channelId': 'test',
    'status': {
        'isActive': True,
        'occupancy': {
            'metrics': {
                'connections': 0,
                'presenceConnections': 0,
                'presenceMembers': 0,
                'presenceSubscribers': 0,
                'publishers': 0,
                'subscribers': 0,
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


# UTS: rest/unit/RSA10a/authorize-default-params-0
async def test_rsa10a_authorize_default_params():
    captured_requests = []

    def on_request(request):
        captured_requests.append(request)
        if request.path.endswith('/requestToken'):
            request.respond_with(200, {
                'token': 'obtained-token',
                'expires': now() + 3600000,
                'keyName': 'appId.keyId',
            })
        else:
            request.respond_with(200, CHANNEL_DETAILS_BODY)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, key=KEY)

    token_details = await client.auth.authorize()

    assert isinstance(token_details, TokenDetails)
    assert token_details.token == 'obtained-token'

    await client.channels.get('test').status()
    assert captured_requests[-1].headers['Authorization'] == bearer('obtained-token')


# UTS: rest/unit/RSA10b/authorize-explicit-params-0
@deviation
async def test_rsa10b_authorize_explicit_params():
    callback_params = []

    async def mock_auth_callback(params):
        callback_params.append(params)
        return TokenDetails(token='callback-token', expires=now() + 3600000)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, {'channelId': 'test'}),
    )
    client = rest_client(mock_http, auth_callback=mock_auth_callback, client_id='default-client')

    # DEVIATION: `Auth._ensure_valid_auth_credentials` overwrites the caller's
    # `client_id` with `Auth.client_id` unconditionally, so the callback is handed
    # 'default-client'. RSA10h has `Auth#clientId` supply a default only, and RSA10j
    # has explicit `TokenParams` supersede configured ones. The token that comes
    # back then carries no clientId, which `Auth._configure_client_id` rejects with
    # IncompatibleClientIdException 40102 before the assertions are reached.
    await client.auth.authorize({'client_id': 'override-client', 'ttl': 7200000})

    params = callback_params[0]
    assert params['client_id'] == 'override-client'
    assert params['ttl'] == 7200000


# UTS: rest/unit/RSA10e/authorize-saves-params-0
async def test_rsa10e_authorize_saves_params():
    callback_invocations = []

    async def mock_auth_callback(params):
        callback_invocations.append(params)
        return TokenDetails(
            token='token-' + str(len(callback_invocations)),
            expires=now() + 3600000,
        )

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, []),
    )
    client = rest_client(mock_http, auth_callback=mock_auth_callback)

    await client.auth.authorize({'client_id': 'saved-client', 'ttl': 3600000})

    await client.auth.authorize()

    assert len(callback_invocations) == 2

    assert callback_invocations[1]['client_id'] == 'saved-client'
    assert callback_invocations[1]['ttl'] == 3600000


# UTS: rest/unit/RSA10g/authorize-updates-token-details-0
async def test_rsa10g_authorize_updates_token_details():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, {
            'token': 'new-token',
            'expires': now() + 3600000,
            'keyName': 'appId.keyId',
            'clientId': 'token-client',
        }),
    )
    client = rest_client(mock_http, key=KEY)

    assert client.auth.token_details is None

    result = await client.auth.authorize()

    assert client.auth.token_details is not None
    assert client.auth.token_details.token == 'new-token'
    assert client.auth.token_details.client_id == 'token-client'
    assert client.auth.token_details == result


# UTS: rest/unit/RSA10h/authorize-replaces-auth-options-0
async def test_rsa10h_authorize_replaces_auth_options():
    calls = {'original': False, 'new': False}

    async def original_callback(params):
        calls['original'] = True
        return TokenDetails(token='original', expires=now() + 3600000)

    async def new_callback(params):
        calls['new'] = True
        return TokenDetails(token='new', expires=now() + 3600000)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, {'channelId': 'test'}),
    )
    client = rest_client(mock_http, auth_callback=original_callback)

    await client.auth.authorize(auth_options=AuthOptions(auth_callback=new_callback))

    assert calls['original'] is False
    assert calls['new'] is True


# UTS: rest/unit/RSA10i/authorize-preserves-key-0
# The assertions block is empty, and the premise that a key survives a provided AuthOptions
# is one RSA8e and RSA10j contradict; see deviations.md.
@spec_error
async def test_rsa10i_authorize_preserves_key():
    captured_requests = []

    def on_request(request):
        captured_requests.append(request)
        if re.fullmatch(r'/keys/.*/requestToken', request.url.path):
            # Initial token request using key
            request.respond_with(200, {
                'token': 'token-via-key',
                'expires': now() + 3600000,
                'keyName': 'appId.keyId',
            })
        else:
            request.respond_with(200, {'channelId': 'test'})

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, key=KEY)

    # Call authorize with new authUrl but no key. The key should still be available for
    # signing, so the implementation can still use it for requestToken.
    await client.auth.authorize(auth_options=AuthOptions(auth_url='https://new-auth.example.com/token'))

    # Key from constructor should be preserved (not cleared). The specification leaves the
    # exact assertion open - "verify by checking that key-based operations still work" - so
    # the stored key and the signed token request stand in for it.
    assert client.auth.auth_options.key_name == 'appId.keyId'
    assert client.auth.auth_options.key_secret == 'keySecret'
    assert any(r.url.path == '/keys/appId.keyId/requestToken' for r in captured_requests)


# UTS: rest/unit/RSA10j/authorize-replaces-existing-token-0
async def test_rsa10j_authorize_replaces_existing_token():
    token_count = {'value': 0}

    async def mock_auth_callback(params):
        token_count['value'] += 1
        return TokenDetails(
            token='token-' + str(token_count['value']),
            expires=now() + 3600000,
        )

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(200, {'channelId': 'test'}),
    )
    client = rest_client(mock_http, auth_callback=mock_auth_callback)

    result1 = await client.auth.authorize()
    result2 = await client.auth.authorize()

    assert result1.token == 'token-1'
    assert result2.token == 'token-2'
    assert client.auth.token_details.token == 'token-2'


# UTS: rest/unit/RSA10k/authorize-query-time-0
async def test_rsa10k_authorize_query_time():
    captured_requests = []

    def on_request(request):
        captured_requests.append(request)
        if request.url.path == '/time':
            # UTS SPEC ERROR: RSA10k - the spec stubs /time as {"time": N}; the REST
            # endpoint and uts/rest/unit/time.md both return a one-element array.
            request.respond_with(200, [1234567890000])
        else:
            request.respond_with(200, {
                'token': 'time-synced-token',
                'expires': 1234567890000 + 3600000,
            })

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, key=KEY)

    # UTS SPEC ERROR: RSA10k - the spec passes `AuthOptions(queryTime: true)` alone and
    # still expects the key to sign the token request, but RSA8e and RSA10j have the
    # argument used "instead of the stored values (even when null)", so the key goes
    # with them. Carrying the key in the same AuthOptions is what those points require
    # of a caller who means to keep signing with it.
    await client.auth.authorize(auth_options=AuthOptions(key=KEY, query_time=True))

    time_request = next((r for r in captured_requests if r.url.path == '/time'), None)
    assert time_request is not None


# UTS: rest/unit/RSA10l/authorize-error-propagated-0
async def test_rsa10l_authorize_error_propagated():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(401, {
            'error': {
                'code': 40100,
                'statusCode': 401,
                'message': 'Unauthorized',
            },
        }),
    )
    client = rest_client(mock_http, key='invalid.key:secret')

    with pytest.raises(AblyException) as excinfo:
        await client.auth.authorize()

    assert excinfo.value.code == 40100
    assert excinfo.value.status_code == 401
