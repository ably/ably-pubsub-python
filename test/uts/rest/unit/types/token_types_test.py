"""Derived from uts/rest/unit/types/token_types.md in ably/specification.

Spec points: TD1, TD2, TD3, TD4, TD5, TK1, TK2, TK3, TK4, TK5, TK6, TE1, TE2, TE3,
TE4, TE5, TE6

ably-python has no TokenParams type: token params travel as a plain dict with snake_case
keys, which is the idiomatic Python rendering of the spec's TokenParams. The TK tests
therefore drive them through `auth.create_token_request`, the surface that consumes them.
"""

import json

from ably.types.tokendetails import TokenDetails
from ably.types.tokenrequest import TokenRequest
from test.uts.helpers.client import rest_client
from test.uts.helpers.deviations import deviation
from test.uts.helpers.mock_http import MockHttpClient

TIMESTAMP_MS = 1234567890000


def offline_client():
    """A client whose only use is `auth`, so no request ever reaches the mock."""
    mock_http = MockHttpClient(on_connection_attempt=lambda conn: conn.respond_with_success())
    return rest_client(mock_http)


# UTS: rest/unit/TD1/token-details-attributes-0
def test_td1_token_details_attributes():
    # TD1 - token attribute
    token_details = TokenDetails(
        token='test-token',
        expires=1234567890000,
    )
    assert token_details.token == 'test-token'

    # TD2 - expires attribute (milliseconds since epoch)
    assert token_details.expires == 1234567890000

    # TD3 - issued attribute
    token_with_issued = TokenDetails(
        token='test-token',
        expires=1234567890000,
        issued=1234567800000,
    )
    assert token_with_issued.issued == 1234567800000

    # TD4 - capability attribute (JSON string)
    token_with_capability = TokenDetails(
        token='test-token',
        expires=1234567890000,
        capability='{"*":["*"]}',
    )
    # NOTE: the spec asserts capability IS the JSON string. ably-python parses it into a
    # Capability mapping, which stringifies back to the same JSON.
    assert json.loads(str(token_with_capability.capability)) == {'*': ['*']}

    # TD5 - clientId attribute
    token_with_client = TokenDetails(
        token='test-token',
        expires=1234567890000,
        client_id='my-client',
    )
    assert token_with_client.client_id == 'my-client'


# UTS: rest/unit/TD/token-details-from-json-0
@deviation
def test_td_token_details_from_json():
    json_data = {
        'token': 'deserialized-token',
        'expires': 1234567890000,
        'issued': 1234567800000,
        'capability': '{"channel-1":["publish"]}',
        'clientId': 'json-client',
        'keyName': 'appId.keyId',
    }

    token_details = TokenDetails.from_json(json_data)

    assert token_details.token == 'deserialized-token'
    assert token_details.expires == 1234567890000
    assert token_details.issued == 1234567800000
    assert json.loads(str(token_details.capability)) == {'channel-1': ['publish']}
    assert token_details.client_id == 'json-client'


# UTS: rest/unit/TK1/token-params-attributes-0
async def test_tk1_token_params_attributes():
    client = offline_client()

    # TK1 - ttl attribute (milliseconds, nullable)
    params = {'ttl': 3600000, 'timestamp': TIMESTAMP_MS}
    assert (await client.auth.create_token_request(params)).ttl == 3600000

    # TK1 - ttl defaults to null when not specified (RSA5 depends on this)
    params = {'timestamp': TIMESTAMP_MS}
    assert (await client.auth.create_token_request(params)).ttl is None

    # TK2 - capability attribute (nullable)
    params = {'capability': '{"*":["subscribe"]}', 'timestamp': TIMESTAMP_MS}
    capability = (await client.auth.create_token_request(params)).capability
    # NOTE: ably-python re-serialises the capability, so the JSON text is not byte-identical.
    assert json.loads(capability) == {'*': ['subscribe']}

    # TK2 - capability defaults to null when not specified (RSA6 depends on this)
    params = {'timestamp': TIMESTAMP_MS}
    assert (await client.auth.create_token_request(params)).capability is None

    # TK3 - clientId attribute
    params = {'client_id': 'param-client', 'timestamp': TIMESTAMP_MS}
    assert (await client.auth.create_token_request(params)).client_id == 'param-client'

    # TK4 - timestamp attribute (milliseconds since epoch)
    params = {'timestamp': 1234567890000}
    assert (await client.auth.create_token_request(params)).timestamp == 1234567890000

    # TK5 - nonce attribute
    params = {'nonce': 'unique-nonce-value', 'timestamp': TIMESTAMP_MS}
    assert (await client.auth.create_token_request(params)).nonce == 'unique-nonce-value'

    # TK6 - All attributes together
    params = {
        'ttl': 7200000,
        'capability': '{"*":["*"]}',
        'client_id': 'full-client',
        'timestamp': 1234567890000,
        'nonce': 'full-nonce',
    }
    token_request = await client.auth.create_token_request(params)
    assert token_request.ttl == 7200000
    assert json.loads(token_request.capability) == {'*': ['*']}
    assert token_request.client_id == 'full-client'
    assert token_request.timestamp == 1234567890000
    assert token_request.nonce == 'full-nonce'


# UTS: rest/unit/TK/token-params-to-query-string-0
async def test_tk_token_params_to_query_string():
    client = offline_client()

    params = {
        'ttl': 3600000,
        'client_id': 'query-client',
        'capability': '{"ch":["pub"]}',
        'timestamp': TIMESTAMP_MS,
    }

    # NOTE: ably-python has no TokenParams.toQueryParams(). Token params are rendered for
    # transmission by create_token_request, whose to_dict() is the wire form; values keep
    # their native types rather than being stringified.
    query_map = (await client.auth.create_token_request(params)).to_dict()

    assert query_map['ttl'] == 3600000
    assert query_map['clientId'] == 'query-client'
    assert json.loads(query_map['capability']) == {'ch': ['pub']}


# UTS: rest/unit/TE1/token-request-attributes-0
def test_te1_token_request_attributes():
    # TE1 - keyName attribute
    request = TokenRequest(
        key_name='appId.keyId',
        timestamp=1234567890000,
        nonce='nonce-1',
    )
    assert request.key_name == 'appId.keyId'

    # TE2 - ttl attribute (nullable)
    request = TokenRequest(
        key_name='appId.keyId',
        ttl=3600000,
        timestamp=1234567890000,
        nonce='nonce-2',
    )
    assert request.ttl == 3600000

    # TE2 - ttl defaults to null when not specified (RSA5 depends on this)
    request = TokenRequest(
        key_name='appId.keyId',
        timestamp=1234567890000,
        nonce='nonce-2b',
    )
    assert request.ttl is None

    # TE3 - capability attribute (nullable)
    request = TokenRequest(
        key_name='appId.keyId',
        capability='{"*":["*"]}',
        timestamp=1234567890000,
        nonce='nonce-3',
    )
    assert request.capability == '{"*":["*"]}'

    # TE3 - capability defaults to null when not specified (RSA6 depends on this)
    request = TokenRequest(
        key_name='appId.keyId',
        timestamp=1234567890000,
        nonce='nonce-3b',
    )
    assert request.capability is None

    # TE4 - clientId attribute
    request = TokenRequest(
        key_name='appId.keyId',
        client_id='request-client',
        timestamp=1234567890000,
        nonce='nonce-4',
    )
    assert request.client_id == 'request-client'

    # TE5 - timestamp attribute
    request = TokenRequest(
        key_name='appId.keyId',
        timestamp=1234567890000,
        nonce='nonce-5',
    )
    assert request.timestamp == 1234567890000

    # TE6 - nonce attribute
    request = TokenRequest(
        key_name='appId.keyId',
        timestamp=1234567890000,
        nonce='unique-nonce',
    )
    assert request.nonce == 'unique-nonce'


# UTS: rest/unit/TE/token-request-mac-signature-0
def test_te_token_request_mac_signature():
    request = TokenRequest(
        key_name='appId.keyId',
        timestamp=1234567890000,
        nonce='nonce-value',
        mac='signature-base64',
    )

    assert request.mac == 'signature-base64'


# UTS: rest/unit/TE/token-request-to-json-1
def test_te_token_request_to_json():
    request = TokenRequest(
        key_name='appId.keyId',
        ttl=3600000,
        capability='{"*":["*"]}',
        client_id='json-client',
        timestamp=1234567890000,
        nonce='json-nonce',
        mac='json-mac',
    )

    json_data = request.to_dict()

    assert json_data['keyName'] == 'appId.keyId'
    assert json_data['ttl'] == 3600000
    assert json_data['capability'] == '{"*":["*"]}'
    assert json_data['clientId'] == 'json-client'
    assert json_data['timestamp'] == 1234567890000
    assert json_data['nonce'] == 'json-nonce'
    assert json_data['mac'] == 'json-mac'


# UTS: rest/unit/TE/token-request-from-json-2
def test_te_token_request_from_json():
    json_data = {
        'keyName': 'appId.keyId',
        'ttl': 7200000,
        'capability': '{"ch":["sub"]}',
        'clientId': 'from-json-client',
        'timestamp': 1234567899999,
        'nonce': 'from-json-nonce',
        'mac': 'from-json-mac',
    }

    request = TokenRequest.from_json(json_data)

    assert request.key_name == 'appId.keyId'
    assert request.ttl == 7200000
    assert request.capability == '{"ch":["sub"]}'
    assert request.client_id == 'from-json-client'
    assert request.timestamp == 1234567899999
    assert request.nonce == 'from-json-nonce'
    assert request.mac == 'from-json-mac'
