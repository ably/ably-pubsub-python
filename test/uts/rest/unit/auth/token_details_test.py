"""Derived from uts/rest/unit/auth/token_details.md in ably/specification.

Spec points: RSA16, RSA16a, RSA16b, RSA16c, RSA16d
"""

import time

import pytest

from ably.types.authoptions import AuthOptions
from ably.types.capability import Capability
from ably.types.tokendetails import TokenDetails
from ably.util.exceptions import AblyException
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient

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

TOKEN_EXPIRED_BODY = {
    'error': {
        'code': 40142,
        'statusCode': 401,
        'message': 'Token expired',
    },
}


def now():
    return int(time.time() * 1000)


def respond_with_channel_details(request):
    request.respond_with(200, CHANNEL_DETAILS_BODY)


# UTS: rest/unit/RSA16a/token-from-callback-0
async def test_rsa16a_token_from_callback():
    async def auth_callback(params):
        return TokenDetails(
            token='callback-token-abc',
            expires=now() + 3600000,
            issued=now(),
            client_id='my-client',
        )

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with_channel_details,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    await client.channels.get('test').status()

    assert client.auth.token_details is not None
    assert client.auth.token_details.token == 'callback-token-abc'
    assert client.auth.token_details.client_id == 'my-client'
    assert client.auth.token_details.expires is not None
    assert client.auth.token_details.issued is not None


# UTS: rest/unit/RSA16a/token-from-request-token-1
async def test_rsa16a_token_from_request_token():
    def on_request(request):
        if request.path.endswith('/requestToken'):
            request.respond_with(200, {
                'token': 'requested-token-xyz',
                'expires': now() + 3600000,
                'issued': now(),
                'keyName': 'appId.keyId',
                'clientId': 'token-client',
            })
        else:
            request.respond_with(200, CHANNEL_DETAILS_BODY)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, key='appId.keyId:keySecret')

    await client.auth.authorize()

    assert client.auth.token_details is not None
    assert client.auth.token_details.token == 'requested-token-xyz'
    assert client.auth.token_details.client_id == 'token-client'


# UTS: rest/unit/RSA16b/token-string-in-options-0
@deviation
async def test_rsa16b_token_string_in_options():
    # DEVIATION: RSA16b requires that only `token` is populated. `TokenDetails.__init__`
    # fabricates `expires` from a default one-hour TTL, defaults `issued` to 0 and turns
    # a missing capability into an empty `Capability`.
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with_channel_details,
    )
    client = rest_client(mock_http, token='standalone-token-string')

    token_details = client.auth.token_details

    assert token_details is not None
    assert token_details.token == 'standalone-token-string'
    assert token_details.expires is None
    assert token_details.issued is None
    assert token_details.client_id is None
    assert token_details.capability is None


# UTS: rest/unit/RSA16b/token-string-from-callback-1
@deviation
async def test_rsa16b_token_string_from_callback():
    # DEVIATION: as above. `Auth.request_token` wraps a token string in a bare
    # `TokenDetails`, which fabricates `expires` and defaults `issued` to 0.
    async def auth_callback(params):
        return 'just-a-token-string'

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with_channel_details,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    await client.channels.get('test').status()

    assert client.auth.token_details is not None
    assert client.auth.token_details.token == 'just-a-token-string'
    assert client.auth.token_details.expires is None
    assert client.auth.token_details.issued is None


# UTS: rest/unit/RSA16c/set-on-instantiation-0
async def test_rsa16c_set_on_instantiation():
    initial_token = TokenDetails(
        token='initial-token',
        expires=now() + 3600000,
        issued=now(),
        client_id='initial-client',
    )

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with_channel_details,
    )
    client = rest_client(mock_http, token_details=initial_token)

    token_details = client.auth.token_details

    assert token_details is not None
    assert token_details.token == 'initial-token'
    assert token_details.client_id == 'initial-client'


# UTS: rest/unit/RSA16c/updated-after-authorize-1
@deviation
async def test_rsa16c_updated_after_authorize():
    # DEVIATION: the second token carries a different clientId, and
    # `Auth._configure_client_id` rejects any change to a clientId the library
    # learned from an earlier token with `IncompatibleClientIdException` (40102).
    # RSA15 only makes the clientId immutable when one was set in ClientOptions,
    # which it is not here, so the second authorize should succeed.
    token_count = 0

    async def auth_callback(params):
        nonlocal token_count
        token_count += 1
        return TokenDetails(
            token=f'token-v{token_count}',
            expires=now() + 3600000,
            client_id=f'client-v{token_count}',
        )

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with_channel_details,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    await client.auth.authorize()
    first_token = client.auth.token_details

    await client.auth.authorize()
    second_token = client.auth.token_details

    assert first_token.token == 'token-v1'
    assert first_token.client_id == 'client-v1'

    assert second_token.token == 'token-v2'
    assert second_token.client_id == 'client-v2'

    assert first_token.token != second_token.token


# UTS: rest/unit/RSA16c/updated-after-expiry-renewal-2
@deviation
async def test_rsa16c_updated_after_expiry_renewal():
    # DEVIATION: ably-python gates its RSA4b1 local expiry check on having a server
    # time offset (`Auth.token_details_has_expired` returns False while
    # `Auth.time_offset` is unset, and `reauth_if_expired` skips the check too). A
    # client authenticating through an authCallback never obtains that offset, so an
    # expired token is reused indefinitely and no renewal is initiated.
    #
    # NOTE: the spec drives this with a TestClock advanced past the token's expiry.
    # ably-python has no clock seam, so the callback backdates `expires` instead,
    # which leaves the token expired under the real clock from the second request on.
    token_count = 0

    async def auth_callback(params):
        nonlocal token_count
        token_count += 1
        return TokenDetails(
            token=f'token-v{token_count}',
            expires=now() - 1000,
            client_id='stable-client',
        )

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with_channel_details,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    await client.channels.get('test').status()
    first_token = client.auth.token_details

    await client.channels.get('test').status()
    second_token = client.auth.token_details

    assert first_token.token == 'token-v1'
    assert second_token.token == 'token-v2'


# UTS: rest/unit/RSA16c/updated-after-40142-renewal-3
@deviation
async def test_rsa16c_updated_after_40142_renewal():
    # DEVIATION: the renewal itself works — `reauth_if_expired` re-authorizes on a
    # token error and replays the request — but the renewed token carries a different
    # clientId, which `Auth._configure_client_id` rejects with 40102. See
    # `test_rsa16c_updated_after_authorize` for the same cause.
    request_count = 0
    token_count = 0

    def on_request(request):
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            request.respond_with(401, TOKEN_EXPIRED_BODY)
        else:
            request.respond_with(200, CHANNEL_DETAILS_BODY)

    async def auth_callback(params):
        nonlocal token_count
        token_count += 1
        return TokenDetails(
            token=f'token-v{token_count}',
            expires=now() + 3600000,
            client_id=f'client-v{token_count}',
        )

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=on_request,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    await client.auth.authorize()
    first_token = client.auth.token_details

    await client.channels.get('test').status()
    second_token = client.auth.token_details

    assert first_token.token == 'token-v1'
    assert second_token.token == 'token-v2'


# UTS: rest/unit/RSA16d/null-with-basic-auth-0
async def test_rsa16d_null_with_basic_auth():
    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with_channel_details,
    )
    client = rest_client(mock_http, key='appId.keyId:keySecret')

    await client.channels.get('test').status()

    assert client.auth.token_details is None


# UTS: rest/unit/RSA16d/null-before-token-obtained-1
async def test_rsa16d_null_before_token_obtained():
    async def auth_callback(params):
        return TokenDetails(token='my-token', expires=now() + 3600000)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with_channel_details,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    token_details = client.auth.token_details

    assert token_details is None


# UTS: rest/unit/RSA16d/null-after-invalidation-2
@deviation
async def test_rsa16d_null_after_invalidation():
    # DEVIATION: RSA16d requires tokenDetails to be null once the token has been
    # determined to be invalid. `Auth._ensure_valid_auth_credentials` only replaces
    # `__token_details` once a replacement has been obtained, so a failed renewal
    # leaves the invalidated token in place.
    callback_count = 0

    async def auth_callback(params):
        nonlocal callback_count
        callback_count += 1
        if callback_count == 1:
            return TokenDetails(token='first-token', expires=now() + 3600000)
        raise Exception('Cannot obtain new token')

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=lambda request: request.respond_with(401, TOKEN_EXPIRED_BODY),
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    await client.auth.authorize()
    assert client.auth.token_details is not None
    assert client.auth.token_details.token == 'first-token'

    with pytest.raises(AblyException):
        await client.channels.get('test').status()

    assert client.auth.token_details is None


# UTS: rest/unit/RSA16d/null-after-switch-to-basic-3
@deviation
async def test_rsa16d_null_after_switch_to_basic():
    # DEVIATION: `Auth._ensure_valid_auth_credentials` sets the auth mechanism to TOKEN
    # unconditionally and `AuthOptions.replace` drops `use_token_auth` entirely, so
    # authorizing with a key and `use_token_auth=False` requests a token from the key
    # instead of switching the client to basic auth. tokenDetails stays populated.
    async def auth_callback(params):
        return TokenDetails(token='my-token', expires=now() + 3600000)

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with_channel_details,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    await client.auth.authorize()
    assert client.auth.token_details is not None

    await client.auth.authorize(auth_options=AuthOptions(
        key='appId.keyId:keySecret',
        use_token_auth=False,
    ))

    assert client.auth.token_details is None


# UTS: rest/unit/RSA16a/preserved-across-requests-0
async def test_rsa16a_preserved_across_requests():
    async def auth_callback(params):
        return TokenDetails(
            token='stable-token',
            expires=now() + 3600000,
            client_id='stable-client',
        )

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with_channel_details,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    await client.channels.get('test').status()
    first_check = client.auth.token_details

    await client.channels.get('test').status()
    second_check = client.auth.token_details

    await client.channels.get('test').status()
    third_check = client.auth.token_details

    assert first_check.token == 'stable-token'
    assert second_check.token == 'stable-token'
    assert third_check.token == 'stable-token'


# UTS: rest/unit/RSA16a/reflects-capability-1
async def test_rsa16a_reflects_capability():
    async def auth_callback(params):
        return TokenDetails(
            token='capable-token',
            expires=now() + 3600000,
            capability='{"channel1":["publish","subscribe"],"channel2":["subscribe"]}',
        )

    mock_http = MockHttpClient(
        on_connection_attempt=lambda conn: conn.respond_with_success(),
        on_request=respond_with_channel_details,
    )
    client = rest_client(mock_http, auth_callback=auth_callback)

    await client.channels.get('test').status()

    assert client.auth.token_details is not None

    # DEVIATION: the spec asserts the stringified JSON
    # '{"channel1":["publish","subscribe"],"channel2":["subscribe"]}'.
    # `TokenDetails.capability` is a parsed `Capability` throughout ably-python, an
    # established SDK-wide choice, so the same capability is asserted in that form.
    capability = client.auth.token_details.capability
    assert isinstance(capability, Capability)
    assert capability.to_dict() == {
        'channel1': ['publish', 'subscribe'],
        'channel2': ['subscribe'],
    }
