"""Derived from uts/rest/unit/auth/token_request_params.md in ably/specification.

Spec points: RSA5, RSA6, RSA9
"""

from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient

KEY = 'appId.keyId:keySecret'


def unreachable_mock():
    """A mock that records nothing; these specifications never reach the network."""
    return MockHttpClient(on_connection_attempt=lambda conn: conn.respond_with_success())


# UTS: rest/unit/RSA5/ttl-null-when-unspecified-0
async def test_rsa5_ttl_null_when_unspecified():
    client = rest_client(unreachable_mock(), key=KEY)

    token_request = await client.auth.create_token_request()

    assert token_request.ttl is None


# UTS: rest/unit/RSA5b/explicit-ttl-preserved-0
async def test_rsa5b_explicit_ttl_preserved():
    client = rest_client(unreachable_mock(), key=KEY)

    token_request = await client.auth.create_token_request({'ttl': 7200000})

    assert token_request.ttl == 7200000


# UTS: rest/unit/RSA5c/ttl-from-default-params-0
@deviation
async def test_rsa5c_ttl_from_default_params():
    client = rest_client(unreachable_mock(), key=KEY, default_token_params={'ttl': 1800000})

    token_request = await client.auth.create_token_request()

    # DEVIATION: `Auth.create_token_request` reads only the token params handed
    # to it (`token_params = token_params or {}`); the defaults are merged in
    # `Auth.request_token`, one level up, so a direct call sees none of them.
    assert token_request.ttl == 1800000


# UTS: rest/unit/RSA5d/explicit-ttl-overrides-default-0
async def test_rsa5d_explicit_ttl_overrides_default():
    client = rest_client(unreachable_mock(), key=KEY, default_token_params={'ttl': 1800000})

    token_request = await client.auth.create_token_request({'ttl': 600000})

    assert token_request.ttl == 600000


# UTS: rest/unit/RSA6/capability-null-when-unspecified-0
async def test_rsa6_capability_null_when_unspecified():
    client = rest_client(unreachable_mock(), key=KEY)

    token_request = await client.auth.create_token_request()

    assert token_request.capability is None


# UTS: rest/unit/RSA6b/explicit-capability-preserved-0
async def test_rsa6b_explicit_capability_preserved():
    client = rest_client(unreachable_mock(), key=KEY)

    token_request = await client.auth.create_token_request(
        {'capability': '{"channel-a":["publish","subscribe"]}'})

    # NOTE: the specification asserts the literal string it passed in. RSA9f has
    # the capability canonicalised before signing, and ably-python renders the
    # canonical form through `json.dumps`, which spaces its separators. The
    # capability is the same; only its rendering differs.
    assert token_request.capability == '{"channel-a": ["publish", "subscribe"]}'


# UTS: rest/unit/RSA6c/capability-from-default-params-0
@deviation
async def test_rsa6c_capability_from_default_params():
    client = rest_client(unreachable_mock(), key=KEY,
                         default_token_params={'capability': '{"*":["subscribe"]}'})

    token_request = await client.auth.create_token_request()

    # DEVIATION: as for RSA5c, `Auth.create_token_request` does not merge
    # `default_token_params`.
    assert token_request.capability == '{"*": ["subscribe"]}'


# UTS: rest/unit/RSA6d/explicit-capability-overrides-default-0
async def test_rsa6d_explicit_capability_overrides_default():
    client = rest_client(unreachable_mock(), key=KEY,
                         default_token_params={'capability': '{"*":["subscribe"]}'})

    token_request = await client.auth.create_token_request(
        {'capability': '{"channel-x":["publish"]}'})

    # NOTE: canonical rendering, as in RSA6b.
    assert token_request.capability == '{"channel-x": ["publish"]}'
