"""Derived from uts/rest/integration/auth.md in ably/specification.

Spec points: RSA4, RSA8, RSC10

The specification's preamble asks for every test to run against both token
formats, JWT first and an Ably native token second. Its Test IDs already carry
that split — `token-auth-jwt-0` and `auth-callback-jwt-3` are the JWT pair,
`token-auth-native-1` and `auth-callback-token-request-2` the native pair — so
the two formats are separate tests here rather than a second axis of
parametrisation over all eight.

There is no `## Protocol Variants` section, so these run against JSON only and
take no `use_binary_protocol`.
"""

import time

import pytest

from ably.transport.defaults import Defaults
from ably.util.exceptions import AblyException
from test.uts.helpers.client import sandbox_rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.sandbox import extract_key_name, extract_key_secret, generate_jwt, random_id

# The specification's `ttl: 3600000`, an hour in milliseconds.
ONE_HOUR_MS = 3600000

# The specification's `expires_at: now() - 5_seconds`, in seconds.
EXPIRED_BY_S = 5


async def channel_status(client, channel_name):
    """The specification's `client.request("GET", "/channels/" + channel_name)`.

    `request` takes the protocol version as a required argument here, and
    answers with an `HttpPaginatedResponse` that does not raise on an error
    status, which is what lets the invalid-credentials test read a 401 off the
    result rather than catching it.
    """
    return await client.request('GET', f'/channels/{channel_name}', version=Defaults.protocol_version)


# UTS: rest/integration/RSA4/basic-auth-key-0
async def test_rsa4_basic_auth_key(sandbox):
    channel_name = f'test-RSA4-{random_id()}'
    client = sandbox_rest_client(sandbox.key_str)

    result = await channel_status(client, channel_name)

    assert 200 <= result.status_code < 300


# UTS: rest/integration/RSA8/token-auth-jwt-0
async def test_rsa8_token_auth_jwt(sandbox):
    api_key = sandbox.key_str
    jwt = generate_jwt(
        key_name=extract_key_name(api_key),
        key_secret=extract_key_secret(api_key),
        ttl=ONE_HOUR_MS,
    )

    channel_name = f'test-RSA8-jwt-{random_id()}'
    client = sandbox_rest_client(token=jwt)

    result = await channel_status(client, channel_name)

    assert 200 <= result.status_code < 300


# UTS: rest/integration/RSA8/token-auth-native-1
async def test_rsa8_token_auth_native(sandbox):
    key_client = sandbox_rest_client(sandbox.key_str)

    # `request_token` takes its token params as a positional dict; every
    # keyword on it is an auth option.
    token_details = await key_client.auth.request_token()

    channel_name = f'test-RSA8-native-{random_id()}'
    token_client = sandbox_rest_client(token=token_details.token)

    result = await channel_status(token_client, channel_name)

    assert isinstance(token_details.token, str)
    assert len(token_details.token) > 0
    assert token_details.expires > time.time() * 1000
    assert 200 <= result.status_code < 300


# UTS: rest/integration/RSA8/auth-callback-token-request-2
async def test_rsa8_auth_callback_token_request(sandbox):
    token_request_client = sandbox_rest_client(sandbox.key_str)

    # The callback has to be a coroutine function: a synchronous one is
    # reported as 401/40170 rather than being awaited.
    async def auth_callback(params):
        return await token_request_client.auth.create_token_request(params)

    channel_name = f'test-RSA8-callback-{random_id()}'
    client = sandbox_rest_client(auth_callback=auth_callback)

    result = await channel_status(client, channel_name)

    assert 200 <= result.status_code < 300


# UTS: rest/integration/RSA8/auth-callback-jwt-3
async def test_rsa8_auth_callback_jwt(sandbox):
    api_key = sandbox.key_str

    # The token params reach the callback as a dict with snake_case keys, and
    # this client configures none, so both reads fall back the way the
    # specification's `params.ttl OR 3600000` does.
    async def auth_callback(params):
        return generate_jwt(
            key_name=extract_key_name(api_key),
            key_secret=extract_key_secret(api_key),
            client_id=params.get('client_id'),
            ttl=params.get('ttl') or ONE_HOUR_MS,
        )

    channel_name = f'test-RSA8-jwt-callback-{random_id()}'
    client = sandbox_rest_client(auth_callback=auth_callback)

    result = await channel_status(client, channel_name)

    assert 200 <= result.status_code < 300


# UTS: rest/integration/RSA4/invalid-credentials-rejected-1
async def test_rsa4_invalid_credentials_rejected(sandbox):
    channel_name = f'test-RSA4-invalid-{random_id()}'

    # The real app id with a fabricated key name, so the server answers 401
    # with error code 40400 rather than rejecting the app.
    invalid_key = f'{sandbox.app_id}.invalidKey:invalidSecret'

    client = sandbox_rest_client(invalid_key)

    result = await channel_status(client, channel_name)

    assert result.status_code == 401
    # `error_code` is the raw `X-Ably-Errorcode` header, so a string.
    assert result.error_code == '40400'


# UTS: rest/integration/RSC10/token-renewal-expired-jwt-0
@deviation
async def test_rsc10_token_renewal_expired_jwt(sandbox):
    api_key = sandbox.key_str
    issued_tokens = []

    async def auth_callback(params):
        if not issued_tokens:
            # An already-expired JWT, so the first request is rejected with a
            # token error: 401/40142, inside the 40140-40149 band RSC10 names.
            token = generate_jwt(
                key_name=extract_key_name(api_key),
                key_secret=extract_key_secret(api_key),
                expires_at=int(time.time()) - EXPIRED_BY_S,
            )
        else:
            token = generate_jwt(
                key_name=extract_key_name(api_key),
                key_secret=extract_key_secret(api_key),
                ttl=ONE_HOUR_MS,
            )
        issued_tokens.append(token)
        return token

    channel_name = f'test-RSC10-renewal-{random_id()}'
    client = sandbox_rest_client(auth_callback=auth_callback)

    result = await channel_status(client, channel_name)

    assert 200 <= result.status_code < 300
    assert len(issued_tokens) == 2
    # Counting the callbacks alone would not show that the renewal is what
    # carried the request: the client has to end up holding the second JWT.
    assert client.auth.token_details.token == issued_tokens[1]


# UTS: rest/integration/RSA8/capability-restriction-4
async def test_rsa8_capability_restriction(sandbox):
    api_key = sandbox.key_str
    allowed_channel = f'test-RSA8-cap-allowed-{random_id()}'
    denied_channel = f'test-RSA8-cap-denied-{random_id()}'

    jwt = generate_jwt(
        key_name=extract_key_name(api_key),
        key_secret=extract_key_secret(api_key),
        capability=f'{{"{allowed_channel}":["publish","subscribe"]}}',
        ttl=ONE_HOUR_MS,
    )

    client = sandbox_rest_client(token=jwt)

    # The allowed channel is publishable, which is the capability the JWT
    # grants; a channel status request would need channel-metadata instead.
    await client.channels.get(allowed_channel).publish(name='test', data='hello')

    with pytest.raises(AblyException) as excinfo:
        await client.channels.get(denied_channel).publish(name='test', data='hello')

    assert excinfo.value.code == 40160
    assert excinfo.value.status_code == 401
